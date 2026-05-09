"""
Call-graph extraction from a parsed clangd index (no Neo4j dependency).
"""

from __future__ import annotations

import gc
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from symbol_parser import Location, RelativeLocation, Symbol, SymbolParser

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ClangdCallGraphExtractorCore:
    """
    Extracts caller -> callees from clangd index data only.
    Neo4j ingestion lives in graph_ingester.call.ClangdCallGraphExtractor.
    """

    def __init__(self, symbol_parser: SymbolParser, log_batch_size: int = 1000, ingest_batch_size: int = 1000):
        self.symbol_parser = symbol_parser
        self.log_batch_size = log_batch_size
        self.ingest_batch_size = ingest_batch_size

    def extract_call_relationships(self, generate_bidirectional: bool = False):
        if self.symbol_parser.has_container_field:
            return self._extract_with_container(generate_bidirectional)
        return self._extract_without_container(generate_bidirectional)

    def _extract_with_container(self, generate_bidirectional: bool = False):
        logger.info("Extracting call relationships using Container field...")
        caller_to_callees: Dict[str, Set[str]] = defaultdict(set)
        callee_to_callers = defaultdict(set) if generate_bidirectional else None

        for callee_symbol in self.symbol_parser.symbols.values():
            if not callee_symbol.references or not callee_symbol.is_function():
                continue

            for reference in callee_symbol.references:
                if reference.container_id and reference.container_id != "0000000000000000" and reference.kind in (20, 28):
                    caller_id = reference.container_id
                    caller_symbol = self.symbol_parser.symbols.get(caller_id)

                    if caller_symbol and caller_symbol.is_function():
                        caller_to_callees[caller_id].add(callee_symbol.id)
                        if generate_bidirectional:
                            callee_to_callers[callee_symbol.id].add(caller_id)

        total_relations = sum(len(v) for v in caller_to_callees.values())
        logger.info("Extracted %s call relationships using Container field.", total_relations)
        return (caller_to_callees, callee_to_callers) if generate_bidirectional else caller_to_callees

    def _extract_without_container(self, generate_bidirectional: bool = False):
        logger.info("Extracting call relationships using spatial indexing fallback...")
        caller_to_callees: Dict[str, Set[str]] = defaultdict(set)
        callee_to_callers = defaultdict(set) if generate_bidirectional else None

        functions_with_bodies = {fid: f for fid, f in self.symbol_parser.functions.items() if f.body_location}

        if not functions_with_bodies:
            logger.warning("No functions have body locations. Call graph will be empty.")
            return (caller_to_callees, callee_to_callers) if generate_bidirectional else caller_to_callees

        file_to_function_bodies_index: Dict[str, List[Tuple[RelativeLocation, Symbol]]] = {}
        for caller_symbol in functions_with_bodies.values():
            if caller_symbol.body_location and caller_symbol.definition:
                file_uri = caller_symbol.definition.file_uri
                file_to_function_bodies_index.setdefault(file_uri, []).append((caller_symbol.body_location, caller_symbol))

        for file_uri in file_to_function_bodies_index:
            file_to_function_bodies_index[file_uri].sort(key=lambda item: item[0].start_line)

        logger.info("Built spatial index for %s files.", len(file_to_function_bodies_index))
        del functions_with_bodies
        gc.collect()

        valid_call_kinds = [20, 28] if self.symbol_parser.has_call_kind else [4, 12]
        logger.info("Using call kinds for detection: %s", valid_call_kinds)

        for callee_symbol in self.symbol_parser.symbols.values():
            if not callee_symbol.references or not callee_symbol.is_function():
                continue

            for reference in callee_symbol.references:
                if reference.kind not in valid_call_kinds:
                    continue

                call_location = reference.location
                if call_location.file_uri in file_to_function_bodies_index:
                    for body_loc, caller_symbol in file_to_function_bodies_index[call_location.file_uri]:
                        if self._is_location_within_function_body(call_location, body_loc, call_location.file_uri):
                            caller_to_callees[caller_symbol.id].add(callee_symbol.id)
                            if generate_bidirectional:
                                callee_to_callers[callee_symbol.id].add(caller_symbol.id)
                            break

        total_relations = sum(len(v) for v in caller_to_callees.values())
        logger.info("Extracted %s call relationships using spatial indexing.", total_relations)
        del file_to_function_bodies_index
        gc.collect()

        return (caller_to_callees, callee_to_callers) if generate_bidirectional else caller_to_callees

    def _is_location_within_function_body(self, call_loc: Location, body_loc: RelativeLocation, body_file_uri: str) -> bool:
        if call_loc.file_uri != body_file_uri:
            return False

        start_ok = (call_loc.start_line > body_loc.start_line) or (
            call_loc.start_line == body_loc.start_line and call_loc.start_column >= body_loc.start_column
        )

        end_ok = (call_loc.end_line < body_loc.end_line) or (
            call_loc.end_line == body_loc.end_line and call_loc.end_column <= body_loc.end_column
        )

        return start_ok and end_ok
