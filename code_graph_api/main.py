"""
FastAPI app: search functions, list callers / callees for CALLS edges.

Run:
  set GRAPH_PATH=D:\\path\\code_graph.yaml
  uvicorn code_graph_api.main:app --reload --host 127.0.0.1 --port 8090

Or:
  python -m code_graph_api D:\\path\\code_graph.yaml
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, HTTPException, Query

from .graph_toolkit import invoke_tool, list_tools_catalog
from .store import GraphStore

_store: Optional[GraphStore] = None


def get_store() -> GraphStore:
    if _store is None:
        raise HTTPException(status_code=503, detail="Graph not loaded. Set GRAPH_PATH or pass path to python -m code_graph_api")
    return _store


def create_app(graph_path: Optional[str] = None) -> FastAPI:
    global _store

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global _store
        path = graph_path or os.environ.get("GRAPH_PATH")
        if not path:
            raise RuntimeError("GRAPH_PATH environment variable or graph_path argument is required")
        p = Path(path)
        if not p.is_file():
            raise RuntimeError(f"Graph file not found: {p.resolve()}")
        _store = GraphStore.from_path(str(p.resolve()))
        yield
        _store = None

    app = FastAPI(title="Code graph API", version="1.0.0", lifespan=lifespan)

    @app.get("/health")
    def health() -> Dict[str, Any]:
        s = _store
        return {
            "ok": s is not None,
            "nodes": len(s.nodes) if s else 0,
            "functions_indexed": s.function_node_count if s else 0,
            "meta": s.meta if s else {},
        }

    @app.get("/graph/stats")
    def graph_stats() -> Dict[str, Any]:
        return get_store().list_graph_stats()

    @app.get("/nodes/{node_id:path}")
    def get_node(node_id: str) -> Dict[str, Any]:
        n = get_store().get_node(node_id)
        if not n:
            raise HTTPException(404, "Node not found")
        return n

    @app.get("/functions/search")
    def search_functions(q: str = Query(..., min_length=1), limit: int = Query(50, ge=1, le=500)) -> List[Dict[str, Any]]:
        return get_store().search_functions(q, limit=limit)

    @app.get("/nodes/search")
    def search_nodes(q: str = Query(..., min_length=1), limit: int = Query(50, ge=1, le=500)) -> List[Dict[str, Any]]:
        return get_store().search_nodes(q, limit=limit)

    @app.get("/functions/{func_id:path}/callers")
    def callers(
        func_id: str,
        limit: int = Query(200, ge=1, le=2000),
    ) -> Dict[str, Any]:
        s = get_store()
        if not s.get_node(func_id):
            raise HTTPException(404, "Node not found")
        ids = s.list_callers(func_id, limit=limit)
        return {"callee_id": func_id, "caller_ids": ids, "callers": [s.get_node(i) for i in ids if s.get_node(i)]}

    @app.get("/functions/{func_id:path}/callees")
    def callees(
        func_id: str,
        limit: int = Query(200, ge=1, le=2000),
    ) -> Dict[str, Any]:
        s = get_store()
        if not s.get_node(func_id):
            raise HTTPException(404, "Node not found")
        ids = s.list_callees(func_id, limit=limit)
        return {"caller_id": func_id, "callee_ids": ids, "callees": [s.get_node(i) for i in ids if s.get_node(i)]}

    @app.get("/functions/{func_id:path}/call-graph")
    def call_graph(
        func_id: str,
        direction: str = Query("both", pattern="^(up|down|both)$"),
        depth: int = Query(1, ge=1, le=5),
        limit: int = Query(500, ge=1, le=5000),
    ) -> Dict[str, Any]:
        """
        Local CALLS neighbourhood: `up` = callers chain, `down` = callees chain, `both` = union (BFS per direction).
        """
        s = get_store()
        if not s.get_node(func_id):
            raise HTTPException(404, "Node not found")

        seen: set[str] = {func_id}
        edges_out: List[Dict[str, str]] = []

        def expand_down() -> None:
            f = {func_id}
            for _ in range(depth):
                nxt: set[str] = set()
                for a in f:
                    for b in s.callees.get(a, ()):
                        if b not in seen and len(seen) < limit:
                            seen.add(b)
                            nxt.add(b)
                            edges_out.append({"type": "CALLS", "src": a, "dst": b})
                f = nxt
                if not f:
                    break

        def expand_up() -> None:
            f = {func_id}
            for _ in range(depth):
                nxt: set[str] = set()
                for b in f:
                    for a in s.callers.get(b, ()):
                        if a not in seen and len(seen) < limit:
                            seen.add(a)
                            nxt.add(a)
                            edges_out.append({"type": "CALLS", "src": a, "dst": b})
                f = nxt
                if not f:
                    break

        if direction == "down":
            expand_down()
        elif direction == "up":
            expand_up()
        else:
            expand_down()
            expand_up()

        nodes_payload = [s.get_node(i) for i in sorted(seen) if s.get_node(i)]
        return {"center": func_id, "direction": direction, "depth": depth, "nodes": nodes_payload, "edges": edges_out}

    @app.get("/graph/query")
    def query_graph(
        pattern: str = Query(...),
        target: str = Query(...),
        limit: int = Query(200, ge=1, le=5000),
    ) -> Dict[str, Any]:
        return get_store().query_graph(pattern=pattern, target=target, limit=limit)

    @app.get("/graph/traverse")
    def traverse_graph(
        start: str = Query(...),
        direction: str = Query("both", pattern="^(up|down|both)$"),
        edge_type: str = Query("CALLS"),
        depth: int = Query(2, ge=1, le=8),
        limit: int = Query(500, ge=1, le=10000),
    ) -> Dict[str, Any]:
        return get_store().traverse_graph(start=start, direction=direction, edge_type=edge_type, depth=depth, limit=limit)

    @app.post("/graph/impact-radius")
    def impact_radius(
        payload: Dict[str, Any],
        max_depth: int = Query(2, ge=1, le=8),
        limit: int = Query(500, ge=1, le=20000),
    ) -> Dict[str, Any]:
        changed_files = payload.get("changed_files") or []
        if not isinstance(changed_files, list) or not all(isinstance(x, str) for x in changed_files):
            raise HTTPException(400, "payload.changed_files must be a list[str]")
        return get_store().impact_radius(changed_files=changed_files, max_depth=max_depth, limit=limit)

    @app.get("/tools/catalog")
    def tools_catalog() -> Dict[str, Any]:
        """clangd-graph-rag export graph toolkit: MCP-style tool names (implemented + documented stubs)."""
        return {"tools": list_tools_catalog()}

    @app.post("/tools/invoke")
    def tools_invoke(
        payload: Dict[str, Any] = Body(...),
    ) -> Any:
        """
        Invoke one tool by name. Body: ``{"tool": "list_graph_stats_tool", "arguments": {}}``.
        """
        tool = str(payload.get("tool") or payload.get("name") or "")
        if not tool:
            raise HTTPException(400, "Missing tool name (body.tool)")
        arguments = payload.get("arguments")
        if arguments is not None and not isinstance(arguments, dict):
            raise HTTPException(400, "arguments must be a JSON object")
        return invoke_tool(get_store(), tool, arguments if isinstance(arguments, dict) else {})

    return app


# Uvicorn entry: graph path from env only (lifespan reads GRAPH_PATH)
app = create_app(graph_path=os.environ.get("GRAPH_PATH"))


def run() -> None:
    """python -m code_graph_api <graph.yaml> [--port 8090]"""
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="Run code graph HTTP API")
    parser.add_argument("graph_path", type=str, help="Path to graph YAML or JSON")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    ns = parser.parse_args()
    os.environ["GRAPH_PATH"] = str(Path(ns.graph_path).resolve())

    # Recreate app with explicit path for lifespan (env already set)
    global app
    app = create_app(graph_path=os.environ["GRAPH_PATH"])
    uvicorn.run(app, host=ns.host, port=ns.port)


if __name__ == "__main__":
    run()
