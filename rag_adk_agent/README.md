# RAG ADK Agent: examples

This directory contains **Google Agent Development Kit (ADK)** examples that query a **C/C++ code graph** in natural language. There are **two** agents:

| Agent | Module | Graph backend | Tools |
|--------|--------|----------------|--------|
| Neo4j + MCP | `agent.py` | Neo4j | `MCPToolset` → `graph_mcp_server.py` (Cypher, source read, …) |
| Export only | `export_graph_agent.py` | In-memory **YAML/JSON** (`GraphStore`) | Python **function tools** → `code_graph_api.graph_toolkit` (no MCP, no Neo4j) |

---

## 1. Neo4j agent (`agent.py`)

Flow: **Orient → Cypher → read source → synthesize.**

### `run_agent.py`

Loads tools from the MCP server and runs a terminal session.

### Running

**Step 1 — tool server**

```bash
python graph_mcp_server.py
```

**Step 2 — agent**

```bash
adk run rag_adk_agent
# or
adk web
# or
python rag_adk_agent/run_agent.py
```

Configure LLM / keys for LiteLLM as in the main [README](../README.md#interacting-with-the-graph-ai-agent).

---

## 2. Export-graph agent (`export_graph_agent.py`) — no MCP, no Neo4j

Uses the same **`*_tool`** names as the HTTP/MCP export surface (`list_graph_stats_tool`, `query_graph_tool`, `traverse_graph_tool`, …), implemented by calling `invoke_tool` on a `GraphStore` loaded from disk.

### Environment

- **`CODE_GRAPH_YAML`** or **`GRAPH_PATH`**: path to `code_graph.yaml` or `.json` (e.g. `<project>/.clangd-graph-rag/code_graph.yaml`).
- **`DEEPSEEK_API_KEY`** (or whatever your `LLM_MODEL` provider needs via LiteLLM).
- Optional **`LLM_MODEL`**: default `deepseek/deepseek-chat`.

### CLI runner (repo root)

```bash
python rag_adk_agent/run_export_graph_agent.py --graph ./.clangd-graph-rag/code_graph.yaml --query "Summarize graph stats and top CALL hubs"
```

Interactive (no `--query`):

```bash
python rag_adk_agent/run_export_graph_agent.py --graph ./.clangd-graph-rag/code_graph.yaml
```

### ADK CLI / Web

Set `CODE_GRAPH_YAML`, then:

```bash
adk run rag_adk_agent.export_graph_agent
# or
adk web
```

Pick the **`export_graph_agent`** / **`Export_Graph_Agent`** app entry as your UI shows.

### Tools exposed to the LLM

- **`list_export_graph_tools()`** — JSON catalog (implemented + unsupported stubs).
- **`invoke_export_graph_tool(tool_name, arguments_json="{}"`)** — runs one tool; `arguments_json` must be a **string** containing a JSON object (e.g. `'{"pattern":"callers_of","target":"src/x.c::f"}'`).
