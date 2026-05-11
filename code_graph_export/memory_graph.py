"""
Build a serializable code graph in memory: nodes + typed edges.
Reuses the same discovery and symbol processing logic as graph_ingester, without Neo4j.
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse, unquote

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover

    def tqdm(iterable, **_kwargs):
        return iterable


from graph_ingester.call_extraction import ClangdCallGraphExtractorCore
from graph_ingester.path import PathManager
from graph_ingester.symbol import SymbolProcessor
from memory_debugger import Debugger
from source_parser import CompilationManager
from symbol_parser import Symbol, SymbolParser
from symbol_enricher import SymbolEnricher
from utils import align_string

logger = logging.getLogger(__name__)


def _discover_project_files(
    symbols: Dict[str, Symbol],
    compilation_manager: CompilationManager,
    path_manager: PathManager,
) -> Set[str]:
    project_files: Set[str] = set()
    for sym in tqdm(symbols.values(), desc=align_string("Paths from symbols")):
        for loc in (sym.definition, sym.declaration):
            if loc and urlparse(loc.file_uri).scheme == "file":
                abs_path = unquote(urlparse(loc.file_uri).path)
                if path_manager.is_within_project(abs_path):
                    project_files.add(path_manager.uri_to_relative_path(loc.file_uri))
    for including_abs, included_abs in tqdm(
        compilation_manager.get_include_relations(),
        desc=align_string("Paths from includes"),
    ):
        for abs_path in (including_abs, included_abs):
            if path_manager.is_within_project(abs_path):
                project_files.add(os.path.relpath(abs_path, path_manager.project_path))
    return project_files


def _folders_from_files(project_files: Set[str]) -> Set[str]:
    folders: Set[str] = set()
    for file_path in project_files:
        parent = Path(file_path).parent
        while str(parent) != "." and str(parent) != "/":
            folders.add(str(parent))
            parent = parent.parent
    return folders


def collect_filesystem_graph(
    project_path: str,
    symbols: Dict[str, Symbol],
    compilation_manager: CompilationManager,
    path_manager: PathManager,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """PROJECT / FOLDER / FILE nodes and CONTAINS edges."""
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    node_label_by_id: Dict[str, str] = {n["id"]: (n.get("labels") or [""])[0] for n in nodes}
    root = os.path.abspath(project_path)
    proj_id = "__PROJECT__"
    nodes.append({"id": proj_id, "labels": ["PROJECT"], "properties": {"root": root}})

    project_files = _discover_project_files(symbols, compilation_manager, path_manager)
    project_folders = _folders_from_files(project_files)

    for folder_path in sorted(project_folders, key=lambda p: len(Path(p).parts)):
        fid = f"folder:{folder_path}"
        parent = str(Path(folder_path).parent)
        parent_id = proj_id if parent == "." else f"folder:{parent}"
        name = Path(folder_path).name
        nodes.append({"id": fid, "labels": ["FOLDER"], "properties": {"path": folder_path, "name": name}})
        edges.append({"type": "CONTAINS", "src": parent_id, "dst": fid, "properties": {}})

    for file_path in project_files:
        file_id = f"file:{file_path}"
        parent = str(Path(file_path).parent)
        parent_id = proj_id if parent == "." else f"folder:{parent}"
        name = Path(file_path).name
        nodes.append({"id": file_id, "labels": ["FILE"], "properties": {"path": file_path, "name": name}})
        edges.append({"type": "CONTAINS", "src": parent_id, "dst": file_id, "properties": {}})

    return nodes, edges


def _dedup_processed_symbols(processed: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
    """Prefer CLASS_STRUCTURE over DATA_STRUCTURE when both share the same id."""
    class_ids = {d["id"] for d in processed.get("CLASS_STRUCTURE", [])}
    if not class_ids:
        return processed
    out = {k: list(v) for k, v in processed.items()}
    out["DATA_STRUCTURE"] = [d for d in out.get("DATA_STRUCTURE", []) if d["id"] not in class_ids]
    return out


def _symbol_node_properties(data: Dict) -> Dict:
    skip = {"node_label", "parent_id", "namespace_id"}
    return {k: v for k, v in data.items() if k not in skip and v is not None}


def collect_symbol_nodes_and_edges(
    symbol_parser: SymbolParser,
    path_manager: PathManager,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Symbol-kind nodes and semantic edges (same intent as SymbolProcessor Neo4j ingest)."""
    processor = SymbolProcessor(path_manager, log_batch_size=5000, ingest_batch_size=2000, cypher_tx_size=2000)
    qualified = processor._build_scope_maps(symbol_parser.symbols)
    processed = _dedup_processed_symbols(processor._process_and_group_symbols(symbol_parser.symbols, qualified))

    root = os.path.abspath(path_manager.project_path)

    def _rel_from_uri(file_uri: str | None) -> str | None:
        if not file_uri:
            return None
        parsed = urlparse(file_uri)
        if parsed.scheme == "file":
            raw_path = unquote(parsed.path or "")
            netloc = unquote(parsed.netloc or "")
            p = raw_path or netloc
            if not p and netloc:
                p = netloc
        else:
            p = file_uri
        p = p.replace("\\", "/")
        if os.name == "nt":
            if len(p) >= 3 and p[0] == "/" and p[2] == ":":
                p = p[1:]
            while len(p) >= 4 and p[0] == "/" and p[1].isalpha() and p[2] == ":" and p[3] == "/":
                p = p[1:]
        ap = os.path.abspath(p)
        try:
            rel = os.path.relpath(ap, root)
            rel = rel.replace("\\", "/")
            if rel.startswith("../") or rel == "..":
                return None
            return rel
        except ValueError:
            return None

    symbol_relpaths: Dict[str, str] = {}
    for sid, sym in symbol_parser.symbols.items():
        loc = sym.definition or sym.declaration
        rel_fp = _rel_from_uri(loc.file_uri) if loc else None
        if rel_fp:
            symbol_relpaths[sid] = rel_fp

    nodes: List[Dict[str, Any]] = []
    for label, items in processed.items():
        for data in items:
            nid = data["id"]
            props = _symbol_node_properties(data)
            props["kind"] = data.get("kind")
            if not props.get("file_path") and not props.get("path"):
                rel_fp = symbol_relpaths.get(nid)
                if rel_fp:
                    props["file_path"] = rel_fp
            nodes.append({"id": nid, "labels": [label], "properties": props})

    # Fallback: if processor pipeline yields no symbol nodes (e.g. path mapping edge
    # cases on Windows), still materialize symbol nodes directly from parsed symbols.
    if not nodes:
        for sym in symbol_parser.symbols.values():
            label = Symbol.get_node_label(sym)
            if not label:
                continue
            loc = sym.definition or sym.declaration
            rel_fp = None
            if loc and loc.file_uri:
                rel_fp = _rel_from_uri(loc.file_uri)
            props = {
                "name": sym.name,
                "kind": sym.kind,
                "language": sym.language or None,
                "signature": sym.signature or None,
                "return_type": sym.return_type or None,
            }
            if rel_fp:
                props["file_path"] = rel_fp
            nodes.append({"id": sym.id, "labels": [label], "properties": {k: v for k, v in props.items() if v is not None}})

    node_label_by_id: Dict[str, str] = {n["id"]: (n.get("labels") or [""])[0] for n in nodes}
    edges: List[Dict[str, Any]] = []

    id_to_label: Dict[str, str] = {}
    for label, symbol_list in processed.items():
        for data in symbol_list:
            id_to_label[data["id"]] = label

    # SCOPE_CONTAINS, HAS_NESTED, DEFINES_TYPE_ALIAS
    for symbol_list in processed.values():
        for symbol_data in symbol_list:
            if "namespace_id" in symbol_data:
                parent_id = symbol_data["namespace_id"]
                child_label = symbol_data["node_label"]
                if child_label in ("NAMESPACE", "CLASS_STRUCTURE", "DATA_STRUCTURE", "FUNCTION", "VARIABLE"):
                    edges.append(
                        {
                            "type": "SCOPE_CONTAINS",
                            "src": parent_id,
                            "dst": symbol_data["id"],
                            "properties": {"child_label": child_label},
                        }
                    )
            if "parent_id" in symbol_data:
                parent_id = symbol_data["parent_id"]
                parent_label = id_to_label.get(parent_id)
                child_label = symbol_data["node_label"]
                if parent_label in ("CLASS_STRUCTURE", "DATA_STRUCTURE", "FUNCTION", "METHOD") and child_label in (
                    "CLASS_STRUCTURE",
                    "DATA_STRUCTURE",
                    "FUNCTION",
                ):
                    edges.append(
                        {
                            "type": "HAS_NESTED",
                            "src": parent_id,
                            "dst": symbol_data["id"],
                            "properties": {"parent_label": parent_label, "child_label": child_label},
                        }
                    )

    for symbol_data in processed.get("TYPE_ALIAS", []):
        parent_id = symbol_data.get("parent_id")
        if not parent_id:
            continue
        parent_label = id_to_label.get(parent_id)
        if parent_label:
            edges.append(
                {
                    "type": "DEFINES_TYPE_ALIAS",
                    "src": parent_id,
                    "dst": symbol_data["id"],
                    "properties": {"parent_label": parent_label},
                }
            )

    for label in ("FUNCTION", "VARIABLE", "DATA_STRUCTURE", "CLASS_STRUCTURE", "TYPE_ALIAS", "MACRO"):
        for symbol_data in processed.get(label, []):
            fp = symbol_data.get("file_path") or symbol_relpaths.get(symbol_data["id"])
            if fp:
                edges.append(
                    {"type": "DEFINES", "src": f"file:{fp}", "dst": symbol_data["id"], "properties": {"symbol_label": label}}
                )

    # Ensure symbol-to-file ownership edges exist even when the processed symbol
    # payload lacks file_path/path on some platforms.
    defines_labels = {"FUNCTION", "VARIABLE", "DATA_STRUCTURE", "CLASS_STRUCTURE", "TYPE_ALIAS", "MACRO", "METHOD", "FIELD"}
    existing_defines = {(e["src"], e["dst"]) for e in edges if e.get("type") == "DEFINES"}
    for sid, fp in symbol_relpaths.items():
        label = node_label_by_id.get(sid, "")
        if label not in defines_labels:
            continue
        key = (f"file:{fp}", sid)
        if key in existing_defines:
            continue
        edges.append({"type": "DEFINES", "src": key[0], "dst": key[1], "properties": {"symbol_label": label}})

    for label in ("FUNCTION", "VARIABLE", "DATA_STRUCTURE", "CLASS_STRUCTURE"):
        for symbol_data in processed.get(label, []):
            if "file_path" not in symbol_data and "path" in symbol_data:
                edges.append(
                    {"type": "DECLARES", "src": f"file:{symbol_data['path']}", "dst": symbol_data["id"], "properties": {"symbol_label": label}}
                )

    for ns in processed.get("NAMESPACE", []):
        if ns.get("path"):
            edges.append({"type": "DECLARES", "src": f"file:{ns['path']}", "dst": ns["id"], "properties": {"symbol_label": "NAMESPACE"}})

    for field in [f for f in processed.get("FIELD", []) if "parent_id" in f]:
        edges.append({"type": "HAS_FIELD", "src": field["parent_id"], "dst": field["id"], "properties": {}})
    for method in [m for m in processed.get("METHOD", []) if "parent_id" in m]:
        edges.append({"type": "HAS_METHOD", "src": method["parent_id"], "dst": method["id"], "properties": {}})

    for subj, obj in symbol_parser.inheritance_relations:
        edges.append({"type": "INHERITS", "src": obj, "dst": subj, "properties": {}})

    for subj, obj in symbol_parser.override_relations:
        edges.append({"type": "OVERRIDDEN_BY", "src": subj, "dst": obj, "properties": {}})

    for data in processed.get("TYPE_ALIAS", []):
        if data.get("aliased_type_id"):
            edges.append(
                {
                    "type": "ALIAS_OF",
                    "src": data["id"],
                    "dst": data["aliased_type_id"],
                    "properties": {"aliased_type_kind": data.get("aliased_type_kind")},
                }
            )

    for label, data_list in processed.items():
        for data in data_list:
            if data.get("expanded_from_id"):
                edges.append(
                    {
                        "type": "EXPANDED_FROM",
                        "src": data["id"],
                        "dst": data["expanded_from_id"],
                        "properties": {"symbol_label": label},
                    }
                )

    for label in ("CLASS_STRUCTURE", "DATA_STRUCTURE"):
        for data in processed.get(label, []):
            if data.get("primary_template_id"):
                edges.append(
                    {
                        "type": "SPECIALIZATION_OF",
                        "src": data["id"],
                        "dst": data["primary_template_id"],
                        "properties": {},
                    }
                )

    return nodes, edges


def collect_include_edges(project_path: str, compilation_manager: CompilationManager) -> List[Dict[str, Any]]:
    edges: List[Dict[str, Any]] = []
    root = os.path.abspath(project_path)
    for including, included in compilation_manager.get_include_relations():
        try:
            rel_in = os.path.relpath(including, root)
            rel_out = os.path.relpath(included, root)
            if ".." in rel_in or ".." in rel_out:
                continue
        except ValueError:
            continue
        edges.append({"type": "INCLUDES", "src": f"file:{rel_in}", "dst": f"file:{rel_out}", "properties": {}})
    return edges


def collect_call_edges(symbol_parser: SymbolParser, log_batch_size: int, ingest_batch_size: int) -> List[Dict[str, Any]]:
    extractor = ClangdCallGraphExtractorCore(symbol_parser, log_batch_size, ingest_batch_size)
    rels = extractor.extract_call_relationships()
    edges: List[Dict[str, Any]] = []
    if isinstance(rels, tuple):
        caller_to_callees = rels[0]
    else:
        caller_to_callees = rels
    for caller_id, callees in caller_to_callees.items():
        for callee_id in callees:
            edges.append({"type": "CALLS", "src": caller_id, "dst": callee_id, "properties": {}})
    return edges


def build_code_graph_dict(
    project_path: str,
    index_yaml_path: str,
    compile_commands_path: Optional[str],
    num_parse_workers: int,
    log_batch_size: int = 2000,
    ingest_batch_size: int = 4000,
    index_source_root: Optional[str] = None,
    local_source_root: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run the same pre-Neo4j passes as graph_builder (parse sources, index, enrich), then materialize nodes/edges.

    When ``index_source_root`` is set (Linux/CI path prefix inside the YAML and compile_commands), paths are
    remapped to the Windows (or local) checkout — same semantics as ``graph_builder.py --index-source-root``.
    """
    from types import SimpleNamespace

    from index_path_remap import compilation_remap_kwargs_from_args
    from symbol_parser import build_parser_for_ingestion_args

    project_path = str(Path(project_path).resolve())
    index_yaml_path = str(Path(index_yaml_path).resolve())

    debugger = Debugger(turnon=False)
    ns = SimpleNamespace(
        project_path=project_path,
        index_file=index_yaml_path,
        log_batch_size=log_batch_size,
        num_parse_workers=num_parse_workers,
        index_source_root=index_source_root,
        local_source_root=local_source_root,
    )
    symbol_parser, parse_kw = build_parser_for_ingestion_args(ns, debugger=debugger)
    symbol_parser.parse(**parse_kw)

    compilation_manager = CompilationManager(
        project_path=project_path,
        compile_commands_path=compile_commands_path,
        **compilation_remap_kwargs_from_args(ns),
    )
    compilation_manager.parse_folder(project_path, num_parse_workers, new_commit=None)

    SymbolEnricher(symbol_parser, compilation_manager).enrich_symbols()

    path_manager = PathManager(project_path)
    fs_nodes, fs_edges = collect_filesystem_graph(project_path, symbol_parser.symbols, compilation_manager, path_manager)
    sym_nodes, sym_edges = collect_symbol_nodes_and_edges(symbol_parser, path_manager)
    inc_edges = collect_include_edges(project_path, compilation_manager)
    call_edges = collect_call_edges(symbol_parser, log_batch_size, ingest_batch_size)

    all_nodes = fs_nodes + sym_nodes
    all_edges = fs_edges + sym_edges + inc_edges + call_edges

    return {
        "meta": {
            "project_path": project_path,
            "index_file": index_yaml_path,
            "compile_commands": compilation_manager.compile_commands_path,
            "node_counts_by_label": _count_labels(all_nodes),
            "edge_counts_by_type": _count_edge_types(all_edges),
        },
        "nodes": all_nodes,
        "edges": all_edges,
    }


def _count_labels(nodes: List[Dict]) -> Dict[str, int]:
    counts: Dict[str, int] = defaultdict(int)
    for n in nodes:
        for lb in n.get("labels", []):
            counts[lb] += 1
    return dict(counts)


def _count_edge_types(edges: List[Dict]) -> Dict[str, int]:
    counts: Dict[str, int] = defaultdict(int)
    for e in edges:
        counts[e["type"]] += 1
    return dict(counts)


def write_code_graph_json(graph: Dict[str, Any], out_path: str) -> None:
    out_path = str(Path(out_path).resolve())
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2, ensure_ascii=False, default=str)
    logger.info("Wrote graph JSON to %s", out_path)


def write_code_graph_yaml(graph: Dict[str, Any], out_path: str) -> None:
    import yaml

    out_path = str(Path(out_path).resolve())
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            graph,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=120,
        )
    logger.info("Wrote graph YAML to %s", out_path)
