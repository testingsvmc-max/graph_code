---
name: graph-traverse-chroma
description: >-
  Combine structural graph traversal from a function (CALLS up/down/both on code_graph.yaml) with Chroma
  retrieval: fetch embedded chunks for neighborhood node ids, optional semantic top-k inside that set.
  Use when the user asks for graph traversal + Chroma, function neighborhood + vector DB, or hybrid
  structural + semantic RAG over clangd-graph-rag exports.
---

# graph-traverse-chroma

**Goal (pattern A):** start from a **function (or any node) id**, **walk the exported graph** (same semantics as `query_code_graph.py traverse`), then **read the matching rows from Chroma** — document id equals graph node id. Optionally run a **natural-language query restricted to those ids** (semantic rerank inside the neighborhood).

**Pattern B (Chroma-first):** use **`chroma-query-graph-traverse`** — same script with **`--chroma-seed-query`**: global Chroma NL search → seed ids → merged traverse → JSON includes **`edges`** + **`nodes`**.

This is **not** a replacement for pure vector search (**search-graph-semantic**) or pure structural CLI (**search-graph-export**); it **joins** both artifacts.

## Prerequisites

1. **`code_graph.yaml`** (or `.json`) — see **build-graph-code**.
2. **Chroma** built from the **same** graph (same node ids as in the YAML), e.g.:

   ```bash
   pip install -r requirements-core.txt
   pip install -r requirements-vectordb.txt
   python standalone_tools/export_graph_rag_chunks.py <project>/.clangd-graph-rag/code_graph.yaml --backend chroma --out-dir <project>/.clangd-graph-rag/rag_chroma
   ```

   That writes **`<out-dir>/chroma_db`** and collection **`code_graph_nodes`** by default (`--chroma-collection` to override).

3. **Same embedding model** at build and query time: `SENTENCE_TRANSFORMER_MODEL`, etc. — see **embed-graph-vectordb** and [docs/offline_embeddings.md](../../../docs/offline_embeddings.md).

**Alignment:** Chroma only contains nodes that were **included at export** (default label set in `export_graph_rag_chunks.py`). Nodes outside that set appear in the traverse JSON from the graph but may be **missing** in Chroma (`chroma_missing_ids` in tool output).

## One-shot CLI (recommended)

**Linux / macOS / Git Bash** (line continuation with `\`):

```bash
python standalone_tools/chroma_graph_neighborhood.py <project>/.clangd-graph-rag/code_graph.yaml \
  --chroma <project>/.clangd-graph-rag/rag_chroma \
  --start "<function_node_id_or_unique_substring>" \
  --direction both --edge-type CALLS --depth 2 --limit 500
```

**Windows `cmd.exe`** (use `^` at line ends instead of `\`).

- **`--chroma`**: path to **`chroma_db`** *or* a parent directory that contains **`chroma_db/`** (the script resolves it).
- **`--collection`**: default `code_graph_nodes` (must match export).
- **`--semantic "…natural language…"`** + **`--k N`**: Chroma `query()` with `where={"id": {"$in": neighborhood_ids}}` (top‑k inside the slice).

Response JSON always includes **`edges`** (graph slice) and **`nodes`** (per-id graph + Chroma).

Exit codes: **0** success; **2** bad paths / import errors; **3** ambiguous or unknown start, or Chroma seed found no nodes (see printed JSON).

## Manual workflow (same logic)

1. **Resolve the start node** (if needed):

   ```bash
   python standalone_tools/query_code_graph.py <graph.yaml> search "MyFunction" --limit 20
   ```

2. **Traverse** (inspect `nodes` / `edges`):

   ```bash
   python standalone_tools/query_code_graph.py <graph.yaml> traverse "<node_id>" --direction both --edge-type CALLS --depth 2 --limit 500
   ```

3. **Chroma** — `PersistentClient(path=".../chroma_db")`, `get_collection(...)`, then `collection.get(ids=[...])` using the **`id`** field from each traversed node. Document ids in Chroma are graph node ids.

## When to use which skill

| Need | Skill |
|------|--------|
| Build Chroma / FAISS / JSONL chunks | **embed-graph-vectordb** |
| Global semantic top‑k (no structural slice) | **search-graph-semantic** |
| Callers / callees / traverse **without** vectors | **search-graph-export** |
| **This** hybrid: traverse then Chroma get / filtered query | **graph-traverse-chroma** |
| Chroma NL seeds → merged CALLS subgraph | **chroma-query-graph-traverse** |
| Unsure | **query-graph-code** |

## Related skills

- **embed-graph-vectordb** — `export_graph_rag_chunks --backend chroma`.
- **search-graph-semantic** — general FAISS / Chroma / JSONL query patterns.
- **search-graph-export** — `query_code_graph.py traverse` reference.
- **chroma-query-graph-traverse** — Chroma semantic seeds, then merged graph neighborhood.
- **query-graph-code** — router across search modes.

Reference: [docs/graph_to_vector_rag.md](../../../docs/graph_to_vector_rag.md).
