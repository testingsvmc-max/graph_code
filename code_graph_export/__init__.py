"""Export clangd + Clang-derived code graphs to plain JSON (no Neo4j)."""

from importlib import import_module
from typing import Any


def __getattr__(name: str) -> Any:
    if name in ("build_code_graph_dict", "write_code_graph_json", "write_code_graph_yaml"):
        mod = import_module(f"{__name__}.memory_graph")
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["build_code_graph_dict", "write_code_graph_json", "write_code_graph_yaml"]
