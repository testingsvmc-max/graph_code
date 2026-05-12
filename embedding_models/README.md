# Offline embedding models (repo-local)

Use this tree so **SentenceTransformer** / Hugging Face weights live **inside the repo** (portable disk, air-gapped mirror, or backup) instead of only `~/.cache/huggingface`.

Nothing under `sentence-transformers/` or `huggingface_cache/` is tracked in Git (large binaries).

## Máy công ty không truy cập được Hugging Face

1. **Trên máy có internet** (nhà / VPN / điện thoại hotspot): clone `clangd-graph-rag`, cài `pip install huggingface_hub`, rồi trong thư mục repo chạy:
   ```bash
   python standalone_tools/download_embedding_model.py
   ```
   Model mặc định sẽ nằm tại: `embedding_models/sentence-transformers/all-MiniLM-L6-v2/` (vài trăm MB).

2. **Copy cả thư mục** `embedding_models/` (hoặc chỉ `embedding_models/sentence-transformers/all-MiniLM-L6-v2/`) vào bản clone trên máy công ty — USB, nội bộ, zip đều được.

3. **Trên máy công ty**: không cần Hub nếu thư mục trên đã có `config.json` + weights. Từ bản cập nhật code này, nếu **không** đặt `SENTENCE_TRANSFORMER_MODEL`, runtime sẽ **tự load** đường dẫn repo `embedding_models/sentence-transformers/all-MiniLM-L6-v2`. Hoặc đặt rõ:
   ```powershell
   $env:SENTENCE_TRANSFORMER_MODEL = "D:\duong-dan\clangd-graph-rag\embedding_models\sentence-transformers\all-MiniLM-L6-v2"
   ```

4. Giữ **cùng một model** khi build FAISS/Chroma/JSONL và khi query (mặc định 384 chiều).

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
