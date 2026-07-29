from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import control_plane.mcp_consent as mcp_consent  # noqa: E402
from control_plane.cli.app import main as cli_main  # noqa: E402
from control_plane.mcp_server import handle_mcp_jsonrpc  # noqa: E402
from control_plane.obsidian_memory import (  # noqa: E402
    approve_project_plan,
    recall_session_project_plan,
    resolve_session_project,
    stage_project_plan,
)
from control_plane.runtime_store import JournalEvent, RuntimeStore  # noqa: E402


def _template_base64(value: object) -> str:
    return base64.b64encode(str(value).encode("utf-8")).decode("ascii")


def _session_hook_context(stdout: str) -> str:
    payload = json.loads(stdout)
    assert payload["continue"] is True
    assert payload["suppressOutput"] is True
    hook_output = payload["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "SessionStart"
    return hook_output["additionalContext"]


def _vault(root: Path) -> Path:
    vault = root / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / "wiki" / "memories").mkdir(parents=True)
    return vault


def _project(root: Path, *, git: bool = False) -> Path:
    project = root
    handoff = project / "docs" / "status" / "HANDOFF.md"
    handoff.parent.mkdir(parents=True)
    handoff.write_text("# Execution Root\n\nCurrent milestone: session memory.\n", encoding="utf-8")
    if git:
        subprocess.run(
            ["git", "init", "--quiet", str(project)],
            check=True,
            capture_output=True,
            text=True,
        )
    return project


def _registered_events(runtime: Path) -> list[dict[str, object]]:
    return [
        event
        for event in RuntimeStore(runtime_dir=runtime).read_all()
        if event.get("event_type") == "project_registered"
    ]


def _authorize(session_id: str, runtime: Path) -> None:
    mcp_consent.register_connection(session_id, "test-client", runtime_dir=runtime)
    mcp_consent.decide(session_id, "allow_once", runtime_dir=runtime)


def test_nested_git_cwd_resolves_once_to_repository_root(tmp_path):
    runtime = tmp_path / "runtime"
    project = _project(tmp_path / "repo", git=True)
    nested = project / "src" / "deep"
    nested.mkdir(parents=True)

    first = resolve_session_project(cwd=nested, runtime_dir=runtime)
    second = resolve_session_project(cwd=project, runtime_dir=runtime)

    assert Path(first["projectRoot"]) == project.resolve()
    assert second["projectId"] == first["projectId"]
    assert first["registered"] is True
    assert second["registered"] is False
    assert len(_registered_events(runtime)) == 1


@pytest.mark.skipif(os.name != "nt", reason="Windows path case normalization")
def test_windows_path_case_variants_keep_one_project_identity(tmp_path):
    runtime = tmp_path / "runtime"
    project = _project(tmp_path / "CaseProject")

    lower = resolve_session_project(cwd=str(project).lower(), runtime_dir=runtime)
    upper = resolve_session_project(cwd=str(project).upper(), runtime_dir=runtime)

    assert lower["projectId"] == upper["projectId"]
    assert len(_registered_events(runtime)) == 1


def test_non_git_same_name_roots_are_stable_and_isolated(tmp_path):
    runtime = tmp_path / "runtime"
    first_root = tmp_path / "one" / "same-name"
    second_root = tmp_path / "two" / "same-name"
    first_root.mkdir(parents=True)
    second_root.mkdir(parents=True)

    first = resolve_session_project(cwd=first_root, runtime_dir=runtime)
    second = resolve_session_project(cwd=second_root, runtime_dir=runtime)
    first_again = resolve_session_project(cwd=first_root, runtime_dir=runtime)

    assert first["projectId"].startswith("same-name-")
    assert second["projectId"].startswith("same-name-")
    assert first["projectId"] != second["projectId"]
    assert first_again["projectId"] == first["projectId"]
    assert len(_registered_events(runtime)) == 2


def test_existing_exact_root_registration_preserves_legacy_project_id(tmp_path):
    runtime = tmp_path / "runtime"
    project = _project(tmp_path / "legacy")
    RuntimeStore(runtime_dir=runtime).append(
        JournalEvent(
            event_type="project_registered",
            project_id="legacy-project",
            payload={"project_root": str(project.resolve()), "priority": 3},
        )
    )

    resolved = resolve_session_project(cwd=project, runtime_dir=runtime)

    assert resolved["projectId"] == "legacy-project"
    assert resolved["registered"] is False
    assert len(_registered_events(runtime)) == 1


def test_session_recall_keeps_same_name_project_plans_isolated(tmp_path):
    runtime = tmp_path / "runtime"
    vault = _vault(tmp_path)
    first_root = _project(tmp_path / "one" / "same-name")
    second_root = _project(tmp_path / "two" / "same-name")
    first = resolve_session_project(cwd=first_root, runtime_dir=runtime)
    second = resolve_session_project(cwd=second_root, runtime_dir=runtime)

    first_stage = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=first_root,
        project_id=str(first["projectId"]),
        plan_markdown="First project's bounded plan.",
    )
    second_stage = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=second_root,
        project_id=str(second["projectId"]),
        plan_markdown="Second project's bounded plan.",
    )
    approve_project_plan(runtime, first_stage["request_id"], confirm=True)
    approve_project_plan(runtime, second_stage["request_id"], confirm=True)

    first_recall = recall_session_project_plan(
        runtime,
        vault_root=vault,
        cwd=first_root,
    )
    second_recall = recall_session_project_plan(
        runtime,
        vault_root=vault,
        cwd=second_root,
    )

    assert first_recall["status"] == "current"
    assert first_recall["plan"] == "First project's bounded plan."
    assert second_recall["status"] == "current"
    assert second_recall["plan"] == "Second project's bounded plan."
    assert str(first_root) not in json.dumps(first_recall)
    assert str(second_root) not in json.dumps(second_recall)
    assert str(vault) not in json.dumps(first_recall)


def test_new_project_without_plan_returns_explicit_missing(tmp_path):
    runtime = tmp_path / "runtime"
    vault = _vault(tmp_path)
    project = tmp_path / "new-project"
    project.mkdir()

    result = recall_session_project_plan(runtime, vault_root=vault, cwd=project)

    assert result["status"] == "missing"
    assert result["reason"] == "no_current_plan"
    assert result["plan"] == ""
    assert result["authority"] == "untrusted_guidance_only"
    assert result["projectId"]
    assert "projectRoot" not in result


def test_unavailable_vault_fails_open_without_path_disclosure(tmp_path):
    runtime = tmp_path / "runtime"
    project = tmp_path / "project"
    project.mkdir()
    missing_vault = tmp_path / "missing-vault"

    result = recall_session_project_plan(
        runtime,
        vault_root=missing_vault,
        cwd=project,
    )

    assert result == {
        "projectId": result["projectId"],
        "status": "unavailable",
        "reason": "memory_unavailable",
        "authority": "untrusted_guidance_only",
        "relativePath": "",
        "plan": "",
    }
    assert str(project) not in json.dumps(result)
    assert str(missing_vault) not in json.dumps(result)


def test_invalid_relative_session_cwd_fails_open(tmp_path):
    result = recall_session_project_plan(
        tmp_path / "runtime",
        vault_root=tmp_path / "vault",
        cwd="relative-project",
    )

    assert result["status"] == "unavailable"
    assert result["reason"] == "project_unavailable"
    assert result["projectId"] == ""
    assert result["plan"] == ""


def test_session_registration_makes_project_visible_to_existing_mcp_resolver(
    tmp_path,
    monkeypatch,
):
    runtime = tmp_path / "runtime"
    vault = _vault(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    resolved = resolve_session_project(cwd=project, runtime_dir=runtime)
    session_id = "session-global-memory"
    _authorize(session_id, runtime)
    monkeypatch.setenv("DEVFRAME_OBSIDIAN_MEMORY_ROOT", str(vault))

    response, _ = handle_mcp_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {
                "name": "recall_project_plan",
                "_meta": {
                    "codex/sandbox-state-meta": {
                        "sandboxCwd": project.resolve().as_uri(),
                    }
                },
                "arguments": {"projectId": resolved["projectId"]},
            },
        },
        runtime_dir=runtime,
        session_id=session_id,
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert response["result"]["isError"] is False
    assert payload["status"] == "missing"
    assert payload["projectId"] == resolved["projectId"]


def test_cli_session_start_returns_sanitized_missing_payload(
    tmp_path,
    monkeypatch,
    capsys,
):
    runtime = tmp_path / "runtime"
    vault = _vault(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "memory",
            "session-start",
            "--cwd",
            str(project),
            "--runtime-dir",
            str(runtime),
            "--vault-root",
            str(vault),
            "--format",
            "json",
        ],
    )

    assert cli_main() == 0
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["status"] == "missing"
    assert result["projectId"]
    assert str(project) not in output
    assert str(runtime) not in output
    assert str(vault) not in output


def test_public_session_hook_template_is_project_dynamic():
    repository_root = Path(__file__).resolve().parents[3]
    template = (
        repository_root
        / "templates"
        / "runtime-bootstrap"
        / "recall-obsidian-working-plan.template.ps1"
    )

    text = template.read_text(encoding="utf-8")

    assert "memory\", \"session-start\"" in text
    assert "--project-id" not in text
    assert "$repo =" not in text
    assert "dev-frame-system" not in text
    assert "untrusted guidance" in text


@pytest.mark.skipif(os.name != "nt", reason="PowerShell SessionStart hook probe")
def test_session_hook_fails_open_when_start_helper_is_unavailable(tmp_path):
    repository_root = Path(__file__).resolve().parents[3]
    template = (
        repository_root
        / "templates"
        / "runtime-bootstrap"
        / "recall-obsidian-working-plan.template.ps1"
    ).read_text(encoding="utf-8")
    fake_python = tmp_path / "fake-python.cmd"
    fake_python.write_text(
        '@echo off\r\necho {"status":"current","projectId":"demo-123","plan":"bounded plan"}\r\n',
        encoding="utf-8",
    )
    rendered = (
        template.replace(
            "{{DEVFRAME_MEMORY_PYTHON_B64}}", _template_base64(fake_python)
        )
        .replace(
            "{{DEVFRAME_RUNTIME_STATE_B64}}",
            _template_base64(tmp_path / "runtime"),
        )
        .replace(
            "{{DEVFRAME_OBSIDIAN_VAULT_B64}}",
            _template_base64(tmp_path / "vault"),
        )
        .replace(
            "{{DEVFRAME_MEMORY_START_SCRIPT_B64}}",
            _template_base64(tmp_path / "absent-start.ps1"),
        )
        .replace("{{DEVFRAME_MEMORY_PORT_B64}}", _template_base64(65534))
    )
    hook = tmp_path / "hook.ps1"
    hook.write_text(rendered, encoding="utf-8")

    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(hook),
        ],
        input=json.dumps(
            {
                "cwd": str(tmp_path),
                "hook_event_name": "SessionStart",
                "source": "startup",
            }
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )

    assert result.returncode == 0
    context = _session_hook_context(result.stdout)
    assert "Status: current" in context
    assert "Project: demo-123" in context
    assert "bounded plan" in context
    assert str(tmp_path) not in result.stdout


@pytest.mark.skipif(os.name != "nt", reason="PowerShell SessionStart hook probe")
def test_session_hook_does_not_wait_for_slow_start_helper(tmp_path):
    repository_root = Path(__file__).resolve().parents[3]
    template = (
        repository_root
        / "templates"
        / "runtime-bootstrap"
        / "recall-obsidian-working-plan.template.ps1"
    ).read_text(encoding="utf-8")
    fake_python = tmp_path / "fake-python.cmd"
    fake_python.write_text(
        '@echo off\r\necho {"status":"missing","projectId":"demo-123","plan":""}\r\n',
        encoding="utf-8",
    )
    slow_start = tmp_path / "slow-start.ps1"
    slow_start.write_text("Start-Sleep -Seconds 5\n", encoding="utf-8")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        unused_port = probe.getsockname()[1]
    rendered = (
        template.replace(
            "{{DEVFRAME_MEMORY_PYTHON_B64}}", _template_base64(fake_python)
        )
        .replace(
            "{{DEVFRAME_RUNTIME_STATE_B64}}",
            _template_base64(tmp_path / "runtime"),
        )
        .replace(
            "{{DEVFRAME_OBSIDIAN_VAULT_B64}}",
            _template_base64(tmp_path / "vault"),
        )
        .replace(
            "{{DEVFRAME_MEMORY_START_SCRIPT_B64}}", _template_base64(slow_start)
        )
        .replace(
            "{{DEVFRAME_MEMORY_PORT_B64}}", _template_base64(unused_port)
        )
    )
    hook = tmp_path / "hook.ps1"
    hook.write_text(rendered, encoding="utf-8")

    started = time.monotonic()
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(hook),
        ],
        input=json.dumps(
            {
                "cwd": str(tmp_path),
                "hook_event_name": "SessionStart",
                "source": "startup",
            }
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=4,
        check=False,
    )
    elapsed = time.monotonic() - started

    assert result.returncode == 0
    context = _session_hook_context(result.stdout)
    assert "Status: missing" in context
    assert elapsed < 3


@pytest.mark.skipif(os.name != "nt", reason="PowerShell SessionStart hook probe")
def test_session_hook_treats_rendered_metacharacter_paths_as_literal(tmp_path):
    repository_root = Path(__file__).resolve().parents[3]
    template = (
        repository_root
        / "templates"
        / "runtime-bootstrap"
        / "recall-obsidian-working-plan.template.ps1"
    ).read_text(encoding="utf-8")
    literal_root = tmp_path / "$(New-Item owned.txt)"
    literal_root.mkdir()
    fake_python = literal_root / "fake-python.cmd"
    fake_python.write_text(
        '@echo off\r\necho {"status":"current","projectId":"literal","plan":"safe"}\r\n',
        encoding="utf-8",
    )
    rendered = (
        template.replace(
            "{{DEVFRAME_MEMORY_PYTHON_B64}}", _template_base64(fake_python)
        )
        .replace(
            "{{DEVFRAME_RUNTIME_STATE_B64}}",
            _template_base64(literal_root / "runtime"),
        )
        .replace(
            "{{DEVFRAME_OBSIDIAN_VAULT_B64}}",
            _template_base64(literal_root / "vault"),
        )
        .replace(
            "{{DEVFRAME_MEMORY_START_SCRIPT_B64}}",
            _template_base64(literal_root / "absent-start.ps1"),
        )
        .replace("{{DEVFRAME_MEMORY_PORT_B64}}", _template_base64(65534))
    )
    hook = tmp_path / "literal-hook.ps1"
    hook.write_text(rendered, encoding="utf-8")

    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(hook),
        ],
        input=json.dumps({"cwd": str(tmp_path), "hook_event_name": "SessionStart"}),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )

    assert result.returncode == 0
    context = _session_hook_context(result.stdout)
    assert "Status: current" in context
    assert "Project: literal" in context
    assert not (tmp_path / "owned.txt").exists()
