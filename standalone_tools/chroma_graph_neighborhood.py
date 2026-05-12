#!/usr/bin/env python3
"""
Structural neighborhood from code_graph (traverse) + Chroma payloads for the same node ids.

Chroma rows use graph node id as the document id (see export_graph_rag_chunks --backend chroma).

Modes:
  * From a known start id: traverse YAML, then Chroma get / optional semantic rerank in that slice.
  * From a Chroma NL seed: query Chroma globally, take top seed ids, merge CALLS neighborhoods from YAML,
    then Chroma get for merged ids (graph-shaped output: nodes + edges).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from code_graph_api.store import GraphStore


def _resolve_chroma_dir(path: Path) -> Path:
    p = path.expanduser().resolve()
    if (p / "chroma_db").is_dir():
        return p / "chroma_db"
    return p


def _traverse_ids(store: GraphStore, args: argparse.Namespace) -> Dict[str, Any]:
    return store.traverse_graph(
        start=args.start,
        direction=args.direction,
        edge_type=args.edge_type,
        depth=args.depth,
        limit=args.limit,
    )


def _open_chroma_collection(chroma_dir: Path, collection_name: str):
    try:
        import chromadb
    except ImportError:
        print(
            "chromadb is required. Install: pip install -r requirements-vectordb.txt",
            file=sys.stderr,
        )
        return None, None
    client = chromadb.PersistentClient(path=str(chroma_dir))
    try:
        collection = client.get_collection(collection_name)
    except Exception as exc:
        print(f"Failed to open Chroma collection `{collection_name}`: {exc}", file=sys.stderr)
        return None, None
    return client, collection


def _merge_traversals_from_seeds(
    store: GraphStore,
    seed_ids: List[str],
    *,
    direction: str,
    edge_type: str,
    depth: int,
    per_seed_limit: int,
    merge_cap: int,
) -> Tuple[Dict[str, Any], List[str]]:
    """Union nodes/edges from multiple traverse_graph runs (CALLS-style subgraph)."""
    merged_nodes: Dict[str, Dict[str, Any]] = {}
    edge_keys: Set[Tuple[str, str, str]] = set()
    merged_edges: List[Dict[str, str]] = []
    seeds_used: List[str] = []

    for sid in seed_ids:
        if sid not in store.nodes:
            continue
        tr = store.traverse_graph(
            start=sid,
            direction=direction,
            edge_type=edge_type,
            depth=depth,
            limit=per_seed_limit,
        )
        if tr.get("status") != "ok":
            continue
        seeds_used.append(sid)
        for n in tr.get("nodes") or []:
            nid = n.get("id")
            if nid is not None:
                merged_nodes[str(nid)] = n
        for e in tr.get("edges") or []:
            key = (str(e.get("type")), str(e.get("src")), str(e.get("dst")))
            if key not in edge_keys:
                edge_keys.add(key)
                merged_edges.append({"type": key[0], "src": key[1], "dst": key[2]})
        if len(merged_nodes) >= merge_cap:
            break

    node_list = [merged_nodes[i] for i in sorted(merged_nodes.keys())]
    pseudo = {
        "status": "ok",
        "mode": "merged_from_chroma_seeds",
        "seeds": seeds_used,
        "direction": direction,
        "edge_type": edge_type,
        "depth": depth,
        "nodes": node_list,
        "edges": merged_edges,
        "node_count": len(node_list),
        "edge_count": len(merged_edges),
    }
    return pseudo, sorted(merged_nodes.keys())


def main() -> int:
    p = argparse.ArgumentParser(
        description="Traverse code_graph from a function/node, then fetch matching Chroma documents by id; "
        "or query Chroma first for NL seeds then merge graph neighborhoods."
    )
    p.add_argument("graph", type=Path, help="Path to code_graph.yaml or .json")
    p.add_argument(
        "--chroma",
        type=Path,
        required=True,
        help="Chroma persistent path: .../chroma_db or parent folder containing chroma_db/",
    )
    p.add_argument(
        "--collection",
        default="code_graph_nodes",
        help="Chroma collection name (default matches export_graph_rag_chunks)",
    )
    p.add_argument(
        "start",
        nargs="?",
        default=None,
        help="Start node id or search string (omit if using --chroma-seed-query)",
    )
    p.add_argument(
        "--chroma-seed-query",
        default=None,
        metavar="TEXT",
        help="Natural-language Chroma query: top --seed-k hits seed merged CALLS traversal (graph slice)",
    )
    p.add_argument("--seed-k", type=int, default=5, help="Chroma global top-k seeds (default 5)")
    p.add_argument(
        "--seed-fetch",
        type=int,
        default=24,
        help="Internal over-fetch before --seed-labels filter (default 24)",
    )
    p.add_argument(
        "--seed-labels",
        default="FUNCTION,METHOD",
        help="Comma labels; metadata.labels must contain one (substring match). Empty = no filter.",
    )
    p.add_argument(
        "--merge-cap",
        type=int,
        default=600,
        help="Stop merging neighborhoods after this many distinct node ids (default 600)",
    )
    p.add_argument("--direction", choices=["up", "down", "both"], default="both")
    p.add_argument("--edge-type", default="CALLS", dest="edge_type")
    p.add_argument("--depth", type=int, default=2)
    p.add_argument("--limit", type=int, default=500)
    p.add_argument(
        "--semantic",
        default=None,
        help="Optional natural-language query: Chroma query() restricted to neighborhood ids (top --k)",
    )
    p.add_argument("--k", type=int, default=12, help="Top-k for --semantic (default 12)")
    args = p.parse_args()

    graph_path = args.graph.expanduser().resolve()
    if not graph_path.is_file():
        print(f"Graph file not found: {graph_path}", file=sys.stderr)
        return 2

    if not args.start and not args.chroma_seed_query:
        print("Provide either start node id (positional) or --chroma-seed-query", file=sys.stderr)
        return 2
    if args.start and args.chroma_seed_query:
        print("Use either positional start or --chroma-seed-query, not both", file=sys.stderr)
        return 2

    try:
        store = GraphStore.from_path(str(graph_path))
    except Exception as exc:
        print(f"Failed to load graph: {exc}", file=sys.stderr)
        return 2

    chroma_dir = _resolve_chroma_dir(args.chroma)
    if not chroma_dir.is_dir():
        print(f"Chroma path is not a directory: {chroma_dir}", file=sys.stderr)
        return 2

    _, collection = _open_chroma_collection(chroma_dir, args.collection)
    if collection is None:
        return 2

    tr: Dict[str, Any]
    ids: List[str]

    if args.chroma_seed_query:
        fetch_n = max(args.seed_k, min(args.seed_fetch, 200))
        try:
            sqr = collection.query(query_texts=[args.chroma_seed_query], n_results=fetch_n)
        except Exception as exc:
            print(json.dumps({"status": "error", "error": f"chroma seed query failed: {exc}"}, ensure_ascii=False, indent=2))
            return 4
        raw_ids = (sqr.get("ids") or [[]])[0]
        raw_metas = (sqr.get("metadatas") or [[]])[0]
        want_labels = [x.strip() for x in str(args.seed_labels or "").split(",") if x.strip()]
        seed_ids: List[str] = []
        for i, doc_id in enumerate(raw_ids):
            if doc_id is None:
                continue
            sid = str(doc_id)
            if want_labels and i < len(raw_metas) and raw_metas[i]:
                lab = str((raw_metas[i] or {}).get("labels") or "")
                if not any(w in lab for w in want_labels):
                    continue
            if sid not in store.nodes:
                continue
            seed_ids.append(sid)
            if len(seed_ids) >= args.seed_k:
                break
        if not seed_ids:
            print(
                json.dumps(
                    {
                        "status": "no_seeds",
                        "chroma_seed_query": args.chroma_seed_query,
                        "hint": "Try larger --seed-fetch, empty --seed-labels, or a different query.",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 3
        per_cap = max(50, min(args.limit, args.merge_cap // max(len(seed_ids), 1)))
        tr, ids = _merge_traversals_from_seeds(
            store,
            seed_ids,
            direction=args.direction,
            edge_type=args.edge_type,
            depth=args.depth,
            per_seed_limit=per_cap,
            merge_cap=args.merge_cap,
        )
        tr["chroma_seed_query"] = args.chroma_seed_query
        tr["chroma_seed_ids"] = seed_ids
    else:
        tr = _traverse_ids(store, args)
        status = tr.get("status")
        if status != "ok":
            print(json.dumps(tr, ensure_ascii=False, indent=2))
            return 3 if status in ("ambiguous", "not_found") else 4
        ids = []
        for n in tr.get("nodes") or []:
            nid = n.get("id")
            if nid is not None:
                ids.append(str(nid))

    id_set: Set[str] = set(ids)

    batch = 256
    chroma_by_id: Dict[str, Dict[str, Any]] = {}
    for i in range(0, len(ids), batch):
        chunk = ids[i : i + batch]
        got = collection.get(ids=chunk, include=["documents", "metadatas"])
        for j, doc_id in enumerate(got.get("ids") or []):
            entry: Dict[str, Any] = {"id": doc_id}
            docs = got.get("documents") or []
            metas = got.get("metadatas") or []
            if j < len(docs) and docs[j] is not None:
                entry["document"] = docs[j]
            if j < len(metas) and metas[j] is not None:
                entry["metadata"] = metas[j]
            chroma_by_id[str(doc_id)] = entry

    missing = sorted(id_set - set(chroma_by_id.keys()))
    trav_summary: Dict[str, Any] = {
        "direction": tr.get("direction"),
        "edge_type": tr.get("edge_type"),
        "depth": tr.get("depth"),
        "node_count": len(ids),
        "edge_count": len(tr.get("edges") or []),
    }
    if tr.get("mode") == "merged_from_chroma_seeds":
        trav_summary["mode"] = tr["mode"]
        trav_summary["chroma_seed_query"] = tr.get("chroma_seed_query")
        trav_summary["chroma_seed_ids"] = tr.get("chroma_seed_ids")
    else:
        trav_summary["start"] = tr.get("start")

    out: Dict[str, Any] = {
        "traverse": trav_summary,
        "edges": tr.get("edges") or [],
        "chroma_path": str(chroma_dir),
        "collection": args.collection,
        "chroma_hits": len(chroma_by_id),
        "chroma_missing_ids": missing,
        "nodes": [],
    }

    for nid in ids:
        row: Dict[str, Any] = {"id": nid, "graph": store.get_node(nid), "chroma": chroma_by_id.get(nid)}
        out["nodes"].append(row)

    if args.semantic:
        k = max(1, min(args.k, len(ids)))
        if not ids:
            out["semantic"] = {"error": "empty neighborhood"}
        else:
            try:
                qr = collection.query(
                    query_texts=[args.semantic],
                    n_results=k,
                    where={"id": {"$in": ids}},
                )
            except Exception as exc:
                out["semantic"] = {"error": str(exc)}
            else:
                out["semantic"] = {
                    "query": args.semantic,
                    "ids": (qr.get("ids") or [[]])[0],
                    "distances": (qr.get("distances") or [[]])[0],
                    "documents": (qr.get("documents") or [[]])[0],
                    "metadatas": (qr.get("metadatas") or [[]])[0],
                }

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
