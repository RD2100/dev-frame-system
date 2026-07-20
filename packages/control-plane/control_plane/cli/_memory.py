"""Minimal Obsidian working-plan CLI."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _parser(action: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=f"devframe memory plan {action}")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    if action == "propose":
        parser.add_argument("--project-root", required=True)
        parser.add_argument("--project-id", required=True)
        parser.add_argument("--vault-root", default=None)
        parser.add_argument("--contents-file", required=True)
        parser.add_argument("--runtime-dir", default=None)
    elif action == "approve":
        parser.add_argument("--request-id", required=True)
        parser.add_argument("--runtime-dir", default=None)
        parser.add_argument("--confirm", action="store_true")
    else:
        parser.add_argument("--project-root", required=True)
        parser.add_argument("--project-id", required=True)
        parser.add_argument("--vault-root", default=None)
    return parser


def _print(payload: dict[str, object], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return
    for key in (
        "status",
        "requestId",
        "projectId",
        "relativePath",
        "operation",
        "applied",
        "alreadyResolved",
    ):
        if key in payload:
            print(f"{key}: {payload[key]}")
    if payload.get("plan"):
        print(payload["plan"])


def cmd_memory() -> int:
    from ..backup_guard import default_runtime_dir
    from ..obsidian_memory import (
        ObsidianMemoryError,
        approve_project_plan,
        recall_project_plan,
        stage_project_plan,
    )

    actions = {"propose", "approve", "recall"}
    if len(sys.argv) < 4 or sys.argv[2] != "plan" or sys.argv[3] not in actions:
        print("Usage: devframe memory plan propose|approve|recall ...")
        return 1
    action = sys.argv[3]
    args = _parser(action).parse_args(sys.argv[4:])
    try:
        runtime_dir = Path(args.runtime_dir).resolve() if getattr(args, "runtime_dir", None) else default_runtime_dir()
        if action == "recall":
            result = recall_project_plan(
                vault_root=args.vault_root,
                project_root=args.project_root,
                project_id=args.project_id,
            )
            _print(result, args.format)
            return 0
        if action == "approve":
            result = approve_project_plan(
                runtime_dir,
                args.request_id,
                confirm=args.confirm,
            )
            _print(result, args.format)
            return 0 if result.get("status") == "applied" else 3
        try:
            contents = Path(args.contents_file).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            print(f"ERROR: cannot read --contents-file: {exc}", file=sys.stderr)
            return 2
        staged = stage_project_plan(
            runtime_dir,
            vault_root=args.vault_root,
            project_root=args.project_root,
            project_id=args.project_id,
            plan_markdown=contents,
        )
        result = {
            "applied": False,
            "humanRequired": True,
            "requestId": staged["request_id"],
            "projectId": staged["project_id"],
            "relativePath": staged["relative_path"],
            "operation": staged["operation"],
            "bytes": staged["bytes"],
            "sourceSha256": staged["source_sha256"],
            "planSha256": staged["plan_sha256"],
        }
        _print(result, args.format)
        return 3
    except ObsidianMemoryError as exc:
        payload = {"error": "obsidian_plan_rejected", "detail": str(exc)}
        if getattr(args, "format", "text") == "json":
            print(json.dumps(payload, indent=2, ensure_ascii=True))
        else:
            print(f"ERROR: Obsidian plan rejected: {exc}", file=sys.stderr)
        return 2
