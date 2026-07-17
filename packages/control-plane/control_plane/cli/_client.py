"""DevFrame client commands: local agent client launcher and client doctor."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from ._common import _is_loopback_host, _wants_help
from ._usage import CLIENT_USAGE


def cmd_client_doctor(*, prog: str = "devframe client doctor") -> int:
    import argparse

    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--runtime-dir", default=None, help="Local devframe runtime directory")
    parser.add_argument("--t3-root", default=None, help="T3 Code checkout root")
    parser.add_argument("--host", default="127.0.0.1", help="Expected dashboard bind host")
    parser.add_argument("--port", type=int, default=8765, help="Expected dashboard bind port")
    parser.add_argument("--lang", choices=["en", "zh-CN"], default="zh-CN", help="Expected dashboard language")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Doctor output format")
    parser.add_argument("--force", action="store_true", help="Allow overwriting existing T3 bridge files")
    parser.add_argument("--allow-remote", action="store_true", help="Allow binding to a non-loopback host")
    parser.add_argument("--cdp-endpoint", default=None, help="Loopback Electron/T3 CDP endpoint for renderer state probing (e.g. http://127.0.0.1:9222)")
    args = parser.parse_args(sys.argv[3:])

    from ..client_launcher import check_client_readiness, render_client_readiness_text

    try:
        result = check_client_readiness(
            args.runtime_dir,
            t3_root=args.t3_root,
            host=args.host,
            port=args.port,
            lang=args.lang,
            force=args.force,
            allow_remote=args.allow_remote,
            cdp_endpoint=args.cdp_endpoint,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=True))
    else:
        print(render_client_readiness_text(result), end="")
    return 0 if result.get("status") in {"pass", "pass-with-warnings"} else 1


def cmd_client() -> int:
    import argparse

    raw_args = sys.argv[2:]
    if _wants_help(raw_args[:1]):
        print(CLIENT_USAGE)
        return 0

    subcommand = "serve"
    if raw_args and raw_args[0] in {"serve", "plan", "bridge", "t3desktop", "smoke", "doctor"}:
        subcommand = raw_args[0]
        raw_args = raw_args[1:]
    elif raw_args and not raw_args[0].startswith("-"):
        print(f"Unknown client subcommand: {raw_args[0]}")
        print(CLIENT_USAGE)
        return 1

    from ..client_launcher import (
        build_client_launch_plan,
        render_client_launch_plan_json,
        render_client_launch_plan_text,
        serve_local_agent_client,
        serve_t3_desktop_client,
    )
    from ..t3_bridge_bundle import (
        build_t3_bridge_bundle,
        install_t3_bridge_bundle,
        render_t3_bridge_bundle_json,
        render_t3_bridge_bundle_text,
        write_t3_bridge_bundle,
    )

    parser = argparse.ArgumentParser(prog=f"devframe client {subcommand}")
    parser.add_argument("--runtime-dir", default=None, help="Local devframe runtime directory")
    parser.add_argument("--paper-project", action="append", default=[], help="Paper iteration project directory to include")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8765, help="Bind port")
    parser.add_argument("--lang", choices=["en", "zh-CN"], default="zh-CN", help="Initial dashboard language")
    parser.add_argument("--refresh-seconds", type=int, default=5, help="Browser refresh interval; use 0 to disable")
    parser.add_argument("--dry-run", action="store_true", help="Print the launch plan without starting the server")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Plan output format for --dry-run or plan")
    parser.add_argument("--open", action="store_true", help="Open the local client URL in the default browser")
    parser.add_argument("--allow-remote", action="store_true", help="Allow binding to a non-loopback host")
    parser.add_argument("--output", default=None, help="Write a standalone T3 bridge bundle directory")
    parser.add_argument("--t3-root", default=None, help="Install bridge files into a local T3 Code checkout")
    parser.add_argument("--force", action="store_true", help="Overwrite existing generated bridge files")
    parser.add_argument(
        "--overwrite-bridge",
        action="store_true",
        help="Overwrite generated bridge files without cleaning up stale T3 processes",
    )
    parser.add_argument("--cdp-endpoint", default=None, help="Loopback CDP endpoint for renderer state probing")
    parser.add_argument("--prod", action="store_true", help="Run the prebuilt production T3 Desktop (fast startup, low memory) instead of the Vite dev server")
    args = parser.parse_args(raw_args)

    if not args.allow_remote and not _is_loopback_host(args.host):
        print("ERROR: client exposes local runtime paths; use --allow-remote to bind outside loopback.")
        return 1

    if subcommand == "bridge":
        plan = build_client_launch_plan(
            args.runtime_dir,
            host=args.host,
            port=args.port,
            lang=args.lang,
            paper_project_dirs=args.paper_project,
        )
        bundle = build_t3_bridge_bundle(plan)
        written_paths: list[Path] = []
        try:
            if args.output:
                written_paths.extend(write_t3_bridge_bundle(args.output, bundle))
            if args.t3_root:
                written_paths.extend(install_t3_bridge_bundle(args.t3_root, bundle, force=args.force))
        except (FileExistsError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        if args.format == "json":
            print(render_t3_bridge_bundle_json(bundle))
        else:
            print(render_t3_bridge_bundle_text(bundle), end="")
            if written_paths:
                for path in written_paths:
                    print(f"wrote       : {path}")
            else:
                print("No files written; pass --output or --t3-root to materialize the bridge.")
        return 0

    if subcommand == "t3desktop":
        return serve_t3_desktop_client(
            args.runtime_dir,
            t3_root=args.t3_root,
            host=args.host,
            port=args.port,
            lang=args.lang,
            paper_project_dirs=args.paper_project,
            force=args.force or args.overwrite_bridge,
            cleanup_stale=args.force,
            open_browser=args.open,
            refresh_seconds=args.refresh_seconds,
            mode="prod" if args.prod else "dev",
        )

    if subcommand == "doctor":
        return cmd_client_doctor()

    if subcommand == "smoke":
        parser = argparse.ArgumentParser(prog="devframe client smoke")
        parser.add_argument("--runtime-dir", default=None, help="Local devframe runtime directory")
        parser.add_argument("--paper-project", action="append", default=[], help="Paper iteration project directory to include")
        parser.add_argument("--host", default="127.0.0.1", help="Bind host")
        parser.add_argument("--port", type=int, default=0, help="Bind port; 0 for auto-selection")
        parser.add_argument("--lang", choices=["en", "zh-CN"], default="zh-CN", help="Initial dashboard language")
        parser.add_argument("--format", choices=["text", "json"], default="text", help="Smoke output format")
        parser.add_argument("--t3-root", default=None, help="Install bridge files into a local T3 Code checkout")
        parser.add_argument("--force", action="store_true", help="Overwrite existing generated bridge files")
        parser.add_argument("--allow-remote", action="store_true", help="Allow binding to a non-loopback host")
        args = parser.parse_args(raw_args)

        if not args.allow_remote and not _is_loopback_host(args.host):
            print("ERROR: client exposes local runtime paths; use --allow-remote to bind outside loopback.")
            return 1

        from ..client_launcher import smoke_local_agent_client
        return smoke_local_agent_client(
            args.runtime_dir,
            host=args.host,
            port=args.port,
            lang=args.lang,
            paper_project_dirs=args.paper_project,
            output_format=args.format,
            t3_root=args.t3_root,
            force=args.force,
        )

    if subcommand == "plan" or args.dry_run:
        plan = build_client_launch_plan(
            args.runtime_dir,
            host=args.host,
            port=args.port,
            lang=args.lang,
            paper_project_dirs=args.paper_project,
        )
        if args.format == "json":
            print(render_client_launch_plan_json(plan))
        else:
            print(render_client_launch_plan_text(plan), end="")
        return 0

    serve_local_agent_client(
        args.runtime_dir,
        host=args.host,
        port=args.port,
        refresh_seconds=args.refresh_seconds,
        lang=args.lang,
        paper_project_dirs=args.paper_project,
        open_browser=args.open,
    )
    return 0
