"""FAISS index bundle (requires faiss-cpu)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "standalone_tools") not in sys.path:
    sys.path.insert(0, str(_ROOT / "standalone_tools"))

pytest.importorskip("faiss")
import faiss_code_graph_index as faiss_mod


def test_write_faiss_bundle_and_search(tmp_path: Path) -> None:
    write = faiss_mod.write_faiss_index_bundle
    search = faiss_mod.search_faiss_dir

    d = tmp_path / "faiss_idx"
    ids = ["a", "b", "c"]
    emb = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    meta = [
        {"labels": "FUNCTION", "name": "fa"},
        {"labels": "FILE", "name": "fb"},
        {"labels": "FUNCTION", "name": "fc"},
    ]
    n, dim = write(d, ids, emb, meta, source="unit-test")
    assert n == 3 and dim == 3

    hits = search(d, [1.0, 0.0, 0.0], k=2)
    assert len(hits) == 2
    assert hits[0]["id"] == "a"
    assert hits[0]["score"] > 0.99

    file_hits = search(d, [1.0, 0.0, 0.0], k=3, labels_filter="FILE")
    assert len(file_hits) == 1
    assert file_hits[0]["id"] == "b"
