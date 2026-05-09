#!/usr/bin/env python3
"""
Build a file-level include graph from C/C++ sources using only regex (no libclang).

Use when compile_commands / clangd-indexer / libclang are not available yet.
Nodes: FILE; edges: INCLUDES (resolved when the included file exists under --root).

Output is JSON by default, or YAML if -o ends with .yaml/.yml or --format yaml.

Example:
  python standalone_tools/export_include_graph_json.py \\
    D:\\GraphCode\\android-wpa_supplicant-master\\android-wpa_supplicant-master\\wpa_supplicant \\
    -o D:\\GraphCode\\android-wpa_supplicant-master\\include_graph.yaml
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_INCLUDE_RE = re.compile(
    r'^\s*#\s*include\s+(?:"([^"]+)"|<([^>]+)>)',
    re.MULTILINE,
)


def discover_files(root: Path, extensions: frozenset[str]) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in extensions:
            out.append(p)
    return sorted(out)


def resolve_include(from_file: Path, spec: str, root: Path, index: dict[str, Path]) -> Path | None:
    """Try "" and dirname-relative, then shallow search by basename under root."""
    cand = (from_file.parent / spec).resolve()
    try:
        cand.relative_to(root)
        if cand.is_file():
            return cand
    except ValueError:
        pass
    base = Path(spec).name
    if base in index:
        return index[base]
    # common: include "utils/common.h" from src/foo -> try root / spec
    r = (root / spec).resolve()
    if r.is_file():
        try:
            r.relative_to(root)
            return r
        except ValueError:
            return None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Export include-only graph as JSON or YAML (no Clang/clangd).")
    parser.add_argument("source_root", type=Path, help="Root directory to scan (e.g. wpa_supplicant/)")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output path (.json or .yaml/.yml)")
    parser.add_argument(
        "--format",
        choices=("json", "yaml", "auto"),
        default="auto",
        help="auto: use .yaml/.yml suffix for YAML, else JSON",
    )
    parser.add_argument(
        "--extensions",
        default=".c,.h,.cc,.cpp,.hpp",
        help="Comma-separated extensions to scan (default: .c,.h,.cc,.cpp,.hpp)",
    )
    args = parser.parse_args()
    root = args.source_root.resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 1

    exts = frozenset(e.strip().lower() for e in args.extensions.split(",") if e.strip())
    files = discover_files(root, exts)
    # basename -> first path (ambiguous headers may map wrong; good enough for exploration)
    by_name: dict[str, Path] = {}
    for f in files:
        by_name.setdefault(f.name, f)

    rel = lambda p: str(p.resolve().relative_to(root)).replace("\\", "/")
    nodes: list[dict] = [{"id": "__PROJECT__", "labels": ["PROJECT"], "properties": {"root": str(root)}}]
    edges: list[dict] = []
    seen_paths: set[str] = set()

    for f in files:
        rp = rel(f)
        if rp not in seen_paths:
            seen_paths.add(rp)
            nodes.append({"id": f"file:{rp}", "labels": ["FILE"], "properties": {"path": rp, "name": f.name}})
        text = f.read_text(encoding="utf-8", errors="replace")
        for m in _INCLUDE_RE.finditer(text):
            spec = m.group(1) or m.group(2)
            if not spec:
                continue
            tgt = resolve_include(f, spec, root, by_name)
            if tgt is None or not tgt.is_file():
                continue
            tr = rel(tgt)
            if tr not in seen_paths:
                seen_paths.add(tr)
                nodes.append({"id": f"file:{tr}", "labels": ["FILE"], "properties": {"path": tr, "name": tgt.name}})
            edges.append({"type": "INCLUDES", "src": f"file:{rp}", "dst": f"file:{tr}", "properties": {}})

    graph = {
        "meta": {
            "mode": "regex_include_graph",
            "source_root": str(root),
            "file_count": len(seen_paths),
            "edge_counts_by_type": {"INCLUDES": len(edges)},
        },
        "nodes": nodes,
        "edges": edges,
    }
    out = str(args.output.resolve())
    fmt = args.format
    if fmt == "auto":
        fmt = "yaml" if out.lower().endswith((".yaml", ".yml")) else "json"

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "yaml":
        import yaml

        with open(out, "w", encoding="utf-8") as fh:
            yaml.safe_dump(graph, fh, default_flow_style=False, allow_unicode=True, sort_keys=False, width=120)
    else:
        args.output.write_text(json.dumps(graph, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out} ({len(nodes)} nodes, {len(edges)} INCLUDES edges, format={fmt})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
