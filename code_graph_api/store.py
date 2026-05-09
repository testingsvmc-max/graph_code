"""Load exported graph and build call-graph indexes."""

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
    """In-memory indexes for nodes and CALLS edges."""

    def __init__(self, graph: Dict[str, Any]) -> None:
        self.meta = dict(graph.get("meta") or {})
        self.nodes: Dict[str, Dict[str, Any]] = {}
        for n in graph.get("nodes") or []:
            nid = n.get("id")
            if nid is not None:
                self.nodes[str(nid)] = n

        self.callers: Dict[str, Set[str]] = {}  # callee -> callers
        self.callees: Dict[str, Set[str]] = {}  # caller -> callees

        for e in graph.get("edges") or []:
            if e.get("type") != "CALLS":
                continue
            src, dst = str(e.get("src")), str(e.get("dst"))
            if src not in self.nodes or dst not in self.nodes:
                continue
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
