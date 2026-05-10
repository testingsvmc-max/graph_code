#!/usr/bin/env python3
"""
Build and query a **FAISS** index over code-graph RAG chunks (cosine similarity).

Vectors are **L2-normalized**; search uses ``IndexFlatIP`` (inner product = cosine
for unit vectors). Artifacts in ``--out-dir``:

- ``vectors.faiss`` — FAISS index
- ``ids.json`` — node id per row (same order as index vectors)
- ``metadata.json`` — list of metadata dicts (parallel to ids)
- ``manifest.json`` — dims, counts, source path

Sources:

- ``build --graph code_graph.yaml`` — embed with ``SentenceTransformer`` (``llm_client``).
  Omit ``--max-nodes`` to index **all** matching graph nodes; pass ``--max-nodes N`` only for smoke caps.
- ``build --chunks chunks.jsonl`` — each line must include an ``embedding`` array.

Query: ``query --index-dir <dir> --text "..."`` — embeds the query with the same model.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "standalone_tools") not in sys.path:
    sys.path.insert(0, str(_ROOT / "standalone_tools"))


def _require_faiss():
    try:
        import faiss  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "faiss is required. Install: pip install -r requirements-faiss.txt"
        ) from exc
    return faiss


def write_faiss_index_bundle(
    out_dir: Path,
    ids: Sequence[str],
    embeddings: Sequence[Sequence[float]],
    metadatas: Sequence[Dict[str, Any]],
    *,
    source: str,
) -> Tuple[int, int]:
    """Write ``vectors.faiss``, ``ids.json``, ``metadata.json``, ``manifest.json``. Returns (n, dim)."""
    faiss = _require_faiss()
    out_dir = Path(out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if not ids:
        raise ValueError("empty ids")
    dim = len(embeddings[0])
    mat = np.asarray(list(embeddings), dtype=np.float32)
    faiss.normalize_L2(mat)
    index = faiss.IndexFlatIP(dim)
    index.add(mat)
    faiss.write_index(index, str(out_dir / "vectors.faiss"))
    (out_dir / "ids.json").write_text(json.dumps(list(ids), ensure_ascii=False), encoding="utf-8")
    (out_dir / "metadata.json").write_text(
        json.dumps(list(metadatas), ensure_ascii=False), encoding="utf-8"
    )
    model = os.environ.get("SENTENCE_TRANSFORMER_MODEL", "all-MiniLM-L6-v2")
    manifest = {
        "backend": "faiss",
        "similarity": "cosine",
        "index_type": "IndexFlatIP",
        "vectors_normalized": True,
        "embedding_dimensions": dim,
        "vector_count": len(ids),
        "embedding_model": model,
        "source": source,
    }
    try:
        from llm_client import get_offline_embedding_dimension

        manifest["model_embedding_dimension"] = get_offline_embedding_dimension()
    except Exception:
        pass
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(ids), dim


def _load_chunks_jsonl(path: Path) -> Tuple[List[str], List[List[float]], List[Dict[str, Any]]]:
    ids: List[str] = []
    embeddings: List[List[float]] = []
    metas: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            emb = row.get("embedding")
            if not isinstance(emb, list) or not emb:
                raise SystemExit(f"{path}:{line_no}: missing or empty 'embedding'")
            ids.append(str(row.get("id") or ""))
            embeddings.append([float(x) for x in emb])
            metas.append(dict(row.get("metadata") or {}))
    if not ids:
        raise SystemExit(f"No rows in {path}")
    return ids, embeddings, metas


def _embed_texts(texts: List[str], batch_size: int) -> List[List[float]]:
    from llm_client import get_embedding_client

    client = get_embedding_client("local")
    out: List[List[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        out.extend(client.generate_embeddings(batch, show_progress_bar=len(texts) > 64))
    return out


def cmd_build(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    ids: List[str]
    embeddings: List[List[float]]
    metas: List[Dict[str, Any]]
    source_desc: str

    if args.chunks:
        cpath = Path(args.chunks).expanduser().resolve()
        if not cpath.is_file():
            print(f"Chunks file not found: {cpath}", file=sys.stderr)
            return 2
        ids, embeddings, metas = _load_chunks_jsonl(cpath)
        source_desc = str(cpath)
    else:
        from code_graph_api.store import GraphStore

        import export_graph_rag_chunks as egc

        gpath = Path(args.graph).expanduser().resolve()
        if not gpath.is_file():
            print(f"Graph file not found: {gpath}", file=sys.stderr)
            return 2
        if args.include_label:
            include = frozenset(str(x) for x in args.include_label)
        else:
            include = egc.DEFAULT_INCLUDE_LABELS
        store = GraphStore.from_path(str(gpath))
        rows = list(egc.iter_graph_rag_chunks(store, include_labels=include, max_nodes=args.max_nodes))
        if not rows:
            print("No chunks matched filters.", file=sys.stderr)
            return 2
        ids = [r["id"] for r in rows]
        texts = [r["text"] for r in rows]
        metas = [r["metadata"] for r in rows]
        embeddings = _embed_texts(texts, args.embed_batch)
        source_desc = str(gpath)

    dim = len(embeddings[0])
    for i, e in enumerate(embeddings):
        if len(e) != dim:
            print(f"Embedding dim mismatch at row {i}: expected {dim}, got {len(e)}", file=sys.stderr)
            return 2

    n, dim = write_faiss_index_bundle(out_dir, ids, embeddings, metas, source=source_desc)
    print(f"Wrote FAISS index: {out_dir / 'vectors.faiss'} ({n} x {dim})")
    return 0


def search_faiss_dir(
    index_dir: Path,
    query_embedding: Sequence[float],
    *,
    k: int,
    labels_filter: str | None = None,
) -> List[Dict[str, Any]]:
    """Return up to ``k`` hits with cosine IP score, optional comma-separated ``labels`` filter on metadata."""
    faiss = _require_faiss()
    d = Path(index_dir).expanduser().resolve()
    index_path = d / "vectors.faiss"
    ids: List[str] = json.loads((d / "ids.json").read_text(encoding="utf-8"))
    metas: List[Dict[str, Any]] = json.loads((d / "metadata.json").read_text(encoding="utf-8"))
    index = faiss.read_index(str(index_path))
    dim = index.d
    if len(query_embedding) != dim:
        raise ValueError(f"query dim {len(query_embedding)} != index dim {dim}")
    q = np.asarray([list(map(float, query_embedding))], dtype=np.float32)
    faiss.normalize_L2(q)

    allow = None
    if labels_filter:
        allow = {x.strip() for x in labels_filter.split(",") if x.strip()}

    # Over-fetch when filtering so we can still return k after dropping rows
    fetch = min(max(k * 8, k + 5), len(ids)) if allow else min(k, len(ids))
    scores, idxs = index.search(q, fetch)
    row_scores = scores[0].tolist()
    row_idx = idxs[0].tolist()

    results: List[Dict[str, Any]] = []
    for sc, ix in zip(row_scores, row_idx):
        if ix < 0:
            continue
        meta = metas[ix] if ix < len(metas) else {}
        if allow:
            node_labels = {x.strip() for x in str(meta.get("labels", "")).split(",") if x.strip()}
            if not (node_labels & allow):
                continue
        results.append(
            {
                "rank": len(results) + 1,
                "score": float(sc),
                "id": ids[ix] if ix < len(ids) else "",
                "metadata": meta,
            }
        )
        if len(results) >= k:
            break
    return results


def cmd_query(args: argparse.Namespace) -> int:
    d = Path(args.index_dir).expanduser().resolve()
    index_path = d / "vectors.faiss"
    if not index_path.is_file():
        print(f"Missing index: {index_path}", file=sys.stderr)
        return 2

    q_emb = _embed_texts([args.text], batch_size=1)[0]
    try:
        results = search_faiss_dir(d, q_emb, k=args.k, labels_filter=args.labels)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            m = r["metadata"]
            print(f"{r['rank']}. score={r['score']:.4f} id={r['id']}")
            print(f"   labels={m.get('labels')} file={m.get('file_path')} name={m.get('name')}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="FAISS index for code graph RAG chunks (cosine / IP)")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="Create vectors.faiss + sidecars from graph or JSONL chunks")
    g = b.add_mutually_exclusive_group(required=True)
    g.add_argument("--graph", type=Path, help="code_graph.yaml / .json (embed with SentenceTransformer)")
    g.add_argument("--chunks", type=Path, help="chunks.jsonl with embedding on each line")
    b.add_argument("--out-dir", type=Path, required=True, help="Directory to write index + json sidecars")
    b.add_argument(
        "--include-label",
        action="append",
        default=[],
        help="With --graph: same as export_graph_rag_chunks (repeatable)",
    )
    b.add_argument(
        "--max-nodes",
        type=int,
        default=None,
        help="Optional: cap how many graph nodes are embedded (smoke tests). "
        "Omit this flag to embed **every** node that matches --include-label filters (full index).",
    )
    b.add_argument("--embed-batch", type=int, default=32)
    b.set_defaults(_fn=cmd_build)

    q = sub.add_parser("query", help="Top-k cosine search against a built index")
    q.add_argument("--index-dir", type=Path, required=True)
    q.add_argument("--text", type=str, required=True, help="Natural language query (embedded)")
    q.add_argument("-k", type=int, default=10, help="Max results (may return fewer after --labels filter)")
    q.add_argument(
        "--labels",
        type=str,
        default=None,
        help="Comma filter: keep hits whose metadata labels intersect this set (e.g. FUNCTION,METHOD)",
    )
    q.add_argument("--json", action="store_true", help="Print hits as JSON")
    q.set_defaults(_fn=cmd_query)

    args = p.parse_args()
    fn = args._fn
    delattr(args, "_fn")
    return int(fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
