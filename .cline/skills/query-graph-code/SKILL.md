---
name: query-graph-code
description: Search callers/callees, graph traversal, impact radius, and MCP-style *_tool invoke on YAML/JSON or SQLite graph.db. Use when the user asks to query the code graph, trace call chains, or use catalog/invoke tools without Neo4j.
---

# query-graph-code

Use this skill after a graph export exists (see **build-graph-code** and [README.md](README.md) Quick Start).

Artifacts (defaults):

- YAML: `<project_path>/.clangd-graph-rag/code_graph.yaml`
- SQLite: `<project_path>/.clangd-graph-rag/graph.db`

## Trigger examples

- "search callers/callees"
- "find who calls this function"
- "graph traversal from function X"
- "trace call chain up/down"
- "list graph tools / invoke list_graph_stats_tool"

## Workflow

### 1. Choose backend

- **YAML/JSON** — function-oriented HTTP on port **8090** (below), or `query_code_graph.py`, or MCP-style tools on the same file.
- **SQLite `graph.db`** — `crg_db_query.py`, or HTTP **`python -m code_graph_api.crg_db_main`** on port **8091** (see README §7b).

### 2. YAML — HTTP API (matches README)

Start (if not running):

```bash
python -m code_graph_api <path/to/code_graph.yaml> --host 127.0.0.1 --port 8090
```

Endpoints:

```text
GET /functions/search?q=<keyword>&limit=50
GET /functions/{func_id}/callers?limit=200
GET /functions/{func_id}/callees?limit=200
GET /functions/{func_id}/call-graph?direction=both&depth=2&limit=500
GET /graph/stats
GET /graph/query?pattern=callers_of&target=<id>
GET /graph/traverse?start=<id>&direction=both&edge_type=CALLS&depth=2
POST /graph/impact-radius  body: {"changed_files":["src/a.c","include/a.h"]}
GET /nodes/search?q=...
```

### 3. MCP-style `*_tool` API (same YAML graph; README)

Stable tool names (`list_graph_stats_tool`, `query_graph_tool`, …):

| Channel | Command / route |
|---------|-----------------|
| HTTP | `GET /tools/catalog`, `POST /tools/invoke` with `{"tool":"…","arguments":{}}` |
| CLI | `python standalone_tools/code_graph_tools.py <code_graph.yaml> catalog` and `… invoke <tool_name> --args '{...}'` |
| MCP | `python code_graph_mcp_tools_server.py <graph.yaml>` — tools `invoke_graph_tool`, `list_graph_tools`; default port **8810** (`GRAPH_PATH` or argv) |

### 4. SQLite — local CLI

```bash
python standalone_tools/crg_db_query.py --db <path/to/graph.db> search "auth"
python standalone_tools/crg_db_query.py --db <path/to/graph.db> callers "<qualified_name>"
python standalone_tools/crg_db_query.py --db <path/to/graph.db> callees "<qualified_name>"
python standalone_tools/crg_db_query.py --db <path/to/graph.db> call-graph "<qualified_name>" --direction both --depth 2
```

### 5. YAML — local CLI (no HTTP)

```bash
python standalone_tools/query_code_graph.py <path/to/code_graph.yaml> stats
python standalone_tools/query_code_graph.py <path/to/code_graph.yaml> search "auth"
python standalone_tools/query_code_graph.py <path/to/code_graph.yaml> query callers_of "<func_id>"
python standalone_tools/query_code_graph.py <path/to/code_graph.yaml> traverse "<func_id>" --direction both --depth 2
python standalone_tools/query_code_graph.py <path/to/code_graph.yaml> impact-radius src/a.c include/a.h
```

## Query guidance

- If the user gives only a function name (not a full id), call `/functions/search` (or `query_code_graph.py … search`) first.
- For upstream impact, use `direction=up`; for downstream, `direction=down`; for neighborhood, `direction=both`.
- Keep `depth` small first (`1` or `2`) to limit noise.
