"""Tests for D3 graph HTML post-process (cross-file CALL annotation + JS patches)."""

from __future__ import annotations

import json

from code_graph_export.crg_d3_postprocess import (
    _ES_OLD_AGG,
    _ES_OLD_MIN,
    annotate_cross_file_edges,
    enhance_crg_d3_html,
)


def test_annotate_cross_file_by_qualified_name() -> None:
    data = {
        "nodes": [
            {
                "qualified_name": "f::a",
                "file_path": "src/a.c",
                "id": 1,
            },
            {
                "qualified_name": "g::b",
                "file_path": "src/b.c",
                "id": 2,
            },
        ],
        "edges": [
            {"kind": "CALLS", "source": "f::a", "target": "g::b"},
        ],
    }
    n = annotate_cross_file_edges(data)
    assert n == 1
    assert data["edges"][0]["cross_file"] is True


def test_annotate_cross_file_by_numeric_id() -> None:
    data = {
        "nodes": [
            {"qualified_name": "f::a", "file_path": "x/a.c", "id": 10},
            {"qualified_name": "g::b", "file_path": "y/b.c", "id": 20},
        ],
        "edges": [
            {"kind": "CALLS", "source": 10, "target": 20},
        ],
    }
    n = annotate_cross_file_edges(data)
    assert n == 1
    assert data["edges"][0].get("cross_file") is True


def test_e_style_snippets_used_by_crg() -> None:
    # Minified (full template) and spaced (aggregated template) must both match.
    assert "EDGE_CFG[d.kind]" in _ES_OLD_MIN
    assert "dash: null" in _ES_OLD_AGG


def test_enhance_minimal_html_roundtrip(tmp_path) -> None:
    graph = {
        "nodes": [
            {"qualified_name": "A::f", "file_path": "a.c", "id": 1, "kind": "Function"},
            {"qualified_name": "B::g", "file_path": "b.c", "id": 2, "kind": "Function"},
        ],
        "edges": [{"kind": "CALLS", "source": "A::f", "target": "B::g"}],
        "stats": {},
        "flows": [],
        "communities": [],
    }
    gj = json.dumps(graph, separators=(",", ":"))
    html = f"""<!DOCTYPE html><html><body>
<script>
var graphData = {gj};
function eStyle(d) {{ return EDGE_CFG[d.kind] || {{ dash: null, width: 1, opacity: 0.3, marker: "" }}; }}
function eColor(d) {{ return EDGE_COLOR[d.kind] || "#484f58"; }}
</script></body></html>"""
    inp = tmp_path / "g.html"
    inp.write_text(html, encoding="utf-8")
    outp = tmp_path / "out.html"
    enhance_crg_d3_html(inp, outp, inject_legend=False)
    text = outp.read_text(encoding="utf-8")
    assert "cross_file" in text
    assert "ff9933" in text
    assert "d.cross_file && d.kind" in text
    assert "width:3.2" in text.replace(" ", "")
