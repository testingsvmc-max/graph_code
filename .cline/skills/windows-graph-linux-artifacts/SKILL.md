---
name: windows-graph-linux-artifacts
description: >-
  On Windows, build code_graph.yaml, SQLite graph.db, and FAISS vector index from Linux-produced
  clangd index YAML + compile_commands.json plus local source — no Neo4j. Use when artifacts
  use /home/... paths but the checkout is on Windows (D:), cross-root mapping, or offline graph + vector DB.
---

# windows-graph-linux-artifacts

**No Neo4j.** Use this flow when:

- `index.yaml` (clangd-indexer) was built on **Linux** (paths like `/home/dpi/...` in `FileURI`).
- `compile_commands.json` may still reference the **same Linux** prefixes.
- Source code lives on **Windows** (e.g. `D:\...`) with the **same relative tree** as on Linux.

The repo remaps Linux roots to your Windows tree via **`--index-source-root`** (and optional **`--local-source-root`**). Do **not** use `Path(...).resolve()` on Linux path strings in PowerShell snippets — pass them as **quoted plain strings**.

## Outputs (three artifacts)

| Artifact | Role | Typical path |
|----------|------|----------------|
| **Graph file** | Serialized nodes/edges (YAML or JSON) | `<project>\.clangd-graph-rag\code_graph.yaml` |
| **SQLite `graph.db`** | Queryable structural graph DB | `<project>\.clangd-graph-rag\graph.db` |
| **FAISS directory** | Vector index (`vectors.faiss` + sidecars) | e.g. `<project>\.clangd-graph-rag\faiss` |

## Prerequisites (Windows)

```powershell
cd <repo-root>
pip install -r requirements-core.txt
pip install -r requirements-faiss.txt
```

Optional env for embeddings: `SENTENCE_TRANSFORMER_MODEL` (default `all-MiniLM-L6-v2`). See **embed-graph-vectordb** for details.

## One-shot pipeline (recommended)

Runs export + SQLite + FAISS with the same mapping flags. **`--skip-neo4j`** ensures Neo4j is never invoked.

Replace placeholders: `INDEX.yaml`, `D:\src\myrepo`, `compile_commands.json`, and **`/linux/root`** = the absolute directory prefix as it appears inside the Linux YAML / JSON (e.g. `/home/dpi/build_server/android/myproject`).

```powershell
python standalone_tools/pipeline_linux_index_windows.py `
  D:\path\to\INDEX.yaml D:\src\myrepo `
  --compile-commands D:\src\myrepo\compile_commands.json `
  --index-source-root /home/dpi/build_server/android/myproject `
  --skip-neo4j --export-yaml --sqlite --faiss-out D:\src\myrepo\.clangd-graph-rag\faiss
```

- **`--export-yaml`**: optional path after the flag; omit the path to use the default `D:\src\myrepo\.clangd-graph-rag\code_graph.yaml`.
- **`--sqlite`**: writes `graph.db` next to the YAML (or use **`--sqlite-out`**).
- **`--faiss-out`**: directory for the FAISS bundle.

## Step-by-step (alternative)

### 1) Graph YAML + SQLite (`graph.db`)

```powershell
python standalone_tools/build_graph_code.py D:\src\myrepo `
  --index-file D:\path\to\index.yaml `
  --compile-commands D:\src\myrepo\compile_commands.json `
  --index-source-root /home/dpi/build_server/android/myproject `
  --also-db
```

Defaults: `D:\src\myrepo\.clangd-graph-rag\code_graph.yaml` and `graph.db` in the same folder.

### 2) Vector DB (FAISS)

```powershell
python standalone_tools/faiss_code_graph_index.py build `
  --graph D:\src\myrepo\.clangd-graph-rag\code_graph.yaml `
  --out-dir D:\src\myrepo\.clangd-graph-rag\faiss
```

### 3) Direct export only (advanced)

```powershell
python standalone_tools/export_code_graph_json.py `
  D:\path\to\index.yaml D:\src\myrepo `
  --compile-commands D:\src\myrepo\compile_commands.json `
  --index-source-root /home/dpi/build_server/android/myproject `
  -o D:\src\myrepo\.clangd-graph-rag\code_graph.yaml --format yaml
```

Then build SQLite with `code_graph_api.store.load_graph_dict` + `code_graph_export.sqlite_db.write_graph_sqlite`, or re-run **`build_graph_code.py --also-db`** which wraps export + DB.

## Mapping rules (agent checklist)

1. **`--index-source-root`**: POSIX absolute root **as on the Linux builder** — must match prefixes in YAML `FileURI` and in `compile_commands.json` (`directory`, `file`, `-I...`, etc.). Prefer a **long, specific** root to avoid accidental substring replaces.
2. **`--local-source-root`**: only if the logical root on Windows **differs** from the second positional / `project_path` (usually omit; defaults to project root).
3. **`compile_commands.json`**: may be a copy from Linux; remapping materializes a temp Windows-friendly copy internally when `--index-source-root` is set.

## After build (query)

Use **search-graph-export** (YAML), **search-graph-db** (`graph.db`), **search-graph-semantic** (FAISS / Chroma / JSONL), or **query-graph-code** if unsure. Shortcuts:

- **Graph file (CLI, no server):** `python standalone_tools/query_code_graph.py "<path>\code_graph.yaml" search "<term>"` — **search-graph-export** (optional HTTP: `python -m code_graph_api … --port 8090`)
- **SQLite (CLI):** `python standalone_tools/crg_db_query.py --db "<path>\graph.db" search "<term>"` — **search-graph-db** (optional: `python -m code_graph_api.crg_db_main … --port 8091`)
- **Vector / semantic:** `python standalone_tools/faiss_code_graph_index.py query --index-dir "<path>\faiss" --text "..." -k 8 --json` — **search-graph-semantic** (build: **embed-graph-vectordb**)

## If something fails

- **`relative_to` / empty graph**: wrong **`--index-source-root`** (too short or wrong segment vs YAML paths).
- **`faiss` / `sentence_transformers`**: install `requirements-faiss.txt` and `requirements-core.txt`.
- **Clang / libclang parse errors**: ensure Windows has a working toolchain and `LIBCLANG_LIBRARY_FILE` / `LIBCLANG_PATH` if needed (see repo README).

## Related skills

- **build-graph-code** — same-family build without cross-root notes.
- **embed-graph-vectordb** — Chroma / JSONL chunks / FAISS tuning and `SENTENCE_TRANSFORMER_*` env.
- **search-graph-export** / **search-graph-db** / **search-graph-semantic** — dedicated search skills.
- **query-graph-code** — router across search types.
- **clangd-graph-setup** — repo onboarding and `setup_clangd_graph.py`.
