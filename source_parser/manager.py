#!/usr/bin/env python3
"""
Main entry point for orchestrating the compilation parsing and caching.
"""
import os
import logging
import gc
import sys
import git
import shutil
import subprocess
import tempfile
import clang.cindex
from pathlib import Path
from typing import Optional, List, Set, Tuple, Dict, Any

from git_manager import get_git_repo, resolve_commit_ref_to_hash
from utils import FileExtensions
from .span_cache import CacheManager
from .orchestrator import ParallelOrchestrator
from .types import SourceSpan, MacroSpan, TypeAliasSpan, IncludeRelation

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def _libclang_windows_help_message() -> str:
    return (
        "python-clang could not load libclang.dll on Windows.\n"
        "  1) Install LLVM for Windows (includes libclang.dll), e.g. "
        "https://github.com/llvm/llvm-project/releases (Windows installer) or: winget install LLVM.LLVM\n"
        "  2) Set either environment variable before running:\n"
        "       LIBCLANG_LIBRARY_FILE = full path to libclang.dll "
        r"(e.g. C:\Program Files\LLVM\bin\libclang.dll)" "\n"
        "       LIBCLANG_PATH = directory containing libclang.dll (e.g. C:\\Program Files\\LLVM\\bin)\n"
        "  Restart the terminal/IDE after installing LLVM so PATH is picked up."
    )


def _iter_windows_libclang_dll_candidates():
    """Typical install locations for libclang.dll on Windows."""
    seen = set()
    w = shutil.which("libclang.dll")
    if w:
        p = Path(w).resolve()
        if p not in seen:
            seen.add(p)
            yield p
    llvm_home = os.environ.get("LLVM_INSTALL_DIR", "").strip()
    if llvm_home:
        p = (Path(llvm_home) / "bin" / "libclang.dll").resolve()
        if p not in seen and p.parent.is_dir():
            seen.add(p)
            yield p
    for key in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(key)
        if not base:
            continue
        p = (Path(base) / "LLVM" / "bin" / "libclang.dll").resolve()
        if p not in seen:
            seen.add(p)
            yield p
    p = Path(r"C:\LLVM\bin\libclang.dll")
    if p not in seen:
        seen.add(p)
        yield p


def _try_configure_libclang_windows() -> bool:
    """Point clang.cindex at the first usable libclang.dll. Returns True if configuration succeeded."""
    if os.name != "nt":
        return False
    for dll in _iter_windows_libclang_dll_candidates():
        if not dll.is_file():
            continue
        try:
            clang.cindex.Config.set_library_file(str(dll))
            logger.info("Using libclang.dll (auto-discovered): %s", dll)
            return True
        except Exception as exc:
            logger.debug("libclang candidate %s: %s", dll, exc)
    return False


def _looks_like_missing_libclang_dll(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "libclang" in msg or "libclang.dll" in msg or "could not find module" in msg


def _configure_libclang_from_env() -> None:
    """Allow Windows/local setups to point python-clang to libclang explicitly."""
    lib_file = os.getenv("LIBCLANG_LIBRARY_FILE")
    if lib_file and os.path.isfile(lib_file):
        try:
            clang.cindex.Config.set_library_file(lib_file)
            logger.info("Using libclang from LIBCLANG_LIBRARY_FILE=%s", lib_file)
            return
        except Exception as exc:
            logger.warning("Failed to set libclang library file '%s': %s", lib_file, exc)
    lib_path = os.getenv("LIBCLANG_PATH")
    if lib_path and os.path.isdir(lib_path):
        try:
            clang.cindex.Config.set_library_path(lib_path)
            logger.info("Using libclang from LIBCLANG_PATH=%s", lib_path)
            return
        except Exception as exc:
            logger.warning("Failed to set libclang library path '%s': %s", lib_path, exc)
    if os.name == "nt" and not lib_file and not lib_path:
        _try_configure_libclang_windows()


_configure_libclang_from_env()

class CompilationManager:
    """Manages parsing, caching, and parallel execution logic."""

    def __init__(
        self,
        project_path: str = ".",
        compile_commands_path: Optional[str] = None,
        compile_commands_remap_from: Optional[str] = None,
        compile_commands_remap_to: Optional[str] = None,
    ):
        self.project_path = os.path.abspath(project_path)
        self.repo = get_git_repo(self.project_path)
        
        # Identity-related state
        self.source_spans: Dict[str, Dict[str, SourceSpan]] = {}
        self.include_relations: Set[IncludeRelation] = set()
        self.static_call_relations: Set[Tuple[str, str]] = set()
        self.type_alias_spans: Dict[str, TypeAliasSpan] = {}
        self.macro_spans: Dict[str, MacroSpan] = {}

        # Cache configuration
        cache_dir = os.path.join(self.project_path, ".cache")
        project_name = os.path.basename(self.project_path)
        self.cache_manager = CacheManager(cache_dir, project_name)

        # Compilation database resolution
        if compile_commands_path:
            self.compile_commands_path = compile_commands_path
        else:
            inferred = os.path.join(self.project_path, 'compile_commands.json')
            if not os.path.exists(inferred):
                raise ValueError("compile_commands.json not found. Use --compile-commands to specify.")
            self.compile_commands_path = inferred

        if compile_commands_remap_from and str(compile_commands_remap_from).strip():
            from index_path_remap import materialize_remapped_compile_commands

            to = compile_commands_remap_to or self.project_path
            _td, jp = materialize_remapped_compile_commands(
                self.compile_commands_path,
                str(compile_commands_remap_from).strip().strip('"'),
                Path(to).expanduser().resolve(),
            )
            self.compile_commands_path = jp

        # Late-initialized components
        self._orchestrator = ParallelOrchestrator()
        self._db = None
        self._clang_include_path = self._get_clang_resource_dir()

    def _get_clang_resource_dir(self):
        try:
            res = subprocess.check_output(['clang', '-print-resource-dir'], text=True).strip()
            return os.path.join(res, 'include')
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def _load_into_self(self, data: Dict[str, Any]):
        self.source_spans = data.get("source_spans", {})
        self.include_relations = data.get("include_relations", set())
        self.static_call_relations = data.get("static_call_relations", set())
        self.type_alias_spans = data.get("type_alias_spans", {})
        self.macro_spans = data.get("macro_spans", {})

    def _perform_parsing(self, files_to_parse: List[str], num_workers: int) -> Dict[str, Any]:
        if not files_to_parse:
            return {"source_spans": {}, "include_relations": set(), "static_call_relations": set(), "type_alias_spans": {}, "macro_spans": {}}

        # Local resolve of the DB directory
        p = Path(self.compile_commands_path).expanduser().resolve()
        if p.is_dir(): db_dir = str(p)
        elif p.is_file():
            if p.name == "compile_commands.json": db_dir = str(p.parent)
            else:
                tmp = tempfile.mkdtemp(prefix="clangdb_")
                shutil.copy(str(p), os.path.join(tmp, "compile_commands.json"))
                db_dir = tmp
        else: raise FileNotFoundError(self.compile_commands_path)

        # Build work items (loads libclang; Windows often needs LIBCLANG_* or LLVM on PATH)
        try:
            db = clang.cindex.CompilationDatabase.fromDirectory(db_dir)
        except Exception as exc:
            if os.name == "nt" and _looks_like_missing_libclang_dll(exc):
                if _try_configure_libclang_windows():
                    try:
                        db = clang.cindex.CompilationDatabase.fromDirectory(db_dir)
                    except Exception as exc2:
                        raise RuntimeError(_libclang_windows_help_message()) from exc2
                else:
                    raise RuntimeError(_libclang_windows_help_message()) from exc
            raise
        source_exts = FileExtensions.ALL_C_CPP
        source_files = [f for f in files_to_parse if f.lower().endswith(source_exts)]
        
        def get_realpath(cmd):
            f = cmd.filename
            if not os.path.isabs(f): f = os.path.join(cmd.directory, f)
            return os.path.realpath(f)

        cmd_files = {get_realpath(c): c for c in db.getAllCompileCommands()}
        compile_entries = [
            {'file': f, 'directory': cmd_files[f].directory, 'arguments': list(cmd_files[f].arguments)[1:]}
            for f in source_files if f in cmd_files
        ]

        logger.info(f"Parsing {len(compile_entries)} TUs with clang using {num_workers} workers...")
        init_args = {'project_path': self.project_path, 'clang_include_path': self._clang_include_path}
        
        results = self._orchestrator.run_parallel_parse(compile_entries, num_workers, "Parsing TUs", init_args)
        gc.collect()
        return results

    def parse_folder(self, folder_path: str, num_workers: int, new_commit: str = None):
        """Resolves a folder to a file list and delegates to parse_files."""
        if self.repo:
            final_hash = new_commit
            if not final_hash:
                final_hash = self.repo.head.object.hexsha
            else:
                final_hash = resolve_commit_ref_to_hash(self.repo, final_hash)
            
            all_files_str = self.repo.git.ls_tree('-r', '--name-only', final_hash)
            all_files_in_commit = [
                os.path.join(self.project_path, f) for f in all_files_str.split('\n')
                if f.lower().endswith(FileExtensions.ALL_C_CPP)
            ]
            self.parse_files(all_files_in_commit, num_workers, new_commit=final_hash)
            return

        logger.warning("Not a Git repository. Using mtime-based caching.")
        all_files = []
        for root, _, fs in os.walk(folder_path):
            for f in fs:
                if f.lower().endswith(FileExtensions.ALL_C_CPP):
                    all_files.append(os.path.join(root, f))
        self.parse_files(all_files, num_workers)

    def parse_files(self, file_list: List[str], num_workers: int, new_commit: str = None, old_commit: str = None):
        """Central method for parsing a list of files with cache support."""
        if self.repo and new_commit:
            new_hash = resolve_commit_ref_to_hash(self.repo, new_commit)
            old_hash = resolve_commit_ref_to_hash(self.repo, old_commit) if old_commit else None
            
            cached = self.cache_manager.find_and_load_git_cache(new_hash, old_hash)
            if cached:
                self._load_into_self(cached)
                return
            
            parsed = self._perform_parsing(file_list, num_workers)
            self.cache_manager.save_git_cache(parsed, new_hash, old_hash)
            self._load_into_self(parsed)
            return

        cached = self.cache_manager.find_and_load_mtime_cache(file_list)
        if cached:
            self._load_into_self(cached)
            return

        parsed = self._perform_parsing(file_list, num_workers)
        self.cache_manager.save_mtime_cache(parsed, file_list)
        self._load_into_self(parsed)

    def get_source_spans(self): return self.source_spans
    def get_include_relations(self): return self.include_relations
    def get_static_call_relations(self): return self.static_call_relations
    def get_type_alias_spans(self): return self.type_alias_spans
    def get_macro_spans(self): return self.macro_spans
