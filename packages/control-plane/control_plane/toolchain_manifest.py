"""Read-only validation for provider-neutral toolchain manifests."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any

import yaml


_COMMAND_NAMES = ("build", "test", "lint")
_TOOLCHAIN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _unsupported_keys(value: dict[Any, Any], allowed: set[str]) -> list[str]:
    return sorted(
        repr(key)
        for key in value
        if not isinstance(key, str) or key not in allowed
    )


def _normalize_command(value: Any, name: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(f"commands.{name} must be a non-empty string token list")
        return []
    if any(
        any(ord(character) < 32 or ord(character) == 127 for character in item)
        for item in value
    ):
        errors.append(f"commands.{name} contains an unsafe control character")
    tokens = [item.strip() for item in value]
    if not tokens:
        errors.append(f"commands.{name} must not be empty")
    if any(not token for token in tokens):
        errors.append(f"commands.{name} contains an empty token")
    return tokens


def _validate_working_directory(value: Any, errors: list[str]) -> str:
    if value is None:
        return "."
    if not isinstance(value, str) or not value.strip():
        errors.append("working_directory must be a relative non-empty string")
        return "."
    text = value.strip().replace("\\", "/")
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or text.startswith("//")
        or re.match(r"^[A-Za-z]:", text)
        or ".." in path.parts
    ):
        errors.append("working_directory must stay within the project")
    return text


def validate_toolchain_manifest(source: str | Path) -> dict[str, Any]:
    """Return a stable preview contract; never executes or writes the manifest."""
    path = Path(source).resolve()
    try:
        source_bytes = path.read_bytes()
    except OSError as exc:
        return {
            "status": "fail",
            "errors": [f"cannot read toolchain manifest: {exc}"],
            "manifest_path": str(path),
            "execution": "explicit_only",
        }
    return validate_toolchain_manifest_bytes(source_bytes, path)


def validate_toolchain_manifest_bytes(
    source_bytes: bytes,
    source: str | Path,
) -> dict[str, Any]:
    """Validate one immutable byte snapshot for preview or execution."""
    path = Path(source).resolve()
    errors: list[str] = []
    try:
        payload = yaml.safe_load(source_bytes.decode("utf-8"))
    except (UnicodeError, yaml.YAMLError) as exc:
        return {
            "status": "fail",
            "errors": [f"cannot read toolchain manifest: {exc}"],
            "manifest_path": str(path),
            "execution": "explicit_only",
        }
    if not isinstance(payload, dict):
        errors.append("toolchain manifest must be a mapping")
        payload = {}
    unknown_fields = _unsupported_keys(
        payload,
        {"toolchain_id", "compiler", "working_directory", "commands"},
    )
    if unknown_fields:
        errors.append(f"toolchain manifest contains unsupported fields: {unknown_fields}")

    raw_toolchain_id = payload.get("toolchain_id")
    toolchain_id = raw_toolchain_id.strip() if isinstance(raw_toolchain_id, str) else ""
    if not _TOOLCHAIN_ID.fullmatch(toolchain_id):
        errors.append("toolchain_id must match [A-Za-z0-9][A-Za-z0-9._-]*")
    compiler = payload.get("compiler", "unspecified")
    if not isinstance(compiler, str) or not compiler.strip():
        errors.append("compiler must be a non-empty string")
        compiler = "unspecified"
    commands = payload.get("commands")
    if not isinstance(commands, dict):
        errors.append("commands must be a mapping")
        commands = {}
    unknown_commands = _unsupported_keys(commands, set(_COMMAND_NAMES))
    if unknown_commands:
        errors.append(f"commands contains unsupported names: {unknown_commands}")
    normalized_commands: dict[str, list[str]] = {}
    for name in _COMMAND_NAMES:
        if name in commands:
            normalized_commands[name] = _normalize_command(commands[name], name, errors)
    for name in ("build", "test"):
        if name not in commands:
            errors.append(f"commands.{name} is required")
    working_directory = _validate_working_directory(
        payload.get("working_directory"), errors
    )
    return {
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "manifest_path": str(path),
        "toolchain_id": toolchain_id,
        "compiler": compiler.strip() if isinstance(compiler, str) else "unspecified",
        "working_directory": working_directory,
        "commands": normalized_commands,
        "execution": "explicit_only",
        "adapter_contract": {"domain": "code", "profile": "toolchain"},
    }
