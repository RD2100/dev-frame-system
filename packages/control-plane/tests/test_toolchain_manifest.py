"""Production-path tests for read-only toolchain manifest preview."""

from __future__ import annotations

import json
import sys

from control_plane.cli.app import main
from control_plane.toolchain_manifest import validate_toolchain_manifest


def test_toolchain_manifest_preview_normalizes_valid_commands(tmp_path):
    manifest = tmp_path / "toolchain.yaml"
    manifest.write_text(
        "toolchain_id: python-ci\n"
        "compiler: python\n"
        "working_directory: src\n"
        "commands:\n"
        "  build: [python, -m, compileall, src]\n"
        "  test: [python, -m, pytest]\n"
        "  lint: [ruff, check, src]\n",
        encoding="utf-8",
    )

    result = validate_toolchain_manifest(manifest)

    assert result["status"] == "pass", result["errors"]
    assert result["execution"] == "explicit_only"
    assert result["commands"]["build"] == ["python", "-m", "compileall", "src"]
    assert result["adapter_contract"] == {"domain": "code", "profile": "toolchain"}


def test_toolchain_manifest_preview_fails_closed_on_scope_and_shape(tmp_path):
    manifest = tmp_path / "invalid.yaml"
    manifest.write_text(
        "toolchain_id: bad id\n"
        "working_directory: C:/outside\n"
        "environment: {TOKEN: forbidden}\n"
        "commands:\n"
        "  build: make all\n"
        "  test: [pytest, '']\n"
        "  deploy: [ship]\n",
        encoding="utf-8",
    )

    result = validate_toolchain_manifest(manifest)

    assert result["status"] == "fail"
    assert any("working_directory" in error for error in result["errors"])
    assert any("unsupported fields" in error for error in result["errors"])
    assert any("unsupported names" in error for error in result["errors"])
    assert any("commands.build" in error for error in result["errors"])
    assert any("commands.test" in error for error in result["errors"])


def test_toolchain_preview_cli_is_read_only_json(tmp_path, monkeypatch, capsys):
    manifest = tmp_path / "toolchain.yaml"
    manifest.write_text(
        "toolchain_id: cli-fixture\ncommands:\n  build: [make]\n  test: [make, test]\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "toolchain",
            "preview",
            "--manifest",
            str(manifest),
            "--format",
            "json",
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert '"status": "pass"' in output
    assert '"execution": "explicit_only"' in output
    assert not (tmp_path / "toolchain-preview.json").exists()


def test_toolchain_manifest_fails_closed_on_mixed_keys_and_control_tokens(tmp_path):
    mixed_keys = tmp_path / "mixed-keys.yaml"
    mixed_keys.write_text(
        "toolchain_id: valid\n1: unexpected\ncommands:\n  build: [make]\n  test: [pytest]\n  true: [bad]\n",
        encoding="utf-8",
    )
    control_token = tmp_path / "control-token.yaml"
    control_token.write_text(
        json.dumps(
            {
                "toolchain_id": "control-token",
                "commands": {
                    "build": ["\tmake"],
                    "test": ["pytest\f"],
                    "lint": ["ruff\x7f"],
                },
            }
        ),
        encoding="utf-8",
    )

    mixed_result = validate_toolchain_manifest(mixed_keys)
    control_result = validate_toolchain_manifest(control_token)

    assert mixed_result["status"] == "fail"
    assert any("unsupported fields" in error for error in mixed_result["errors"])
    assert any("unsupported names" in error for error in mixed_result["errors"])
    assert control_result["status"] == "fail"
    assert sum(
        "unsafe control character" in error for error in control_result["errors"]
    ) == 3
