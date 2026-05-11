#!/usr/bin/env python3
"""Download a SentenceTransformers-compatible model into embedding_models/ for offline use."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_REPO_ID = "sentence-transformers/all-MiniLM-L6-v2"
_DEFAULT_LOCAL = (
    _REPO_ROOT / "embedding_models" / "sentence-transformers" / "all-MiniLM-L6-v2"
)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Download HF model snapshot into repo embedding_models/ (offline-friendly)."
    )
    p.add_argument(
        "--repo-id",
        default=_DEFAULT_REPO_ID,
        help=f"Hugging Face model id (default: {_DEFAULT_REPO_ID!r})",
    )
    p.add_argument(
        "--local-dir",
        type=Path,
        default=_DEFAULT_LOCAL,
        help=f"Destination directory (default: {_DEFAULT_LOCAL})",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print paths only; do not download.",
    )
    args = p.parse_args()
    dest: Path = args.local_dir.expanduser().resolve()

    if args.dry_run:
        print(f"repo_id:   {args.repo_id}")
        print(f"local_dir: {dest}")
        return 0

    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        print(
            "Missing huggingface_hub. Install with: pip install huggingface_hub",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    dest.parent.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=args.repo_id, local_dir=str(dest))
    print(f"Downloaded {args.repo_id!r} -> {dest}")
    print("Set for this shell (adjust drive/path):")
    print(f'  SENTENCE_TRANSFORMER_MODEL="{dest}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
