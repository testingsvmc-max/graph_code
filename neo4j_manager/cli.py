#!/usr/bin/env python3
"""CLI interface for Neo4j database management and graph querying."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

from . import Neo4jManager

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def _recursive_type_check(data, indent=0, path="", output_lines: list = None):
    """Recursively traverses a nested data structure and logs types/shapes."""
    if output_lines is None:
        output_lines = []
    prefix = "  " * indent
    if isinstance(data, dict):
        output_lines.append(f"{prefix}{path} (dict)")
        for k, v in data.items():
            _recursive_type_check(v, indent + 1, f"{path}.{k}", output_lines)
    elif isinstance(data, list):
        output_lines.append(f"{prefix}{path} (list of {len(data)} items)")
        if data:
            _recursive_type_check(data[0], indent + 1, f"{path}[0]", output_lines)
    elif isinstance(data, tuple):
        output_lines.append(f"{prefix}{path} (tuple of {len(data)} items)")
        if data:
            _recursive_type_check(data[0], indent + 1, f"{path}[0]", output_lines)
    else:
        output_lines.append(f"{prefix}{path} ({type(data).__name__}) = {str(data)[:50]}")
    return output_lines


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _parse_labels_csv(s: str) -> list[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def _resolve_target_candidates(neo4j_mgr: Neo4jManager, target: str, labels: list[str], limit: int = 10) -> list[dict]:
    q = """
    MATCH (n)
    WHERE any(lbl IN labels(n) WHERE lbl IN $labels)
      AND (
        toLower(coalesce(n.qualified_name, "")) = toLower($target)
        OR toLower(coalesce(n.name, "")) = toLower($target)
      )
    RETURN
      coalesce(n.id, n.symbol_id, n.usr, elementId(n)) AS id,
      labels(n) AS labels,
      coalesce(n.name, "") AS name,
      coalesce(n.qualified_name, "") AS qualified_name,
      coalesce(n.file_path, "") AS file_path
    ORDER BY qualified_name
    LIMIT $limit
    """
    return neo4j_mgr.execute_read_query(q, {"target": target, "labels": labels, "limit": limit})


def _pick_single_target(neo4j_mgr: Neo4jManager, target: str, labels: list[str]) -> tuple[dict | None, list[dict]]:
    candidates = _resolve_target_candidates(neo4j_mgr, target, labels, limit=25)
    if not candidates:
        return None, []
    qn_exact = [x for x in candidates if x.get("qualified_name", "").lower() == target.lower()]
    if len(qn_exact) == 1:
        return qn_exact[0], candidates
    if len(candidates) == 1:
        return candidates[0], candidates
    return None, candidates

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    parser = argparse.ArgumentParser(description="A CLI tool for Neo4j database management.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- dump-schema command ---
    parser_schema = subparsers.add_parser("dump-schema", help="Fetch and print the graph schema.")
    parser_schema.add_argument("-o", "--output", help="Optional path to save the output JSON file.")
    parser_schema.add_argument("--only-relations", action="store_true", help="Only show relationships, skip node properties.")
    parser_schema.add_argument("--with-node-counts", action="store_true", help="Include node and relationship counts in the output.")
    parser_schema.add_argument("--json-format", action="store_true", help="Output raw JSON from APOC meta procedures instead of formatted text.")

    # --- delete-property command ---
    parser_delete = subparsers.add_parser("delete-property", help="Delete a property from all nodes with a given label.")
    parser_delete.add_argument("--label", help="The node label to target (e.g., 'FUNCTION'). Required unless --all-labels is used.")
    parser_delete.add_argument("--key", required=True, help="The property key to remove (e.g., 'summaryEmbedding').")
    parser_delete.add_argument("--all-labels", action="store_true", help="Delete the property from all nodes that have it, regardless of label.")
    parser_delete.add_argument("--rebuild-indices", action="store_true", help="If deleting embedding properties, drop and recreate vector indices.")

    # --- dump-schema-types command ---
    parser_check_types = subparsers.add_parser("dump-schema-types", help="Recursively check and print types of the schema data returned by Neo4j.")
    parser_check_types.add_argument("-o", "--output", help="Optional path to save the output text file.")

    # --- search command ---
    parser_search = subparsers.add_parser("search", help="Search graph nodes by name/qualified_name/file_path.")
    parser_search.add_argument("query", help="Search text")
    parser_search.add_argument("--labels", default="FUNCTION,METHOD", help="Comma-separated labels to filter")
    parser_search.add_argument("--limit", type=int, default=30, help="Max results")

    # --- callers command ---
    parser_callers = subparsers.add_parser("callers", help="List callers of a function/method.")
    parser_callers.add_argument("target", help="Function target (qualified_name preferred)")
    parser_callers.add_argument("--labels", default="FUNCTION,METHOD", help="Comma-separated labels to resolve target")
    parser_callers.add_argument("--limit", type=int, default=200, help="Max caller rows")

    # --- callees command ---
    parser_callees = subparsers.add_parser("callees", help="List callees of a function/method.")
    parser_callees.add_argument("target", help="Function source (qualified_name preferred)")
    parser_callees.add_argument("--labels", default="FUNCTION,METHOD", help="Comma-separated labels to resolve source")
    parser_callees.add_argument("--limit", type=int, default=200, help="Max callee rows")

    # --- call-graph command ---
    parser_callgraph = subparsers.add_parser("call-graph", help="Get local CALLS graph around one function.")
    parser_callgraph.add_argument("target", help="Center function (qualified_name preferred)")
    parser_callgraph.add_argument("--labels", default="FUNCTION,METHOD", help="Comma-separated labels to resolve center")
    parser_callgraph.add_argument("--direction", choices=["up", "down", "both"], default="both")
    parser_callgraph.add_argument("--depth", type=int, default=1, help="Hop depth")
    parser_callgraph.add_argument("--limit", type=int, default=1000, help="Max discovered nodes")

    args = parser.parse_args()

    with Neo4jManager() as neo4j_mgr:
        if not neo4j_mgr.check_connection():
            sys.exit(1)

        if args.command == "dump-schema":
            schema_info = neo4j_mgr.get_schema()
            if not schema_info or schema_info.get("error"):
                logger.error("Could not retrieve schema.")
                sys.exit(1)
            
            if args.json_format:
                output_content = json.dumps(schema_info, default=str, indent=2)
            else:
                output_content = neo4j_mgr.format_schema_for_display(schema_info, args)

            if args.output:
                try:
                    with open(args.output, 'w') as f:
                        f.write(output_content)
                    logger.info(f"Schema successfully written to {args.output}")
                except Exception as e:
                    logger.error(f"Failed to write schema to file: {e}")
            else:
                print(output_content)
        
        elif args.command == "delete-property":
            if not args.label and not args.all_labels:
                logger.error("Error: Either --label or --all-labels must be specified for 'delete-property'.")
                sys.exit(1)
            if args.label and args.all_labels:
                logger.error("Error: Cannot specify both --label and --all-labels. Choose one.")
                sys.exit(1)

            count = neo4j_mgr.delete_property(args.label, args.key, args.all_labels)
            logger.info(f"Removed property '{args.key}' from {count} nodes.")

            if args.rebuild_indices and "embedding" in args.key.lower():
                logger.info("Rebuilding vector indices as requested...")
                neo4j_mgr.rebuild_vector_indices()
        
        elif args.command == "dump-schema-types":
            output_lines = _recursive_type_check(neo4j_mgr.get_schema(), path="schema_info")
            output_content = "\n".join(output_lines)

            if args.output:
                try:
                    with open(args.output, 'w') as f:
                        f.write(output_content)
                    logger.info(f"Schema types successfully written to {args.output}")
                except Exception as e:
                    logger.error(f"Failed to write schema types to file: {e}")
            else:
                print(output_content)

        elif args.command == "search":
            labels = _parse_labels_csv(args.labels)
            q = """
            MATCH (n)
            WHERE any(lbl IN labels(n) WHERE lbl IN $labels)
              AND (
                toLower(coalesce(n.name, "")) CONTAINS $query
                OR toLower(coalesce(n.qualified_name, "")) CONTAINS $query
                OR toLower(coalesce(n.file_path, "")) CONTAINS $query
              )
            RETURN
              coalesce(n.id, n.symbol_id, n.usr, elementId(n)) AS id,
              labels(n) AS labels,
              coalesce(n.name, "") AS name,
              coalesce(n.qualified_name, "") AS qualified_name,
              coalesce(n.file_path, "") AS file_path
            ORDER BY name, qualified_name
            LIMIT $limit
            """
            rows = neo4j_mgr.execute_read_query(
                q,
                {
                    "query": (args.query or "").lower().strip(),
                    "labels": labels,
                    "limit": max(1, int(args.limit)),
                },
            )
            _print_json({"query": args.query, "labels": labels, "count": len(rows), "results": rows})

        elif args.command in {"callers", "callees", "call-graph"}:
            labels = _parse_labels_csv(args.labels)
            picked, candidates = _pick_single_target(neo4j_mgr, args.target, labels)
            if not picked:
                if not candidates:
                    logger.error("No node found for target='%s'", args.target)
                    return 2
                _print_json(
                    {
                        "status": "ambiguous",
                        "target": args.target,
                        "message": "Multiple candidates matched. Use qualified_name.",
                        "candidates": candidates,
                    }
                )
                return 2

            center_qn = picked.get("qualified_name", "")
            if args.command == "callers":
                q = """
                MATCH (caller)-[:CALLS]->(callee)
                WHERE coalesce(callee.qualified_name, "") = $qn
                RETURN DISTINCT
                  coalesce(caller.id, caller.symbol_id, caller.usr, elementId(caller)) AS id,
                  labels(caller) AS labels,
                  coalesce(caller.name, "") AS name,
                  coalesce(caller.qualified_name, "") AS qualified_name,
                  coalesce(caller.file_path, "") AS file_path
                ORDER BY name, qualified_name
                LIMIT $limit
                """
                rows = neo4j_mgr.execute_read_query(q, {"qn": center_qn, "limit": max(1, int(args.limit))})
                _print_json({"target": picked, "caller_count": len(rows), "callers": rows})
                return 0

            if args.command == "callees":
                q = """
                MATCH (caller)-[:CALLS]->(callee)
                WHERE coalesce(caller.qualified_name, "") = $qn
                RETURN DISTINCT
                  coalesce(callee.id, callee.symbol_id, callee.usr, elementId(callee)) AS id,
                  labels(callee) AS labels,
                  coalesce(callee.name, "") AS name,
                  coalesce(callee.qualified_name, "") AS qualified_name,
                  coalesce(callee.file_path, "") AS file_path
                ORDER BY name, qualified_name
                LIMIT $limit
                """
                rows = neo4j_mgr.execute_read_query(q, {"qn": center_qn, "limit": max(1, int(args.limit))})
                _print_json({"target": picked, "callee_count": len(rows), "callees": rows})
                return 0

            # call-graph (BFS)
            direction = args.direction
            max_depth = max(1, int(args.depth))
            max_nodes = max(1, int(args.limit))
            seen_qn = {center_qn}
            nodes = {center_qn: picked}
            edges: list[dict] = []

            def fetch_out(src_qn: str) -> list[dict]:
                q_out = """
                MATCH (a)-[:CALLS]->(b)
                WHERE coalesce(a.qualified_name, "") = $qn
                RETURN DISTINCT
                  coalesce(a.qualified_name, "") AS src_qn,
                  coalesce(b.qualified_name, "") AS dst_qn,
                  coalesce(b.id, b.symbol_id, b.usr, elementId(b)) AS id,
                  labels(b) AS labels,
                  coalesce(b.name, "") AS name,
                  coalesce(b.file_path, "") AS file_path
                """
                return neo4j_mgr.execute_read_query(q_out, {"qn": src_qn})

            def fetch_in(dst_qn: str) -> list[dict]:
                q_in = """
                MATCH (a)-[:CALLS]->(b)
                WHERE coalesce(b.qualified_name, "") = $qn
                RETURN DISTINCT
                  coalesce(a.qualified_name, "") AS src_qn,
                  coalesce(b.qualified_name, "") AS dst_qn,
                  coalesce(a.id, a.symbol_id, a.usr, elementId(a)) AS id,
                  labels(a) AS labels,
                  coalesce(a.name, "") AS name,
                  coalesce(a.file_path, "") AS file_path
                """
                return neo4j_mgr.execute_read_query(q_in, {"qn": dst_qn})

            if direction in {"down", "both"}:
                frontier = {center_qn}
                for _ in range(max_depth):
                    nxt = set()
                    for qn in frontier:
                        for r in fetch_out(qn):
                            src_qn = r["src_qn"]
                            dst_qn = r["dst_qn"]
                            edges.append({"type": "CALLS", "src": src_qn, "dst": dst_qn})
                            if dst_qn and dst_qn not in seen_qn and len(seen_qn) < max_nodes:
                                seen_qn.add(dst_qn)
                                nodes[dst_qn] = {
                                    "id": r["id"],
                                    "labels": r["labels"],
                                    "name": r["name"],
                                    "qualified_name": dst_qn,
                                    "file_path": r["file_path"],
                                }
                                nxt.add(dst_qn)
                    frontier = nxt
                    if not frontier:
                        break

            if direction in {"up", "both"}:
                frontier = {center_qn}
                for _ in range(max_depth):
                    nxt = set()
                    for qn in frontier:
                        for r in fetch_in(qn):
                            src_qn = r["src_qn"]
                            dst_qn = r["dst_qn"]
                            edges.append({"type": "CALLS", "src": src_qn, "dst": dst_qn})
                            if src_qn and src_qn not in seen_qn and len(seen_qn) < max_nodes:
                                seen_qn.add(src_qn)
                                nodes[src_qn] = {
                                    "id": r["id"],
                                    "labels": r["labels"],
                                    "name": r["name"],
                                    "qualified_name": src_qn,
                                    "file_path": r["file_path"],
                                }
                                nxt.add(src_qn)
                    frontier = nxt
                    if not frontier:
                        break

            # stable unique edges
            edge_seen = set()
            uniq_edges = []
            for e in edges:
                k = (e["src"], e["dst"], e["type"])
                if k in edge_seen:
                    continue
                edge_seen.add(k)
                uniq_edges.append(e)
            _print_json(
                {
                    "center": picked,
                    "direction": direction,
                    "depth": max_depth,
                    "node_count": len(nodes),
                    "edge_count": len(uniq_edges),
                    "nodes": list(nodes.values()),
                    "edges": uniq_edges,
                }
            )
            return 0

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
