"""Provider-neutral executor CLI projections."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..executor_readiness import (
    ExecutorReadinessRegistry,
    is_local_absolute_path,
)
from ..pi_executor_adapter import create_pi_readiness_adapter


def cmd_executor_readiness(
    argv: list[str],
    *,
    prog: str = "devframe executor readiness",
) -> int:
    """Project one registered driver's bounded local readiness result."""

    registry = _default_readiness_registry()
    drivers = registry.drivers
    parser = argparse.ArgumentParser(prog=prog)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--driver", choices=drivers)
    selection.add_argument("--list", action="store_true", dest="list_drivers")
    parser.add_argument("--project", default=".")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    if args.list_drivers:
        _emit_driver_list(drivers, args.format)
        return 0

    project_root = _resolve_local_project(args.project)
    if project_root is None:
        return _emit_blocked(args.driver, "PROJECT_INVALID", args.format, exit_code=2)

    try:
        result = registry.resolve(args.driver).probe(project_root)
    except Exception:
        return _emit_blocked(
            args.driver,
            "READINESS_FAILED",
            args.format,
            exit_code=1,
        )
    _emit(result.payload(args.driver), args.format)
    return 0 if result.status == "ready" else 1


def _default_readiness_registry() -> ExecutorReadinessRegistry:
    return ExecutorReadinessRegistry((create_pi_readiness_adapter(),))


def _resolve_local_project(value: object) -> Path | None:
    if not isinstance(value, str) or not value or "\x00" in value:
        return None
    if value.startswith(("\\\\", "//")):
        return None
    raw = Path(value)
    if raw.is_absolute() and not is_local_absolute_path(value):
        return None
    try:
        resolved = raw.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not resolved.is_dir() or not is_local_absolute_path(str(resolved)):
        return None
    return resolved


def _emit_blocked(driver: str, reason: str, output_format: str, *, exit_code: int) -> int:
    _emit(
        {
            "driver": driver,
            "reason": reason,
            "status": "blocked",
        },
        output_format,
    )
    return exit_code


def _emit(payload: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
        return
    print("Executor readiness")
    for key in sorted(payload):
        print(f"{key}: {payload[key]}")


def _emit_driver_list(drivers: tuple[str, ...], output_format: str) -> None:
    if output_format == "json":
        print(
            json.dumps(
                {"drivers": list(drivers)},
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return
    print("Executor readiness drivers")
    for driver in drivers:
        print(driver)
