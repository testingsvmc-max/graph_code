"""
clangd-graph-rag **export graph toolkit**: MCP-style ``*_tool`` names over YAML/JSON (GraphStore).

Tool names mirror common graph-review MCP surfaces so agents can reuse prompts;
this package does not depend on external graph-review Python packages.

Features that need flows, communities, multi-repo registries, or refactor pipelines
are returned as ``{"status": "unsupported", ...}`` so callers never crash.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Callable, DefaultDict, Dict, List, Optional, Set, Tuple

from .store import GraphStore

ToolFn = Callable[[GraphStore, Dict[str, Any]], Any]


def _unsupported(reason: str, alternatives: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "status": "unsupported",
        "reason": reason,
        "alternatives": alternatives or [],
    }


def _ok(payload: Dict[str, Any]) -> Dict[str, Any]:
    out = {"status": "ok"}
    out.update(payload)
    return out


def tool_list_graph_stats(store: GraphStore, args: Dict[str, Any]) -> Dict[str, Any]:
    _ = args
    return _ok({"stats": store.list_graph_stats()})


def tool_query_graph(store: GraphStore, args: Dict[str, Any]) -> Dict[str, Any]:
    pattern = str(args.get("pattern") or args.get("query_type") or "")
    target = str(args.get("target") or args.get("node_id") or "")
    limit = int(args.get("limit") or 200)
    return store.query_graph(pattern=pattern, target=target, limit=limit)


def tool_traverse_graph(store: GraphStore, args: Dict[str, Any]) -> Dict[str, Any]:
    start = str(args.get("start") or args.get("node_id") or "")
    direction = str(args.get("direction") or "both")
    edge_type = str(args.get("edge_type") or "CALLS")
    depth = int(args.get("depth") or 2)
    limit = int(args.get("limit") or 500)
    return store.traverse_graph(start=start, direction=direction, edge_type=edge_type, depth=depth, limit=limit)


def tool_get_impact_radius(store: GraphStore, args: Dict[str, Any]) -> Dict[str, Any]:
    changed = args.get("changed_files") or args.get("files") or []
    if not isinstance(changed, list):
        return {"status": "error", "error": "changed_files must be a list of strings"}
    max_depth = int(args.get("max_depth") or 2)
    limit = int(args.get("limit") or 500)
    return store.impact_radius(changed_files=[str(x) for x in changed], max_depth=max_depth, limit=limit)


def tool_semantic_search_nodes(store: GraphStore, args: Dict[str, Any]) -> Dict[str, Any]:
    q = str(args.get("query") or args.get("q") or "")
    limit = int(args.get("limit") or 30)
    mode = str(args.get("mode") or "lexical")
    rows = store.search_nodes(q, limit=limit)
    out: Dict[str, Any] = {
        "query": q,
        "mode": mode,
        "count": len(rows),
        "results": rows,
    }
    if mode == "semantic" or args.get("meaning"):
        out["note"] = (
            "True vector semantic search needs per-node embeddings in your store (YAML export has none by default). "
            "Use export_graph_rag_chunks --with-embeddings, a FAISS/Chroma index, or your own pipeline; "
            "falling back to lexical search_nodes."
        )
    return _ok(out)


def tool_get_minimal_context(store: GraphStore, args: Dict[str, Any]) -> Dict[str, Any]:
    """Ultra-compact: center id + short names of immediate CALL neighbors."""
    center = str(args.get("center") or args.get("target") or args.get("node_id") or "")
    max_tokens_hint = int(args.get("max_tokens") or args.get("token_budget") or 100)
    caller_limit = int(args.get("caller_limit") or 5)
    callee_limit = int(args.get("callee_limit") or 5)
    if not center:
        return {"status": "error", "error": "center (or target/node_id) is required"}

    def _label(nid: str) -> str:
        n = store.get_node(nid)
        if not n:
            return nid
        p = n.get("properties") or {}
        name = p.get("name") or nid
        fp = p.get("file_path") or p.get("path") or ""
        return f"{name} [{fp}]" if fp else str(name)

    callers = store.list_callers(center, limit=caller_limit)
    callees = store.list_callees(center, limit=callee_limit)
    lines = [
        f"center={_label(center)}",
        f"callers({len(callers)}): " + ", ".join(_label(c) for c in callers),
        f"callees({len(callees)}): " + ", ".join(_label(c) for c in callees),
    ]
    text = "\n".join(lines)
    return _ok(
        {
            "center_id": center,
            "approx_chars": len(text),
            "max_tokens_hint": max_tokens_hint,
            "compact_text": text[: max_tokens_hint * 4],
        }
    )


def tool_get_review_context(store: GraphStore, args: Dict[str, Any]) -> Dict[str, Any]:
    center = str(args.get("center") or args.get("target") or args.get("node_id") or "")
    depth = int(args.get("depth") or 2)
    limit = int(args.get("limit") or 80)
    if not center:
        return {"status": "error", "error": "center is required"}
    tr = store.traverse_graph(start=center, direction="both", edge_type="CALLS", depth=depth, limit=limit)
    stats = store.list_graph_stats()
    node_count = len(tr.get("nodes") or [])
    edge_count = len(tr.get("edges") or [])
    summary = (
        f"Neighborhood of `{center}`: {node_count} nodes, {edge_count} {tr.get('edge_type', 'CALLS')} edges "
        f"(depth={depth}, graph total nodes={stats.get('nodes')})."
    )
    return _ok({"summary": summary, "traverse": tr, "graph_stats": stats})


def tool_find_large_functions(store: GraphStore, args: Dict[str, Any]) -> Dict[str, Any]:
    min_lines = int(args.get("min_lines") or args.get("threshold") or 100)
    limit = int(args.get("limit") or 50)
    found: List[Dict[str, Any]] = []
    for nid in store._function_ids:
        n = store.get_node(nid)
        if not n:
            continue
        p = n.get("properties") or {}
        ls, le = p.get("line_start"), p.get("line_end")
        if ls is None or le is None:
            continue
        try:
            span = int(le) - int(ls) + 1
        except (TypeError, ValueError):
            continue
        if span >= min_lines:
            found.append({"id": nid, "name": p.get("name"), "lines": span, "file_path": p.get("file_path") or p.get("path")})
    found.sort(key=lambda x: -x["lines"])
    return _ok({"min_lines": min_lines, "count": len(found), "functions": found[:limit]})


def tool_get_hub_nodes(store: GraphStore, args: Dict[str, Any]) -> Dict[str, Any]:
    k = int(args.get("top_k") or args.get("limit") or 20)
    deg: DefaultDict[str, int] = defaultdict(int)
    for e in store._all_edges:
        if e.get("type") != "CALLS":
            continue
        deg[str(e["src"])] += 1
        deg[str(e["dst"])] += 1
    ranked = sorted(deg.items(), key=lambda x: -x[1])[:k]
    out = []
    for nid, d in ranked:
        n = store.get_node(nid)
        p = (n or {}).get("properties") or {}
        out.append({"id": nid, "degree": d, "name": p.get("name"), "file_path": p.get("file_path") or p.get("path")})
    return _ok({"metric": "call_graph_degree", "hubs": out})


def _articulation_points_call_graph(store: GraphStore) -> List[str]:
    """Undirected articulation points on CALLS endpoints (classic DFS)."""
    adj: DefaultDict[str, Set[str]] = defaultdict(set)
    nodes: Set[str] = set()
    for e in store._all_edges:
        if e.get("type") != "CALLS":
            continue
        u, v = str(e["src"]), str(e["dst"])
        if u not in store.nodes or v not in store.nodes:
            continue
        adj[u].add(v)
        adj[v].add(u)
        nodes.add(u)
        nodes.add(v)
    if not nodes:
        return []

    visited: Set[str] = set()
    disc: Dict[str, int] = {}
    low: Dict[str, int] = {}
    parent: Dict[str, Optional[str]] = {}
    ap: Set[str] = set()
    time_counter = 0

    def dfs(u: str) -> None:
        nonlocal time_counter
        children = 0
        visited.add(u)
        time_counter += 1
        disc[u] = low[u] = time_counter
        for v in adj[u]:
            if v not in visited:
                parent[v] = u
                children += 1
                dfs(v)
                low[u] = min(low[u], low[v])
                if parent.get(u) is None and children > 1:
                    ap.add(u)
                if parent.get(u) is not None and low[v] >= disc[u]:
                    ap.add(u)
            elif v != parent.get(u):
                low[u] = min(low[u], disc[v])

    for start in nodes:
        if start not in visited:
            parent[start] = None
            dfs(start)
    return sorted(ap)


def tool_get_bridge_nodes(store: GraphStore, args: Dict[str, Any]) -> Dict[str, Any]:
    _ = args
    ap = _articulation_points_call_graph(store)
    detail = []
    for nid in ap[:100]:
        n = store.get_node(nid)
        p = (n or {}).get("properties") or {}
        detail.append({"id": nid, "name": p.get("name"), "file_path": p.get("file_path") or p.get("path")})
    return _ok(
        {
            "metric": "articulation_points_on_undirected_CALLS",
            "note": "This is structural chokepoints on the call graph, not edge-betweenness.",
            "nodes": detail,
            "count": len(ap),
        }
    )


def tool_detect_changes(store: GraphStore, args: Dict[str, Any]) -> Dict[str, Any]:
    """Risk-scored impact: reuse impact_radius + simple heuristics."""
    changed = args.get("changed_files") or []
    if not isinstance(changed, list) or not changed:
        return {"status": "error", "error": "changed_files (list) is required"}
    base = store.impact_radius(changed_files=[str(x) for x in changed], max_depth=int(args.get("max_depth") or 2), limit=int(args.get("limit") or 500))
    impacted_n = len(base.get("impacted_nodes") or [])
    impacted_f = len(base.get("impacted_files") or [])
    risk = "low"
    if impacted_n > 200 or impacted_f > 40:
        risk = "high"
    elif impacted_n > 50 or impacted_f > 10:
        risk = "medium"
    base["risk_tier"] = risk
    base["status"] = "ok"
    return base


def tool_get_knowledge_gaps(store: GraphStore, args: Dict[str, Any]) -> Dict[str, Any]:
    """Heuristic: high out-degree callees, few callers (possible untested leaf complexity)."""
    limit = int(args.get("limit") or 20)
    out_d: DefaultDict[str, int] = defaultdict(int)
    in_d: DefaultDict[str, int] = defaultdict(int)
    for e in store._all_edges:
        if e.get("type") != "CALLS":
            continue
        out_d[str(e["src"])] += 1
        in_d[str(e["dst"])] += 1
    candidates: List[Tuple[int, str]] = []
    for nid in store._function_ids:
        if out_d[nid] >= 8 and in_d[nid] <= 2:
            candidates.append((out_d[nid], nid))
    candidates.sort(reverse=True)
    rows = []
    for _, nid in candidates[:limit]:
        n = store.get_node(nid)
        p = (n or {}).get("properties") or {}
        rows.append(
            {
                "id": nid,
                "name": p.get("name"),
                "file_path": p.get("file_path") or p.get("path"),
                "out_degree": out_d[nid],
                "in_degree": in_d[nid],
            }
        )
    return _ok({"heuristic": "high_fanout_low_fanin", "gaps": rows})


def tool_get_surprising_connections(store: GraphStore, args: Dict[str, Any]) -> Dict[str, Any]:
    """Heuristic: cross-folder CALLS (first path segment differs)."""
    limit = int(args.get("limit") or 30)

    def folder(fp: str) -> str:
        fp = str(fp).replace("\\", "/").strip()
        if "/" not in fp:
            return fp or "."
        return fp.split("/", 1)[0]

    hits: List[Dict[str, Any]] = []
    for e in store._all_edges:
        if e.get("type") != "CALLS":
            continue
        su, sv = store.get_node(str(e["src"])), store.get_node(str(e["dst"]))
        if not su or not sv:
            continue
        pu = (su.get("properties") or {}).get("file_path") or (su.get("properties") or {}).get("path") or ""
        pv = (sv.get("properties") or {}).get("file_path") or (sv.get("properties") or {}).get("path") or ""
        if not pu or not pv:
            continue
        if folder(pu) != folder(pv):
            hits.append(
                {
                    "src": e["src"],
                    "dst": e["dst"],
                    "src_file": pu,
                    "dst_file": pv,
                }
            )
        if len(hits) >= limit:
            break
    return _ok({"heuristic": "cross_top_level_folder_calls", "edges": hits})


def tool_get_suggested_questions(store: GraphStore, args: Dict[str, Any]) -> Dict[str, Any]:
    _ = args
    hubs = tool_get_hub_nodes(store, {"top_k": 5}).get("hubs") or []
    qs = [
        "Which hubs in the call graph should be covered by tests first?",
        "What is the blast radius if we change the top hub function?",
    ]
    for h in hubs[:3]:
        qs.append(f"What calls `{h.get('name')}` ({h.get('id')}) and what does it call?")
    return _ok({"questions": qs})


def tool_build_or_update_graph(store: GraphStore, args: Dict[str, Any]) -> Dict[str, Any]:
    _ = store, args
    return _unsupported(
        "Graph build/update is not executed inside the in-memory API.",
        alternatives=[
            "python standalone_tools/build_graph_code.py <project> --index-file <clangd-index.yaml> --compile-commands <compile_commands.json> --also-db",
            "python graph_builder.py ...  # optional full Neo4j ingest",
        ],
    )


def tool_embed_graph(store: GraphStore, args: Dict[str, Any]) -> Dict[str, Any]:
    _ = store, args
    return _unsupported(
        "Embedding generation is not executed inside the in-memory GraphStore API.",
        alternatives=[
            "python standalone_tools/export_graph_rag_chunks.py <code_graph.yaml> --backend jsonl --with-embeddings",
            "python standalone_tools/faiss_code_graph_index.py build --graph <code_graph.yaml> --out-dir ./rag_faiss",
            "python standalone_tools/export_graph_rag_chunks.py <code_graph.yaml> --backend chroma  (requires chromadb)",
        ],
    )


TOOL_REGISTRY: Dict[str, ToolFn] = {
    "list_graph_stats_tool": tool_list_graph_stats,
    "query_graph_tool": tool_query_graph,
    "traverse_graph_tool": tool_traverse_graph,
    "get_impact_radius_tool": tool_get_impact_radius,
    "semantic_search_nodes_tool": tool_semantic_search_nodes,
    "get_minimal_context_tool": tool_get_minimal_context,
    "get_review_context_tool": tool_get_review_context,
    "find_large_functions_tool": tool_find_large_functions,
    "get_hub_nodes_tool": tool_get_hub_nodes,
    "get_bridge_nodes_tool": tool_get_bridge_nodes,
    "detect_changes_tool": tool_detect_changes,
    "get_knowledge_gaps_tool": tool_get_knowledge_gaps,
    "get_surprising_connections_tool": tool_get_surprising_connections,
    "get_suggested_questions_tool": tool_get_suggested_questions,
    "build_or_update_graph_tool": tool_build_or_update_graph,
    "embed_graph_tool": tool_embed_graph,
}


UNSUPPORTED_TOOLS: Dict[str, str] = {
    "get_docs_section_tool": "No documentation corpus is attached to YAML exports.",
    "list_flows_tool": "Execution flows are not present in clangd-graph-rag exports.",
    "get_flow_tool": "Execution flows are not present in clangd-graph-rag exports.",
    "get_affected_flows_tool": "Execution flows are not present in clangd-graph-rag exports.",
    "list_communities_tool": "Community detection is not computed in the default export (use external analytics).",
    "get_community_tool": "Community detection is not computed in the default export.",
    "get_architecture_overview_tool": "Community-based architecture overview is not computed in the default export.",
    "refactor_tool": "Refactor preview is not implemented for YAML-backed graphs.",
    "apply_refactor_tool": "Refactor apply is not implemented for YAML-backed graphs.",
    "generate_wiki_tool": "Wiki generation from communities is not implemented.",
    "get_wiki_page_tool": "Wiki pages are not generated.",
    "list_repos_tool": "Single-graph mode: only the loaded export is visible.",
    "cross_repo_search_tool": "Single-graph mode: only the loaded export is visible.",
}


def list_tools_catalog() -> List[Dict[str, Any]]:
    catalog: List[Dict[str, Any]] = []
    for name, fn in sorted(TOOL_REGISTRY.items()):
        catalog.append({"name": name, "implemented": True, "description": (fn.__doc__ or "").strip().split("\n")[0]})
    for name, reason in sorted(UNSUPPORTED_TOOLS.items()):
        catalog.append({"name": name, "implemented": False, "reason": reason})
    return catalog


def invoke_tool(store: GraphStore, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
    arguments = arguments or {}
    if tool_name in UNSUPPORTED_TOOLS:
        return _unsupported(UNSUPPORTED_TOOLS[tool_name])
    fn = TOOL_REGISTRY.get(tool_name)
    if not fn:
        return {"status": "error", "error": f"Unknown tool: {tool_name}", "known": sorted(TOOL_REGISTRY) + sorted(UNSUPPORTED_TOOLS)}
    return fn(store, arguments)


def invoke_tool_json(store: GraphStore, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> str:
    return json.dumps(invoke_tool(store, tool_name, arguments), ensure_ascii=False, default=str)
