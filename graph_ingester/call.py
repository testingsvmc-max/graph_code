#!/usr/bin/env python3
"""
This module consumes parsed clangd symbol data and function span data
to produce a function-level call graph.
"""

from typing import Dict, Optional, Set
import logging
import argparse
from tqdm import tqdm

import input_params
from source_parser import CompilationManager
from symbol_parser import SymbolParser
from neo4j_manager import Neo4jManager
from utils import align_string

from .call_extraction import ClangdCallGraphExtractorCore

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ClangdCallGraphExtractor(ClangdCallGraphExtractorCore):
    """
    Unified class for extracting call relationships from clangd index data
    and optionally ingesting them into Neo4j.
    """

    def ingest_call_relations(self, caller_to_callees_map: Dict[str, Set[str]], neo4j_mgr: Optional[Neo4jManager] = None) -> None:
        """Ingests call relations from a map into Neo4j in batches."""
        if not caller_to_callees_map:
            logger.info("No call relationships to ingest.")
            return

        all_relations = []
        for caller_id, callee_set in caller_to_callees_map.items():
            for callee_id in callee_set:
                all_relations.append({"caller_id": caller_id, "callee_id": callee_id})

        total_relations = len(all_relations)
        logger.info(f"Preparing {total_relations} call relationships for ingestion...")

        query = """
        UNWIND $relations as relation
        MATCH (caller) WHERE (caller:FUNCTION OR caller:METHOD) AND caller.id = relation.caller_id
        MATCH (callee) WHERE (callee:FUNCTION OR callee:METHOD) AND callee.id = relation.callee_id
        MERGE (caller)-[:CALLS]->(callee)
        """

        if neo4j_mgr:
            total_rels_created = 0
            for i in tqdm(range(0, total_relations, self.ingest_batch_size), desc=align_string("Ingesting CALLS relations")):
                batch = all_relations[i:i + self.ingest_batch_size]
                all_counters = neo4j_mgr.process_batch([(query, {"relations": batch})])
                for counters in all_counters:
                    total_rels_created += counters.relationships_created
            logger.info(f"  Total CALLS relationships created: {total_rels_created}")
        else:
            # Fallback to writing to a file for debugging
            output_file_path = "generated_call_graph_cypher_queries.cql"
            with open(output_file_path, 'w') as f:
                f.write(f"// Total relations: {total_relations}\n")
                f.write(f"{query.strip()};\n")
            logger.info(f"Batched Cypher queries written to {output_file_path}")

    def generate_statistics(self, caller_to_callees_map: Dict[str, Set[str]]) -> str:
        """Generate summary statistics about the call graph."""
        all_call_relations = [(c, e) for c, e_set in caller_to_callees_map.items() for e in e_set]
        callers = set(caller_to_callees_map.keys())
        callees = {e for e_set in caller_to_callees_map.values() for e in e_set}
        functions_in_graph = callers.union(callees)
        recursive_calls = sum(1 for c, e_set in caller_to_callees_map.items() if c in e_set)

        return f"""
Call Graph Statistics:
=====================
Total functions in index: {len(self.symbol_parser.functions)}
Functions in call graph:  {len(functions_in_graph)}
Functions calling:        {len(callers)}
Functions called:         {len(callees)}
Total call relationships: {len(all_call_relations)}
Recursive calls:          {recursive_calls}
Entry points (only call): {len(callers - callees)}
Leaf functions (only called): {len(callees - callers)}
"""


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    parser = argparse.ArgumentParser(description='Extract call graph from clangd index YAML')
    input_params.add_core_input_args(parser)
    input_params.add_worker_args(parser)
    input_params.add_batching_args(parser)
    input_params.add_logistic_args(parser)
    input_params.add_source_parser_args(parser)

    args = parser.parse_args()
    args.index_file = str(args.index_file.resolve())
    args.project_path = str(args.project_path.resolve())

    if args.ingest_batch_size is None:
        args.ingest_batch_size = args.cypher_tx_size

    logger.info("\n--- Phase 0: Parsing Clangd Index ---")
    symbol_parser = SymbolParser(index_file_path=args.index_file, log_batch_size=args.log_batch_size)
    symbol_parser.parse(num_workers=args.num_parse_workers)

    logger.info("\n--- Phase 1: Parsing Source Code for Spans ---")
    compilation_manager = CompilationManager(project_path=args.project_path, compile_commands_path=args.compile_commands)
    compilation_manager.parse_folder(args.project_path)

    from symbol_enricher import SymbolEnricher
    logger.info("\n--- Phase 2: Enriching Symbols with Spans ---")
    symbol_enricher = SymbolEnricher(symbol_parser=symbol_parser, compilation_manager=compilation_manager)
    symbol_enricher.enrich_symbols()

    logger.info("\n--- Phase 3: Extracting Call Relationships ---")
    extractor = ClangdCallGraphExtractor(symbol_parser, args.log_batch_size, args.ingest_batch_size)
    caller_to_callees_map = extractor.extract_call_relationships(generate_bidirectional=False)

    logger.info("\n--- Phase 4: Ingesting Call Relations ---")
    if args.ingest:
        with Neo4jManager() as neo4j_mgr:
            if neo4j_mgr.check_connection():
                if not neo4j_mgr.check_connection(): return
                extractor.ingest_call_relations(caller_to_callees_map, neo4j_mgr=neo4j_mgr)
    else:
        extractor.ingest_call_relations(caller_to_callees_map, neo4j_mgr=None)

    if args.stats:
        print(extractor.generate_statistics(caller_to_callees_map))


if __name__ == "__main__":
    main()
