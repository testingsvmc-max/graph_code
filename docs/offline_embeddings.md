# Offline embeddings (no Neo4j required)

Local embeddings use **`llm_client.get_embedding_client()`** → one process-wide **`SentenceTransformer`** model. You **do not** need Neo4j to embed or search: use **YAML/JSON export** + **`export_graph_rag_chunks`**, **FAISS**, or **Chroma** as below.

## Recommended flow (YAML-only)

1. Build `code_graph.yaml` (e.g. `standalone_tools/build_graph_code.py --also-db`).
2. **Chunks + vectors (JSONL):**  
   `python standalone_tools/export_graph_rag_chunks.py path/to/code_graph.yaml --backend jsonl --with-embeddings`  
   → `rag_export/chunks.jsonl` with an `embedding` array per line.
3. **Or FAISS in one step:**  
   `python standalone_tools/faiss_code_graph_index.py build --graph path/to/code_graph.yaml --out-dir ./rag_faiss`  
   (`--max-nodes` is **optional**; omit it to index every matching node.)
4. **Or Chroma:**  
   `python standalone_tools/export_graph_rag_chunks.py path/to/code_graph.yaml --backend chroma`  
   (see `requirements-vectordb.txt`).

Design notes: [graph_to_vector_rag.md](./graph_to_vector_rag.md).

## Configuration

| Variable | Purpose | Default |
|----------|---------|---------|
| `SENTENCE_TRANSFORMER_MODEL` | HuggingFace id or local path | `all-MiniLM-L6-v2` (384 dimensions) |
| `SENTENCE_TRANSFORMER_DEVICE` | Optional `device` for `.encode()` (`cuda`, `cpu`, …) | unset → library default |
| `EMBEDDING_DIMENSION` | Optional declared width for **checks** (must match the model if set) | unset → no extra check |
| `NEO4J_VECTOR_DIMENSION` | Legacy alias for `EMBEDDING_DIMENSION` (only if you still use Neo4j tools) | same as above |

If `EMBEDDING_DIMENSION` is set and differs from the model’s real output width, the client logs a **warning** so FAISS/Chroma/JSONL stay aligned.

## Behaviour (quality / safety)

1. **Singleton** — Model loaded **once per process** (export scripts, optional MCP servers, etc.).
2. **Input sanitization** — Empty / whitespace-only strings are not passed raw to `encode` (avoids fragile edge cases).
3. **Batch integrity** — Row count from `encode` must match input count; otherwise **`RuntimeError`**.
4. **Width consistency** — All vectors in a run share one dimension; mismatches raise **`RuntimeError`**.

## Call sites

| Component | Role |
|-----------|------|
| **`standalone_tools/export_graph_rag_chunks.py`** | JSONL / Chroma vectors from `code_graph.yaml` |
| **`standalone_tools/faiss_code_graph_index.py`** | FAISS index from graph or pre-embedded JSONL |
| **`graph_mcp_server.py`** | Optional: Neo4j + MCP semantic search (only if you use Neo4j) |
| **`summary_engine.orchestrator`** | Optional: writes `summaryEmbedding` on **Neo4j** after summaries |

## API helpers

- **`get_embedding_client(api_name)`** — singleton `SentenceTransformer` client.
- **`get_offline_embedding_dimension()`** — model output width (no full batch encode when the API exposes `get_sentence_embedding_dimension`).

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Chroma / FAISS dim errors | Same `SENTENCE_TRANSFORMER_MODEL` for build and query; rebuild index if you change the model. |
| CUDA OOM | `SENTENCE_TRANSFORMER_DEVICE=cpu` or a smaller model. |
| Slow first run | HuggingFace model download/cache; ensure cache directory is writable. |

### Optional Neo4j only

If you **do** use Neo4j, `neo4j_manager.schema.create_vector_indexes()` reads **`EMBEDDING_DIMENSION`** / **`NEO4J_VECTOR_DIMENSION`** (default **384**). After changing the model, drop/recreate the vector index and re-run embedding generation.
