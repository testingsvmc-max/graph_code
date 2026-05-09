# clangd-graph-rag evaluation helpers

This folder mirrors the *idea* of GitNexus’s `eval/` tree in a narrower scope:

| GitNexus (`GitNexus-main/eval/`) | This repo (`clangd-graph-rag/eval/`) |
|----------------------------------|---------------------------------------|
| `run_eval.py` — SWE-bench agent runs, Docker, model × mode matrix | `run_graph_eval.py` — **deterministic graph quality metrics** on your export |
| Agent metrics (`gitnexus_metrics`, cost, tool calls) | Structural metrics: node/edge counts, **`CALLS` cross-file ratio**, function `file_path` coverage |
| `eval-server` — HTTP tool server for agents | Not duplicated here; use `python -m code_graph_api` or `standalone_tools/crg_db_query.py` for interactive query |

## Run graph eval

From the repository root:

```bash
python eval/run_graph_eval.py --yaml path/to/code_graph.yaml
python eval/run_graph_eval.py --db path/to/graph.db --json-out eval/last_metrics.json
```

Optional CI gates (exit code `2` on failure):

```bash
python eval/run_graph_eval.py --yaml path/to/code_graph.yaml --min-cross-file-calls 100 --min-function-file-path-coverage 0.5
```

## Tests

Graph metric helpers are covered by pytest:

```bash
python -m pytest tests/test_graph_eval.py
```
