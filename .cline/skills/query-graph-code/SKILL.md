---
name: query-graph-code
description: >-
  Router: pick the right code-graph search — YAML/JSON structural (search-graph-export), SQLite graph.db
  (search-graph-db), vector semantic (search-graph-semantic), traverse+Chroma from a known id
  (graph-traverse-chroma), Chroma NL seeds then merged graph slice (chroma-query-graph-traverse), or HTML
  visualization (visualize-graph-html). Use when the user asks generically to query the graph, is unsure
  which artifact they have, or wants one overview table linking all interfaces.
---

# query-graph-code (router)

Use a **dedicated** skill when you know the target:

| User goal | Artifact | Skill |
|-----------|------------|--------|
| Structural search on **`code_graph.yaml` / `.json`** — **direct CLI** (`query_code_graph.py`, `code_graph_tools.py`); optional MCP **8810**; optional HTTP **8090** | Graph file | **search-graph-export** |
| Structural search on **`graph.db`** — **direct CLI** `crg_db_query.py`; optional HTTP **8091** | SQLite | **search-graph-db** |
| **Semantic / vector** search — FAISS `query`, Chroma, JSONL embeddings | Index / chunks | **search-graph-semantic** (+ **embed-graph-vectordb** to build) |
| **Traverse from a function then Chroma** — neighborhood ids + vectors / optional NL query in that set | YAML + `chroma_db` | **graph-traverse-chroma** (`chroma_graph_neighborhood.py` + start id) |
| **Chroma query → graph traversal** — NL seeds, merged CALLS subgraph + edges JSON | YAML + `chroma_db` | **chroma-query-graph-traverse** (`chroma_graph_neighborhood.py --chroma-seed-query`) |
| **HTML visualization** — vis-network in browser from YAML/JSON or `graph.db` | Graph file or DB | **visualize-graph-html** |

**Rule of thumb:** callers, callees, traverse, impact → **export** or **db**; “similar code”, “meaning of”, embedding top‑k → **semantic**; known id + Chroma on that slice → **graph-traverse-chroma**; **query Chroma first** then call-graph slice → **chroma-query-graph-traverse**; “see graph / nodes in browser / HTML diagram” → **visualize-graph-html**.

---

## Quick pointers

- After **build-graph-code**: YAML under `.clangd-graph-rag/`; optional `graph.db` with `--also-db`.
- **embed-graph-vectordb** builds vector artifacts; **search-graph-semantic** runs queries on them.
- **windows-graph-linux-artifacts** — cross-root build; then use the same three search skills on the produced paths.
- **visualize-graph-html** — export graph to interactive HTML (vis-network).

Full command tables live in **search-graph-export**, **search-graph-db**, and **search-graph-semantic**. Repo overview: [README.md](README.md) (Query reference section).

## Related skills

- **build-graph-code** — produce `code_graph.yaml` + optional `graph.db`.
- **embed-graph-vectordb** — embed / index for semantic search.
- **windows-graph-linux-artifacts** — Linux artifacts + Windows tree.
- **run-graph-agent** — ADK agent on the YAML export.
- **visualize-graph-html** — vis-network HTML from YAML/JSON or `graph.db`.
- **graph-traverse-chroma** — `chroma_graph_neighborhood.py`: known start id + Chroma.
- **chroma-query-graph-traverse** — `chroma_graph_neighborhood.py --chroma-seed-query`: Chroma NL → merged graph.
