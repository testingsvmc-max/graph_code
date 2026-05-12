---
name: search-graph-semantic
description: >-
  Semantic (vector) search on graph-derived chunks: FAISS index query, Chroma collections, JSONL
  embeddings — cosine / top-k by text. Not structural callers/callees on YAML or graph.db. Use when
  the user asks semantic search, vector similarity, RAG retrieval, FAISS query, or embedding search on code graph chunks.
---

# search-graph-semantic

**Scope:** **vector stores** built from the code graph (chunks + embeddings). Natural-language or example-text **top‑k** retrieval — **not** graph traversal, **not** `crg_db_query` / YAML `callers_of` (those are **search-graph-export** and **search-graph-db**).

**Build** indexes with **embed-graph-vectordb** (`export_graph_rag_chunks`, `faiss_code_graph_index.py build`, etc.). This skill covers **query** paths once artifacts exist.

---

## FAISS

Requires a directory with `vectors.faiss`, `ids.json`, `metadata.json` (from `faiss_code_graph_index.py build`).

```bash
python standalone_tools/faiss_code_graph_index.py query --index-dir <path/to/rag_faiss> --text "buffer overflow" -k 8 --json
python standalone_tools/faiss_code_graph_index.py query --index-dir <path/to/rag_faiss> --text "init" -k 5 --labels FUNCTION,METHOD
```

Use the **same** `SENTENCE_TRANSFORMER_MODEL` (and related env) as at **build** time.

---

## Chroma

Persistent folder from `export_graph_rag_chunks --backend chroma`. Query with the **`chromadb`** client (collection + `query` / `get`). See **embed-graph-vectordb** for layout and env.

---

## JSONL + embeddings

Lines with `id`, `text`, `metadata`, optional **`embedding`** array: load in your app, or rebuild FAISS via `faiss_code_graph_index.py build --chunks …` then use **FAISS** `query` above.

---

## Guidance

- **Call graph / symbol id / impact-radius** → **search-graph-export** or **search-graph-db**, not vectors.
- Re‑rank or filter vector hits using `metadata` (file, symbol kind, labels) from the index JSON sidecars.
- Linux index + Windows source: build with correct remap (**windows-graph-linux-artifacts**), then query here.

## Related skills

- **embed-graph-vectordb** — create chunks, Chroma store, FAISS index, JSONL with `--with-embeddings`.
- **graph-traverse-chroma** — after structural traverse, fetch or query Chroma only within neighborhood node ids.
- **chroma-query-graph-traverse** — Chroma `query` for NL seeds, then merged CALLS subgraph from YAML.
- **search-graph-export** — structural YAML graph.
- **search-graph-db** — structural SQLite `graph.db`.
- **query-graph-code** — router across all three search types.

Reference: [docs/offline_embeddings.md](../../../docs/offline_embeddings.md), [docs/graph_to_vector_rag.md](../../../docs/graph_to_vector_rag.md).
