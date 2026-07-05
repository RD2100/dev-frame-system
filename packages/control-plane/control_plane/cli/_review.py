"""Phase 1C: prepare-only review command helpers."""
from __future__ import annotations

import argparse

from ..rdreview import cmd_rdreview_prepare


def cmd_rdreview(argv: list[str] | None = None) -> int:
    """rdreview: prepare a sample review packet (read-only, no state changes)."""
    parser = argparse.ArgumentParser(
        prog="devframe rdreview",
        description="Prepare a sample review-governance packet (no runtime writes).",
    )
    parser.add_argument("work_item_id", help="Work item ID (e.g. wi-review-1)")
    parser.add_argument("intent", nargs="+", help="Review intent description (multi-word OK)")
    parser.add_argument("--project", default="proj-review-demo", help="Project ID")
    parser.add_argument("--output", default=None, help="Output file path (default: stdout)")
    args = parser.parse_args(argv)
    intent = " ".join(args.intent)
    return cmd_rdreview_prepare(
        work_item_id=args.work_item_id,
        intent=intent,
        output=args.output,
        project_id=args.project,
    )
