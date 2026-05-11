#!/usr/bin/env python3
"""
Optional tiktoken: use the real library when installed; otherwise a small shim
so ``pip install -r requirements-core.txt`` never requires a Rust build for tiktoken.

For accurate OpenAI-style counts/chunking, also install::

    pip install -r requirements-tiktoken.txt
"""

from __future__ import annotations

import logging
from typing import Any, List

logger = logging.getLogger(__name__)

# ``False`` = import was attempted and failed; module object = real tiktoken.
_tiktoken_mod: Any = None
_warned_shim = False


def _ensure_tiktoken():
    global _tiktoken_mod
    if _tiktoken_mod is not None:
        return _tiktoken_mod if _tiktoken_mod is not False else None
    try:
        import tiktoken as t  # type: ignore

        _tiktoken_mod = t
        return t
    except Exception as exc:  # ImportError, missing native lib, partial install, etc.
        logger.debug("tiktoken not usable: %s", exc)
        _tiktoken_mod = False
        return None


class _CharShimEncoding:
    """~1 \"token\" per Unicode codepoint (rough vs BPE); good enough for chunk boundaries."""

    name = "tiktoken-shim-char"

    def encode(
        self,
        text: str,
        allowed_special: Any = "all",
        disallowed_special: Any = "all",
    ) -> List[int]:
        return [ord(c) for c in text]

    def decode(self, tokens: List[int], errors: str = "replace") -> str:
        out: List[str] = []
        for i in tokens:
            if 0 <= i <= 0x10FFFF:
                try:
                    out.append(chr(i))
                except ValueError:
                    if errors == "strict":
                        raise
                    out.append("\ufffd")
            else:
                if errors == "strict":
                    raise ValueError(f"invalid codepoint {i}")
                out.append("\ufffd")
        return "".join(out)


def _maybe_warn_shim():
    global _warned_shim
    if not _warned_shim:
        logger.warning(
            "tiktoken is not installed (or failed to import). Using a character-level "
            "fallback for token estimates. For accurate chunking install: pip install -r requirements-tiktoken.txt"
        )
        _warned_shim = True


def get_encoding(encoding_name: str):
    t = _ensure_tiktoken()
    if t is not None:
        return t.get_encoding(encoding_name)
    _maybe_warn_shim()
    return _CharShimEncoding()


def encoding_for_model(model_name: str):
    t = _ensure_tiktoken()
    if t is not None:
        try:
            return t.encoding_for_model(model_name)
        except KeyError:
            return t.get_encoding("cl100k_base")
    _maybe_warn_shim()
    return _CharShimEncoding()
