---
name: chroma-query-graph-traverse
description: >-
  Query Chroma (natural language) to pick seed symbols, then expand a CALLS subgraph from code_graph.yaml
  and attach Chroma documents — graph-shaped JSON (nodes + edges). Use when the user asks to search Chroma
  for functions then graph traversal, NL seed + call graph, or hybrid semantic-to-structural slice.
---

# chroma-query-graph-traverse

**Scope:** **Chroma-first** — dùng **`collection.query`** với câu tiếng Việt / tiếng Anh để lấy vài **node hạt** (thường FUNCTION/METHOD), rồi **traverse** trên **`code_graph.yaml`** (cùng semantics `query_code_graph.py traverse`) và **gộp** neighborhood; output có **`edges`** (đồ thị) + **`nodes`** (graph node + payload Chroma).

**Khác** skill **graph-traverse-chroma**: skill kia là **đã biết id / tên hàm** → traverse → Chroma `get`. Skill này là **chưa biết id** → Chroma semantic → merge traverse.

## Prerequisites

Giống **embed-graph-vectordb** / **graph-traverse-chroma**: `code_graph.yaml`, thư mục **`chroma_db`** từ `export_graph_rag_chunks --backend chroma`, cùng **`SENTENCE_TRANSFORMER_*`** lúc build và query.

## CLI (cùng một script)

```bash
python standalone_tools/chroma_graph_neighborhood.py <project>/.clangd-graph-rag/code_graph.yaml \
  --chroma <project>/.clangd-graph-rag/rag_chroma \
  --chroma-seed-query "xử lý buffer overflow" \
  --seed-k 5 --depth 2 --direction both --edge-type CALLS \
  --merge-cap 600
```

| Flag | Ý nghĩa |
|------|--------|
| `--chroma-seed-query` | Câu NL; Chroma trả **top** kết quả toàn collection |
| `--seed-k` | Số **hạt** sau lọc label (mặc định 5) |
| `--seed-fetch` | Lấy dư trước khi lọc `--seed-labels` (mặc định 24) |
| `--seed-labels` | Mặc định `FUNCTION,METHOD`; để **trống** (`""`) nếu không lọc theo label |
| `--merge-cap` | Giới hạn số **node** khác nhau khi gộp nhiều traverse |
| `--depth` / `--direction` / `--edge-type` | Giống `query_code_graph.py traverse` |

JSON stdout gồm **`traverse`** (tóm tắt), **`edges`** (cạnh CALLS…), **`nodes`** (mỗi phần tử: `id`, `graph`, `chroma`), tùy chọn **`--semantic`** để top‑k NL **trong** tập id đã gộp.

## Khi nào dùng skill nào

| Mục đích | Skill |
|----------|--------|
| Chỉ vector toàn graph (không merge traverse) | **search-graph-semantic** |
| Đã có **node id** / search struct → traverse | **graph-traverse-chroma** |
| **Chroma NL →** subgraph hàm **dạng graph** | **chroma-query-graph-traverse** (file này) |
| Build Chroma | **embed-graph-vectordb** |
| Chưa chắc | **query-graph-code** |

## Related skills

- **graph-traverse-chroma** — start id cố định → traverse → Chroma.
- **embed-graph-vectordb** — tạo `chroma_db`.
- **search-graph-semantic** — gợi ý API Chroma / FAISS / JSONL.
- **search-graph-export** — `traverse` / `search` thuần struct trên YAML.

Reference: [docs/graph_to_vector_rag.md](../../../docs/graph_to_vector_rag.md).
