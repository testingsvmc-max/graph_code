"""
Self-contained D3 force-directed HTML from ``code_graph`` export dict (YAML/JSON).

Output is similar to ``graph_d3.html``: force layout, ``var graphData``, full mode,
and orange / thicker **CALLS** edges for **cross_file** (different ``file_path``).
No optional ``code_review_graph`` package required.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

D3_CDN = "https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js"


def _norm_fp(fp: str | None) -> str:
    if not fp:
        return ""
    return str(fp).replace("\\", "/").lower()


def _tag_cross_file_calls(graph_data: Dict[str, Any]) -> int:
    """Tag CALLS edges where endpoints map to different file_path (by node id)."""
    nodes: List[Dict[str, Any]] = graph_data.get("nodes") or []
    id_fp: Dict[Any, str] = {}
    for n in nodes:
        nid = n.get("id")
        if nid is None:
            continue
        fp = _norm_fp(n.get("file_path"))
        if fp:
            id_fp[nid] = fp
    n_tagged = 0
    for e in graph_data.get("edges") or []:
        if e.get("kind") != "CALLS":
            continue
        fs, ft = id_fp.get(e.get("source"), ""), id_fp.get(e.get("target"), "")
        if fs and ft and fs != ft:
            e["cross_file"] = True
            n_tagged += 1
    return n_tagged


def graph_to_d3_graphdata(
    graph: Dict[str, Any],
    *,
    edge_types: Optional[Set[str]] = None,
    max_nodes: Optional[int] = None,
) -> Dict[str, Any]:
    """Build ``graphData`` object for D3 (nodes + edges, review-style keys)."""
    nodes_in: List[Dict] = list(graph.get("nodes") or [])
    edges_in: List[Dict] = list(graph.get("edges") or [])

    if edge_types is not None:
        edges_in = [e for e in edges_in if e.get("type") in edge_types]

    node_ids = {n["id"] for n in nodes_in}
    edges_f = [e for e in edges_in if e.get("src") in node_ids and e.get("dst") in node_ids]

    if max_nodes is not None and len(nodes_in) > max_nodes:
        used: Set[Any] = set()
        for e in edges_f:
            used.add(e["src"])
            used.add(e["dst"])
        if not used:
            nodes_in = list(nodes_in)[:max_nodes]
        elif len(used) > max_nodes:
            keep_ids = set(list(used)[:max_nodes])
            nodes_in = [n for n in nodes_in if n["id"] in keep_ids]
            edges_f = [e for e in edges_f if e["src"] in keep_ids and e["dst"] in keep_ids]
        else:
            nodes_in = [n for n in nodes_in if n["id"] in used]
        logger.warning("D3 graph reduced to %s nodes (cap=%s)", len(nodes_in), max_nodes)

    d3_nodes: List[Dict[str, Any]] = []
    for n in nodes_in:
        props = n.get("properties") or {}
        labels = n.get("labels") or ["NODE"]
        nid = n["id"]
        qn = props.get("qualified_name") or props.get("name") or str(nid)
        lbl = str(props.get("name") or qn)[:72]
        fp = props.get("path") or props.get("file_path") or ""
        if not fp and isinstance(nid, str) and nid.startswith("file:"):
            fp = nid[len("file:") :]
        d3_nodes.append(
            {
                "id": nid,
                "label": lbl,
                "qualified_name": qn,
                "file_path": fp or "",
                "group": labels[0] if labels else "NODE",
            }
        )

    d3_edges: List[Dict[str, Any]] = []
    for e in edges_f:
        kind = str(e.get("type", "REL"))
        row: Dict[str, Any] = {
            "source": e["src"],
            "target": e["dst"],
            "kind": kind,
        }
        if (e.get("properties") or {}).get("cross_file") and kind == "CALLS":
            row["cross_file"] = True
        d3_edges.append(row)

    data: Dict[str, Any] = {"mode": "full", "nodes": d3_nodes, "edges": d3_edges}
    extra = _tag_cross_file_calls(data)
    logger.info("Tagged %s cross-file CALL edges (by node id / file_path)", extra)
    return data


def _d3_html(title: str, graph_json: str) -> str:
    return (
        """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>__TITLE__</title>
  <script src="__D3_CDN__"></script>
  <style>
    body { margin:0; font-family: system-ui, sans-serif; background:#0d1117; color:#c9d1d9; overflow:hidden; }
    svg { width:100vw; height:100vh; cursor:grab; }
    line.link { stroke-opacity:0.45; }
    circle.node { stroke:#30363d; stroke-width:1.2px; }
    text.nl { font-size:10px; fill:#8b949e; pointer-events:none; }
    header { position:absolute; top:0; left:0; right:0; z-index:10; padding:8px 12px;
      background:rgba(13,17,23,0.92); border-bottom:1px solid #30363d; display:flex; gap:12px; flex-wrap:wrap; align-items:center; }
    #legend { font-size:12px; color:#ff9933; }
    .hint { color:#8b949e; font-size:12px; }
  </style>
</head>
<body>
<header>
  <strong>Code graph (D3)</strong>
  <span class="hint">Scroll zoom · drag background · drag nodes</span>
  <span id="legend"><strong>CALL liên file</strong>: cạnh cam = CALLS giữa hai file</span>
</header>
<script>
var graphData = __GRAPH_JSON__;
const EDGE_COLOR = {
  CALLS: "#58a6ff",
  INCLUDES: "#7ee787",
  CONTAINS: "#8b949e",
  DEFINES: "#d2a8ff",
  DECLARES: "#bc8cff",
  INHERITS: "#ffa657",
  OVERRIDDEN_BY: "#ff7b72",
  HAS_METHOD: "#79c0ff",
  HAS_FIELD: "#56d364",
  SCOPE_CONTAINS: "#6e7681",
};
function eColor(d) {
  if (d.cross_file && d.kind === "CALLS") return "#ff9933";
  return EDGE_COLOR[d.kind] || "#484f58";
}
function eStyle(d) {
  if (d.cross_file && d.kind === "CALLS") return {dash:null,width:3.2,opacity:0.92,marker:""};
  return {dash:null,width:1,opacity:0.35,marker:""};
}
const NODE_COL = {
  FUNCTION: "#79c0ff", FILE: "#ffa657", FOLDER: "#8b949e", PROJECT: "#f0883e",
  CLASS: "#d2a8ff", STRUCT: "#d2a8ff", MACRO: "#ff7b72", VARIABLE: "#56d364",
  NAMESPACE: "#bc8cff", TYPE_ALIAS: "#a5a5ff", UNKNOWN: "#6e7681",
};
const nodes = graphData.nodes.map(d => ({...d}));
const links = graphData.edges.map(d => ({...d}));
const svg = d3.select("body").append("svg");
const g = svg.append("g");
const zoom = d3.zoom().on("zoom", ev => g.attr("transform", ev.transform));
svg.call(zoom);
const W = () => window.innerWidth;
const H = () => window.innerHeight;
const sim = d3.forceSimulation(nodes)
  .force("link", d3.forceLink(links).id(d => d.id).distance(55).strength(0.35))
  .force("charge", d3.forceManyBody().strength(-120))
  .force("center", d3.forceCenter(W() / 2, H() / 2 + 24))
  .force("collide", d3.forceCollide().radius(14));
const link = g.append("g").attr("class", "links").selectAll("line").data(links).join("line").attr("class", "link");
const node = g.append("g").attr("class", "nodes").selectAll("circle").data(nodes).join("circle")
  .attr("class", "node").attr("r", 9)
  .attr("fill", d => NODE_COL[d.group] || NODE_COL.UNKNOWN)
  .call(d3.drag().on("start", dragstarted).on("drag", dragged).on("end", dragended));
const label = g.append("g").selectAll("text").data(nodes).join("text")
  .attr("class", "nl").attr("dx", 12).attr("dy", 4).text(d => d.label || d.id);
function tick() {
  link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
      .attr("x2", d => d.target.x).attr("y2", d => d.target.y)
      .attr("stroke", d => eColor(d))
      .each(function(d) {
        const s = eStyle(d);
        d3.select(this).attr("stroke-width", s.width).attr("opacity", s.opacity);
      });
  node.attr("cx", d => d.x).attr("cy", d => d.y);
  label.attr("x", d => d.x).attr("y", d => d.y);
}
sim.on("tick", tick);
function dragstarted(event, d) {
  if (!event.active) sim.alphaTarget(0.35).restart();
  d.fx = d.x;
  d.fy = d.y;
}
function dragged(event, d) {
  d.fx = event.x;
  d.fy = event.y;
}
function dragended(event, d) {
  if (!event.active) sim.alphaTarget(0);
  d.fx = null;
  d.fy = null;
}
window.addEventListener("resize", () => {
  sim.force("center", d3.forceCenter(W() / 2, H() / 2 + 24));
  sim.alpha(0.25).restart();
});
</script>
</body>
</html>
"""
        .replace("__TITLE__", title.replace("<", "").replace(">", ""))
        .replace("__D3_CDN__", D3_CDN)
        .replace("__GRAPH_JSON__", graph_json)
    )


def write_d3_force_html(
    graph: Dict[str, Any],
    out_path: str,
    *,
    title: str = "code-graph-d3",
    edge_types: Optional[Set[str]] = None,
    max_nodes: Optional[int] = None,
) -> None:
    data = graph_to_d3_graphdata(graph, edge_types=edge_types, max_nodes=max_nodes)
    graph_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    graph_json = graph_json.replace("</", "<\\/")
    html = _d3_html(title, graph_json)
    outp = Path(out_path).resolve()
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(html, encoding="utf-8")
    logger.info("Wrote D3 HTML graph to %s", outp)


def write_d3_force_html_from_file(
    graph_path: str,
    out_path: str,
    *,
    title: Optional[str] = None,
    edge_types: Optional[Set[str]] = None,
    max_nodes: Optional[int] = None,
) -> None:
    p = Path(graph_path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() in (".yaml", ".yml"):
        import yaml

        graph = yaml.safe_load(text)
    else:
        graph = json.loads(text)
    write_d3_force_html(
        graph,
        out_path,
        title=title or p.stem,
        edge_types=edge_types,
        max_nodes=max_nodes,
    )
