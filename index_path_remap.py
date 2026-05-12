#!/usr/bin/env python3
"""
Remap clangd index FileURI values from one machine root to another.

Also remap ``compile_commands.json`` when it still contains the build-server
``directory`` / ``file`` / ``arguments`` paths (Linux) while the checkout lives
on Windows (e.g. ``D:\\...``). Optional: infer the Linux workspace root from
``compile_commands.json`` via ``infer_index_source_root_from_compile_commands_path``.

**Important on Windows:** never use ``Path(...).resolve()`` on a Linux path like
``/home/dpi/...`` — Python turns it into ``D:\\home\\dpi\\...``. Index-side roots
and paths decoded from ``file:///home/...`` URIs are handled as POSIX strings;
only the local root uses ``pathlib.Path.resolve()``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import posixpath
import shutil
import tempfile
import atexit
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse, unquote

logger = logging.getLogger(__name__)


def is_posix_style_index_root(root: str) -> bool:
    """True for Linux/CI roots like ``/home/dpi/...``; false for ``C:\\...`` or relative paths."""
    s = str(root).strip().replace("\\", "/")
    if not s.startswith("/"):
        return False
    # ``/D:/path`` (file URI style on Windows) — treat as native, not POSIX tree.
    if len(s) >= 3 and s[0] == "/" and s[2] == ":" and s[1].isalpha():
        return False
    return True


def normalize_index_root(root: str) -> str:
    """POSIX-style absolute root string for prefix checks (Linux build dir)."""
    s = str(root).strip().strip('"').replace("\\", "/").rstrip("/")
    if not s.startswith("/"):
        s = "/" + s.lstrip("/")
    return posixpath.normpath(s) or "/"


def normalize_native_index_root(root: str) -> str:
    """Native absolute root for same-OS index paths (e.g. two Windows checkouts)."""
    return os.path.normcase(os.path.abspath(str(root).strip().strip('"')))


def cache_key_index_root(index_source_root: str) -> str:
    """Stable string for pickle cache hashing."""
    if is_posix_style_index_root(index_source_root):
        return normalize_index_root(index_source_root)
    return normalize_native_index_root(index_source_root)


def path_from_file_uri_for_remap(file_uri: str) -> str:
    """
    Decode ``file_uri`` to a comparable path string.

    Linux index URIs (``file:///home/...``) stay as ``/home/...`` on Windows.
    Native Windows ``file:///D:/...`` and ``file://D:\\...`` become local absolutes.
    """
    parsed = urlparse(file_uri)
    if parsed.scheme and parsed.scheme != "file":
        return file_uri
    if parsed.netloc:
        p = unquote(parsed.netloc + parsed.path)
    else:
        p = unquote(parsed.path)
    # ``file:///D:/path`` → path ``/D:/path``
    if len(p) >= 3 and p[0] == "/" and p[2] == ":" and p[1].isalpha():
        p = p[1:]
    p_slash = p.replace("\\", "/")
    if p_slash.startswith("/") and not (len(p_slash) >= 3 and p_slash[2] == ":" and p_slash[1].isalpha()):
        return posixpath.normpath(p_slash)
    return os.path.abspath(os.path.normpath(p.replace("/", os.sep)))


def file_uri_to_abs_path(file_uri: str) -> str:
    """Decode a ``file:`` URI to a native absolute path (alias of remap decoder + abspath for locals)."""
    p = path_from_file_uri_for_remap(file_uri)
    if p.startswith("/") and os.name == "nt" and not (len(p) >= 3 and p[2] == ":" and p[1].isalpha()):
        # Linux-style path on Windows host: cannot map to one local path without remap context
        return p
    if p.startswith("/") and os.name != "nt":
        return os.path.abspath(p)
    return p


def abs_path_to_worker_file_uri(abs_path: str) -> str:
    """Match ``source_parser`` / node_parser: ``file://`` + ``os.path.abspath`` path."""
    p = os.path.abspath(os.path.normpath(abs_path))
    return "file://" + p


def make_index_root_to_local_uri_remapper(
    index_source_root: str,
    local_source_root: str,
) -> Callable[[str], str]:
    """
    Map ``file:`` URIs under ``index_source_root`` to URIs under ``local_source_root``.

    Supports Linux/POSIX index roots (``/home/dpi/...``) and native Windows roots
    (two checkouts on the same OS).
    """
    loc = Path(local_source_root).expanduser().resolve()
    posix_mode = is_posix_style_index_root(index_source_root)
    if posix_mode:
        idx_posix = normalize_index_root(index_source_root)
    else:
        idx_native = normalize_native_index_root(index_source_root)

    def remap(uri: str) -> str:
        if not uri or not uri.startswith("file:"):
            return uri
        p = path_from_file_uri_for_remap(uri)
        if posix_mode:
            pn = posixpath.normpath(p.replace("\\", "/"))
            if not pn.startswith("/"):
                return uri
            if pn != idx_posix and not pn.startswith(idx_posix + "/"):
                return uri
            rel = pn[len(idx_posix) :].lstrip("/")
        else:
            pn = os.path.normcase(os.path.normpath(p.replace("/", os.sep)))
            if not (pn == idx_native or pn.startswith(idx_native + os.sep)):
                return uri
            rel = os.path.relpath(pn, idx_native)
        new_abs = loc if rel in (".", "") else (loc / rel).resolve()
        try:
            new_abs.relative_to(loc)
        except ValueError:
            return uri
        return abs_path_to_worker_file_uri(str(new_abs))

    return remap


def remap_cache_suffix(index_source_root: str, local_source_root: str) -> str:
    """Short stable suffix for pickle cache when remapping is enabled."""
    idx_s = cache_key_index_root(index_source_root)
    loc_s = str(Path(local_source_root).expanduser().resolve())
    h = hashlib.sha256(f"{idx_s}|{loc_s}".encode("utf-8")).hexdigest()[:16]
    return f".remap_{h}.pkl"


def parse_optional_remap_args(
    index_source_root: Optional[str],
    local_source_root: Optional[str],
    project_path: Path,
) -> Optional[Callable[[str], str]]:
    if index_source_root is None or str(index_source_root).strip() == "":
        if local_source_root is not None and str(local_source_root).strip() != "":
            raise ValueError("--local-source-root requires --index-source-root")
        return None
    local_path = (
        Path(local_source_root).expanduser().resolve()
        if local_source_root and str(local_source_root).strip()
        else project_path.expanduser().resolve()
    )
    # Linux/CI path must stay a string — never Path(...).resolve() on Windows.
    idx_raw = str(index_source_root).strip().strip('"')
    return make_index_root_to_local_uri_remapper(idx_raw, str(local_path))


def compilation_remap_kwargs_from_args(args: Any) -> Dict[str, str]:
    """``**kwargs`` for ``CompilationManager`` when ``args.index_source_root`` is set."""
    idx = getattr(args, "index_source_root", None)
    if not idx or not str(idx).strip():
        return {}
    loc = getattr(args, "local_source_root", None)
    project_path = Path(args.project_path)
    to = (
        Path(loc).expanduser().resolve()
        if loc and str(loc).strip()
        else project_path.expanduser().resolve()
    )
    return {
        "compile_commands_remap_from": str(idx).strip().strip('"'),
        "compile_commands_remap_to": str(to),
    }


def longest_common_posix_path_prefix(paths: List[str]) -> str:
    """
    Longest common path prefix for a set of POSIX-style paths (``/a/b``, ``/a/c`` → ``/a``).

    Paths are normalized with ``posixpath.normpath``; drive-letter ``/D:/`` paths are ignored by callers.
    """
    norm: List[List[str]] = []
    for raw in paths:
        if not raw or not str(raw).strip():
            continue
        s = posixpath.normpath(str(raw).strip().replace("\\", "/")).rstrip("/")
        if not s or s == ".":
            continue
        parts = [p for p in s.split("/") if p]
        if parts:
            norm.append(parts)
    if not norm:
        return "/"
    if len(norm) == 1:
        return "/" + "/".join(norm[0])
    min_len = min(len(p) for p in norm)
    common: List[str] = []
    for i in range(min_len):
        seg = norm[0][i]
        if all(len(p) > i and p[i] == seg for p in norm):
            common.append(seg)
        else:
            break
    if not common:
        return "/"
    return "/" + "/".join(common)


def collect_path_hints_from_compile_commands_entries(entries: List[Dict[str, Any]]) -> List[str]:
    """Paths from ``directory`` and ``file`` fields (compile_commands schema)."""
    hints: List[str] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        d = e.get("directory")
        if isinstance(d, str) and d.strip():
            hints.append(d.strip())
        f = e.get("file")
        if isinstance(f, str) and f.strip():
            hints.append(f.strip())
    return hints


def infer_index_source_root_from_compile_commands_path(
    compile_commands_path: str,
    *,
    min_path_segments: int = 2,
) -> str:
    """
    Infer a Linux/POSIX workspace root from ``compile_commands.json`` (unique ``directory`` and ``file`` paths).

    Intended when the DB was produced on a build server: all paths share a long common prefix; that prefix
    is used as ``--index-source-root`` together with a Windows ``project_path`` / ``--local-source-root``.

    If paths are not POSIX-style (e.g. already Windows), raises ``ValueError``.
    """
    p = Path(compile_commands_path).expanduser().resolve()
    src = p / "compile_commands.json" if p.is_dir() else p
    if not src.is_file():
        raise FileNotFoundError(f"compile_commands.json not found: {src}")
    with open(src, encoding="utf-8", errors="replace") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("compile_commands.json must be a JSON array")
    hints = collect_path_hints_from_compile_commands_entries(data)
    posix_hints = [h for h in hints if is_posix_style_index_root(h)]
    if not posix_hints:
        raise ValueError(
            "No POSIX-style absolute paths (e.g. /home/...) found under directory/file in compile_commands.json; "
            "nothing to infer. Use explicit --index-source-root."
        )
    lcp = longest_common_posix_path_prefix(posix_hints)
    lcp = normalize_index_root(lcp)
    seg_count = len([x for x in lcp.strip("/").split("/") if x])
    if seg_count < min_path_segments:
        raise ValueError(
            f"Inferred root {lcp!r} is too short ({seg_count} segments < {min_path_segments}); "
            "paths in compile_commands may not share one workspace. Set --index-source-root explicitly."
        )
    return lcp


def apply_infer_index_source_root_flag(args: Any, compile_commands_path: str) -> None:
    """
    If ``args.infer_index_source_root_from_compile_commands`` is true, set ``args.index_source_root``.

    Raises ``ValueError`` if the flag conflicts with an explicit ``--index-source-root`` or inference fails.
    """
    if not getattr(args, "infer_index_source_root_from_compile_commands", False):
        return
    existing = getattr(args, "index_source_root", None)
    if existing is not None and str(existing).strip():
        raise ValueError(
            "Do not combine --index-source-root with --infer-index-source-root-from-compile-commands"
        )
    if not compile_commands_path or not str(compile_commands_path).strip():
        raise ValueError("--infer-index-source-root-from-compile-commands requires a compile_commands.json path")
    args.index_source_root = infer_index_source_root_from_compile_commands_path(compile_commands_path)


def _path_prefix_replace_bounded(n: str, old: str, new: str, case_insensitive: bool) -> str:
    """
    Replace every occurrence of ``old`` as a filesystem path prefix, not a substring of a longer
    directory name (e.g. ``/proj/android`` must not match inside ``/proj/android2``).
    """
    if not old or not n:
        return n

    def boundary_ok_at(end: int) -> bool:
        if end >= len(n):
            return True
        c = n[end]
        # Continuation of the same path segment (android vs android2) — do not treat as prefix end.
        if c.isalnum() or c == "_":
            return False
        return True

    out: List[str] = []
    i = 0
    old_len = len(old)
    while i < len(n):
        if case_insensitive:
            lower_n = n.lower()
            lower_old = old.lower()
            j = lower_n.find(lower_old, i)
        else:
            j = n.find(old, i)
        if j == -1:
            out.append(n[i:])
            break
        end = j + old_len
        if boundary_ok_at(end):
            out.append(n[i:j])
            out.append(new)
            i = end
        else:
            out.append(n[i : j + 1])
            i = j + 1
    return "".join(out)


def bulk_replace_index_root(s: str, index_root_user: str, local_root: Path) -> str:
    """
    Replace ``index_root_user`` with ``local_root`` inside a string (paths, ``-I``, ``command``, etc.).

    Uses bounded path-prefix rules for ``/home/...`` roots (avoids ``/android`` matching ``/android2``).
    Case-insensitive bounded replace for native Windows roots.
    """
    if not isinstance(s, str) or not s:
        return s
    loc_alt = str(local_root.expanduser().resolve()).replace("\\", "/")
    if is_posix_style_index_root(index_root_user):
        irn = normalize_index_root(index_root_user)
        n = s.replace("\\", "/")
        if irn not in n:
            return s
        return _path_prefix_replace_bounded(n, irn, loc_alt, case_insensitive=False)
    old = normalize_native_index_root(index_root_user).replace("\\", "/")
    n = s.replace("\\", "/")
    if old.lower() not in n.lower():
        return s
    return _path_prefix_replace_bounded(n, old, loc_alt, case_insensitive=True)


def remap_compile_commands_entries(
    entries: List[Dict[str, Any]],
    index_root_user: str,
    local_root: Path,
) -> List[Dict[str, Any]]:
    """Return a new list with paths under ``index_root_user`` rewritten to ``local_root``."""
    loc = Path(local_root).expanduser().resolve()
    out: List[Dict[str, Any]] = []

    for entry in entries:
        e = dict(entry)
        for key in ("directory", "file", "output"):
            if key in e and isinstance(e[key], str):
                e[key] = bulk_replace_index_root(e[key], index_root_user, loc)
        if "arguments" in e and isinstance(e["arguments"], list):
            e["arguments"] = [
                bulk_replace_index_root(x, index_root_user, loc) if isinstance(x, str) else x
                for x in e["arguments"]
            ]
        if "command" in e and isinstance(e["command"], str):
            e["command"] = bulk_replace_index_root(e["command"], index_root_user, loc)
        out.append(e)
    return out


def materialize_remapped_compile_commands(
    compile_commands_path: str,
    index_root_user: str,
    local_root: Path,
) -> tuple[str, str]:
    """
    Read ``compile_commands.json``, remap Linux roots to ``local_root``, write a temp
    copy, return ``(temp_dir, path_to_json)`` for ``CompilationDatabase.fromDirectory``.

    Registers ``atexit`` to delete ``temp_dir``.
    """
    p = Path(compile_commands_path).expanduser().resolve()
    if p.is_dir():
        src = p / "compile_commands.json"
    else:
        src = p
    if not src.is_file():
        raise FileNotFoundError(f"compile_commands.json not found: {src}")

    with open(src, encoding="utf-8", errors="replace") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("compile_commands.json must be a JSON array")

    remapped = remap_compile_commands_entries(data, index_root_user, local_root)
    td = tempfile.mkdtemp(prefix="cc_remap_")
    out_json = Path(td) / "compile_commands.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(remapped, f, ensure_ascii=False)

    def _cleanup():
        shutil.rmtree(td, ignore_errors=True)

    atexit.register(_cleanup)
    logger.info(
        "Wrote remapped compile_commands for local tree under %s (from index root %s)",
        local_root.expanduser().resolve(),
        cache_key_index_root(index_root_user),
    )
    return str(td), str(out_json)
