"""devframe writeback CLI — human-gated, audited workspace write-back (M8.2)."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def cmd_writeback_apply(*, prog: str = "devframe writeback apply") -> int:
    import argparse

    from ..backup_guard import default_runtime_dir
    from ..writeback import WritebackError, apply_writeback_with_audit

    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--workspace", required=True, help="Workspace root the write-back is confined to")
    parser.add_argument("--path", required=True, help="Workspace-relative target file path")
    parser.add_argument("--contents-file", required=True, help="UTF-8 file whose contents are written to --path")
    parser.add_argument("--action-id", default=None, help="Optional action id for the audit record")
    parser.add_argument("--runtime-dir", default=None, help="Local devframe runtime directory for the audit record")
    parser.add_argument("--confirm", action="store_true", help="Human gate: actually apply the write (omit to preview only)")
    parser.add_argument("--format", default="text", choices=["text", "json"], help="Output format")
    args = parser.parse_args(sys.argv[3:])

    contents_path = Path(args.contents_file)
    try:
        contents = contents_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: cannot read --contents-file: {exc}", file=sys.stderr)
        return 2

    runtime_dir = Path(args.runtime_dir).resolve() if args.runtime_dir else default_runtime_dir()

    try:
        result = apply_writeback_with_audit(
            args.workspace,
            args.path,
            contents,
            runtime_dir=runtime_dir,
            action_id=args.action_id,
            confirm=args.confirm,
        )
    except WritebackError as exc:
        if args.format == "json":
            print(json.dumps({"error": "writeback_rejected", "detail": str(exc)}, indent=2, ensure_ascii=True))
        else:
            print(f"ERROR: write-back rejected: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=True))
    else:
        if result.get("applied"):
            print("DevFrame write-back applied (human-gated)")
            print(f"  path      : {result['relative_path']}")
            print(f"  operation : {result['operation']}")
            print(f"  bytes     : {result['bytes_written']}")
            if result.get("audit_path"):
                print(f"  audit     : {result['audit_path']}")
        else:
            print("DevFrame write-back preview (human gate required)")
            print(f"  path      : {result['relative_path']}")
            print(f"  operation : {result['operation']}")
            print(f"  bytes     : {result['bytes']}")
            print("  confirm   : re-run with --confirm to apply")

    if not args.confirm:
        # Preview-only is a successful gate stop, not an error, but signal that
        # no write happened with a distinct, non-zero, non-failure code.
        return 3
    return 0
