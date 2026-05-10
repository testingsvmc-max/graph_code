#!/usr/bin/env python3
"""
Export clangd-graph-rag YAML/JSON code graph into RAG-oriented chunks:

- jsonl: one JSON object per line {id, text, metadata} (+ optional embeddings) for any vector DB / framework.
- chroma: PersistentClient + precomputed embeddings (SentenceTransformer via llm_client).

Does not use Neo4j. See docs/graph_to_vector_rag.md for design notes.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Sequence, Tuple

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from code_graph_api.store import GraphStore

logger = logging.getLogger(__name__)

# Default: nodes likely useful for semantic code search (tune with --include-label).
DEFAULT_INCLUDE_LABELS = _DEFAULT_LABELS = frozenset(
    {
        "FUNCTION",
        "METHOD",
        "FILE",
        "FOLDER",
        "CLASS_STRUCTURE",
        "DATA_STRUCTURE",
        "MACRO",
        "TYPE_ALIAS",
        "NAMESPACE",
    }
)


def _node_labels(node: Dict[str, Any]) -> List[str]:
    return [str(x) for x in (node.get("labels") or [])]


def _node_matches_include(node: Dict[str, Any], include: frozenset[str]) -> bool:
    labels = set(_node_labels(node))
    if not include:
        return True
    return bool(labels & include)


def _node_to_text(node: Dict[str, Any]) -> str:
    """Flatten node into a single embedding-friendly string."""
    labels = _node_labels(node)
    nid = str(node.get("id") or "")
    p = node.get("properties") or {}
    lines = [
        " ".join(labels),
        f"id: {nid}",
    ]
    name = p.get("name")
    if name:
        lines.append(f"name: {name}")
    fp = p.get("file_path") or p.get("path")
    if fp:
        lines.append(f"path: {fp}")
    sig = p.get("signature")
    if sig:
        lines.append(f"signature: {sig}")
    summ = p.get("summary")
    if summ:
        lines.append(f"summary: {summ}")
    qn = p.get("qualified_name")
    if qn:
        lines.append(f"qualified_name: {qn}")
    return "\n".join(lines)


def _node_metadata(node: Dict[str, Any]) -> Dict[str, Any]:
    p = node.get("properties") or {}
    fp = p.get("file_path") or p.get("path") or ""
    return {
        "id": str(node.get("id") or ""),
        "labels": ",".join(_node_labels(node)),
        "file_path": str(fp),
        "name": str(p.get("name") or ""),
    }


def iter_graph_rag_chunks(
    store: GraphStore,
    *,
    include_labels: frozenset[str] | None = None,
    max_nodes: int | None = None,
) -> Iterator[Dict[str, Any]]:
    """Yield ``{id, text, metadata}`` per graph node (same rules as JSONL export)."""
    inc = include_labels if include_labels is not None else _DEFAULT_LABELS
    for node in _iter_nodes(store, include_labels=inc, max_nodes=max_nodes):
        yield {
            "id": str(node.get("id") or ""),
            "text": _node_to_text(node),
            "metadata": _node_metadata(node),
        }


def _iter_nodes(
    store: GraphStore,
    *,
    include_labels: frozenset[str],
    max_nodes: int | None,
) -> Iterator[Dict[str, Any]]:
    n_out = 0
    for node in store.nodes.values():
        if not _node_matches_include(node, include_labels):
            continue
        text = _node_to_text(node).strip()
        if not text:
            continue
        yield node
        n_out += 1
        if max_nodes is not None and n_out >= max_nodes:
            break


def _batched(items: List[Any], batch_size: int) -> Iterator[List[Any]]:
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


def export_jsonl(
    store: GraphStore,
    out_path: Path,
    *,
    include_labels: frozenset[str],
    max_nodes: int | None,
    with_embeddings: bool,
    embed_batch: int,
) -> Tuple[int, int | None]:
    rows: List[Dict[str, Any]] = list(
        iter_graph_rag_chunks(store, include_labels=include_labels, max_nodes=max_nodes)
    )

    dim: int | None = None
    if with_embeddings:
        from llm_client import get_embedding_client

        client = get_embedding_client("local")
        texts = [r["text"] for r in rows]
        all_emb: List[List[float]] = []
        for batch in _batched(texts, embed_batch):
            all_emb.extend(client.generate_embeddings(batch, show_progress_bar=len(texts) > 64))
        dim = len(all_emb[0]) if all_emb else None
        for r, emb in zip(rows, all_emb):
            r["embedding"] = emb
        try:
            from llm_client import get_offline_embedding_dimension

            expected = get_offline_embedding_dimension()
            if dim is not None and expected != dim:
                logger.warning(
                    "Embedding width from batch (%s) != model.get_embedding_dimension() (%s); check model state.",
                    dim,
                    expected,
                )
        except Exception as exc:
            logger.debug("Embedding dimension cross-check skipped: %s", exc)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    return len(rows), dim


def export_chroma(
    store: GraphStore,
    chroma_path: Path,
    collection_name: str,
    *,
    include_labels: frozenset[str],
    max_nodes: int | None,
    embed_batch: int,
    reset: bool,
) -> Tuple[int, int]:
    try:
        import chromadb
    except ImportError as exc:
        raise SystemExit(
            "chromadb is required for --backend chroma. "
            "Install: pip install -r requirements-vectordb.txt"
        ) from exc

    from llm_client import get_embedding_client

    nodes_list = list(_iter_nodes(store, include_labels=include_labels, max_nodes=max_nodes))
    if not nodes_list:
        raise SystemExit("No nodes matched filters; nothing to export.")

    texts = [_node_to_text(n) for n in nodes_list]
    ids = [str(n.get("id") or "") for n in nodes_list]
    metadatas = [_node_metadata(n) for n in nodes_list]

    client = chromadb.PersistentClient(path=str(chroma_path))
    if reset:
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    embed_client = get_embedding_client("local")
    embeddings: List[List[float]] = []
    for batch in _batched(texts, embed_batch):
        embeddings.extend(embed_client.generate_embeddings(batch, show_progress_bar=len(texts) > 64))

    dim = len(embeddings[0]) if embeddings else 0

    # Chroma add in chunks to avoid huge single requests
    add_batch = 256
    for i in range(0, len(ids), add_batch):
        collection.add(
            ids=ids[i : i + add_batch],
            documents=texts[i : i + add_batch],
            embeddings=embeddings[i : i + add_batch],
            metadatas=metadatas[i : i + add_batch],
        )

    return len(ids), dim


def _write_manifest(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(
        description="Export code_graph.yaml/json to JSONL or Chroma for RAG / vector search"
    )
    p.add_argument("graph", type=Path, help="Path to code_graph.yaml or .json")
    p.add_argument(
        "--backend",
        choices=("jsonl", "chroma"),
        default="jsonl",
        help="jsonl = portable lines; chroma = local persistent vector DB",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (default: <graph_dir>/rag_export)",
    )
    p.add_argument(
        "--include-label",
        action="append",
        default=[],
        help="Include only nodes having this label (repeatable). Default: common semantic labels.",
    )
    p.add_argument(
        "--max-nodes",
        type=int,
        default=None,
        help="Optional: cap nodes embedded/exported (smoke tests). Omit for **all** matching nodes (full export).",
    )
    p.add_argument("--embed-batch", type=int, default=32, help="Batch size for SentenceTransformer.encode")
    p.add_argument(
        "--with-embeddings",
        action="store_true",
        help="For jsonl only: add embedding vectors to each line (large files)",
    )
    p.add_argument(
        "--chroma-collection",
        default="code_graph_nodes",
        help="Chroma collection name",
    )
    p.add_argument(
        "--reset-chroma-collection",
        action="store_true",
        help="Delete existing Chroma collection before writing",
    )
    args = p.parse_args()

    graph_path = args.graph.expanduser().resolve()
    if not graph_path.is_file():
        print(f"Graph file not found: {graph_path}", file=sys.stderr)
        return 2

    out_dir = args.out_dir
    if out_dir is None:
        out_dir = graph_path.parent / "rag_export"
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.include_label:
        include_labels = frozenset(str(x) for x in args.include_label)
    else:
        include_labels = _DEFAULT_LABELS

    store = GraphStore.from_path(str(graph_path))
    model = os.environ.get("SENTENCE_TRANSFORMER_MODEL", "all-MiniLM-L6-v2")

    if args.backend == "jsonl":
        out_jsonl = out_dir / "chunks.jsonl"
        n, dim = export_jsonl(
            store,
            out_jsonl,
            include_labels=include_labels,
            max_nodes=args.max_nodes,
            with_embeddings=args.with_embeddings,
            embed_batch=args.embed_batch,
        )
        manifest = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_graph": str(graph_path),
            "backend": "jsonl",
            "chunks_file": str(out_jsonl),
            "node_chunks": n,
            "embedding_model": model,
            "embedding_dimensions": dim,
            "include_labels": sorted(include_labels),
            "with_embeddings": args.with_embeddings,
        }
        if args.with_embeddings:
            try:
                from llm_client import get_offline_embedding_dimension

                manifest["model_embedding_dimension"] = get_offline_embedding_dimension()
            except Exception:
                pass
        _write_manifest(out_dir / "manifest.json", manifest)
        print(f"Wrote {n} lines to {out_jsonl}")
        print(f"Manifest: {out_dir / 'manifest.json'}")
        return 0

    chroma_dir = out_dir / "chroma_db"
    n, dim = export_chroma(
        store,
        chroma_dir,
        args.chroma_collection,
        include_labels=include_labels,
        max_nodes=args.max_nodes,
        embed_batch=args.embed_batch,
        reset=args.reset_chroma_collection,
    )
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_graph": str(graph_path),
        "backend": "chroma",
        "chroma_path": str(chroma_dir),
        "collection": args.chroma_collection,
        "node_chunks": n,
        "embedding_model": model,
        "embedding_dimensions": dim,
        "include_labels": sorted(include_labels),
    }
    try:
        from llm_client import get_offline_embedding_dimension

        manifest["model_embedding_dimension"] = get_offline_embedding_dimension()
    except Exception:
        pass
    _write_manifest(out_dir / "manifest.json", manifest)
    print(f"Chroma persistent path: {chroma_dir}")
    print(f"Collection `{args.chroma_collection}`: {n} vectors, dim={dim}")
    print(f"Manifest: {out_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
