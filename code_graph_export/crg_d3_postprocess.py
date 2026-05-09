"""
Post-process D3 graph HTML (``graph.html`` / ``graph_d3.html``) for clangd-graph-rag workflows.

Upstream embeds ``var graphData = <json>;`` then uses ``eColor(d)`` / ``eStyle(d)``
for link styling. We:

1. Parse that JSON, annotate each ``CALL`` edge with ``cross_file: true`` when
   ``source`` and ``target`` nodes live in different ``file_path`` values.
2. Patch ``eColor`` / ``eStyle`` so cross-file CALL edges render in orange with
   thicker strokes (so hàm A file X → hàm B file Y stands out).

Requires a D3 HTML file using the common graph-review template (e.g. from a
``visualize`` step; see README). The HTML must contain the ``eColor`` / ``eStyle``
snippets patched below.
"""

from __future__ import annotations

import json
import logging
import re
from json.decoder import JSONDecoder
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# Snippets from the reference D3 template (_HTML_TEMPLATE) — patched in-place.
_EC_OLD = 'function eColor(d) { return EDGE_COLOR[d.kind] || "#484f58"; }'
_EC_NEW = (
    'function eColor(d) { '
    'if (d.cross_file && d.kind === "CALLS") return "#ff9933"; '
    'return EDGE_COLOR[d.kind] || "#484f58"; '
    "}"
)

# Full-mode template (_HTML_TEMPLATE) minifies the fallback object.
_ES_OLD_MIN = 'function eStyle(d) { return EDGE_CFG[d.kind] || {dash:null,width:1,opacity:0.3,marker:""}; }'
# Community/file aggregated template uses spaced braces (see visualization._AGGREGATED_HTML_TEMPLATE).
_ES_OLD_AGG = (
    'function eStyle(d) { return EDGE_CFG[d.kind] || '
    '{ dash: null, width: 1, opacity: 0.3, marker: "" }; }'
)
_ES_NEW = (
    "function eStyle(d) { "
    "var s = EDGE_CFG[d.kind] || {dash:null,width:1,opacity:0.3,marker:\"\"}; "
    'if (d.cross_file && d.kind === "CALLS") { '
    "return {dash:s.dash, width:3.2, opacity:0.92, marker:s.marker}; "
    "} return s; }"
)

_LEGEND_HTML = """
<div id="crg-cross-file-legend" style="position:absolute;top:52px;left:16px;z-index:11;
  background:rgba(22,27,34,0.95);border:1px solid #30363d;border-radius:8px;
  padding:8px 12px;font-size:11px;color:#ff9933;max-width:280px;line-height:1.5;">
  <strong>CALL liên file</strong>: cạnh màu cam = hàm ở file nguồn khác file đích
</div>
"""


def _norm_fp(fp: str | None) -> str:
    if not fp:
        return ""
    return str(fp).replace("\\", "/").lower()


def annotate_cross_file_edges(data: Dict[str, Any]) -> int:
    """Mutate ``data['edges']`` in place. Returns count of edges tagged."""
    nodes: List[Dict[str, Any]] = data.get("nodes") or []
    qn_fp: Dict[str, str] = {}
    id_fp: Dict[Any, str] = {}
    for n in nodes:
        qn = n.get("qualified_name")
        if qn:
            qn_fp[qn] = _norm_fp(n.get("file_path"))
        nid = n.get("id")
        if nid is not None and qn:
            id_fp[nid] = qn_fp.get(qn, "")

    def _fp_for_endpoint(edge: Dict[str, Any], key: str) -> str:
        v = edge.get(key)
        if v is None:
            return ""
        if isinstance(v, str):
            return qn_fp.get(v, "")
        return id_fp.get(v, "")

    n_tagged = 0
    for e in data.get("edges") or []:
        if e.get("kind") != "CALLS":
            continue
        fs, ft = _fp_for_endpoint(e, "source"), _fp_for_endpoint(e, "target")
        if fs and ft and fs != ft:
            e["cross_file"] = True
            n_tagged += 1
    return n_tagged


def _warn_if_no_call_level_graph(data: Dict[str, Any]) -> None:
    """``auto`` visualize mode may switch to community aggregation when node count is high."""
    edges = data.get("edges") or []
    has_calls = any(e.get("kind") == "CALLS" for e in edges)
    if data.get("mode") == "community" or (edges and not has_calls):
        logger.warning(
            "Embedded graph has no CALLS edges (likely community/file aggregate view). "
            "To see function A in file X calling B in file Y in D3, regenerate full-mode HTML "
            "(``visualize --mode full``; large graphs may be slow in the browser), "
            "then run this enhancer again."
        )


def _split_graph_data_json(html: str) -> Tuple[str, Dict[str, Any], int, int] | None:
    """Return (prefix, graph_dict, json_start, json_end_exclusive) or None."""
    marker = "var graphData = "
    pos = html.find(marker)
    if pos == -1:
        logger.error("Could not find 'var graphData = ' in HTML (not a compatible D3 export?)")
        return None
    json_start = pos + len(marker)
    dec = JSONDecoder()
    try:
        data, end = dec.raw_decode(html, json_start)
    except json.JSONDecodeError as exc:
        logger.error("JSON decode failed at %s: %s", json_start, exc)
        return None
    if not isinstance(data, dict):
        logger.error("graphData is not an object")
        return None
    return html[:json_start], data, json_start, end


def enhance_crg_d3_html(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    inject_legend: bool = True,
) -> Path:
    """
    Read D3 ``graph.html``, write enhanced HTML (default: overwrite input).

    Returns path written.
    """
    inp = Path(input_path).resolve()
    text = inp.read_text(encoding="utf-8")
    split = _split_graph_data_json(text)
    if split is None:
        raise ValueError(f"Not a valid D3 graph HTML: {inp}")

    prefix, data, _js, json_end = split
    _warn_if_no_call_level_graph(data)
    n_cf = annotate_cross_file_edges(data)
    logger.info("Tagged %s cross-file CALL edges", n_cf)

    new_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    new_json = new_json.replace("</", "<\\/")

    suffix = text[json_end:]
    if not suffix.lstrip().startswith(";"):
        logger.warning("Unexpected content after graphData JSON; proceeding anyway")

    out = text[: _js] + new_json + text[json_end:]

    if _EC_OLD not in out:
        logger.warning("eColor snippet not found; D3 links may not highlight cross-file calls")
    else:
        out = out.replace(_EC_OLD, _EC_NEW, 1)
    if _ES_OLD_MIN in out:
        out = out.replace(_ES_OLD_MIN, _ES_NEW, 1)
    elif _ES_OLD_AGG in out:
        out = out.replace(_ES_OLD_AGG, _ES_NEW, 1)
    else:
        logger.warning("eStyle snippet not found; cross-file stroke width may be unchanged")

    if inject_legend and 'id="crg-cross-file-legend"' not in out:
        # Insert after opening <body> or after #legend — use #legend anchor
        anchor = '<div id="legend">'
        if anchor in out:
            out = out.replace(anchor, anchor + _LEGEND_HTML, 1)
        else:
            out = out.replace("<body>", "<body>" + _LEGEND_HTML, 1)

    outp = Path(output_path).resolve() if output_path else inp
    outp.write_text(out, encoding="utf-8")
    logger.info("Wrote enhanced D3 HTML to %s", outp)
    return outp
