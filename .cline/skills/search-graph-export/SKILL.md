---
name: search-graph-export
description: >-
  Structural graph search on code_graph.yaml or .json without requiring HTTP 8090 by default: direct
  query_code_graph.py and code_graph_tools.py CLI; optional MCP 8810; optional REST on 8090. Callers,
  callees, traverse, impact-radius. No vector semantic search. Use when the user asks to search the
  YAML graph, call graph, or graph file tools (not graph.db, not FAISS).
---

# search-graph-export

**Scope:** exported **graph file** only (`code_graph.yaml` / `.json`). Symbol-level structure: search by name, callers/callees, traversal, impact — **not** cosine/embedding search (use **search-graph-semantic**).

**Default:** query **directly** via subprocess-friendly CLI — **no** long-running HTTP server on **8090** unless you explicitly want REST/curl.

**Prerequisite:** graph file exists (see **build-graph-code**, **windows-graph-linux-artifacts**).

---

## 1) Direct CLI — `query_code_graph.py` (recommended)

One-shot commands; no server.

```bash
python standalone_tools/query_code_graph.py <path/to/code_graph.yaml> stats
python standalone_tools/query_code_graph.py <path/to/code_graph.yaml> search "auth"
python standalone_tools/query_code_graph.py <path/to/code_graph.yaml> query callers_of "<func_id>"
python standalone_tools/query_code_graph.py <path/to/code_graph.yaml> traverse "<func_id>" --direction both --depth 2
python standalone_tools/query_code_graph.py <path/to/code_graph.yaml> impact-radius src/a.c include/a.h
```

---

## 2) Direct CLI — `code_graph_tools.py` (stable `*_tool` names)

Same tool surface as the HTTP/MCP catalog, but **invoke from the shell** (still no 8090):

```bash
python standalone_tools/code_graph_tools.py <code_graph.yaml> catalog
python standalone_tools/code_graph_tools.py <code_graph.yaml> invoke <tool_name> --args '{"…": …}'
```

---

## 3) MCP server (optional, port **8810**)

For editors/agents that speak MCP — separate from HTTP **8090**:

```bash
python code_graph_mcp_tools_server.py <graph.yaml>
```

Default port **8810** (see script / README).

---

## 4) HTTP API (optional — port **8090**)

Use only when you need a **long-running** REST service (browser, curl, other services):

```bash
python -m code_graph_api <path/to/code_graph.yaml> --host 127.0.0.1 --port 8090
```

Example routes (when server is up):

```text
GET /functions/search?q=<keyword>&limit=50
GET /functions/{func_id}/callers?limit=200
GET /functions/{func_id}/callees?limit=200
GET /graph/stats
GET /graph/query?pattern=callers_of&target=<id>
GET /graph/traverse?start=<id>&direction=both&edge_type=CALLS&depth=2
POST /graph/impact-radius  body: {"changed_files":["src/a.c","include/a.h"]}
```

`GET /tools/catalog` and `POST /tools/invoke` are also available over HTTP when this server runs.

---

## Guidance

- User gives a **name** only → `query_code_graph.py … search` first, then callers/callees/traverse with the returned `id`.
- Start **call-graph depth** at `1` or `2`.
- Same graph in **SQLite** → **search-graph-db** (often same project dir: `graph.db`).

## Related skills

- **search-graph-db** — query **`graph.db`** (prefer **`crg_db_query.py`**; HTTP **8091** optional).
- **search-graph-semantic** — FAISS / Chroma / JSONL **vector** query.
- **graph-traverse-chroma** — known id → traverse → Chroma `get` / filtered `query`.
- **chroma-query-graph-traverse** — Chroma NL `query` → merged traverse subgraph + edges JSON.
- **query-graph-code** — router if unsure which artifact you have.
- **embed-graph-vectordb** — build vector indexes from this YAML.
- **run-graph-agent** — ADK agent over the same export file.
