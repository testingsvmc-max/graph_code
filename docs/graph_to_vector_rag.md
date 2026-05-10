# Research: code graph → RAG / vector databases

This note summarizes how **clangd-graph-rag** relates to vector RAG today, and common patterns for exporting a **YAML/JSON code graph** into an external vector store.

## What this repo already does

| Layer | Mechanism |
|-------|-----------|
| **Neo4j as graph + vector store** | After summaries exist, `summary_engine.orchestrator.SummaryEngine.generate_embeddings()` writes `summaryEmbedding` on nodes; `neo4j_manager` creates vector index `summary_embeddings` (dimensions from `EMBEDDING_DIMENSION` / `NEO4J_VECTOR_DIMENSION`, default **384** for `all-MiniLM-L6-v2`, cosine). See [offline_embeddings.md](./offline_embeddings.md). |
| **Query-time semantic search** | `graph_mcp_server.py` → `search_nodes_for_semantic_similarity` uses the same local `SentenceTransformer` client as the summarizer (`llm_client.get_embedding_client("local")`). |
| **YAML export** | `GraphStore` has **lexical** `search_nodes` only; `graph_toolkit.tool_embed_graph` is intentionally unsupported for YAML (no bundled embedding pipeline on the export file). |

So: **full graph RAG with vectors in-DB** is the Neo4j path. **Offline / portable RAG** needs an export step (below).

## Design choices when exporting

1. **Chunk = graph node (recommended baseline)**  
   One embedding per symbol/file (or per FILE + per FUNCTION). Metadata carries `id`, labels, `file_path`, optional `qualified_name`. Text = labels + name + path + signature + optional `summary` if you later merge summary JSON into the export.

2. **Chunk = source slice**  
   Better for huge functions: split by lines or tokens. Requires `project_root` + reliable spans; more moving parts.

3. **Embedding model**  
   Keep the same model everywhere (`SENTENCE_TRANSFORMER_MODEL`, default `all-MiniLM-L6-v2`, **384** dimensions by default) so JSONL, Chroma, and FAISS stay aligned. Optional Neo4j users: set **`EMBEDDING_DIMENSION`** (alias `NEO4J_VECTOR_DIMENSION`) to match and rebuild vector indexes after a model change. Details: [offline_embeddings.md](./offline_embeddings.md).

4. **Target systems (2024–2026 common stack)**  
   - **Chroma**: local persistent store, simple Python API; good for laptops and CI smoke tests.  
   - **Qdrant / Weaviate / Milvus**: server deployments, filtering, multi-tenant.  
   - **pgvector**: reuse Postgres; good if you already run Postgres.  
   - **LanceDB**: embedded columnar + vectors; nice for datasets on disk.  
   - **Frameworks**: LangChain / LlamaIndex loaders often accept **JSONL** `{text, metadata}` — generate JSONL first, then ingest in their docs.

## Tooling added in this repo

- **`standalone_tools/export_graph_rag_chunks.py`**  
  - **`--backend jsonl`**: writes `chunks.jsonl` (+ `manifest.json`) — no extra pip beyond core; ingest into any DB.  
  - **`--backend chroma`**: writes a **Chroma** persistent directory with precomputed embeddings (`pip install -r requirements-vectordb.txt`).

See `requirements-vectordb.txt` for optional Chroma dependency.

### FAISS (local ANN index)

- **`standalone_tools/faiss_code_graph_index.py`** — `build` / `query` subcommands.  
  - Vectors are **L2-normalized**; index is **`IndexFlatIP`** (inner product = cosine for unit vectors).  
  - **Build** from `--graph` (embed via `SentenceTransformer` + `iter_graph_rag_chunks`) or from `--chunks` JSONL (each line must include `embedding`).  
  - **Artifacts**: `vectors.faiss`, `ids.json`, `metadata.json`, `manifest.json` under `--out-dir`.  
  - **Query**: embeds `--text` with the same model, returns top‑`k` hits; optional `--labels FUNCTION,FILE` post-filter on metadata.  
  - **`--max-nodes`**: optional on `build`; **omit** to embed every matching node (full index).

Install: `pip install -r requirements-faiss.txt` (adds `faiss-cpu` and pins `numpy`).

## Related reading

- [Building an AI-Ready Code Graph RAG…](./Building_an_AI-Ready_Code_Graph_RAG_based_on_Clangd_index.md)  
- [summary_driver README](../summary_driver/README.md)  
- Neo4j vector index setup: `neo4j_manager/schema.py` (`create_vector_indexes`)
