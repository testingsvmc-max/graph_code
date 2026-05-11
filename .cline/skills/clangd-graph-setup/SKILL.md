---
name: clangd-graph-setup
description: >-
  Set up clangd-graph-rag for local use without Neo4j: dependencies, setup_clangd_graph, compile_commands.
  Use when the user asks to setup clangd graph, install deps, or initialize VSCode/Cline workflow.
---

# clangd-graph-setup

Onboarding for this repo **without Neo4j** as the default. **Source of truth:** [README.md](README.md) — Quick Start (No Neo4j) and prerequisites.

## Default behavior

- **`requirements-core.txt` only** — no `requirements-neo4j.txt` unless the user explicitly wants Neo4j.
- Prefer **standalone_tools** + **build-graph-code** + **search-graph-export** / **search-graph-db** / **search-graph-semantic** (or **query-graph-code** as router); do not install or suggest Neo4j unless asked.
- Minimal prompts; `compile_commands.json` can be saved to `.env.clangd_graph` via setup.

## Workflow

1. Install Python deps:

```bash
pip install -r requirements-core.txt
```

**tiktoken / wheel build errors:** `tiktoken` is optional in core; `tiktoken_compat` provides a fallback. For accurate counts: `pip install -r requirements-tiktoken.txt` (prefer Python **3.12–3.13** on Windows if wheels are missing). Try `pip install -U pip` and `pip install tiktoken --only-binary=:all:`.

2. Run setup:

```bash
python standalone_tools/setup_clangd_graph.py
```

3. If `compile_commands.json` is already known:

```bash
python standalone_tools/setup_clangd_graph.py --compile-commands <path/to/compile_commands.json>
```

4. Skip automatic `clangd-indexer` hints:

```bash
python standalone_tools/setup_clangd_graph.py --skip-clangd-indexer
```

5. **Build then query** (no Neo4j):

```bash
python standalone_tools/build_graph_code.py <project_dir> --index-file <path/to/index.yaml> --compile-commands <path/to/compile_commands.json> --also-db
python standalone_tools/query_code_graph.py <project_dir>/.clangd-graph-rag/code_graph.yaml stats
```

(Optional REST: `python -m code_graph_api <project_dir>/.clangd-graph-rag/code_graph.yaml --host 127.0.0.1 --port 8090` — see **search-graph-export**.)

Cline skills: **build-graph-code**, **search-graph-export**, **search-graph-db**, **search-graph-semantic**, **query-graph-code** (router), **embed-graph-vectordb**, **windows-graph-linux-artifacts** (Linux YAML + Windows source, no Neo4j).

---

## Optional: Neo4j (only when the user asks)

Not part of the default Cline flow. If they explicitly want the Neo4j pipeline:

```bash
pip install -r requirements-core.txt -r requirements-neo4j.txt
python standalone_tools/setup_clangd_graph.py --with-neo4j
```

Then follow [README.md](README.md) Neo4j / `graph_builder` sections — not duplicated here.
