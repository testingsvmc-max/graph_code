---
name: run-graph-agent
description: >-
  Run Google ADK coding agents against the exported code graph (YAML/JSON) — no Neo4j, no graph_mcp_server
  in the default path. Use when the user asks to run the AI agent, ADK agent, rag_adk_agent, adk web,
  or natural-language chat on code_graph.yaml.
---

# run-graph-agent

**Default: Path A only** — `code_graph.yaml` / `.json` + **export_graph_agent** (function tools). No Neo4j, no `graph_mcp_server.py`.

This repo has **two** ADK entrypoints in `rag_adk_agent/`. Prefer **Path A** unless the user **explicitly** already uses Neo4j. Details: [rag_adk_agent/README.md](../../../rag_adk_agent/README.md).

## Trigger examples

- "run the graph agent / ADK agent on the export"
- "`adk web` / `adk run` for export_graph_agent"
- "chat with the codebase using the YAML graph"

## Prerequisites

- Python deps: **google-adk**, **litellm** (`requirements-core.txt`).
- **LLM API key** (default LiteLLM model `deepseek/deepseek-chat` → e.g. `DEEPSEEK_API_KEY`). Override with `LLM_MODEL` if needed.
- Repo root as working directory.

---

## Path A — Export graph agent (default)

Use when **`<project>/.clangd-graph-rag/code_graph.yaml`** (or `.json`) exists (**build-graph-code**).

### Environment

- **`CODE_GRAPH_YAML`** or **`GRAPH_PATH`**: path to the export file.
- **`DEEPSEEK_API_KEY`** (or keys for your `LLM_MODEL`).

### Commands (repo root)

One-shot:

```bash
python rag_adk_agent/run_export_graph_agent.py --graph <project>/.clangd-graph-rag/code_graph.yaml --query "Your question"
```

Interactive REPL (omit `--query`):

```bash
python rag_adk_agent/run_export_graph_agent.py --graph <project>/.clangd-graph-rag/code_graph.yaml
```

**ADK UI:**

```bash
adk run rag_adk_agent.export_graph_agent
```

```bash
adk web
```

Pick **Export_Graph_Agent** / `rag_adk_agent.export_graph_agent` in the UI.

### Behaviour

Tools: `list_export_graph_tools()`, `invoke_export_graph_tool(...)`. **No** Neo4j, **no** `graph_mcp_server.py`.

---

## Path B — Neo4j + MCP (only if user already uses Neo4j)

**Do not** install or start Neo4j when the user wants a no-Neo4j workflow. Use Path B only if they already run Neo4j and ask for Cypher / `graph_mcp_server` tools.

### Terminal 1

```bash
python graph_mcp_server.py
```

Needs **`NEO4J_URI`**, **`NEO4J_USER`**, **`NEO4J_PASSWORD`**. Default MCP URL **`http://127.0.0.1:8800/mcp`** (see `rag_adk_agent/agent.py`).

### Terminal 2

```bash
adk run rag_adk_agent
```

or `adk web` → select **`rag_adk_agent`** (not export_graph_agent).

---

## Windows (PowerShell) — Path A

```powershell
$env:CODE_GRAPH_YAML = "D:\path\to\project\.clangd-graph-rag\code_graph.yaml"
$env:DEEPSEEK_API_KEY = "<key>"
python rag_adk_agent/run_export_graph_agent.py --graph $env:CODE_GRAPH_YAML --query "List stats and suggest a callers query for main"
```

---

## If something fails

- **Export agent**: graph file missing → **build-graph-code** or fix `--graph` / `CODE_GRAPH_YAML`.
- **401/403 LLM** → API key / `LLM_MODEL`.
- **Path B only**: Neo4j / MCP connection → DB running and env vars set before `adk run`.

## Related skills

- **build-graph-code** — create `code_graph.yaml` / `graph.db`.
- **clangd-graph-setup** — install and `compile_commands` wiring.
- **search-graph-export** — direct CLI on `code_graph.yaml` (`query_code_graph.py`, `code_graph_tools.py`); optional HTTP **8090** / MCP **8810** without the LLM agent.
- **search-graph-db** / **search-graph-semantic** — SQLite or vector query paths.
- **query-graph-code** — router across search skills.
