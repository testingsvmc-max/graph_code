---
name: visualize-graph-html
description: >-
  Export code_graph.yaml/json or graph.db to interactive HTML: D3 force layout (graph_d3-style via
  export_code_graph_d3_html.py) or vis-network (export_code_graph_html.py / crg_db_to_vis_html.py). Use when
  the user asks for graph visualization, graph_d3, D3 HTML, vis.js, see nodes, or call graph in browser without Neo4j.
---

# visualize-graph-html

Turn a **structural** graph artifact into **one self-contained `.html`** (open with `file://` in Chrome/Edge/Firefox).

## D3 (giống `graph_d3.html`) — khuyến nghị khi cần layout D3 + CALL liên file (cam)

**Không** cần gói `code_review_graph`. Từ **YAML/JSON** export:

```powershell
python standalone_tools/export_code_graph_d3_html.py `
  D:\proj\.clangd-graph-rag\code_graph.yaml `
  -o D:\proj\.clangd-graph-rag\graph_d3.html
```

Cùng tùy chọn lọc như vis: `--edge-types CALLS`, `--max-nodes 800`, `--title "…"`.

### Legacy: D3 từ `graph.db` + gói ngoài

`standalone_tools/crg_visualize_full_d3.py` + `crg_enhance_d3_html.py` — chỉ khi đã cài visualize helpers (`code_review_graph`); thường không có trên máy sạch.

---

## vis-network (tuỳ chọn)

| Artifact | Tool | Notes |
|----------|------|--------|
| **`code_graph.yaml` / `.json`** | `standalone_tools/export_code_graph_html.py` | vis-network |
| **`graph.db`** (SQLite) | `standalone_tools/crg_db_to_vis_html.py` | cùng engine vis |

### 1) From YAML or JSON export

```bash
python standalone_tools/export_code_graph_html.py \
  path/to/code_graph.yaml \
  -o path/to/code_graph_vis.html
```

**PowerShell (Windows):**

```powershell
python standalone_tools/export_code_graph_html.py `
  D:\proj\.clangd-graph-rag\code_graph.yaml `
  -o D:\proj\.clangd-graph-rag\code_graph_vis.html
```

### Optional flags (vis)

- **`--edge-types`** — comma list to reduce clutter, e.g. `CALLS`, `CALLS,INCLUDES`, `INCLUDES` (default: all types in file).
- **`--max-nodes N`** — cap nodes (keeps endpoints of selected edges first when trimming).
- **`--title`** — browser tab title (default: stem of input file).

## 2) From SQLite `graph.db`

```powershell
python standalone_tools/crg_db_to_vis_html.py `
  --db "D:\proj\.clangd-graph-rag\graph.db" `
  -o "D:\proj\.clangd-graph-rag\graph_vis.html"
```

### Useful flags

- **`--edge-kinds`** — default `CALLS,IMPORTS_FROM,INHERITS`; use `CALLS` only for call-only view.
- **`--max-nodes`** — limit graph size for huge DBs.
- **`--views`** — install SQL helper views inside the DB (`v_calls`, …).
- **`--stub-missing-call-targets`** / **`--inter-file-full`** — see script `--help` (larger HTML when stubs enabled).

## 3) Open the result

Double-click the `.html` or:

```powershell
start msedge "D:\proj\.clangd-graph-rag\code_graph_vis.html"
```

No local server required; **offline** use works if the machine has loaded the page once while online (CDN scripts), or use a browser that already cached the library.

## Related skills

- **build-graph-code** — produce `code_graph.yaml` + optional `graph.db`.
- **search-graph-export** — CLI query on YAML/JSON.
- **search-graph-db** — CLI query on `graph.db`.
- **query-graph-code** — router when unsure which artifact to use.

Implementation: [code_graph_export/d3_code_graph_html.py](../../../code_graph_export/d3_code_graph_html.py), [code_graph_export/html_report.py](../../../code_graph_export/html_report.py).
