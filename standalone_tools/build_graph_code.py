#!/usr/bin/env python3
"""
Build graph export for a project/code directory (no Neo4j).

Primary intent: Cline trigger command
  "Build graph code for this project or code directory"
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import input_params


def _is_tty() -> bool:
    return sys.stdin.isatty()


def _prompt(msg: str) -> str:
    try:
        return input(msg).strip()
    except EOFError:
        return ""


def _resolve_project_path(arg_project: str | None) -> Path:
    if arg_project:
        return Path(arg_project).expanduser().resolve()
    return Path.cwd().resolve()


def _resolve_index_file(arg_index: str | None) -> Path | None:
    if arg_index:
        p = Path(arg_index).expanduser().resolve()
        return p if p.is_file() else None
    env = os.getenv("CLANGD_INDEX_PATH", "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        if p.is_file():
            return p
    return None


def _resolve_compile_commands(arg_cc: str | None, project: Path) -> Path | None:
    if arg_cc:
        p = Path(arg_cc).expanduser().resolve()
        return p if p.is_file() else None
    env = os.getenv("COMPILE_COMMANDS_PATH", "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        if p.is_file():
            return p
    local = project / "compile_commands.json"
    if local.is_file():
        return local.resolve()
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Build code graph export (YAML/JSON) for a code directory.")
    parser.add_argument("project_path", nargs="?", default=None, help="Project/code directory (default: current directory)")
    parser.add_argument("--index-file", default=None, help="Path to clangd index YAML")
    parser.add_argument("--compile-commands", default=None, help="Path to compile_commands.json")
    parser.add_argument("-o", "--output", default=None, help="Output graph path (default: <project>/.clangd-graph-rag/code_graph.yaml)")
    parser.add_argument("--format", choices=("json", "yaml", "auto"), default="auto")
    parser.add_argument("--also-db", action="store_true", help="Also write SQLite graph.db after YAML/JSON export")
    parser.add_argument("--db-output", default=None, help="SQLite DB output path (default: <project>/.clangd-graph-rag/graph.db)")
    input_params.add_cross_machine_path_args(parser)
    args = parser.parse_args()

    project = _resolve_project_path(args.project_path)
    if not project.is_dir():
        print(f"Project directory not found: {project}", file=sys.stderr)
        return 2

    index_file = _resolve_index_file(args.index_file)
    if index_file is None and _is_tty():
        raw = _prompt("Enter path to clangd index YAML: ")
        if raw:
            p = Path(raw).expanduser().resolve()
            if p.is_file():
                index_file = p
    if index_file is None:
        print(
            "Missing clangd index YAML. Pass --index-file or set CLANGD_INDEX_PATH.",
            file=sys.stderr,
        )
        return 2

    compile_commands = _resolve_compile_commands(args.compile_commands, project)
    if compile_commands is None and _is_tty():
        raw = _prompt("Enter path to compile_commands.json (leave empty to skip): ")
        if raw:
            p = Path(raw).expanduser().resolve()
            if p.is_file():
                compile_commands = p
    if compile_commands is None:
        print(
            "Missing compile_commands.json. Put it under project root, pass --compile-commands, "
            "or set COMPILE_COMMANDS_PATH.",
            file=sys.stderr,
        )
        return 2

    if args.output:
        output = Path(args.output).expanduser().resolve()
    else:
        output = (project / ".clangd-graph-rag" / "code_graph.yaml").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str((Path(__file__).resolve().parents[0] / "export_code_graph_json.py")),
        str(index_file),
        str(project),
        "--compile-commands",
        str(compile_commands),
        "-o",
        str(output),
    ]
    if args.format != "auto":
        cmd.extend(["--format", args.format])
    if getattr(args, "index_source_root", None) and str(args.index_source_root).strip():
        cmd.extend(["--index-source-root", str(args.index_source_root).strip().strip('"')])
    if getattr(args, "local_source_root", None) and str(args.local_source_root).strip():
        cmd.extend(["--local-source-root", str(args.local_source_root).strip().strip('"')])

    print("+", " ".join(cmd))
    rc = subprocess.call(cmd)
    if rc != 0:
        return rc

    print(f"\nGraph build complete: {output}")
    if args.also_db:
        from code_graph_api.store import load_graph_dict
        from code_graph_export.sqlite_db import write_graph_sqlite

        if args.db_output:
            db_path = Path(args.db_output).expanduser().resolve()
        else:
            db_path = (project / ".clangd-graph-rag" / "graph.db").resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        graph = load_graph_dict(str(output))
        write_graph_sqlite(graph, db_path)
        print(f"SQLite graph DB complete: {db_path}")

    print("Query API:")
    print(f"  python -m code_graph_api \"{output}\" --host 127.0.0.1 --port 8090")
    if args.also_db:
        print("DB Query:")
        print(f"  python standalone_tools/crg_db_query.py --db \"{db_path}\" search \"auth\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
