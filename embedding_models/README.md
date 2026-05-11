# Offline embedding models (repo-local)

Use this tree so **SentenceTransformer** / Hugging Face weights live **inside the repo** (portable disk, air-gapped mirror, or backup) instead of only `~/.cache/huggingface`.

Nothing under `sentence-transformers/` or `huggingface_cache/` is tracked in Git (large binaries).

## Option A — One-shot download (recommended)

From the repository root:

```bash
python standalone_tools/download_embedding_model.py
```

Default: `sentence-transformers/all-MiniLM-L6-v2` → `embedding_models/sentence-transformers/all-MiniLM-L6-v2/`.

Then point the runtime at the folder (absolute path on Windows):

```powershell
$env:SENTENCE_TRANSFORMER_MODEL = "D:\GraphCode\clangd-graph-rag\embedding_models\sentence-transformers\all-MiniLM-L6-v2"
```

Linux/macOS:

```bash
export SENTENCE_TRANSFORMER_MODEL="$PWD/embedding_models/sentence-transformers/all-MiniLM-L6-v2"
```

`SENTENCE_TRANSFORMER_MODEL` accepts either a **Hugging Face id** or a **local directory** that contains a saved model (`config.json`, weights, etc.).

## Option B — Hugging Face cache root under this repo

Put all Hub downloads under `embedding_models/huggingface_cache` (creates `hub/` inside it):

**PowerShell**

```powershell
$env:HF_HOME = "D:\GraphCode\clangd-graph-rag\embedding_models\huggingface_cache"
python standalone_tools/download_embedding_model.py
# or: huggingface-cli download sentence-transformers/all-MiniLM-L6-v2 --local-dir .\embedding_models\sentence-transformers\all-MiniLM-L6-v2
```

**bash**

```bash
export HF_HOME="$PWD/embedding_models/huggingface_cache"
python standalone_tools/download_embedding_model.py
```

After the first download, the same `HF_HOME` keeps new models beside your clone. For a **fully offline** machine, copy the whole `embedding_models/` directory.

## Option C — `huggingface-cli` only

```bash
pip install huggingface_hub[cli]
huggingface-cli download sentence-transformers/all-MiniLM-L6-v2 --local-dir embedding_models/sentence-transformers/all-MiniLM-L6-v2
```

Then set `SENTENCE_TRANSFORMER_MODEL` to that absolute path as in option A.

## See also

- [docs/offline_embeddings.md](../docs/offline_embeddings.md) — `SENTENCE_TRANSFORMER_DEVICE`, dimensions, troubleshooting.
