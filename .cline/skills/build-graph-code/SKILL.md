---
name: build-graph-code
description: Build graph artifacts for the current project or a code directory — code_graph.yaml/json and optional SQLite graph.db (no Neo4j required). Use when the user asks to build the code graph or export graph core.
---

# build-graph-code

Graph-core build for the **no-Neo4j** flow. Full context: [README.md](README.md) Quick Start and §7 (combined YAML + DB).

Default outputs should include **both**:

- `code_graph.yaml` (or JSON if the user chose JSON)
- `graph.db` when `--also-db` is used

## Inputs

- Optional `project_path` (default: workspace / user-specified directory)
- `index.yaml` from `clangd-indexer` (see README)
- `compile_commands.json` (path or `COMPILE_COMMANDS_PATH` in env / `.env.clangd_graph` from setup)

## Workflow

1. Ensure dependencies (README):

```bash
pip install -r requirements-core.txt
```

2. Core build (YAML + DB):

```bash
python standalone_tools/build_graph_code.py --also-db
```

3. If the user provided a directory:

```bash
python standalone_tools/build_graph_code.py <project_path> --also-db
```

4. Explicit inputs:

```bash
python standalone_tools/build_graph_code.py <project_path> --index-file <path/to/index.yaml> --compile-commands <path/to/compile_commands.json> --also-db
```

5. Default output paths:

```text
<project_path>/.clangd-graph-rag/code_graph.yaml
<project_path>/.clangd-graph-rag/graph.db
```

6. Custom DB path:

```bash
python standalone_tools/build_graph_code.py <project_path> --index-file <path/to/index.yaml> --compile-commands <path/to/compile_commands.json> --also-db --db-output <custom/path/graph.db>
```

7. After a successful build, **query without starting HTTP** (see **search-graph-export** / **search-graph-db**):

```bash
python standalone_tools/query_code_graph.py <project_path>/.clangd-graph-rag/code_graph.yaml stats
python standalone_tools/query_code_graph.py <project_path>/.clangd-graph-rag/code_graph.yaml search "main"
```

With **`--also-db`**, query SQLite directly: `python standalone_tools/crg_db_query.py --db <project_path>/.clangd-graph-rag/graph.db search "…"` (optional HTTP: `python -m code_graph_api.crg_db_main … --port 8091`).

Optional long-running REST on YAML: `python -m code_graph_api <project_path>/.clangd-graph-rag/code_graph.yaml --host 127.0.0.1 --port 8090`.

Optional quality check: `python eval/run_graph_eval.py --yaml <project_path>/.clangd-graph-rag/code_graph.yaml` ([eval/README.md](../../../eval/README.md)).

8. To **embed** the same YAML into a vector store (Chroma / FAISS / JSONL) and run **semantic query**, use **embed-graph-vectordb** (build) and **search-graph-semantic** (query).

9. **Where to search:** YAML / JSON → **search-graph-export**; `graph.db` → **search-graph-db**; vectors → **search-graph-semantic**; unsure → **query-graph-code**.
