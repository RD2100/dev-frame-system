from __future__ import annotations

import base64
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from control_plane.cli.app import main as cli_main  # noqa: E402
import control_plane.mcp_consent as mcp_consent  # noqa: E402
from control_plane.mcp_server import handle_mcp_jsonrpc  # noqa: E402
from control_plane.obsidian_memory import (  # noqa: E402
    MEMORY_READ_ONLY_ENV,
    ObsidianMemoryError,
    capture_project_checkpoint,
    capture_session_checkpoint_from_transcript,
    create_project_lesson,
    list_project_lessons,
    resolve_session_project,
    search_project_lessons,
    stage_global_playbook_promotion,
)
from control_plane.writeback import (  # noqa: E402
    load_writeback_proposal,
    resolve_writeback_proposal,
)


def _template_base64(value: object) -> str:
    return base64.b64encode(str(value).encode("utf-8")).decode("ascii")


def _vault(root: Path) -> Path:
    vault = root / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / "wiki" / "memories").mkdir(parents=True)
    return vault


def _project(root: Path, runtime: Path) -> tuple[Path, str]:
    root.mkdir(parents=True)
    handoff = root / "docs" / "status" / "HANDOFF.md"
    handoff.parent.mkdir(parents=True)
    handoff.write_text("# Execution Root\n\nCurrent slice.\n", encoding="utf-8")
    resolved = resolve_session_project(cwd=root, runtime_dir=runtime)
    return root, str(resolved["projectId"])


def _codex_sandbox_meta(cwd: Path) -> dict[str, object]:
    return {
        "codex/sandbox-state-meta": {
            "sandboxCwd": cwd.resolve().as_uri(),
        }
    }


def _checkpoint(runtime: Path, vault: Path, project: Path, project_id: str, key: str):
    return capture_project_checkpoint(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id=project_id,
        idempotency_key=key,
        session_id="session-1",
        trigger="manual",
        goal="Ship the bounded memory slice.",
        decisions=["Use deterministic create-only notes."],
        failed_attempts=["Name-only client identity was too weak."],
        verification=["Focused tests pass."],
        blockers=[],
        next_action="Run a native lifecycle probe.",
    )


def test_checkpoint_retry_is_idempotent_and_does_not_disclose_vault_path(tmp_path):
    runtime = tmp_path / "runtime"
    vault = _vault(tmp_path)
    project, project_id = _project(tmp_path / "project", runtime)

    first = _checkpoint(runtime, vault, project, project_id, "event-1")
    second = _checkpoint(runtime, vault, project, project_id, "event-1")

    assert first["created"] is True
    assert first["duplicate"] is False
    assert second["created"] is False
    assert second["duplicate"] is True
    assert first["memoryId"] == second["memoryId"]
    assert str(vault) not in json.dumps(first)
    assert "relativePath" not in first
    files = list(
        (vault / "wiki" / "memories" / "devframe-agent" / "projects" / project_id / "checkpoints").glob("*.md")
    )
    assert len(files) == 1


def test_checkpoint_conflicting_idempotency_key_never_overwrites(tmp_path):
    runtime = tmp_path / "runtime"
    vault = _vault(tmp_path)
    project, project_id = _project(tmp_path / "project", runtime)
    first = _checkpoint(runtime, vault, project, project_id, "event-1")
    note = next(vault.rglob(f"{first['memoryId']}.md"))
    before = note.read_bytes()

    with pytest.raises(ObsidianMemoryError, match="idempotency"):
        capture_project_checkpoint(
            runtime,
            vault_root=vault,
            project_root=project,
            project_id=project_id,
            idempotency_key="event-1",
            session_id="session-1",
            trigger="manual",
            goal="Different content under the same event.",
            decisions=[],
            failed_attempts=[],
            verification=[],
            blockers=[],
            next_action="Reject.",
        )

    assert note.read_bytes() == before


def test_exact_existing_checkpoint_requires_matching_audit(tmp_path):
    runtime = tmp_path / "runtime"
    vault = _vault(tmp_path)
    project, project_id = _project(tmp_path / "project", runtime)
    created = _checkpoint(runtime, vault, project, project_id, "event-audit")
    audit_files = list((runtime / "writeback-runs").rglob("*.json"))
    assert len(audit_files) == 1
    audit_files[0].unlink()

    with pytest.raises(ObsidianMemoryError, match="matching audit"):
        _checkpoint(runtime, vault, project, project_id, "event-audit")

    assert len(list(vault.rglob(f"{created['memoryId']}.md"))) == 1


def test_concurrent_checkpoint_calls_create_one_logical_record(tmp_path):
    runtime = tmp_path / "runtime"
    vault = _vault(tmp_path)
    project, project_id = _project(tmp_path / "project", runtime)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: _checkpoint(runtime, vault, project, project_id, "event-race"),
                range(2),
            )
        )

    assert sum(bool(result["created"]) for result in results) == 1
    assert sum(bool(result["duplicate"]) for result in results) == 1
    files = list(
        (vault / "wiki" / "memories" / "devframe-agent" / "projects" / project_id / "checkpoints").glob("*.md")
    )
    assert len(files) == 1


def test_checkpoint_rejects_forged_project_secret_and_read_only_mode(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    vault = _vault(tmp_path)
    project, project_id = _project(tmp_path / "project", runtime)
    other_project, other_id = _project(tmp_path / "other", runtime)

    with pytest.raises(ObsidianMemoryError, match="project"):
        _checkpoint(runtime, vault, project, other_id, "forged")
    with pytest.raises(ObsidianMemoryError, match="secret"):
        capture_project_checkpoint(
            runtime,
            vault_root=vault,
            project_root=project,
            project_id=project_id,
            idempotency_key="secret",
            session_id="session-1",
            trigger="manual",
            goal="Use Bearer abcdefghijklmnopqrstuvwxyz123456",
            decisions=[],
            failed_attempts=[],
            verification=[],
            blockers=[],
            next_action="Stop.",
        )
    monkeypatch.setenv(MEMORY_READ_ONLY_ENV, "true")
    with pytest.raises(ObsidianMemoryError, match="read-only"):
        _checkpoint(runtime, vault, project, project_id, "read-only")
    assert other_project != project


def test_agent_owned_reparse_path_is_rejected(tmp_path):
    runtime = tmp_path / "runtime"
    vault = _vault(tmp_path)
    project, project_id = _project(tmp_path / "project", runtime)
    agent_root = vault / "wiki" / "memories" / "devframe-agent"
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        agent_root.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation is unavailable")

    with pytest.raises(ObsidianMemoryError, match="unsafe|unavailable|reparse"):
        _checkpoint(runtime, vault, project, project_id, "linked")

    assert list(outside.rglob("*.md")) == []


def test_project_lesson_survives_handoff_change_and_is_searchable(tmp_path):
    runtime = tmp_path / "runtime"
    vault = _vault(tmp_path)
    project, project_id = _project(tmp_path / "project", runtime)
    created = create_project_lesson(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id=project_id,
        idempotency_key="lesson-1",
        title="Stable idempotency",
        lesson="Derive the immutable path from the project and event key.",
        evidence=["Concurrent retry produced one note."],
        tags=["idempotency", "memory"],
        global_candidate=True,
    )
    (project / "docs" / "status" / "HANDOFF.md").write_text(
        "# Execution Root\n\nA different slice.\n",
        encoding="utf-8",
    )

    listed = list_project_lessons(
        vault_root=vault,
        project_id=project_id,
        limit=20,
    )
    searched = search_project_lessons(
        vault_root=vault,
        project_id=project_id,
        query="immutable path",
        limit=10,
    )

    assert created["created"] is True
    assert listed["lessons"][0]["memoryId"] == created["memoryId"]
    assert listed["lessons"][0]["globalCandidate"] is True
    assert searched["lessons"][0]["memoryId"] == created["memoryId"]
    assert str(vault) not in json.dumps(listed)


def test_global_promotion_is_staged_only_and_human_create_only(tmp_path):
    runtime = tmp_path / "runtime"
    vault = _vault(tmp_path)
    project, project_id = _project(tmp_path / "project", runtime)
    lesson = create_project_lesson(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id=project_id,
        idempotency_key="global-candidate",
        title="Checkpoint before compaction",
        lesson="Persist only bounded high-signal state.",
        evidence=["Native PreCompact event."],
        tags=["codex", "checkpoint"],
        global_candidate=True,
    )

    staged = stage_global_playbook_promotion(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id=project_id,
        lesson_id=lesson["memoryId"],
    )
    proposal = load_writeback_proposal(runtime, staged["request_id"])

    assert staged["staged"] is True
    assert staged["humanRequired"] is True
    assert proposal["status"] == "pending"
    assert proposal["create_only"] is True
    assert not list((vault / "wiki" / "memories" / "devframe-agent").glob("global-playbooks/*.md"))

    applied = resolve_writeback_proposal(runtime, staged["request_id"], "approve")

    assert applied["applied"] is True
    assert len(list((vault / "wiki" / "memories" / "devframe-agent").glob("global-playbooks/*.md"))) == 1


def test_transcript_checkpoint_uses_bounded_high_signal_fields(tmp_path):
    runtime = tmp_path / "runtime"
    vault = _vault(tmp_path)
    project, project_id = _project(tmp_path / "project", runtime)
    codex_home = tmp_path / "codex-home"
    transcript = codex_home / "sessions" / "2026" / "07" / "rollout-test.jsonl"
    transcript.parent.mkdir(parents=True)
    records = [
        {
            "type": "event_msg",
            "payload": {
                "type": "user_message",
                "message": "Implement safe automatic Obsidian checkpoints.",
            },
        },
        {
            "type": "event_msg",
            "payload": {
                "type": "agent_message",
                "message": (
                    "Decision: use immutable create-only notes.\n"
                    "Failed: name-only trust was too weak.\n"
                    "Verification: focused tests passed.\n"
                    "Next action: run the native hook probe.\n"
                    "Unclassified raw conversation must not be persisted."
                ),
            },
        },
    ]
    transcript.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )

    captured = capture_session_checkpoint_from_transcript(
        runtime,
        vault_root=vault,
        cwd=project,
        transcript_path=transcript,
        session_id="native-session",
        turn_id="native-turn",
        trigger="auto",
        codex_home=codex_home,
    )
    note = next(vault.rglob(f"{captured['memoryId']}.md")).read_text(encoding="utf-8")

    assert captured["projectId"] == project_id
    assert "Implement safe automatic Obsidian checkpoints." in note
    assert "immutable create-only notes" in note
    assert "Unclassified raw conversation" not in note
    assert "native-session" not in note
    assert str(transcript) not in note


def test_transcript_outside_codex_sessions_is_rejected(tmp_path):
    runtime = tmp_path / "runtime"
    vault = _vault(tmp_path)
    project, _project_id = _project(tmp_path / "project", runtime)
    codex_home = tmp_path / "codex-home"
    (codex_home / "sessions").mkdir(parents=True)
    transcript = tmp_path / "foreign.jsonl"
    transcript.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ObsidianMemoryError, match="transcript"):
        capture_session_checkpoint_from_transcript(
            runtime,
            vault_root=vault,
            cwd=project,
            transcript_path=transcript,
            session_id="native-session",
            turn_id="native-turn",
            trigger="auto",
            codex_home=codex_home,
        )


def test_transcript_scan_reaches_goal_before_tool_heavy_tail(tmp_path):
    runtime = tmp_path / "runtime"
    vault = _vault(tmp_path)
    project, _project_id = _project(tmp_path / "project", runtime)
    codex_home = tmp_path / "codex-home"
    transcript = codex_home / "sessions" / "tool-heavy.jsonl"
    transcript.parent.mkdir(parents=True)
    user = json.dumps(
        {
            "type": "event_msg",
            "payload": {
                "type": "user_message",
                "message": "Preserve the goal before a tool-heavy tail.",
            },
        }
    )
    filler = json.dumps(
        {
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "padding": "x" * 1_200,
            },
        }
    )
    transcript.write_text(
        user + "\n" + (filler + "\n") * 2_100,
        encoding="utf-8",
    )
    assert transcript.stat().st_size > 2_097_152

    captured = capture_session_checkpoint_from_transcript(
        runtime,
        vault_root=vault,
        cwd=project,
        transcript_path=transcript,
        session_id="session-heavy",
        turn_id="turn-heavy",
        trigger="auto",
        codex_home=codex_home,
    )
    note = next(vault.rglob(f"{captured['memoryId']}.md")).read_text(encoding="utf-8")

    assert captured["status"] == "captured"
    assert "Preserve the goal before a tool-heavy tail." in note
    assert "x" * 100 not in note


def test_cli_capture_from_transcript_returns_sanitized_result(
    tmp_path,
    monkeypatch,
    capsys,
):
    runtime = tmp_path / "runtime"
    vault = _vault(tmp_path)
    project, _project_id = _project(tmp_path / "project", runtime)
    codex_home = tmp_path / "codex-home"
    transcript = codex_home / "sessions" / "rollout.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(
        json.dumps(
            {
                "type": "event_msg",
                "payload": {
                    "type": "user_message",
                    "message": "Capture a bounded checkpoint.",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "memory",
            "checkpoint",
            "capture-from-transcript",
            "--cwd",
            str(project),
            "--transcript-path",
            str(transcript),
            "--session-id",
            "session",
            "--turn-id",
            "turn",
            "--trigger",
            "auto",
            "--runtime-dir",
            str(runtime),
            "--vault-root",
            str(vault),
            "--codex-home",
            str(codex_home),
            "--format",
            "json",
        ],
    )

    assert cli_main() == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["status"] == "captured"
    assert payload["created"] is True
    assert str(project) not in output
    assert str(transcript) not in output
    assert str(vault) not in output


def test_mcp_safe_lesson_create_and_search_round_trip(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    vault = _vault(tmp_path)
    project_root, project_id = _project(tmp_path / "project", runtime)
    monkeypatch.setenv("DEVFRAME_OBSIDIAN_MEMORY_ROOT", str(vault))
    mcp_consent._reset_for_tests()
    mcp_consent.register_connection("memory-mcp", "test-client", runtime_dir=runtime)
    mcp_consent.decide("memory-mcp", "allow_once", runtime_dir=runtime)

    created_response, _ = handle_mcp_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "create_project_lesson",
                "_meta": _codex_sandbox_meta(project_root),
                "arguments": {
                    "projectId": project_id,
                    "idempotencyKey": "mcp-lesson",
                    "title": "Bounded MCP memory",
                    "lesson": "Safe creates use server-derived immutable paths.",
                    "evidence": ["MCP round trip."],
                    "tags": ["mcp"],
                },
            },
        },
        runtime_dir=runtime,
        session_id="memory-mcp",
    )
    created = json.loads(created_response["result"]["content"][0]["text"])
    searched_response, _ = handle_mcp_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "search_project_lessons",
                "_meta": _codex_sandbox_meta(project_root),
                "arguments": {
                    "projectId": project_id,
                    "query": "server-derived",
                },
            },
        },
        runtime_dir=runtime,
        session_id="memory-mcp",
    )
    searched = json.loads(searched_response["result"]["content"][0]["text"])

    assert created_response["result"]["isError"] is False
    assert created["created"] is True
    assert searched_response["result"]["isError"] is False
    assert searched["lessons"][0]["memoryId"] == created["memoryId"]
    assert str(vault) not in json.dumps(created)
    assert "relativePath" not in created


def test_mcp_memory_rejects_missing_cross_project_and_forged_scope(
    tmp_path,
    monkeypatch,
):
    runtime = tmp_path / "runtime"
    vault = _vault(tmp_path)
    project_a_root, project_a_id = _project(tmp_path / "project-a", runtime)
    _project_b_root, project_b_id = _project(tmp_path / "project-b", runtime)
    monkeypatch.setenv("DEVFRAME_OBSIDIAN_MEMORY_ROOT", str(vault))
    mcp_consent._reset_for_tests()
    mcp_consent.register_connection("memory-scope", "test-client", runtime_dir=runtime)
    mcp_consent.decide("memory-scope", "allow_once", runtime_dir=runtime)

    def call(project_id: str, request_meta: dict[str, object] | None):
        params = {
            "name": "create_project_lesson",
            "arguments": {
                "projectId": project_id,
                "idempotencyKey": f"scope-{project_id}",
                "title": "Scoped memory",
                "lesson": "This must stay in the current Codex project.",
            },
        }
        if request_meta is not None:
            params["_meta"] = request_meta
        response, _ = handle_mcp_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": params,
            },
            runtime_dir=runtime,
            session_id="memory-scope",
        )
        return response

    missing = call(project_a_id, None)
    cross_project = call(project_b_id, _codex_sandbox_meta(project_a_root))
    forged = call("forged-project", _codex_sandbox_meta(project_a_root))
    traversal = call(
        project_b_id,
        {
            "codex/sandbox-state-meta": {
                "sandboxCwd": project_a_root.as_uri() + "/../project-b",
            }
        },
    )
    remote_authority = call(
        project_a_id,
        {
            "codex/sandbox-state-meta": {
                "sandboxCwd": "file://remote-host/share/project-a",
            }
        },
    )

    for response in (
        missing,
        cross_project,
        forged,
        traversal,
        remote_authority,
    ):
        assert response["result"]["isError"] is True
        text = response["result"]["content"][0]["text"]
        assert "project_scope" in text
        assert str(project_a_root) not in text
        assert str(vault) not in text

    assert list_project_lessons(
        vault_root=vault,
        project_id=project_a_id,
    )["lessons"] == []
    assert list_project_lessons(
        vault_root=vault,
        project_id=project_b_id,
    )["lessons"] == []


def test_public_precompact_hook_template_is_bounded_and_path_private():
    repository_root = Path(__file__).resolve().parents[3]
    template = (
        repository_root
        / "templates"
        / "runtime-bootstrap"
        / "checkpoint-obsidian-session.template.ps1"
    )

    text = template.read_text(encoding="utf-8")

    assert '"checkpoint", "capture-from-transcript"' in text
    assert "session_id" in text
    assert "turn_id" in text
    assert "transcript_path" in text
    assert "Start-Job" in text
    assert '"continue":true' in text
    assert "Write-Output $vaultRoot" not in text


@pytest.mark.skipif(os.name != "nt", reason="PowerShell PreCompact hook probe")
def test_precompact_hook_is_fail_open_and_suppresses_private_output(tmp_path):
    repository_root = Path(__file__).resolve().parents[3]
    template = (
        repository_root
        / "templates"
        / "runtime-bootstrap"
        / "checkpoint-obsidian-session.template.ps1"
    ).read_text(encoding="utf-8")
    literal_root = tmp_path / "$(New-Item owned.txt)"
    literal_root.mkdir()
    fake_python = literal_root / "fake-python.cmd"
    fake_python.write_text(
        "@echo off\r\necho PRIVATE-CLI-OUTPUT\r\nexit /b 0\r\n",
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
    )
    hook = tmp_path / "checkpoint-hook.ps1"
    hook.write_text(rendered, encoding="utf-8")
    transcript = tmp_path / "private-transcript.jsonl"
    transcript.write_text("{}\n", encoding="utf-8")

    result = __import__("subprocess").run(
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
                "session_id": "session",
                "turn_id": "turn",
                "transcript_path": str(transcript),
                "cwd": str(tmp_path),
                "hook_event_name": "PreCompact",
                "trigger": "auto",
            }
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
        cwd=tmp_path,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["continue"] is True
    assert "PRIVATE-CLI-OUTPUT" not in result.stdout
    assert str(transcript) not in result.stdout
    assert not (tmp_path / "owned.txt").exists()
