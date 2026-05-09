"""Load exported graph and build query indexes (no MCP)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def load_graph_dict(path: str) -> Dict[str, Any]:
    p = Path(path)
    raw = p.read_text(encoding="utf-8")
    if p.suffix.lower() in (".yaml", ".yml"):
        import yaml

        return yaml.safe_load(raw)
    return json.loads(raw)


class GraphStore:
    """In-memory indexes for nodes and edge traversal."""

    def __init__(self, graph: Dict[str, Any]) -> None:
        self.meta = dict(graph.get("meta") or {})
        self.nodes: Dict[str, Dict[str, Any]] = {}
        for n in graph.get("nodes") or []:
            nid = n.get("id")
            if nid is not None:
                self.nodes[str(nid)] = n

        self.callers: Dict[str, Set[str]] = {}  # callee -> callers
        self.callees: Dict[str, Set[str]] = {}  # caller -> callees
        self._out_by_type: Dict[str, Dict[str, Set[str]]] = {}
        self._in_by_type: Dict[str, Dict[str, Set[str]]] = {}
        self._all_edges: List[Dict[str, Any]] = []

        for e in graph.get("edges") or []:
            et = str(e.get("type") or "")
            src, dst = str(e.get("src")), str(e.get("dst"))
            if src not in self.nodes or dst not in self.nodes:
                continue
            self._all_edges.append({"type": et, "src": src, "dst": dst, "properties": e.get("properties") or {}})
            self._out_by_type.setdefault(et, {}).setdefault(src, set()).add(dst)
            self._in_by_type.setdefault(et, {}).setdefault(dst, set()).add(src)
            if et == "CALLS":
                self.callees.setdefault(src, set()).add(dst)
                self.callers.setdefault(dst, set()).add(src)

        self._function_ids: Set[str] = set()
        for nid, n in self.nodes.items():
            labels = set(n.get("labels") or [])
            if labels & {"FUNCTION", "METHOD"}:
                self._function_ids.add(nid)
        # also treat endpoints of CALLS as functions for API purposes
        for a, bs in self.callees.items():
            self._function_ids.add(a)
            self._function_ids.update(bs)

    @property
    def function_node_count(self) -> int:
        return len(self._function_ids)

    @classmethod
    def from_path(cls, path: str) -> "GraphStore":
        return cls(load_graph_dict(path))

    def is_function(self, node_id: str) -> bool:
        return node_id in self._function_ids

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        return self.nodes.get(node_id)

    def list_graph_stats(self) -> Dict[str, Any]:
        node_counts: Dict[str, int] = {}
        for n in self.nodes.values():
            labels = n.get("labels") or []
            if not labels:
                node_counts["UNLABELED"] = node_counts.get("UNLABELED", 0) + 1
            for lb in labels:
                node_counts[str(lb)] = node_counts.get(str(lb), 0) + 1
        edge_counts: Dict[str, int] = {}
        for e in self._all_edges:
            et = e["type"]
            edge_counts[et] = edge_counts.get(et, 0) + 1
        return {
            "nodes": len(self.nodes),
            "edges": len(self._all_edges),
            "functions_indexed": self.function_node_count,
            "node_counts_by_label": dict(sorted(node_counts.items())),
            "edge_counts_by_type": dict(sorted(edge_counts.items())),
            "meta": self.meta,
        }

    def list_callers(self, callee_id: str, limit: int = 200) -> List[str]:
        s = sorted(self.callers.get(callee_id, ()))
        return s[:limit]

    def list_callees(self, caller_id: str, limit: int = 200) -> List[str]:
        s = sorted(self.callees.get(caller_id, ()))
        return s[:limit]

    def search_functions(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        q = (query or "").lower().strip()
        if not q:
            return []
        out: List[Tuple[float, Dict[str, Any]]] = []
        for nid in self._function_ids:
            n = self.nodes.get(nid)
            if not n:
                continue
            props = n.get("properties") or {}
            name = str(props.get("name") or "").lower()
            sig = str(props.get("signature") or "").lower()
            nid_l = nid.lower()
            score = 0.0
            if q in nid_l:
                score += 3.0
            if q in name:
                score += 2.0
            if q in sig:
                score += 1.0
            if score > 0:
                out.append(
                    (
                        score,
                        {
                            "id": nid,
                            "labels": n.get("labels"),
                            "name": props.get("name"),
                            "signature": props.get("signature"),
                            "path": props.get("path") or props.get("file_path"),
                        },
                    )
                )
        out.sort(key=lambda x: -x[0])
        return [x[1] for x in out[:limit]]

    def search_nodes(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        q = (query or "").lower().strip()
        if not q:
            return []
        out: List[Tuple[float, Dict[str, Any]]] = []
        for nid, n in self.nodes.items():
            props = n.get("properties") or {}
            name = str(props.get("name") or "").lower()
            file_path = str(props.get("path") or props.get("file_path") or "").lower()
            sig = str(props.get("signature") or "").lower()
            score = 0.0
            if q in nid.lower():
                score += 3.0
            if q in name:
                score += 2.0
            if q in file_path:
                score += 1.0
            if q in sig:
                score += 0.5
            if score > 0:
                out.append((score, {"id": nid, "labels": n.get("labels"), "properties": props}))
        out.sort(key=lambda x: -x[0])
        return [x[1] for x in out[:limit]]

    def _edge_targets(self, edge_type: str, source_id: str) -> Set[str]:
        return self._out_by_type.get(edge_type, {}).get(source_id, set())

    def _edge_sources(self, edge_type: str, target_id: str) -> Set[str]:
        return self._in_by_type.get(edge_type, {}).get(target_id, set())

    def query_graph(self, pattern: str, target: str, limit: int = 200) -> Dict[str, Any]:
        patterns = {
            "callers_of",
            "callees_of",
            "imports_of",
            "importers_of",
            "children_of",
            "tests_for",
            "inheritors_of",
            "file_summary",
        }
        if pattern not in patterns:
            return {"status": "error", "error": f"Unknown pattern: {pattern}", "available": sorted(patterns)}

        target_id = target if target in self.nodes else None
        if target_id is None:
            cand = self.search_nodes(target, limit=10)
            if len(cand) == 1:
                target_id = cand[0]["id"]
            elif not cand:
                return {"status": "not_found", "target": target}
            else:
                return {"status": "ambiguous", "target": target, "candidates": cand}

        results: List[Dict[str, Any]] = []
        edges: List[Dict[str, str]] = []

        if pattern == "callers_of":
            for src in sorted(self._edge_sources("CALLS", target_id))[:limit]:
                edges.append({"type": "CALLS", "src": src, "dst": target_id})
                if self.get_node(src):
                    results.append(self.get_node(src))
        elif pattern == "callees_of":
            for dst in sorted(self._edge_targets("CALLS", target_id))[:limit]:
                edges.append({"type": "CALLS", "src": target_id, "dst": dst})
                if self.get_node(dst):
                    results.append(self.get_node(dst))
        elif pattern == "imports_of":
            for dst in sorted(self._edge_targets("INCLUDES", target_id) | self._edge_targets("IMPORTS_FROM", target_id))[:limit]:
                t = "INCLUDES" if dst in self._edge_targets("INCLUDES", target_id) else "IMPORTS_FROM"
                edges.append({"type": t, "src": target_id, "dst": dst})
                if self.get_node(dst):
                    results.append(self.get_node(dst))
        elif pattern == "importers_of":
            in_includes = self._edge_sources("INCLUDES", target_id)
            in_imports = self._edge_sources("IMPORTS_FROM", target_id)
            for src in sorted(in_includes | in_imports)[:limit]:
                t = "INCLUDES" if src in in_includes else "IMPORTS_FROM"
                edges.append({"type": t, "src": src, "dst": target_id})
                if self.get_node(src):
                    results.append(self.get_node(src))
        elif pattern == "children_of":
            for dst in sorted(self._edge_targets("CONTAINS", target_id))[:limit]:
                edges.append({"type": "CONTAINS", "src": target_id, "dst": dst})
                if self.get_node(dst):
                    results.append(self.get_node(dst))
        elif pattern == "tests_for":
            for src in sorted(self._edge_sources("TESTED_BY", target_id))[:limit]:
                edges.append({"type": "TESTED_BY", "src": src, "dst": target_id})
                if self.get_node(src):
                    results.append(self.get_node(src))
        elif pattern == "inheritors_of":
            srcs = self._edge_sources("INHERITS", target_id) | self._edge_sources("IMPLEMENTS", target_id)
            for src in sorted(srcs)[:limit]:
                et = "INHERITS" if src in self._edge_sources("INHERITS", target_id) else "IMPLEMENTS"
                edges.append({"type": et, "src": src, "dst": target_id})
                if self.get_node(src):
                    results.append(self.get_node(src))
        elif pattern == "file_summary":
            file_node = self.get_node(target_id) or {}
            fp = str((file_node.get("properties") or {}).get("path") or (file_node.get("properties") or {}).get("file_path") or "")
            if not fp:
                fp = target
            for n in self.nodes.values():
                props = n.get("properties") or {}
                nfp = str(props.get("path") or props.get("file_path") or "")
                if nfp == fp:
                    results.append(n)
            results = results[:limit]

        return {"status": "ok", "pattern": pattern, "target": target_id, "result_count": len(results), "results": results, "edges": edges}

    def traverse_graph(self, start: str, direction: str = "both", edge_type: str = "CALLS", depth: int = 2, limit: int = 500) -> Dict[str, Any]:
        start_id = start if start in self.nodes else None
        if start_id is None:
            cand = self.search_nodes(start, limit=10)
            if len(cand) == 1:
                start_id = cand[0]["id"]
            elif not cand:
                return {"status": "not_found", "target": start}
            else:
                return {"status": "ambiguous", "target": start, "candidates": cand}
        direction = (direction or "both").lower()
        if direction not in {"up", "down", "both"}:
            return {"status": "error", "error": "direction must be up/down/both"}
        seen = {start_id}
        edges_out: List[Dict[str, str]] = []

        def expand_down(frontier: Set[str]) -> Set[str]:
            nxt: Set[str] = set()
            for src in frontier:
                for dst in self._edge_targets(edge_type, src):
                    edges_out.append({"type": edge_type, "src": src, "dst": dst})
                    if dst not in seen and len(seen) < limit:
                        seen.add(dst)
                        nxt.add(dst)
            return nxt

        def expand_up(frontier: Set[str]) -> Set[str]:
            nxt: Set[str] = set()
            for dst in frontier:
                for src in self._edge_sources(edge_type, dst):
                    edges_out.append({"type": edge_type, "src": src, "dst": dst})
                    if src not in seen and len(seen) < limit:
                        seen.add(src)
                        nxt.add(src)
            return nxt

        if direction in {"down", "both"}:
            f = {start_id}
            for _ in range(max(1, depth)):
                f = expand_down(f)
                if not f:
                    break
        if direction in {"up", "both"}:
            f = {start_id}
            for _ in range(max(1, depth)):
                f = expand_up(f)
                if not f:
                    break

        node_payload = [self.nodes[nid] for nid in sorted(seen) if nid in self.nodes]
        return {"status": "ok", "start": start_id, "direction": direction, "edge_type": edge_type, "depth": depth, "nodes": node_payload, "edges": edges_out}

    def impact_radius(self, changed_files: List[str], max_depth: int = 2, limit: int = 500) -> Dict[str, Any]:
        targets = {str(x).replace("\\", "/").lower() for x in changed_files}
        changed: Set[str] = set()
        for nid, n in self.nodes.items():
            props = n.get("properties") or {}
            fp = str(props.get("path") or props.get("file_path") or "").replace("\\", "/").lower()
            if not fp:
                continue
            if fp in targets or any(fp.endswith("/" + t) for t in targets):
                changed.add(nid)
        if not changed:
            return {"status": "ok", "summary": "No changed nodes found", "changed_nodes": [], "impacted_nodes": [], "impacted_files": []}
        seen = set(changed)
        frontier = set(changed)
        edges: List[Dict[str, str]] = []
        for _ in range(max(1, max_depth)):
            nxt: Set[str] = set()
            for nid in frontier:
                for dst in self._edge_targets("CALLS", nid):
                    edges.append({"type": "CALLS", "src": nid, "dst": dst})
                    if dst not in seen and len(seen) < limit:
                        seen.add(dst)
                        nxt.add(dst)
                for src in self._edge_sources("CALLS", nid):
                    edges.append({"type": "CALLS", "src": src, "dst": nid})
                    if src not in seen and len(seen) < limit:
                        seen.add(src)
                        nxt.add(src)
            frontier = nxt
            if not frontier:
                break
        impacted = sorted(seen - changed)
        files: Set[str] = set()
        for nid in impacted:
            props = (self.nodes.get(nid) or {}).get("properties") or {}
            fp = props.get("path") or props.get("file_path")
            if fp:
                files.add(str(fp))
        return {
            "status": "ok",
            "changed_nodes": [self.nodes[nid] for nid in sorted(changed) if nid in self.nodes],
            "impacted_nodes": [self.nodes[nid] for nid in impacted if nid in self.nodes],
            "impacted_files": sorted(files),
            "edges": edges[:limit],
        }
