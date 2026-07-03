"""Command-line operations for the backend.

Usage:
    uv run python -m backend.app.cli reembed [--batch-size N]
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from backend.app.services.reembed import reembed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    p_reembed = sub.add_parser(
        "reembed",
        help="Re-embed stored chunks with the currently configured embedding model.",
    )
    p_reembed.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Chunks per embedding request (default: 64).",
    )

    args = parser.parse_args(argv)
    if args.command == "reembed":
        return reembed(batch_size=args.batch_size)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
