"""
FastAPI for querying clangd-graph-rag SQLite ``graph.db`` (no Neo4j).

Run:
  set GRAPH_DB_PATH=D:\\path\\project\\.clangd-graph-rag\\graph.db
  uvicorn code_graph_api.crg_db_main:app --host 127.0.0.1 --port 8091

Or:
  python -m code_graph_api.crg_db_main D:\\path\\project\\.clangd-graph-rag\\graph.db --port 8091
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Query

from integrations.crg_sqlite import (
    call_graph_neighborhood,
    get_callees,
    get_callers,
    load_crg_db,
    resolve_function_target,
    search_nodes,
)

_conn = None


def _get_conn():
    if _conn is None:
        raise HTTPException(status_code=503, detail="DB not loaded. Set GRAPH_DB_PATH.")
    return _conn


def create_app(db_path: Optional[str] = None) -> FastAPI:
    global _conn

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global _conn
        path = db_path or os.environ.get("GRAPH_DB_PATH")
        if not path:
            raise RuntimeError("GRAPH_DB_PATH is required")
        p = Path(path)
        if not p.is_file():
            raise RuntimeError(f"graph.db not found: {p.resolve()}")
        _conn = load_crg_db(str(p.resolve()))
        yield
        if _conn is not None:
            _conn.close()
        _conn = None

    app = FastAPI(title="clangd-graph-rag SQLite graph API", version="1.0.0", lifespan=lifespan)

    @app.get("/health")
    def health() -> Dict[str, Any]:
        conn = _get_conn()
        row = conn.execute("SELECT COUNT(*) AS n FROM nodes").fetchone()
        erow = conn.execute("SELECT COUNT(*) AS n FROM edges").fetchone()
        return {"ok": True, "nodes": row["n"], "edges": erow["n"]}

    @app.get("/functions/search")
    def search_functions(q: str = Query(..., min_length=1), limit: int = Query(50, ge=1, le=500)):
        return search_nodes(_get_conn(), q, limit=limit)

    @app.get("/functions/{target:path}/resolve")
    def resolve(target: str, limit: int = Query(20, ge=1, le=200)):
        return resolve_function_target(_get_conn(), target, limit=limit)

    @app.get("/functions/{target:path}/callers")
    def callers(target: str, resolve_limit: int = Query(20, ge=1, le=200)):
        conn = _get_conn()
        r = resolve_function_target(conn, target, limit=resolve_limit)
        if r["status"] != "ok":
            raise HTTPException(status_code=404 if r["status"] == "not_found" else 409, detail=r)
        qn = r["node"]["qualified_name"]
        rows = get_callers(conn, qn)
        return {"target": r["node"], "caller_count": len(rows), "callers": rows}

    @app.get("/functions/{target:path}/callees")
    def callees(target: str, resolve_limit: int = Query(20, ge=1, le=200)):
        conn = _get_conn()
        r = resolve_function_target(conn, target, limit=resolve_limit)
        if r["status"] != "ok":
            raise HTTPException(status_code=404 if r["status"] == "not_found" else 409, detail=r)
        qn = r["node"]["qualified_name"]
        rows = get_callees(conn, qn)
        return {"target": r["node"], "callee_count": len(rows), "callees": rows}

    @app.get("/functions/{target:path}/call-graph")
    def call_graph(
        target: str,
        direction: str = Query("both", pattern="^(up|down|both)$"),
        depth: int = Query(1, ge=1, le=6),
        limit: int = Query(500, ge=1, le=20000),
        resolve_limit: int = Query(20, ge=1, le=200),
    ):
        conn = _get_conn()
        r = resolve_function_target(conn, target, limit=resolve_limit)
        if r["status"] != "ok":
            raise HTTPException(status_code=404 if r["status"] == "not_found" else 409, detail=r)
        qn = r["node"]["qualified_name"]
        out = call_graph_neighborhood(conn, qn, direction=direction, depth=depth, limit=limit)
        out["center_node"] = r["node"]
        return out

    return app


app = create_app(db_path=os.environ.get("GRAPH_DB_PATH"))


def run() -> None:
    import argparse
    import uvicorn

    p = argparse.ArgumentParser(description="Run clangd-graph-rag SQLite graph.db query API")
    p.add_argument("graph_db_path", type=str, help="Path to graph.db")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8091)
    ns = p.parse_args()

    os.environ["GRAPH_DB_PATH"] = str(Path(ns.graph_db_path).resolve())
    global app
    app = create_app(db_path=os.environ["GRAPH_DB_PATH"])
    uvicorn.run(app, host=ns.host, port=ns.port)


if __name__ == "__main__":
    run()
