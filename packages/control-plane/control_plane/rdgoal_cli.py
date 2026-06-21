"""CLI for rdgoal total-control orchestration."""
from __future__ import annotations

import argparse
import sys

from .orchestrator import Orchestrator
from .rdgoal import rdgoal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rdgoal")
    parser.add_argument("project_path")
    parser.add_argument("requirement")
    parser.add_argument(
        "--operation",
        default="direction choice",
        help="Current operation to route through the controller.",
    )
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="Target file or directory. May be repeated.",
    )
    parser.add_argument(
        "--apply-rdinit",
        action="store_true",
        help="Run bootstrap.ps1 when full bootstrap assets are available and the target project has no AGENTS.md.",
    )
    parser.add_argument(
        "--runtime-dir",
        default=None,
        help="Local runtime directory for journals and snapshots.",
    )
    parser.add_argument(
        "--contracts-dir",
        default=None,
        help="Directory for project contracts. Defaults to <project>/rules/project-contracts.",
    )
    parser.add_argument("--digest", action="store_true", help="Print markdown digest.")
    return parser


def build_ingest_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rdgoal ingest")
    parser.add_argument("packet_dir")
    parser.add_argument("report_path")
    parser.add_argument(
        "--runtime-dir",
        default=None,
        help="Local runtime directory for journals and report summaries.",
    )
    return parser


def build_worker_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rdgoal worker")
    parser.add_argument("packet_dir")
    parser.add_argument(
        "--runtime-dir",
        default=None,
        help="Local runtime directory for journals and report summaries.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=900,
        help="Worker command timeout in seconds.",
    )
    parser.add_argument(
        "--command",
        nargs=argparse.REMAINDER,
        default=[],
        help="Command to run. Omit for local dry-run worker.",
    )
    parser.add_argument(
        "--aihub-go",
        action="store_true",
        help="Run ai_workflow_hub.cli go against TASKSPEC.json.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Pass --apply to --aihub-go. Default is --dry-run.",
    )
    parser.add_argument(
        "--python",
        default=None,
        help="Python executable for --aihub-go.",
    )
    parser.add_argument(
        "--aihub-module",
        default="ai_workflow_hub.cli",
        help="Python module for --aihub-go.",
    )
    return parser


def build_digest_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rdgoal digest")
    parser.add_argument(
        "--runtime-dir",
        default=None,
        help="Local runtime directory for journals and report summaries.",
    )
    return parser


def _worker_exit_code(status: str) -> int:
    return 0 if status in {"pass", "passed", "completed"} else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if argv and argv[0] == "digest":
        from .runtime_digest import build_runtime_digest, render_runtime_digest_markdown

        args = build_digest_parser().parse_args(argv[1:])
        print(render_runtime_digest_markdown(build_runtime_digest(args.runtime_dir)))
        return 0
    if argv and argv[0] == "ingest":
        args = build_ingest_parser().parse_args(argv[1:])
        orchestrator = Orchestrator(runtime_dir=args.runtime_dir)
        summary = orchestrator.ingest_report(args.packet_dir, args.report_path)
        print(f"packet_id      : {summary.packet_id}")
        print(f"project_id     : {summary.project_id}")
        print(f"status         : {summary.status}")
        print(f"changed_files  : {len(summary.changed_files)}")
        print(f"report_path    : {summary.report_path}")
        return 0
    if argv and argv[0] == "worker":
        from .worker import AihubGoWorker, CommandWorker, LocalDryRunWorker

        args = build_worker_parser().parse_args(argv[1:])
        if args.aihub_go:
            result = AihubGoWorker(
                runtime_dir=args.runtime_dir,
                timeout_seconds=args.timeout,
            ).run_packet(
                args.packet_dir,
                apply_changes=args.apply,
                python_executable=args.python,
                module_name=args.aihub_module,
            )
            worker_name = "aihub-go"
        elif args.command:
            result = CommandWorker(
                runtime_dir=args.runtime_dir,
                timeout_seconds=args.timeout,
            ).run_packet(args.packet_dir, args.command)
            worker_name = "command"
        else:
            result = LocalDryRunWorker(runtime_dir=args.runtime_dir).run_packet(args.packet_dir)
            worker_name = "local-dry-run"
        print(f"packet_id      : {result.packet.packet_id}")
        print(f"project_id     : {result.packet.project_id}")
        print(f"worker         : {worker_name}")
        print(f"status         : {result.summary.status}")
        print(f"report_path    : {result.report_path}")
        return _worker_exit_code(result.summary.status)

    args = build_parser().parse_args(argv)
    orchestrator = Orchestrator(runtime_dir=args.runtime_dir)
    result = rdgoal(
        orchestrator,
        args.project_path,
        args.requirement,
        operation=args.operation,
        targets=args.target,
        apply_rdinit=args.apply_rdinit,
        contracts_dir=args.contracts_dir if args.contracts_dir else None,
    )

    print(f"project_id     : {result.project_id}")
    print(f"project_root   : {result.project_root}")
    print(f"governed       : {result.governed} ({result.rdinit_action})")
    print(f"contract       : {result.contract_path}")
    print(f"decision       : {result.dispatch.decision.mode.value}")
    print(f"dispatch_ready : {result.dispatch.dispatch_ready}")
    if result.dispatch.packet:
        print(f"packet         : {result.dispatch.packet.packet_dir}")
    if result.dispatch.guard.snapshot:
        print(f"snapshot       : {result.dispatch.guard.snapshot.reference}")
    for note in result.notes:
        print(f"note           : {note}")

    print()
    print("--- sub-agent objective ---")
    print(result.dispatch.objective.text)

    if args.digest:
        print()
        print(orchestrator.render_digest_markdown())
    return 0


if __name__ == "__main__":
    sys.exit(main())
