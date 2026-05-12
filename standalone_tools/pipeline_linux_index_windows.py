#!/usr/bin/env python3
"""
End-to-end pipeline: Linux-produced ``index.yaml`` + ``compile_commands.json`` + Windows source tree.

Maps ``/home/...`` paths to your Windows checkout (same as ``--index-source-root`` elsewhere), then optionally:

1. **Neo4j** — full ``graph_builder`` (graph DB + optional ``--generate-summary`` for embeddings on nodes)
2. **Export** — ``code_graph.yaml`` / JSON (offline graph file)
3. **SQLite** — ``graph.db`` for ``crg_db_query`` / tooling
4. **FAISS** — vector index directory (requires ``pip install -r requirements-faiss.txt``)

Example::

    python standalone_tools/pipeline_linux_index_windows.py ^
      D:\\artifacts\\index.yaml D:\\src\\myrepo ^
      --compile-commands D:\\src\\myrepo\\compile_commands.json ^
      --infer-index-source-root-from-compile-commands ^
      --export-yaml --sqlite --faiss-out D:\\src\\myrepo\\.clangd-graph-rag\\faiss_index ^
      -- --generate-summary

Or pass an explicit Linux root::

    python standalone_tools/pipeline_linux_index_windows.py ^
      D:\\artifacts\\index.yaml D:\\src\\myrepo ^
      --compile-commands D:\\src\\myrepo\\compile_commands.json ^
      --index-source-root /home/dpi/build_server/android/myproject ^
      --export-yaml --sqlite --faiss-out D:\\src\\myrepo\\.clangd-graph-rag\\faiss_index ^
      -- --generate-summary

Arguments after ``--`` are forwarded to ``graph_builder.py`` (Neo4j phase only).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _split_at_ddash(argv: list[str]) -> tuple[list[str], list[str]]:
    if "--" in argv:
        i = argv.index("--")
        return argv[:i], argv[i + 1 :]
    return argv, []


def main() -> int:
    argv, neo_extra = _split_at_ddash(sys.argv[1:])

    p = argparse.ArgumentParser(
        description="Linux YAML + compile_commands + Windows source to Neo4j and/or export SQLite/FAISS."
    )
    p.add_argument("index_file", type=Path, help="Clangd index YAML (from Linux)")
    p.add_argument("project_path", type=Path, help="Windows checkout root (same layout as Linux tree)")
    p.add_argument(
        "--compile-commands",
        type=Path,
        required=True,
        help="compile_commands.json (may still list /home/... paths; it will be remapped)",
    )
    root = p.add_mutually_exclusive_group(required=True)
    root.add_argument(
        "--index-source-root",
        type=str,
        default=None,
        metavar="POSIX_DIR",
        help="Linux absolute root as in YAML FileURI / JSON paths, e.g. /home/dpi/build/.../repo",
    )
    root.add_argument(
        "--infer-index-source-root-from-compile-commands",
        action="store_true",
        help="Infer Linux root from compile_commands directory/file paths (longest common prefix).",
    )
    p.add_argument(
        "--local-source-root",
        type=str,
        default=None,
        metavar="DIR",
        help="Optional Windows root if it differs from project_path",
    )
    p.add_argument(
        "--skip-neo4j",
        action="store_true",
        help="Skip graph_builder; only run export/SQLite/FAISS (Neo4j must already match this mapping).",
    )
    p.add_argument(
        "--export-yaml",
        nargs="?",
        const="DEFAULT",
        default=None,
        metavar="PATH",
        help="Write code graph YAML. Use alone for default path, or pass a file path.",
    )
    p.add_argument("--sqlite", action="store_true", help="After export, write SQLite graph.db")
    p.add_argument(
        "--sqlite-out",
        type=Path,
        default=None,
        help="SQLite path (default: <project>/.clangd-graph-rag/graph.db)",
    )
    p.add_argument(
        "--faiss-out",
        type=Path,
        default=None,
        metavar="DIR",
        help="Build FAISS index under this directory (runs after export)",
    )
    args = p.parse_args(argv)

    index_f = args.index_file.expanduser().resolve()
    proj = args.project_path.expanduser().resolve()
    cc = args.compile_commands.expanduser().resolve()
    if not index_f.is_file():
        print(f"Index not found: {index_f}", file=sys.stderr)
        return 2
    if not proj.is_dir():
        print(f"Project not a directory: {proj}", file=sys.stderr)
        return 2
    if not cc.is_file():
        print(f"compile_commands.json not found: {cc}", file=sys.stderr)
        return 2

    if args.infer_index_source_root_from_compile_commands:
        from index_path_remap import infer_index_source_root_from_compile_commands_path

        try:
            idx_root = infer_index_source_root_from_compile_commands_path(str(cc))
        except (OSError, ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
            print(f"Infer index root failed: {exc}", file=sys.stderr)
            return 2
        print(f"Inferred --index-source-root: {idx_root}", file=sys.stderr)
    else:
        idx_root = str(args.index_source_root).strip().strip('"')
    local_root = str(args.local_source_root).strip() if args.local_source_root else None

    neo_cmd = [
        sys.executable,
        str(_ROOT / "graph_builder.py"),
        str(index_f),
        str(proj),
        "--compile-commands",
        str(cc),
        "--index-source-root",
        idx_root,
    ]
    if local_root:
        neo_cmd.extend(["--local-source-root", local_root])
    neo_cmd.extend(neo_extra)

    if not args.skip_neo4j:
        print("+", " ".join(neo_cmd))
        rc = subprocess.call(neo_cmd, cwd=str(_ROOT))
        if rc != 0:
            return rc

    need_export = args.export_yaml is not None or args.sqlite or args.faiss_out is not None
    if not need_export:
        return 0

    if args.export_yaml is None or args.export_yaml == "DEFAULT":
        export_path = proj / ".clangd-graph-rag" / "code_graph.yaml"
    else:
        export_path = Path(args.export_yaml).expanduser().resolve()
    export_path.parent.mkdir(parents=True, exist_ok=True)

    exp_cmd = [
        sys.executable,
        str(_ROOT / "standalone_tools" / "export_code_graph_json.py"),
        str(index_f),
        str(proj),
        "--compile-commands",
        str(cc),
        "--index-source-root",
        idx_root,
        "-o",
        str(export_path),
        "--format",
        "yaml",
    ]
    if local_root:
        exp_cmd.extend(["--local-source-root", local_root])

    print("+", " ".join(exp_cmd))
    rc = subprocess.call(exp_cmd, cwd=str(_ROOT))
    if rc != 0:
        return rc

    if args.sqlite:
        from code_graph_api.store import load_graph_dict
        from code_graph_export.sqlite_db import write_graph_sqlite

        db_path = (
            args.sqlite_out.expanduser().resolve()
            if args.sqlite_out
            else (proj / ".clangd-graph-rag" / "graph.db").resolve()
        )
        db_path.parent.mkdir(parents=True, exist_ok=True)
        graph = load_graph_dict(str(export_path))
        write_graph_sqlite(graph, db_path)
        print(f"SQLite OK: {db_path}")

    if args.faiss_out is not None:
        faiss_dir = args.faiss_out.expanduser().resolve()
        faiss_dir.mkdir(parents=True, exist_ok=True)
        faiss_cmd = [
            sys.executable,
            str(_ROOT / "standalone_tools" / "faiss_code_graph_index.py"),
            "build",
            "--graph",
            str(export_path),
            "--out-dir",
            str(faiss_dir),
        ]
        print("+", " ".join(faiss_cmd))
        rc = subprocess.call(faiss_cmd, cwd=str(_ROOT))
        if rc != 0:
            return rc
        print(f"FAISS OK: {faiss_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
