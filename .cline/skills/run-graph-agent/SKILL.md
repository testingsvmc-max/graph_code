---
name: run-graph-agent
description: Run Google ADK coding agents against the code graph — either Neo4j via graph_mcp_server.py or YAML export via export_graph_agent (no Neo4j/MCP). Use when the user asks to run the AI agent, ADK agent, rag_adk_agent, adk web, or natural-language graph chat.
---

# run-graph-agent

This repo has **two** ADK agents in `rag_adk_agent/`. Pick **one** path; do not start both unless the user asks. Details: [rag_adk_agent/README.md](../../../rag_adk_agent/README.md).

## Trigger examples

- "run the graph agent / ADK agent"
- "`adk web` / `adk run` for this project"
- "chat with the codebase using the agent"
- "agent without Neo4j" / "YAML-only agent"

## Prerequisites

- Python deps include **google-adk** and **litellm** (see `requirements-core.txt`).
- **LLM API key** for the chosen model (default LiteLLM model is `deepseek/deepseek-chat` → e.g. `DEEPSEEK_API_KEY`). Override with `LLM_MODEL` if needed.
- Repo root as working directory for paths below.

---

## Path A — Export graph agent (no Neo4j, no MCP)

Use when the user already has **`<project>/.clangd-graph-rag/code_graph.yaml`** (or `.json`) from **build-graph-code**.

### Environment

- **`CODE_GRAPH_YAML`** or **`GRAPH_PATH`**: absolute or repo-relative path to the export file.
- **`DEEPSEEK_API_KEY`** (or keys for whatever `LLM_MODEL` uses).

### Commands (repo root)

One-shot question:

```bash
python rag_adk_agent/run_export_graph_agent.py --graph <project>/.clangd-graph-rag/code_graph.yaml --query "Your question in natural language"
```

Interactive REPL (no `--query`):

```bash
python rag_adk_agent/run_export_graph_agent.py --graph <project>/.clangd-graph-rag/code_graph.yaml
```

**ADK UI / standard runner** (set `CODE_GRAPH_YAML` first, then from repo root):

```bash
adk run rag_adk_agent.export_graph_agent
```

```bash
adk web
```

In the web UI, select the app that loads **`rag_adk_agent.export_graph_agent`** / **Export_Graph_Agent** if multiple apps appear.

### Behaviour

The agent uses **function tools** only: `list_export_graph_tools()` and `invoke_export_graph_tool(tool_name, arguments_json)`. No `graph_mcp_server.py`, no Neo4j.

---

## Path B — Neo4j + MCP agent (full GraphRAG)

Use when Neo4j is populated and the user wants **Cypher**, `get_source_code_by_id`, semantic search on summaries, etc.

### Step 1 — MCP tool server (terminal 1, repo root)

```bash
python graph_mcp_server.py
```

Requires **`NEO4J_URI`**, **`NEO4J_USER`**, **`NEO4J_PASSWORD`** (and a reachable DB). Default MCP URL is **`http://127.0.0.1:8800/mcp`** (see `rag_adk_agent/agent.py` if you need to align ports).

### Step 2 — Agent (terminal 2, repo root)

```bash
adk run rag_adk_agent
```

or:

```bash
adk web
```

Select **`rag_adk_agent`** in the UI, or use the custom runner:

```bash
python rag_adk_agent/run_agent.py
```

### Behaviour

Tools come from **`MCPToolset`** → **`graph_mcp_server.py`**. The agent instruction assumes Neo4j labels and Cypher.

---

## Windows (PowerShell) quick env

```powershell
$env:CODE_GRAPH_YAML = "D:\path\to\project\.clangd-graph-rag\code_graph.yaml"
$env:DEEPSEEK_API_KEY = "<key>"
python rag_adk_agent/run_export_graph_agent.py --graph $env:CODE_GRAPH_YAML --query "List stats and suggest callers query for main"
```

Neo4j path:

```powershell
$env:NEO4J_URI = "bolt://localhost:7687"
$env:NEO4J_USER = "neo4j"
$env:NEO4J_PASSWORD = "<password>"
python graph_mcp_server.py
```

---

## If something fails

- **Export agent**: "Graph export not found" → run **build-graph-code** or set `--graph` / `CODE_GRAPH_YAML` correctly.
- **401/403 from LLM** → check API key and `LLM_MODEL` for LiteLLM.
- **Neo4j agent**: connection errors → Neo4j not running or wrong env; MCP must be up **before** `adk run`.

## Related skills

- **build-graph-code** — produce `code_graph.yaml` / `graph.db` for Path A.
- **clangd-graph-setup** — first-time install and `compile_commands` wiring.
- **query-graph-code** — deterministic HTTP/CLI query without running the LLM agent.
