#!/usr/bin/env python3
"""
One-command local setup for clangd-graph-rag (default: no Neo4j).

This script is designed for VSCode+Cline onboarding:
  python standalone_tools/setup_clangd_graph.py

Optional:
  python standalone_tools/setup_clangd_graph.py --compile-commands D:/proj/compile_commands.json
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str]) -> int:
    print("+", " ".join(cmd))
    return subprocess.call(cmd)


def _find_windows_clangd_indexer() -> str | None:
    candidates = [
        r"C:\Program Files\LLVM\bin\clangd-indexer.exe",
        r"C:\Program Files\clangd\bin\clangd-indexer.exe",
    ]
    for p in candidates:
        if Path(p).is_file():
            return p
    return None


def _ensure_clangd_indexer() -> int:
    exe = shutil.which("clangd-indexer")
    if exe:
        print(f"Found clangd-indexer: {exe}")
        return 0

    print("clangd-indexer not found in PATH. Trying to install...")
    if sys.platform.startswith("win"):
        winget = shutil.which("winget")
        if winget:
            # Try dedicated clangd package first, then LLVM full package.
            rc = _run([winget, "install", "-e", "--id", "LLVM.clangd"])
            if rc != 0:
                rc = _run([winget, "install", "-e", "--id", "LLVM.LLVM"])
            # Re-check PATH + common install locations.
            exe = shutil.which("clangd-indexer") or _find_windows_clangd_indexer()
            if exe:
                print(f"clangd-indexer is available at: {exe}")
                if str(exe).lower().endswith(".exe") and "\\" in str(exe):
                    print("Tip: add LLVM bin to PATH if command is still not recognized in new shells.")
                return 0
        print("Could not auto-install clangd-indexer on Windows.")
        print("Please install clangd indexing tools from: https://github.com/clangd/clangd/releases")
        return 2

    if sys.platform.startswith("linux"):
        if shutil.which("apt-get"):
            # On Debian/Ubuntu, clangd-indexer may come from clang-tools package.
            rc = _run(["sudo", "apt-get", "update"])
            if rc == 0:
                rc = _run(["sudo", "apt-get", "install", "-y", "clangd", "clang-tools"])
            if rc == 0 and shutil.which("clangd-indexer"):
                print(f"Found clangd-indexer: {shutil.which('clangd-indexer')}")
                return 0
        print("Could not auto-install clangd-indexer on Linux.")
        print("Install clangd/clang-tools from distro packages or clangd release binaries.")
        return 2

    print("Unsupported OS for auto-install clangd-indexer. Please install manually.")
    return 2


def _confirm_yes_no(prompt: str, *, default_yes: bool = True) -> bool:
    """Prompt user in interactive terminal, fallback to default in non-interactive mode."""
    if not sys.stdin.isatty():
        return default_yes
    suffix = "[Y/n]" if default_yes else "[y/N]"
    answer = input(f"{prompt} {suffix} ").strip().lower()
    if not answer:
        return default_yes
    return answer in {"y", "yes"}


def _prompt_compile_commands_path() -> Path | None:
    """Ask user if they want to provide compile_commands.json path now."""
    if not sys.stdin.isatty():
        # Non-interactive runs (agents/CI) should never block on input.
        return None
    if not _confirm_yes_no("Do you want to provide compile_commands.json path now?", default_yes=True):
        return None
    try:
        raw = input("Enter path to compile_commands.json (leave empty to skip): ").strip()
    except EOFError:
        return None
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def main() -> int:
    p = argparse.ArgumentParser(description="Setup clangd-graph-rag for no-Neo4j workflow")
    p.add_argument(
        "--compile-commands",
        type=Path,
        default=None,
        help="Optional path to compile_commands.json to persist into .env.clangd_graph",
    )
    p.add_argument(
        "--skip-pip",
        action="store_true",
        help="Skip dependency installation",
    )
    p.add_argument(
        "--with-neo4j",
        action="store_true",
        help="Also install Neo4j extras (requirements-neo4j.txt)",
    )
    p.add_argument(
        "--skip-clangd-indexer",
        action="store_true",
        help="Skip clangd-indexer availability check/installation",
    )
    args = p.parse_args()

    repo = Path(__file__).resolve().parents[1]
    req_core = repo / "requirements-core.txt"
    req_neo4j = repo / "requirements-neo4j.txt"
    if not req_core.is_file():
        print(f"requirements-core.txt not found: {req_core}", file=sys.stderr)
        return 2

    if not args.skip_pip:
        rc = _run([sys.executable, "-m", "pip", "install", "-r", str(req_core)])
        if rc != 0:
            return rc
        if args.with_neo4j:
            if not req_neo4j.is_file():
                print(f"requirements-neo4j.txt not found: {req_neo4j}", file=sys.stderr)
                return 2
            rc = _run([sys.executable, "-m", "pip", "install", "-r", str(req_neo4j)])
            if rc != 0:
                return rc

    if not args.skip_clangd_indexer:
        rc = _ensure_clangd_indexer()
        if rc != 0:
            return rc

    cc = args.compile_commands
    if cc is None:
        cc = _prompt_compile_commands_path()
    if cc is not None:
        cc = cc.expanduser().resolve()
        if not cc.is_file():
            print(f"compile_commands.json not found: {cc}", file=sys.stderr)
            return 2
        env_file = repo / ".env.clangd_graph"
        env_file.write_text(
            f'COMPILE_COMMANDS_PATH="{str(cc).replace(chr(92), "/")}"\n',
            encoding="utf-8",
        )
        os.environ["COMPILE_COMMANDS_PATH"] = str(cc)
        print(f"Wrote {env_file}")
        print("COMPILE_COMMANDS_PATH is set for this process.")

    print("\nSetup complete (Neo4j not installed).")
    print("Next steps:")
    print("1) Generate clangd index YAML if you do not have one yet.")
    print("2) Export graph:")
    print(
        "   python standalone_tools/export_code_graph_json.py <index.yaml> <project_path> -o code_graph.yaml"
    )
    print("3) Run API:")
    print("   python -m code_graph_api code_graph.yaml --host 127.0.0.1 --port 8090")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
