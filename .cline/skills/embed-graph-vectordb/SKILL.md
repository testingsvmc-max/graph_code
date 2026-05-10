---
name: embed-graph-vectordb
description: Embed clangd-graph-rag code_graph.yaml into a local vector store (JSONL with vectors, Chroma, or FAISS) using offline SentenceTransformer; full index by default (omit --max-nodes). Use when the user asks to embed the graph for RAG, vector DB, semantic search, FAISS, Chroma, or export embeddings from the code graph.
---

# embed-graph-vectordb

Turn **`code_graph.yaml`** (or `.json`) into **searchable vectors** for RAG. **No Neo4j required.** Uses local **`SentenceTransformer`** via `llm_client` (same model as optional Neo4j summaries).

**Prerequisite:** a graph export exists (see **build-graph-code**), typically:

```text
<project>/.clangd-graph-rag/code_graph.yaml
```

Reference docs: [docs/offline_embeddings.md](../../../docs/offline_embeddings.md), [docs/graph_to_vector_rag.md](../../../docs/graph_to_vector_rag.md).

## Trigger examples

- "embed the code graph for vector search / RAG"
- "export graph to Chroma / FAISS"
- "add embeddings to graph chunks"
- "build a vector index from code_graph.yaml"

## Environment (before running)

| Variable | Purpose |
|----------|---------|
| `SENTENCE_TRANSFORMER_MODEL` | HF model id (default `all-MiniLM-L6-v2`, 384-dim) |
| `SENTENCE_TRANSFORMER_DEVICE` | Optional: `cpu`, `cuda`, … |
| `EMBEDDING_DIMENSION` | Optional sanity check; must match model if set |

Install base + optional backends:

```bash
pip install -r requirements-core.txt
# Chroma:
pip install -r requirements-vectordb.txt
# FAISS:
pip install -r requirements-faiss.txt
```

## Path A — JSONL + any vector DB (portable)

Writes `rag_export/chunks.jsonl` (+ `manifest.json`) beside the graph by default; each line has `id`, `text`, `metadata`, and **`embedding`** when `--with-embeddings`.

**Full graph (default — do not pass `--max-nodes`):**

```bash
python standalone_tools/export_graph_rag_chunks.py <project>/.clangd-graph-rag/code_graph.yaml --backend jsonl --with-embeddings
```

**Optional smoke test** (cap node count and/or restrict labels):

```bash
python standalone_tools/export_graph_rag_chunks.py <path/to/code_graph.yaml> --backend jsonl --with-embeddings --include-label FUNCTION --max-nodes 5000
```

Ingest the JSONL into Qdrant / pgvector / LangChain yourself, or use Path B/C.

## Path B — Chroma persistent store

```bash
python standalone_tools/export_graph_rag_chunks.py <path/to/code_graph.yaml> --backend chroma --out-dir ./rag_chroma
```

Creates a **`chroma_db`** folder under `--out-dir`. Use `--reset-chroma-collection` to replace an existing collection.

## Path C — FAISS index (one-shot)

Builds **`vectors.faiss`** + `ids.json` + `metadata.json` + `manifest.json` under `--out-dir`.

**Full index (default — omit `--max-nodes`):** every graph node that matches the default label set (or your `--include-label` filters) is embedded.

```bash
python standalone_tools/faiss_code_graph_index.py build --graph <path/to/code_graph.yaml> --out-dir ./rag_faiss
```

**Optional:** `--max-nodes N` only when you want a smaller index for a quick test (same flag as `export_graph_rag_chunks.py`).

Query (same model env as build):

```bash
python standalone_tools/faiss_code_graph_index.py query --index-dir ./rag_faiss --text "where is error handling for I/O" -k 8 --json
```

Optional filter on node metadata labels:

```bash
python standalone_tools/faiss_code_graph_index.py query --index-dir ./rag_faiss --text "init" -k 5 --labels FUNCTION,METHOD
```

## Path D — JSONL first, then FAISS from file

```bash
python standalone_tools/export_graph_rag_chunks.py ./code_graph.yaml --backend jsonl --with-embeddings --out-dir ./rag_export
python standalone_tools/faiss_code_graph_index.py build --chunks ./rag_export/chunks.jsonl --out-dir ./rag_faiss
```

Each JSONL line **must** contain an `embedding` array.

## Defaults and tuning

- **Labels included** (unless `--include-label` is repeated): FUNCTION, METHOD, FILE, FOLDER, CLASS_STRUCTURE, DATA_STRUCTURE, MACRO, TYPE_ALIAS, NAMESPACE (see `export_graph_rag_chunks.py`).
- **`--embed-batch`** (default 32): batch size for encoding.
- **`--max-nodes`**: **optional only.** If omitted, **all** matching nodes are embedded (full graph / full FAISS). Pass `N` to cap for faster smoke runs.

## If something fails

- **`ModuleNotFoundError: sentence_transformers`** → `pip install -r requirements-core.txt`
- **`chromadb` / `faiss`** → install the matching optional requirements file above.
- **Dimension mismatch** after changing `SENTENCE_TRANSFORMER_MODEL` → rebuild index / chunks; set `EMBEDDING_DIMENSION` to the new model width if you use env checks.

## Related skills

- **build-graph-code** — produce `code_graph.yaml` first.
- **query-graph-code** — structural / lexical query without vectors.
- **run-graph-agent** — ADK agent on YAML (lexical tools unless you wire a vector retriever yourself).
