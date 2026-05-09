"""
Write a single self-contained HTML file with an interactive graph (vis-network).
Reads the same structure as memory_graph export: meta, nodes, edges.
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from collections import defaultdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_INTER_EDGE_COLOR = {"color": "#cc6600", "highlight": "#ff9933"}

VIS_NETWORK_JS = "https://cdn.jsdelivr.net/npm/vis-network@9.1.6/standalone/umd/vis-network.min.js"
VIS_NETWORK_CSS = "https://cdn.jsdelivr.net/npm/vis-network@9.1.6/styles/vis-network.min.css"


def _load_graph_file(path: str) -> Dict[str, Any]:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() in (".yaml", ".yml"):
        import yaml

        return yaml.safe_load(text)
    return json.loads(text)


def graph_to_vis_payload(
    graph: Dict[str, Any],
    *,
    edge_types: Optional[set[str]] = None,
    max_nodes: Optional[int] = None,
) -> Dict[str, Any]:
    """Convert export graph dict to vis-network nodes/edges JSON-serializable lists."""
    nodes_in: List[Dict] = graph.get("nodes") or []
    edges_in: List[Dict] = graph.get("edges") or []

    if edge_types is not None:
        edges_in = [e for e in edges_in if e.get("type") in edge_types]

    node_ids = {n["id"] for n in nodes_in}
    # keep edges whose endpoints exist
    edges_f = [e for e in edges_in if e.get("src") in node_ids and e.get("dst") in node_ids]

    if max_nodes is not None and len(nodes_in) > max_nodes:
        used: set[str] = set()
        for e in edges_f:
            used.add(e["src"])
            used.add(e["dst"])
        if not used:
            nodes_in = list(nodes_in)[:max_nodes]
        elif len(used) > max_nodes:
            cross_ids: set[str] = set()
            for e in edges_f:
                if (e.get("properties") or {}).get("cross_file"):
                    cross_ids.add(e["src"])
                    cross_ids.add(e["dst"])
            deg: Dict[str, int] = defaultdict(int)
            for e in edges_f:
                deg[e["src"]] += 1
                deg[e["dst"]] += 1

            def _keep_score(nid: str) -> tuple:
                bonus = 100000 if nid in cross_ids else 0
                return (bonus + deg[nid], nid)

            ranked = sorted(used, key=_keep_score, reverse=True)
            keep_ids = set(ranked[:max_nodes])
            nodes_in = [n for n in nodes_in if n["id"] in keep_ids]
            edges_f = [e for e in edges_f if e["src"] in keep_ids and e["dst"] in keep_ids]
        else:
            nodes_in = [n for n in nodes_in if n["id"] in used]
        logger.warning("Graph reduced to %s nodes (cap=%s)", len(nodes_in), max_nodes)

    vis_nodes = []
    for n in nodes_in:
        labels = n.get("labels") or []
        props = n.get("properties") or {}
        name = props.get("name") or props.get("path") or n["id"]
        title = json.dumps(props, ensure_ascii=False)[:2000]
        primary = labels[0] if labels else "UNKNOWN"
        vis_nodes.append(
            {
                "id": n["id"],
                "label": str(name)[:80],
                "title": title,
                "group": primary,
            }
        )

    vis_edges = []
    for i, e in enumerate(edges_f):
        item: Dict[str, Any] = {
            "id": f"e{i}",
            "from": e["src"],
            "to": e["dst"],
            "label": str(e.get("type", "")),
            "arrows": "to",
        }
        if (e.get("properties") or {}).get("cross_file"):
            item["color"] = _INTER_EDGE_COLOR
            item["width"] = 2
        vis_edges.append(item)

    return {"nodes": vis_nodes, "edges": vis_edges, "meta": graph.get("meta") or {}}


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Code graph — __TITLE__</title>
  <link rel="stylesheet" href="__VIS_CSS__"/>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 0; display: flex; flex-direction: column; height: 100vh; }}
    header {{ padding: 8px 12px; border-bottom: 1px solid #ccc; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }}
    #net {{ flex: 1; border: none; }}
    input[type="search"] {{ min-width: 220px; padding: 6px 10px; }}
    .meta {{ color: #555; font-size: 13px; }}
  </style>
</head>
<body>
  <header>
    <strong>Code graph</strong>
    <span class="meta">__META__</span>
    <label>Filter <input type="search" id="q" placeholder="node id / name substring"/></label>
    <label><input type="checkbox" id="physics" checked/> Physics</label>
    <span style="color:#cc6600;font-weight:600;">■</span>
    <span class="meta">Cạnh cam = CALL giữa hai file (cross-file)</span>
  </header>
  <div id="net"></div>
  <script src="__VIS_JS__"></script>
  <script>
  const payload = JSON.parse(atob("__PAYLOAD_B64__"));
  const container = document.getElementById("net");
  const nodes = new vis.DataSet(payload.nodes);
  const edges = new vis.DataSet(payload.edges);
  const net = new vis.Network(container, {{ nodes, edges }}, {{
    physics: {{ enabled: true }},
    nodes: {{ shape: "dot", size: 16, font: {{ size: 12 }} }},
    edges: {{ font: {{ size: 10, align: "middle" }}, smooth: {{ type: "dynamic" }} }},
    groups: {{
      useDefaultGroups: false,
    }},
    layout: {{ improvedLayout: true }},
  }});

  const orig = payload.nodes.map(n => ({{ ...n }}));
  document.getElementById("q").addEventListener("input", (ev) => {{
    const q = (ev.target.value || "").toLowerCase();
    if (!q) {{
      nodes.clear();
      nodes.add(orig);
      return;
    }}
    const keep = new Set(orig.filter(n =>
      String(n.id).toLowerCase().includes(q) || String(n.label).toLowerCase().includes(q)
    ).map(n => n.id));
    nodes.clear();
    nodes.add(orig.filter(n => keep.has(n.id)));
    const ekeep = payload.edges.filter(e => keep.has(e.from) && keep.has(e.to));
    edges.clear();
    edges.add(ekeep);
  }});

  document.getElementById("physics").addEventListener("change", (ev) => {{
    net.setOptions({{ physics: {{ enabled: ev.target.checked }} }});
  }});
  </script>
</body>
</html>
"""


def write_interactive_html(
    graph: Dict[str, Any],
    out_path: str,
    *,
    title: str = "export",
    edge_types: Optional[set[str]] = None,
    max_nodes: Optional[int] = None,
) -> None:
    """Write one HTML file; graph is the dict from build_code_graph_dict / include export."""
    payload = graph_to_vis_payload(graph, edge_types=edge_types, max_nodes=max_nodes)
    meta = payload.get("meta") or {}
    meta_s = json.dumps(meta, ensure_ascii=False)[:500]
    raw = json.dumps(payload, ensure_ascii=False)
    b64 = base64.b64encode(raw.encode("utf-8")).decode("ascii")
    html = (
        HTML_TEMPLATE.replace("__TITLE__", title.replace("<", ""))
        .replace("__META__", meta_s.replace("<", ""))
        .replace("__VIS_JS__", VIS_NETWORK_JS)
        .replace("__VIS_CSS__", VIS_NETWORK_CSS)
        .replace("__PAYLOAD_B64__", b64)
    )
    outp = Path(out_path).resolve()
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(html, encoding="utf-8")
    logger.info("Wrote HTML graph to %s", outp)


def write_interactive_html_from_file(
    graph_path: str,
    out_path: str,
    *,
    title: Optional[str] = None,
    edge_types: Optional[set[str]] = None,
    max_nodes: Optional[int] = None,
) -> None:
    graph = _load_graph_file(graph_path)
    write_interactive_html(
        graph,
        out_path,
        title=title or Path(graph_path).stem,
        edge_types=edge_types,
        max_nodes=max_nodes,
    )
