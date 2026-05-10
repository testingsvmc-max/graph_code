# Skill: clangd-graph-rag

This repository builds a **C/C++ code graph** from clang/clangd for analysis, RAG, and agent tooling. The **default onboarding path** is **no Neo4j**: YAML/JSON export plus optional SQLite `graph.db`, HTTP APIs, and MCP-style `*_tool` helpers. **Neo4j** remains an optional path for full GraphRAG and Cypher.

Authoritative steps and options live in **[README.md](README.md)** (Quick Start, prerequisites, Neo4j ingest, MCP servers). Use this file as a short map for agents.

## When to use which flow

| User intent | Start here |
|-------------|--------------|
| Setup / first run | [README — Quick Start (No Neo4j)](README.md#quick-start-no-neo4j), `python standalone_tools/setup_clangd_graph.py` |
| Build `code_graph.yaml` + `graph.db` | `python standalone_tools/build_graph_code.py … --also-db` — outputs under `<project>/.clangd-graph-rag/` |
| Query callers/callees / traversal | `python -m code_graph_api <code_graph.yaml> --port 8090`, or `standalone_tools/query_code_graph.py`, or `standalone_tools/crg_db_query.py --db …` for SQLite |
| Stable `*_tool` names (stats, query, traverse, impact, …) | [README — Export graph tools](README.md#export-graph-tools--mcp-style-_tool-api-http--mcp--cli): HTTP `GET /tools/catalog` / `POST /tools/invoke`, CLI `standalone_tools/code_graph_tools.py`, MCP `code_graph_mcp_tools_server.py` (default port **8810**) |
| Run **ADK** coding agent (YAML or Neo4j) | `.cline/skills/run-graph-agent`, [rag_adk_agent/README.md](rag_adk_agent/README.md) |
| **Embed graph → vector DB** (JSONL / Chroma / FAISS, offline ST; omit `--max-nodes` for full index) | `.cline/skills/embed-graph-vectordb`, [docs/offline_embeddings.md](docs/offline_embeddings.md) |
| Graph quality metrics (CI-style) | [eval/README.md](eval/README.md), `python eval/run_graph_eval.py --help` |
| Full Neo4j GraphRAG + Cypher MCP | [README — End-to-end](README.md#end-to-end-build-the-graph-from-scratch), `graph_mcp_server.py`, `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` |

## Cline skills (project-local)

Under `.cline/skills/`:

- **clangd-graph-setup** — `setup_clangd_graph.py`, optional `--with-neo4j`
- **build-graph-code** — `build_graph_code.py --also-db`
- **query-graph-code** — REST on YAML export, SQLite CLI, optional MCP-style tools
- **run-graph-agent** — `adk run` / `adk web` or `run_export_graph_agent.py`; Neo4j+MCP vs YAML-only paths
- **embed-graph-vectordb** — `export_graph_rag_chunks`, `faiss_code_graph_index`; Chroma / FAISS / JSONL+embeddings

## Neo4j-only agent notes (optional)

If the graph lives in **Neo4j** and `graph_mcp_server.py` is the MCP server:

- Start with `get_project_info` and `get_graph_schema`; use **relative** paths vs project root.
- Prefer labeled Cypher (`FUNCTION`, `CALLS`, …) with **`LIMIT`** on exploratory queries.
- Use `get_source_code_by_id` for exact spans; `search_nodes_for_semantic_similarity` for concept search.

Details: [README — Interacting with the Graph](README.md#interacting-with-the-graph-ai-agent) and [neo4j_simplified_schema.txt](neo4j_simplified_schema.txt).
