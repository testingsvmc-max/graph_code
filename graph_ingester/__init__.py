#!/usr/bin/env python3
"""
Graph Ingester package for populating the Neo4j graph with code structure and metadata.

Imports are lazy so submodules like ``call_extraction`` can be used without pulling
optional dependencies (e.g. Neo4j driver) until graph-building entry points run.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = [
    "PathProcessor",
    "PathManager",
    "SymbolProcessor",
    "ClangdCallGraphExtractor",
    "IncludeRelationProvider",
]

_EXPORTS = {
    "PathProcessor": (".path", "PathProcessor"),
    "PathManager": (".path", "PathManager"),
    "SymbolProcessor": (".symbol", "SymbolProcessor"),
    "ClangdCallGraphExtractor": (".call", "ClangdCallGraphExtractor"),
    "IncludeRelationProvider": (".include", "IncludeRelationProvider"),
}


def __getattr__(name: str) -> Any:
    if name in _EXPORTS:
        mod_path, attr = _EXPORTS[name]
        mod = import_module(__name__ + mod_path, __name__)
        return getattr(mod, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + list(__all__))
