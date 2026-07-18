"""Zero-configuration activation commands for governed Obsidian memory."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

from ._common import _wants_help
from ._usage import MEMORY_USAGE


def _default_state_dir() -> Path:
    return Path.home() / ".devframe" / "obsidian-memory"


def _default_codex_home() -> Path:
    configured = str(os.environ.get("CODEX_HOME") or "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def _runtime_root_for(state_dir: Path) -> Path:
    from ..obsidian_memory_activation import ISOLATED_RUNTIME_DIR

    return state_dir / ISOLATED_RUNTIME_DIR


def _runtime_python_for(state_dir: Path) -> Path:
    runtime = _runtime_root_for(state_dir)
    if os.name == "nt":
        return runtime / "Scripts" / "python.exe"
    return runtime / "bin" / "python"


def _print_result(result: dict[str, object], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return
    print(f"Memory status: {result.get('status', 'unknown')}")
    if result.get("vaultName"):
        print(f"  vault   : {result['vaultName']}")
    if result.get("upstream"):
        print(f"  runtime : {result['upstream']}")
    if result.get("enabledTools"):
        print(f"  tools   : {', '.join(str(item) for item in result['enabledTools'])}")
    if result.get("runtimeRefreshRequired"):
        print("  runtime : managed facade refresh required on confirmation")
    elif result.get("runtimeRefreshed"):
        print("  runtime : managed facade refreshed")
    if result.get("restartRequired"):
        print("  next    : restart Codex to load the managed MCP server and SessionStart hook")


def _activate() -> int:
    from ..obsidian_memory_activation import (
        ObsidianMemoryActivationError,
        STATE_FILE,
        _activate_obsidian_memory_unlocked,
        _codex_lifecycle_lock,
        _lifecycle_lock,
        activate_obsidian_memory,
        _recover_lifecycle_transaction,
        _remove_new_runtime,
        _require_plain_directory,
        _require_plain_write_root,
        provision_obsidian_memory_runtime,
    )

    parser = argparse.ArgumentParser(prog="devframe memory activate")
    parser.add_argument("--vault", required=True, help="Dedicated disposable Obsidian vault")
    parser.add_argument("--codex-home", default=None, help="Codex home (default: CODEX_HOME or ~/.codex)")
    parser.add_argument("--state-dir", default=None, help="Private DevFrame activation state")
    parser.add_argument("--runtime-python", default=None, help="Pre-provisioned exact memory runtime")
    parser.add_argument("--source-package", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--confirm", action="store_true", help="Install and activate after preview")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(sys.argv[3:])

    state_dir = Path(args.state_dir).expanduser() if args.state_dir else _default_state_dir()
    codex_home = Path(args.codex_home).expanduser() if args.codex_home else _default_codex_home()
    runtime_python = (
        Path(args.runtime_python).expanduser()
        if args.runtime_python
        else _runtime_python_for(state_dir)
    )
    try:
        if args.runtime_python:
            expected_runtime = _runtime_python_for(state_dir)
            if os.path.normcase(str(runtime_python.absolute())) != os.path.normcase(
                str(expected_runtime.absolute())
            ):
                raise ObsidianMemoryActivationError(
                    "--runtime-python must be the managed runtime under --state-dir"
                )
        if args.confirm and not args.runtime_python:
            resolved_state_dir = _require_plain_write_root(
                state_dir,
                kind="activation state directory",
            )
            resolved_codex_home = _require_plain_directory(
                codex_home,
                kind="Codex home",
            )
            with _codex_lifecycle_lock(resolved_codex_home):
                with _lifecycle_lock(resolved_state_dir):
                    _recover_lifecycle_transaction(
                        resolved_codex_home,
                        resolved_state_dir,
                    )
                    runtime_root = _runtime_root_for(resolved_state_dir)
                    runtime_existed_before = runtime_root.exists()
                    try:
                        runtime_python = provision_obsidian_memory_runtime(
                            state_dir=resolved_state_dir,
                            source_package=(
                                Path(args.source_package) if args.source_package else None
                            ),
                        )
                        result = _activate_obsidian_memory_unlocked(
                            vault_root=Path(args.vault),
                            codex_home=resolved_codex_home,
                            state_dir=resolved_state_dir,
                            runtime_python=runtime_python,
                            confirm=True,
                            now=lambda: datetime.now(timezone.utc).isoformat(),
                        )
                    except Exception:
                        if (
                            not runtime_existed_before
                            and not (resolved_state_dir / STATE_FILE).exists()
                        ):
                            _remove_new_runtime(resolved_state_dir, runtime_root)
                        raise
        else:
            result = activate_obsidian_memory(
                vault_root=Path(args.vault),
                codex_home=codex_home,
                state_dir=state_dir,
                runtime_python=runtime_python,
                confirm=args.confirm,
                now=lambda: datetime.now(timezone.utc).isoformat(),
            )
    except ObsidianMemoryActivationError as exc:
        if args.format == "json":
            print(json.dumps({"error": "memory_activation_rejected", "detail": str(exc)}, ensure_ascii=True, indent=2))
        else:
            print(f"ERROR: memory activation rejected: {exc}", file=sys.stderr)
        return 2
    _print_result(result, args.format)
    return 0


def _status() -> int:
    from ..obsidian_memory_activation import (
        ObsidianMemoryActivationError,
        obsidian_memory_status,
    )

    parser = argparse.ArgumentParser(prog="devframe memory status")
    parser.add_argument("--state-dir", default=None)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(sys.argv[3:])
    state_dir = Path(args.state_dir).expanduser() if args.state_dir else _default_state_dir()
    try:
        result = obsidian_memory_status(state_dir=state_dir)
    except ObsidianMemoryActivationError as exc:
        if args.format == "json":
            print(json.dumps({"error": "memory_status_rejected", "detail": str(exc)}, ensure_ascii=True, indent=2))
        else:
            print(f"ERROR: memory status unavailable: {exc}", file=sys.stderr)
        return 2
    _print_result(result, args.format)
    return 0


def _repair() -> int:
    from ..obsidian_memory_activation import (
        ObsidianMemoryActivationError,
        UPSTREAM_PACKAGE,
        _codex_lifecycle_lock,
        _default_runtime_probe,
        _lifecycle_lock,
        _load_active_state,
        _recover_lifecycle_transaction,
        _repair_obsidian_memory_unlocked,
        _require_plain_directory,
        _require_plain_write_root,
        _runtime_marker_dependencies_match,
        _runtime_marker_matches,
        provision_obsidian_memory_runtime,
    )

    parser = argparse.ArgumentParser(prog="devframe memory repair")
    parser.add_argument("--codex-home", default=None)
    parser.add_argument("--state-dir", default=None)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Restore the exact missing managed MCP config block",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(sys.argv[3:])
    state_dir = Path(args.state_dir).expanduser() if args.state_dir else _default_state_dir()
    codex_home = Path(args.codex_home).expanduser() if args.codex_home else _default_codex_home()

    def runtime_refresh_preflight(
        resolved_codex_home: Path,
        resolved_state_dir: Path,
    ) -> dict[str, object]:
        result = _repair_obsidian_memory_unlocked(
            codex_home=resolved_codex_home,
            state_dir=resolved_state_dir,
            confirm=False,
            now=lambda: datetime.now(timezone.utc).isoformat(),
            runtime_probe=lambda _runtime, _package: True,
        )
        loaded = _load_active_state(
            resolved_state_dir,
            runtime_probe=lambda _runtime, _package: True,
            validate_managed_codex_files=False,
        )
        if loaded is None:
            raise ObsidianMemoryActivationError("memory activation is unavailable")
        recorded_runtime = loaded[3]
        expected_runtime = _runtime_python_for(resolved_state_dir)
        if os.path.normcase(str(recorded_runtime.absolute())) != os.path.normcase(
            str(expected_runtime.absolute())
        ):
            raise ObsidianMemoryActivationError(
                "repair requires the managed runtime under --state-dir"
            )
        runtime_root = _runtime_root_for(resolved_state_dir)
        if runtime_root.exists() and (
            not recorded_runtime.is_file()
            or not _runtime_marker_dependencies_match(recorded_runtime)
        ):
            raise ObsidianMemoryActivationError(
                "existing memory runtime provenance is unavailable"
            )
        runtime_ready = (
            recorded_runtime.is_file()
            and _runtime_marker_matches(recorded_runtime)
            and _default_runtime_probe(recorded_runtime, UPSTREAM_PACKAGE)
        )
        result["runtimeRefreshRequired"] = not runtime_ready
        return result

    try:
        resolved_state_dir = _require_plain_write_root(
            state_dir,
            kind="activation state directory",
        )
        resolved_codex_home = _require_plain_directory(
            codex_home,
            kind="Codex home",
        )
        if args.confirm:
            with _codex_lifecycle_lock(resolved_codex_home):
                with _lifecycle_lock(resolved_state_dir):
                    _recover_lifecycle_transaction(
                        resolved_codex_home,
                        resolved_state_dir,
                    )
                    preview = runtime_refresh_preflight(
                        resolved_codex_home,
                        resolved_state_dir,
                    )
                    provision_obsidian_memory_runtime(
                        state_dir=resolved_state_dir,
                    )
                    result = _repair_obsidian_memory_unlocked(
                        codex_home=resolved_codex_home,
                        state_dir=resolved_state_dir,
                        confirm=True,
                        now=lambda: datetime.now(timezone.utc).isoformat(),
                    )
                    result["runtimeRefreshed"] = bool(
                        preview["runtimeRefreshRequired"]
                    )
        else:
            result = runtime_refresh_preflight(
                resolved_codex_home,
                resolved_state_dir,
            )
    except ObsidianMemoryActivationError as exc:
        if args.format == "json":
            print(json.dumps({"error": "memory_repair_rejected", "detail": str(exc)}, ensure_ascii=True, indent=2))
        else:
            print(f"ERROR: memory repair rejected: {exc}", file=sys.stderr)
        return 2
    _print_result(result, args.format)
    return 0 if args.confirm or result.get("status") == "active" else 3


def _deactivate() -> int:
    from ..obsidian_memory_activation import (
        ObsidianMemoryActivationError,
        deactivate_obsidian_memory,
    )

    parser = argparse.ArgumentParser(prog="devframe memory deactivate")
    parser.add_argument("--codex-home", default=None)
    parser.add_argument("--state-dir", default=None)
    parser.add_argument("--confirm", action="store_true", help="Remove the exact managed activation")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(sys.argv[3:])
    state_dir = Path(args.state_dir).expanduser() if args.state_dir else _default_state_dir()
    codex_home = Path(args.codex_home).expanduser() if args.codex_home else _default_codex_home()
    try:
        result = deactivate_obsidian_memory(
            codex_home=codex_home,
            state_dir=state_dir,
            confirm=args.confirm,
        )
    except ObsidianMemoryActivationError as exc:
        if args.format == "json":
            print(json.dumps({"error": "memory_deactivation_rejected", "detail": str(exc)}, ensure_ascii=True, indent=2))
        else:
            print(f"ERROR: memory deactivation rejected: {exc}", file=sys.stderr)
        return 2
    _print_result(result, args.format)
    return 0 if args.confirm or result.get("status") == "inactive" else 3


def _serve() -> int:
    from ..obsidian_memory_activation import (
        ObsidianMemoryActivationError,
        serve_obsidian_memory,
    )

    parser = argparse.ArgumentParser(prog="devframe memory serve")
    parser.add_argument("--state-dir", required=True)
    args = parser.parse_args(sys.argv[3:])
    try:
        serve_obsidian_memory(state_dir=Path(args.state_dir))
    except ObsidianMemoryActivationError as exc:
        print(f"memory server unavailable: {exc}", file=sys.stderr)
        return 2
    return 0


def _recall_hook() -> int:
    from ..obsidian_memory_activation import HOOK_MARKER, recall_hook_output

    parser = argparse.ArgumentParser(prog="devframe memory recall-hook")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--managed-marker", required=True)
    args = parser.parse_args(sys.argv[3:])
    if args.managed_marker != HOOK_MARKER:
        return 2
    raw = sys.stdin.read(65_537)
    if len(raw) > 65_536:
        hook_input: dict[str, object] = {}
    else:
        try:
            parsed = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            parsed = {}
        hook_input = parsed if isinstance(parsed, dict) else {}
    print(
        recall_hook_output(
            state_dir=Path(args.state_dir),
            hook_input=hook_input,
        ),
        end="",
    )
    return 0


def cmd_memory() -> int:
    subcommand = sys.argv[2] if len(sys.argv) > 2 else ""
    if subcommand == "activate":
        return _activate()
    if subcommand == "status":
        return _status()
    if subcommand == "repair":
        return _repair()
    if subcommand == "deactivate":
        return _deactivate()
    if subcommand == "serve":
        return _serve()
    if subcommand == "recall-hook":
        return _recall_hook()
    if not subcommand or _wants_help(sys.argv[2:]):
        print(MEMORY_USAGE)
        return 0
    print(f"Unknown memory subcommand: {subcommand}")
    return 1
