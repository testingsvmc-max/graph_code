---
name: search-graph-db
description: >-
  Search and traverse SQLite graph.db via direct crg_db_query.py CLI (recommended); optional HTTP
  crg_db_main on 8091. Structural only — not YAML graph file CLI, not vector search. Use when the user
  asks to query graph.db or the SQLite graph database without starting a server.
---

# search-graph-db

**Scope:** **`graph.db`** only (SQLite graph produced with **`build_graph_code.py --also-db`** or equivalent). Prefer **direct** `crg_db_query.py` (no server). Optional FastAPI mirror on **8091** — **not** the YAML export graph, **not** FAISS semantic search.

**Typical path:**

```text
<project>/.clangd-graph-rag/graph.db
```

---

## CLI

```bash
python standalone_tools/crg_db_query.py --db <path/to/graph.db> search "auth"
python standalone_tools/crg_db_query.py --db <path/to/graph.db> callers "<qualified_name>"
python standalone_tools/crg_db_query.py --db <path/to/graph.db> callees "<qualified_name>"
python standalone_tools/crg_db_query.py --db <path/to/graph.db> call-graph "<qualified_name>" --direction both --depth 2
```

---

## Optional HTTP (port **8091**)

Only if you need a long-running REST service:

```bash
python -m code_graph_api.crg_db_main <path/to/graph.db> --host 127.0.0.1 --port 8091
```

Same structural ideas as the YAML HTTP API where implemented (see `crg_db_main` / OpenAPI for your version).

---

## Guidance

- Prefer **`graph.db`** when tooling or automation already targets SQLite, or you want a single-file DB without loading full YAML into memory.
- **YAML / JSON export** on port **8090** → **search-graph-export**.
- **Natural-language / embedding** top‑k → **search-graph-semantic**.

## Related skills

- **search-graph-export** — `code_graph.yaml`; direct **`query_code_graph.py`** / **`code_graph_tools.py`** (optional HTTP **8090**, MCP **8810**).
- **search-graph-semantic** — FAISS / Chroma / JSONL vectors.
- **build-graph-code** — produce `graph.db` with `--also-db`.
- **query-graph-code** — router if unsure YAML vs DB vs vectors.
