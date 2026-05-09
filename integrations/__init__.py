"""Optional bridges to other graph / review tools."""

from importlib import import_module
from typing import Any


def __getattr__(name: str) -> Any:
    if name in (
        "ensure_query_views",
        "get_callers",
        "get_callees",
        "load_crg_db",
        "crg_db_to_export_dict",
        "apply_views_to_file",
    ):
        return getattr(import_module(f"{__name__}.crg_sqlite"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ensure_query_views",
    "get_callers",
    "get_callees",
    "load_crg_db",
    "crg_db_to_export_dict",
    "apply_views_to_file",
]
