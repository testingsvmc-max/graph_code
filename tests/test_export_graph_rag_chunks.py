"""Tests for export_graph_rag_chunks (jsonl path, no chromadb)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "standalone_tools") not in sys.path:
    sys.path.insert(0, str(_ROOT / "standalone_tools"))

from code_graph_api.store import GraphStore
import export_graph_rag_chunks as export_mod


def _tiny_store() -> GraphStore:
    graph = {
        "meta": {"source": "test"},
        "nodes": [
            {
                "id": "file:a.c",
                "labels": ["FILE"],
                "properties": {"path": "a.c"},
            },
            {
                "id": "F1",
                "labels": ["FUNCTION"],
                "properties": {
                    "name": "foo",
                    "file_path": "a.c",
                    "line_start": 1,
                    "line_end": 10,
                    "signature": "void foo()",
                },
            },
        ],
        "edges": [],
    }
    return GraphStore(graph)


def test_export_jsonl_without_embeddings(tmp_path: Path) -> None:
    out = tmp_path / "chunks.jsonl"
    n, dim = export_mod.export_jsonl(
        _tiny_store(),
        out,
        include_labels=frozenset({"FUNCTION", "FILE"}),
        max_nodes=None,
        with_embeddings=False,
        embed_batch=8,
    )
    assert n == 2
    assert dim is None
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    row0 = json.loads(lines[0])
    assert "id" in row0 and "text" in row0 and "metadata" in row0
    assert "embedding" not in row0


def test_export_jsonl_with_embeddings(tmp_path: Path) -> None:
    pytest.importorskip("sentence_transformers")

    out = tmp_path / "chunks.jsonl"
    n, dim = export_mod.export_jsonl(
        _tiny_store(),
        out,
        include_labels=frozenset({"FUNCTION"}),
        max_nodes=None,
        with_embeddings=True,
        embed_batch=8,
    )
    assert n == 1
    assert dim is not None and dim > 0
    row = json.loads(out.read_text(encoding="utf-8").strip())
    assert len(row["embedding"]) == dim
