---
name: clangd-graph-setup
description: Set up clangd-graph-rag for local use (no-Neo4j by default). Use when the user asks to setup clangd graph, install dependencies, or initialize the VSCode/Cline workflow.
---

# clangd-graph-setup

Onboarding for this repo. **Source of truth:** [README.md](README.md) — Quick Start (No Neo4j), prerequisites, optional Neo4j.

## Default behavior

- Prefer **no-Neo4j** setup (`requirements-core.txt`).
- Use repository **standalone_tools** only unless the user asks for Neo4j.
- Ask minimal questions; prompt for `compile_commands.json` only if needed (setup can persist it to `.env.clangd_graph`).

## Workflow

1. Install Python deps (README):

```bash
pip install -r requirements-core.txt
```

2. Run setup:

```bash
python standalone_tools/setup_clangd_graph.py
```

3. If `compile_commands.json` is already known:

```bash
python standalone_tools/setup_clangd_graph.py --compile-commands <path/to/compile_commands.json>
```

4. Skip automatic `clangd-indexer` install hints (if user insists):

```bash
python standalone_tools/setup_clangd_graph.py --skip-clangd-indexer
```

5. If the user explicitly wants Neo4j extras:

```bash
pip install -r requirements-core.txt -r requirements-neo4j.txt
python standalone_tools/setup_clangd_graph.py --with-neo4j
```

6. After setup, point to **build** then **query** (README):

```bash
python standalone_tools/build_graph_code.py <project_dir> --index-file <path/to/index.yaml> --compile-commands <path/to/compile_commands.json> --also-db
python -m code_graph_api <project_dir>/.clangd-graph-rag/code_graph.yaml --host 127.0.0.1 --port 8090
```

Cline can also load **query-graph-code** / **build-graph-code** skills under `.cline/skills/` for scripted follow-ups.
