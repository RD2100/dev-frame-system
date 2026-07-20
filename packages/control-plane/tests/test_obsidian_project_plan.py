from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import control_plane.dashboard as dashboard_module  # noqa: E402
import control_plane.mcp_consent as mcp_consent  # noqa: E402
import control_plane.obsidian_memory as obsidian_memory_module  # noqa: E402
import control_plane.writeback as writeback_module  # noqa: E402
from control_plane.cli.app import main as cli_main  # noqa: E402
from control_plane.mcp_server import handle_mcp_jsonrpc  # noqa: E402
from control_plane.obsidian_memory import (  # noqa: E402
    ObsidianMemoryError,
    approve_project_plan,
    managed_plan_relative_path,
    recall_project_plan,
    stage_project_plan,
)
from control_plane.writeback import (  # noqa: E402
    WritebackError,
    apply_single_file_writeback,
    load_writeback_proposal,
    resolve_writeback_proposal,
)


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    handoff = project / "docs" / "status" / "HANDOFF.md"
    handoff.parent.mkdir(parents=True)
    handoff.write_text("# Execution Root\n\nCurrent milestone: memory MVP.\n", encoding="utf-8")
    return project


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / "wiki" / "memories").mkdir(parents=True)
    return vault


def _require_windows_junctions(tmp_path: Path) -> None:
    probe_target = tmp_path / "junction-capability-target"
    probe_link = tmp_path / "junction-capability-link"
    probe_target.mkdir()
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(probe_link), str(probe_target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"junction creation unavailable: {result.stderr.strip()}")
    probe_link.rmdir()


def _create_junction(link: Path, target: Path) -> None:
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def _restore_swapped_directory(link: Path, moved: Path) -> None:
    is_junction = getattr(link, "is_junction", lambda: False)
    if is_junction():
        link.rmdir()
    if moved.exists() and not link.exists():
        moved.rename(link)


def _authorize(session_id: str, runtime_dir: Path) -> None:
    mcp_consent.register_connection(session_id, "test-client", runtime_dir=runtime_dir)
    mcp_consent.decide(session_id, "allow_once", runtime_dir=runtime_dir)


def _call(tool: str, args: dict[str, object], runtime_dir: Path, session_id: str) -> dict[str, object]:
    response, _ = handle_mcp_jsonrpc(
        {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": tool, "arguments": args}},
        runtime_dir=runtime_dir,
        session_id=session_id,
    )
    assert response is not None
    result = response["result"]
    payload = json.loads(result["content"][0]["text"])
    payload["_isError"] = result["isError"]
    return payload


def test_real_mcp_plan_propose_approve_recall(tmp_path, monkeypatch):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    session_id = "sess-plan"
    _authorize(session_id, runtime)
    monkeypatch.setenv("DEVFRAME_OBSIDIAN_MEMORY_ROOT", str(vault))
    monkeypatch.setattr(
        dashboard_module,
        "_resolve_writeback_workspace_root",
        lambda _runtime, _paper, project_id: str(project) if project_id == "dev-frame-system" else "",
    )

    proposed = _call(
        "propose_project_plan",
        {"projectId": "dev-frame-system", "contents": "## Goal\n\nShip one unified memory path."},
        runtime,
        session_id,
    )
    assert proposed["_isError"] is False
    assert proposed["staged"] is True
    target = vault / str(proposed["relativePath"])
    assert not target.exists()
    pending = _call("list_pending_writebacks", {}, runtime, session_id)
    assert pending["_isError"] is False
    assert len(pending["pending"]) == 1
    assert str(vault) not in json.dumps(pending)
    assert str(project) not in json.dumps(pending)

    approved = resolve_writeback_proposal(runtime, str(proposed["requestId"]), "approve")
    assert approved["applied"] is True
    assert str(vault) not in json.dumps(approved)
    assert str(project) not in json.dumps(approved)
    assert target.is_file()

    recalled = _call(
        "recall_project_plan",
        {"projectId": "dev-frame-system"},
        runtime,
        session_id,
    )
    assert recalled["_isError"] is False
    assert recalled["status"] == "current"
    assert recalled["authority"] == "untrusted_guidance_only"
    assert "Ship one unified memory path" in recalled["plan"]
    assert recalled["relativePath"] == proposed["relativePath"]
    assert str(vault) not in json.dumps(recalled)
    assert str(project) not in json.dumps(recalled)


def test_mcp_discovers_project_plan_tools():
    response, _ = handle_mcp_jsonrpc(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        runtime_dir=None,
        session_id="discovery-session",
    )

    assert response is not None
    names = {tool["name"] for tool in response["result"]["tools"]}
    assert {"propose_project_plan", "recall_project_plan"} <= names


def test_mcp_rejects_lone_surrogate_plan_as_controlled_tool_error(tmp_path, monkeypatch):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    session_id = "sess-invalid-unicode"
    _authorize(session_id, runtime)
    monkeypatch.setenv("DEVFRAME_OBSIDIAN_MEMORY_ROOT", str(vault))
    monkeypatch.setattr(
        dashboard_module,
        "_resolve_writeback_workspace_root",
        lambda _runtime, _paper, project_id: str(project) if project_id == "demo" else "",
    )

    proposed = _call(
        "propose_project_plan",
        {"projectId": "demo", "contents": "invalid surrogate: \ud800"},
        runtime,
        session_id,
    )

    assert proposed["_isError"] is True
    assert proposed["error"] == "obsidian_plan_rejected"
    assert "UTF-8" in proposed["detail"]


def test_crlf_plan_is_canonical_before_hash_and_approval(tmp_path):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    victim = vault / "existing-note.md"
    victim.write_text("original user note", encoding="utf-8")
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="## Goal\r\n\r\nCanonicalize Windows line endings.\r\n",
    )

    approved = approve_project_plan(runtime, staged["request_id"], confirm=True)
    assert approved["status"] == "applied"
    recalled = recall_project_plan(vault_root=vault, project_root=project, project_id="demo")
    assert recalled["plan"] == "## Goal\n\nCanonicalize Windows line endings."


def test_recall_returns_missing_before_first_managed_directory_exists(tmp_path):
    project = _project(tmp_path)
    vault = tmp_path / "fresh-vault"
    (vault / ".obsidian").mkdir(parents=True)

    recalled = recall_project_plan(vault_root=vault, project_root=project, project_id="demo")

    assert recalled["status"] == "missing"
    assert recalled["plan"] == ""
    assert recalled["relativePath"] == ""


def test_plan_approval_rejects_target_drift(tmp_path):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="## Goal\n\nInitial proposal.",
    )
    target = vault / staged["relative_path"]
    target.write_text("user changed this after preview", encoding="utf-8")
    with pytest.raises(WritebackError, match="create-only target"):
        resolve_writeback_proposal(runtime, staged["request_id"], "approve")
    assert target.read_text(encoding="utf-8") == "user changed this after preview"


def test_redacted_approval_error_does_not_expose_moved_vault_root(tmp_path, monkeypatch):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="A moved Vault must fail without exposing its private path.",
    )
    moved_vault = tmp_path / "moved-vault"
    vault.rename(moved_vault)
    original_sha256 = writeback_module.workspace_file_sha256

    def fail_with_private_path(workspace_root, relative_path, **kwargs):
        if Path(workspace_root) == vault:
            raise WritebackError(f"workspace root is unavailable: {vault}")
        return original_sha256(workspace_root, relative_path, **kwargs)

    monkeypatch.setattr(writeback_module, "workspace_file_sha256", fail_with_private_path)

    with pytest.raises(WritebackError) as captured:
        resolve_writeback_proposal(runtime, staged["request_id"], "approve")

    assert str(vault) not in str(captured.value)
    assert str(moved_vault) not in str(captured.value)
    assert load_writeback_proposal(runtime, staged["request_id"])["status"] == "pending"


def test_redacted_resolver_response_hides_root_identity(tmp_path):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="Resolver responses must not expose the private Vault root.",
    )

    result = resolve_writeback_proposal(runtime, staged["request_id"], "approve")

    encoded = json.dumps(result, ensure_ascii=True)
    assert str(vault) not in encoded
    assert "workspace_root_identity" not in result


def test_approval_rejects_handoff_change_before_vault_write(tmp_path):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="## Next\n\nDo the bounded slice.",
    )
    (project / "docs" / "status" / "HANDOFF.md").write_text("# New authority\n", encoding="utf-8")
    with pytest.raises(WritebackError, match="source changed after proposal"):
        resolve_writeback_proposal(runtime, staged["request_id"], "approve")
    assert not (vault / staged["relative_path"]).exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows Vault identity regression")
def test_approval_rejects_replaced_vault_root(tmp_path):
    _require_windows_junctions(tmp_path)
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="The proposal must stay bound to its original Vault root.",
    )
    moved_vault = tmp_path / "moved-vault"
    attacker_vault = _vault(tmp_path / "attacker")
    vault.rename(moved_vault)
    _create_junction(vault, attacker_vault)

    try:
        with pytest.raises(WritebackError, match="workspace root changed after proposal"):
            resolve_writeback_proposal(runtime, staged["request_id"], "approve")
        assert not (attacker_vault / staged["relative_path"]).exists()
    finally:
        _restore_swapped_directory(vault, moved_vault)


def test_approval_rechecks_handoff_at_publish_boundary(tmp_path, monkeypatch):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="Do not publish after the authority changes.",
    )
    target = vault / staged["relative_path"]
    handoff = project / "docs" / "status" / "HANDOFF.md"
    original_apply = writeback_module.apply_writeback_with_audit

    def change_source_then_apply(*args, **kwargs):
        handoff.write_text("# Changed during approval\n", encoding="utf-8")
        return original_apply(*args, **kwargs)

    monkeypatch.setattr(
        writeback_module,
        "apply_writeback_with_audit",
        change_source_then_apply,
    )

    with pytest.raises(WritebackError, match="source changed after proposal"):
        resolve_writeback_proposal(runtime, staged["request_id"], "approve")
    assert not target.exists()
    assert load_writeback_proposal(runtime, staged["request_id"])["status"] == "pending"


def test_plan_is_project_isolated(tmp_path):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="project-a",
        plan_markdown="Only project A may read this.",
    )
    resolve_writeback_proposal(runtime, staged["request_id"], "approve")

    recalled = recall_project_plan(vault_root=vault, project_root=project, project_id="project-b")
    assert recalled["status"] == "missing"
    assert recalled["plan"] == ""


def test_recall_fails_closed_when_plan_body_changes(tmp_path):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="Original reviewed working plan.",
    )
    resolve_writeback_proposal(runtime, staged["request_id"], "approve")
    target = vault / staged["relative_path"]
    target.write_text(
        target.read_text(encoding="utf-8").replace(
            "Original reviewed working plan.",
            "Unreviewed manual replacement.",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ObsidianMemoryError, match="body hash"):
        recall_project_plan(vault_root=vault, project_root=project, project_id="demo")


def test_recall_rechecks_handoff_at_response_boundary(tmp_path, monkeypatch):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="The source must still match after the note read.",
    )
    resolve_writeback_proposal(runtime, staged["request_id"], "approve")
    handoff = project / "docs" / "status" / "HANDOFF.md"
    original_read = obsidian_memory_module._read_bounded
    changed = False

    def change_source_during_note_read(root, path, *, max_bytes, kind):
        nonlocal changed
        data = original_read(root, path, max_bytes=max_bytes, kind=kind)
        if kind == "managed plan" and not changed:
            changed = True
            handoff.write_text("# Changed while recalling\n", encoding="utf-8")
        return data

    monkeypatch.setattr(obsidian_memory_module, "_read_bounded", change_source_during_note_read)
    recalled = recall_project_plan(
        vault_root=vault,
        project_root=project,
        project_id="demo",
    )

    assert changed is True
    assert recalled["status"] == "stale"
    assert recalled["plan"] == ""
    assert recalled["relativePath"] == ""


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ('authority: "working_only"', 'authority: "project_authority"'),
        ('status: "active"', 'status: "accepted"'),
        (
            'source_path: "docs/status/HANDOFF.md"',
            'source_path: "docs/status/OTHER.md"',
        ),
    ],
)
def test_recall_rejects_managed_metadata_tamper(tmp_path, field, replacement):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="Metadata must remain working-only guidance.",
    )
    resolve_writeback_proposal(runtime, staged["request_id"], "approve")
    target = vault / staged["relative_path"]
    contents = target.read_text(encoding="utf-8")
    assert field in contents
    target.write_text(contents.replace(field, replacement, 1), encoding="utf-8")

    with pytest.raises(ObsidianMemoryError, match="metadata is invalid"):
        recall_project_plan(vault_root=vault, project_root=project, project_id="demo")


def test_recall_enforces_plan_limit_in_utf8_bytes(tmp_path):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="tiny-plan",
    )
    resolve_writeback_proposal(runtime, staged["request_id"], "approve")
    original = (vault / staged["relative_path"]).read_text(encoding="utf-8")
    oversized = "界" * 6_000
    assert len(oversized) < 16_384
    assert len(oversized.encode("utf-8")) > 16_384
    oversized_sha256 = hashlib.sha256(oversized.encode("utf-8")).hexdigest()
    forged = original.replace(
        f'plan_sha256: "{staged["plan_sha256"]}"',
        f'plan_sha256: "{oversized_sha256}"',
        1,
    ).replace("tiny-plan", oversized, 1)
    oversized_target = vault / managed_plan_relative_path(
        "demo",
        staged["source_sha256"],
        oversized_sha256,
        staged["version_id"],
    )
    oversized_target.write_text(forged, encoding="utf-8")

    with pytest.raises(ObsidianMemoryError, match="body exceeds the size limit"):
        recall_project_plan(vault_root=vault, project_root=project, project_id="demo")


@pytest.mark.skipif(os.name != "nt", reason="Windows junction regression")
def test_plan_rejects_windows_junction_memory_directory(tmp_path):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    memory_dir = vault / "wiki" / "memories"
    external = tmp_path / "external-memory"
    memory_dir.rmdir()
    external.mkdir()
    created = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(memory_dir), str(external)],
        capture_output=True,
        text=True,
        check=False,
    )
    if created.returncode != 0:
        pytest.skip(f"junction creation unavailable: {created.stderr.strip()}")
    try:
        with pytest.raises(ObsidianMemoryError, match="link or reparse point"):
            stage_project_plan(
                tmp_path / "runtime",
                vault_root=vault,
                project_root=project,
                project_id="demo",
                plan_markdown="Never traverse a junction.",
            )
        assert not list(external.iterdir())
    finally:
        memory_dir.rmdir()


@pytest.mark.skipif(os.name != "nt", reason="Windows junction race regression")
def test_temp_open_parent_swap_is_blocked_before_writing_outside_vault(tmp_path, monkeypatch):
    _require_windows_junctions(tmp_path)
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="No plan bytes may cross a pre-open parent swap.",
    )
    memory_dir = vault / "wiki" / "memories"
    moved_memory = tmp_path / "outside-pre-open-memory"
    original_create = writeback_module._create_windows_temporary_file
    attack_attempted = False
    swap_succeeded = False

    def swap_parent_then_create(path):
        nonlocal attack_attempted, swap_succeeded
        attack_attempted = True
        try:
            memory_dir.rename(moved_memory)
        except OSError:
            pass
        else:
            _create_junction(memory_dir, moved_memory)
            swap_succeeded = True
        return original_create(path)

    monkeypatch.setattr(
        writeback_module,
        "_create_windows_temporary_file",
        swap_parent_then_create,
    )
    try:
        result = resolve_writeback_proposal(runtime, staged["request_id"], "approve")
        assert result["applied"] is True
        assert attack_attempted is True
        assert swap_succeeded is False
        assert not moved_memory.exists()
        assert (vault / staged["relative_path"]).is_file()
    finally:
        _restore_swapped_directory(memory_dir, moved_memory)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction race regression")
def test_create_only_publish_parent_swap_cannot_escape_vault(tmp_path, monkeypatch):
    _require_windows_junctions(tmp_path)
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="Directory replacement must not redirect approved bytes.",
    )
    memory_dir = vault / "wiki" / "memories"
    moved_memory = tmp_path / "outside-memory"
    target_name = Path(staged["relative_path"]).name
    original_rename = writeback_module._rename_windows_handle
    attack_attempted = False
    swap_succeeded = False

    def swap_parent_then_rename(os_handle, destination, *, replace):
        nonlocal attack_attempted, swap_succeeded
        attack_attempted = True
        try:
            memory_dir.rename(moved_memory)
        except OSError:
            pass
        else:
            _create_junction(memory_dir, moved_memory)
            swap_succeeded = True
        return original_rename(os_handle, destination, replace=replace)

    monkeypatch.setattr(
        writeback_module,
        "_rename_windows_handle",
        swap_parent_then_rename,
    )
    try:
        result = resolve_writeback_proposal(runtime, staged["request_id"], "approve")
        assert result["applied"] is True
        assert attack_attempted is True
        assert swap_succeeded is False
        assert not (moved_memory / target_name).exists()
        assert (memory_dir / target_name).is_file()
    finally:
        _restore_swapped_directory(memory_dir, moved_memory)


@pytest.mark.skipif(os.name != "nt", reason="Windows file-attribute regression")
def test_published_plan_is_not_marked_temporary_on_windows(tmp_path):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="Permanent notes must not retain a temporary-file attribute.",
    )

    resolve_writeback_proposal(runtime, staged["request_id"], "approve")
    attributes = int(getattr((vault / staged["relative_path"]).stat(), "st_file_attributes", 0))
    assert attributes & stat.FILE_ATTRIBUTE_TEMPORARY == 0


@pytest.mark.skipif(os.name != "nt", reason="Windows junction race regression")
def test_generic_replace_parent_swap_cannot_escape_workspace(tmp_path, monkeypatch):
    _require_windows_junctions(tmp_path)
    workspace = tmp_path / "workspace"
    target_parent = workspace / "notes"
    target_parent.mkdir(parents=True)
    moved_parent = tmp_path / "outside-notes"
    target = target_parent / "result.md"
    original_rename = writeback_module._rename_windows_handle
    attack_attempted = False
    swap_succeeded = False

    def swap_parent_then_rename(os_handle, destination, *, replace):
        nonlocal attack_attempted, swap_succeeded
        attack_attempted = True
        try:
            target_parent.rename(moved_parent)
        except OSError:
            pass
        else:
            _create_junction(target_parent, moved_parent)
            swap_succeeded = True
        return original_rename(os_handle, destination, replace=replace)

    monkeypatch.setattr(
        writeback_module,
        "_rename_windows_handle",
        swap_parent_then_rename,
    )
    try:
        result = apply_single_file_writeback(workspace, "notes/result.md", "approved")
        assert result["operation"] == "created"
        assert attack_attempted is True
        assert swap_succeeded is False
        assert not (moved_parent / target.name).exists()
        assert target.read_text(encoding="utf-8") == "approved"
    finally:
        _restore_swapped_directory(target_parent, moved_parent)


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode regression")
def test_generic_posix_writeback_preserves_existing_and_umask_modes(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    existing = workspace / "existing.md"
    existing.write_text("before", encoding="utf-8")
    existing.chmod(0o640)

    apply_single_file_writeback(workspace, "existing.md", "after")
    assert stat.S_IMODE(existing.stat().st_mode) == 0o640

    previous_umask = os.umask(0o027)
    try:
        apply_single_file_writeback(workspace, "created.md", "new")
    finally:
        os.umask(previous_umask)
    assert stat.S_IMODE((workspace / "created.md").stat().st_mode) == 0o640


@pytest.mark.skipif(os.name == "nt", reason="POSIX private proposal mode regression")
def test_private_plan_proposal_is_owner_only_on_posix(tmp_path):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    previous_umask = os.umask(0o022)
    try:
        staged = stage_project_plan(
            runtime,
            vault_root=vault,
            project_root=project,
            project_id="demo",
            plan_markdown="Private staged guidance must remain owner-only.",
        )
    finally:
        os.umask(previous_umask)

    proposal_dir = runtime / "writeback-proposals"
    proposal_path = proposal_dir / f"{staged['request_id']}.json"
    assert stat.S_IMODE(proposal_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(proposal_path.stat().st_mode) == 0o600

    resolve_writeback_proposal(runtime, staged["request_id"], "approve")
    assert stat.S_IMODE(proposal_path.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name == "nt", reason="POSIX replace recovery regression")
def test_generic_posix_replace_restores_original_after_parent_move(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    parent = workspace / "notes"
    parent.mkdir(parents=True)
    target = parent / "result.md"
    target.write_text("original bytes", encoding="utf-8")
    moved_parent = tmp_path / "moved-notes"
    original_replace = writeback_module.os.replace
    moved = False

    def replace_then_move(source, destination, *args, **kwargs):
        nonlocal moved
        result = original_replace(source, destination, *args, **kwargs)
        if not moved and ".devframe-writeback-" in str(source):
            parent.rename(moved_parent)
            moved = True
        return result

    monkeypatch.setattr(writeback_module.os, "replace", replace_then_move)
    try:
        with pytest.raises(WritebackError, match="directory changed"):
            apply_single_file_writeback(workspace, "notes/result.md", "approved bytes")
        assert moved is True
        assert (moved_parent / "result.md").read_text(encoding="utf-8") == "original bytes"
    finally:
        if moved_parent.exists() and not parent.exists():
            moved_parent.rename(parent)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction race regression")
def test_recall_rejects_parent_swap_between_validation_and_open(tmp_path, monkeypatch):
    _require_windows_junctions(tmp_path)
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="Never recall through a replaced parent directory.",
    )
    resolve_writeback_proposal(runtime, staged["request_id"], "approve")
    target = vault / staged["relative_path"]
    memory_dir = target.parent
    moved_memory = tmp_path / "outside-recall-memory"
    original_open = Path.open
    attack_attempted = False

    def swap_parent_then_open(path, *args, **kwargs):
        nonlocal attack_attempted
        if path == target and not attack_attempted:
            attack_attempted = True
            memory_dir.rename(moved_memory)
            _create_junction(memory_dir, moved_memory)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", swap_parent_then_open)
    try:
        with pytest.raises(ObsidianMemoryError, match="managed plan is unavailable"):
            recall_project_plan(vault_root=vault, project_root=project, project_id="demo")
        assert attack_attempted is True
    finally:
        _restore_swapped_directory(memory_dir, moved_memory)


def test_create_only_publish_loses_race_without_overwrite(tmp_path, monkeypatch):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="The approved bytes must never replace a concurrent file.",
    )
    target = vault / staged["relative_path"]
    if os.name == "nt":
        original_rename = writeback_module._rename_windows_handle

        def publish_after_concurrent_create(os_handle, destination, *, replace):
            Path(destination).write_text("concurrent user bytes", encoding="utf-8")
            return original_rename(os_handle, destination, replace=replace)

        monkeypatch.setattr(
            writeback_module,
            "_rename_windows_handle",
            publish_after_concurrent_create,
        )
    else:
        original_link = writeback_module.os.link

        def publish_after_concurrent_create(source, destination, *args, **kwargs):
            Path(destination).write_text("concurrent user bytes", encoding="utf-8")
            return original_link(source, destination, *args, **kwargs)

        monkeypatch.setattr(writeback_module.os, "link", publish_after_concurrent_create)
    with pytest.raises(WritebackError, match="create-only target already exists"):
        resolve_writeback_proposal(runtime, staged["request_id"], "approve")
    assert target.read_text(encoding="utf-8") == "concurrent user bytes"


def test_approve_and_reject_cannot_both_claim_one_proposal(tmp_path, monkeypatch):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="Only one human decision may consume this request.",
    )
    target = vault / staged["relative_path"]
    entered_publish = threading.Event()
    release_publish = threading.Event()
    approval_result: dict[str, object] = {}
    approval_errors: list[BaseException] = []

    def approve():
        try:
            approval_result.update(
                resolve_writeback_proposal(runtime, staged["request_id"], "approve")
            )
        except BaseException as exc:  # pragma: no cover - reported by assertions below
            approval_errors.append(exc)

    if os.name == "nt":
        original_rename = writeback_module._rename_windows_handle

        def paused_publish(os_handle, destination, *, replace):
            entered_publish.set()
            if not release_publish.wait(timeout=5):
                raise TimeoutError("test did not release create-only publication")
            return original_rename(os_handle, destination, replace=replace)

        monkeypatch.setattr(writeback_module, "_rename_windows_handle", paused_publish)
    else:
        original_link = writeback_module.os.link

        def paused_publish(source, destination, *args, **kwargs):
            entered_publish.set()
            if not release_publish.wait(timeout=5):
                raise TimeoutError("test did not release create-only publication")
            return original_link(source, destination, *args, **kwargs)

        monkeypatch.setattr(writeback_module.os, "link", paused_publish)
    thread = threading.Thread(target=approve, daemon=True)
    thread.start()
    assert entered_publish.wait(timeout=5)
    try:
        with pytest.raises(WritebackError, match="already processing"):
            resolve_writeback_proposal(runtime, staged["request_id"], "reject")
        assert not target.exists()
    finally:
        release_publish.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert not approval_errors
    assert approval_result["applied"] is True
    assert target.is_file()
    assert load_writeback_proposal(runtime, staged["request_id"])["status"] == "applied"
    assert not writeback_module._PROPOSAL_THREAD_LOCKS


def test_dashboard_decision_conflict_returns_non_success(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()

    def reject_conflict(*_args, **_kwargs):
        raise WritebackError("write-back proposal decision is already processing")

    monkeypatch.setattr(writeback_module, "resolve_writeback_proposal", reject_conflict)
    server = dashboard_module.build_dashboard_server(runtime_dir=runtime, port=0, refresh_seconds=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    request = Request(
        f"http://127.0.0.1:{server.server_address[1]}/api/t3/approval-response",
        data=json.dumps(
            {
                "requestId": "wb-00112233445566aa",
                "threadId": "thread-a",
                "decision": "reject",
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with pytest.raises(HTTPError) as captured:
            urlopen(request, timeout=5)
        assert captured.value.code == 400
        payload = json.loads(captured.value.read().decode("utf-8"))
        assert payload["responded"] is False
        assert payload["error"] == "writeback_rejected"
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_approval_rejects_tampered_project_plan_action(tmp_path):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    victim = vault / "existing-note.md"
    victim.write_text("original user note", encoding="utf-8")
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="Approve only the managed immutable note.",
        thread_id="thread-plan",
    )
    proposal_path = runtime / "writeback-proposals" / f"{staged['request_id']}.json"
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    proposal.update(
        {
            "relative_path": "existing-note.md",
            "contents": "tampered action",
            "create_only": False,
        }
    )
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")

    server = dashboard_module.build_dashboard_server(
        runtime_dir=runtime,
        port=0,
        refresh_seconds=0,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    request = Request(
        f"http://127.0.0.1:{server.server_address[1]}/api/t3/approval-response",
        data=json.dumps(
            {
                "requestId": staged["request_id"],
                "threadId": "thread-plan",
                "decision": "approve",
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with pytest.raises(HTTPError) as captured:
            urlopen(request, timeout=5)
        assert captured.value.code == 400
        payload = json.loads(captured.value.read().decode("utf-8"))
        assert payload["error"] == "writeback_rejected"
        assert victim.read_text(encoding="utf-8") == "original user note"
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_rejects_consistently_downgraded_project_plan_action(tmp_path):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    victim = vault / "existing-note.md"
    victim.write_text("original user note", encoding="utf-8")
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="The managed note must not become a generic overwrite.",
        thread_id="thread-plan",
    )
    proposal_path = runtime / "writeback-proposals" / f"{staged['request_id']}.json"
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    tampered_contents = "tampered generic overwrite"
    generic_preview = writeback_module.preview_single_file_writeback(
        vault,
        "existing-note.md",
        tampered_contents,
        create_only=False,
    )
    generic_preview.update(
        {
            "contents_sha256": hashlib.sha256(tampered_contents.encode("utf-8")).hexdigest(),
            "workspace_root_identity_sha256": proposal["preview"]["workspace_root_identity_sha256"],
            "source_preconditions_sha256": proposal["preview"]["source_preconditions_sha256"],
            "create_only": False,
            "proposal_kind": "writeback",
            "project_id": "demo",
            "thread_id": "thread-plan",
            "redact_paths": False,
        }
    )
    proposal.update(
        {
            "relative_path": "existing-note.md",
            "contents": tampered_contents,
            "preview": generic_preview,
            "create_only": False,
            "proposal_kind": "writeback",
            "redact_paths": False,
        }
    )
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")

    server = dashboard_module.build_dashboard_server(
        runtime_dir=runtime,
        port=0,
        refresh_seconds=0,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    request = Request(
        f"http://127.0.0.1:{server.server_address[1]}/api/t3/approval-response",
        data=json.dumps(
            {
                "requestId": staged["request_id"],
                "threadId": "thread-plan",
                "decision": "approve",
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with pytest.raises(HTTPError) as captured:
            urlopen(request, timeout=5)
        assert captured.value.code == 400
        assert victim.read_text(encoding="utf-8") == "original user note"
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_route_race_cannot_approve_plan_as_generic_writeback(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    victim = vault / "existing-note.md"
    victim.write_text("original user note", encoding="utf-8")
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="A route race must not drop plan validation.",
        thread_id="thread-plan",
    )
    proposal_path = runtime / "writeback-proposals" / f"{staged['request_id']}.json"
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    tampered_contents = "generic content must not pass plan validation"
    tampered_preview = writeback_module.preview_single_file_writeback(
        vault,
        "existing-note.md",
        tampered_contents,
        create_only=False,
    )
    tampered_preview.update(
        {
            "contents_sha256": hashlib.sha256(tampered_contents.encode("utf-8")).hexdigest(),
            "workspace_root_identity_sha256": proposal["preview"]["workspace_root_identity_sha256"],
            "source_preconditions_sha256": proposal["preview"]["source_preconditions_sha256"],
            "create_only": False,
            "proposal_kind": "obsidian_project_plan",
            "project_id": "demo",
            "thread_id": "thread-plan",
            "redact_paths": True,
        }
    )
    proposal.update(
        {
            "relative_path": "existing-note.md",
            "contents": tampered_contents,
            "preview": tampered_preview,
            "create_only": False,
        }
    )
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
    original_load = writeback_module.load_writeback_proposal
    load_count = 0

    def race_load(runtime_dir, request_id):
        nonlocal load_count
        load_count += 1
        proposal = original_load(runtime_dir, request_id)
        if load_count == 1 and proposal is not None:
            proposal = {**proposal, "proposal_kind": "writeback"}
        return proposal

    monkeypatch.setattr(writeback_module, "load_writeback_proposal", race_load)
    server = dashboard_module.build_dashboard_server(
        runtime_dir=runtime,
        port=0,
        refresh_seconds=0,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    request = Request(
        f"http://127.0.0.1:{server.server_address[1]}/api/t3/approval-response",
        data=json.dumps(
            {
                "requestId": staged["request_id"],
                "threadId": "thread-plan",
                "decision": "approve",
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with pytest.raises(HTTPError) as captured:
            urlopen(request, timeout=5)
        assert captured.value.code == 400
        assert load_count >= 2
        assert victim.read_text(encoding="utf-8") == "original user note"
    finally:
        server.shutdown()
        server.server_close()


def test_approval_rejects_tampered_request_id_without_applying(tmp_path):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="The request ID must remain bound to its proposal file.",
    )
    proposal_path = runtime / "writeback-proposals" / f"{staged['request_id']}.json"
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    tampered_request_id = "wb-" + ("b" * 16)
    proposal["request_id"] = tampered_request_id
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")

    with pytest.raises(WritebackError, match="request id"):
        resolve_writeback_proposal(runtime, staged["request_id"], "approve")

    assert not (vault / staged["relative_path"]).exists()
    assert json.loads(proposal_path.read_text(encoding="utf-8"))["status"] == "pending"
    assert not (runtime / "writeback-proposals" / f"{tampered_request_id}.json").exists()
    assert not (runtime / "writeback-runs" / staged["request_id"]).exists()


def test_approval_rejects_tampered_surrogate_as_controlled_error(tmp_path):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="The persisted proposal must remain valid UTF-8.",
    )
    proposal_path = runtime / "writeback-proposals" / f"{staged['request_id']}.json"
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    proposal["contents"] = "tampered surrogate: \ud800"
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")

    with pytest.raises(WritebackError, match="valid UTF-8"):
        resolve_writeback_proposal(runtime, staged["request_id"], "approve")
    assert load_writeback_proposal(runtime, staged["request_id"])["status"] == "pending"


def test_proposal_lock_is_released_when_owner_process_exits(tmp_path):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="A crashed decision owner must not block this forever.",
    )
    package_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(package_root), environment.get("PYTHONPATH", "")])
    )
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import sys,time; "
                "from control_plane.writeback import _claim_writeback_proposal; "
                "claim=_claim_writeback_proposal(sys.argv[1],sys.argv[2]); "
                "assert claim is not None; print('locked',flush=True); time.sleep(60)"
            ),
            str(runtime),
            staged["request_id"],
        ],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "locked"
        with pytest.raises(WritebackError, match="already processing"):
            resolve_writeback_proposal(runtime, staged["request_id"], "approve")
    finally:
        holder.terminate()
        try:
            holder.wait(timeout=5)
        except subprocess.TimeoutExpired:
            holder.kill()
            holder.wait(timeout=5)

    recovered = resolve_writeback_proposal(runtime, staged["request_id"], "approve")
    assert recovered["applied"] is True
    assert (vault / staged["relative_path"]).is_file()


def test_exact_publication_recovers_after_terminal_status_failure(tmp_path, monkeypatch):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="Recover only these exact approved bytes.",
    )
    target = vault / staged["relative_path"]
    original_set_status = writeback_module._set_proposal_status
    failed_once = False
    stamps = iter(["20260720-000001", "20260720-000002"])

    class FakeTime:
        @staticmethod
        def strftime(_format):
            return next(stamps)

    monkeypatch.setattr(writeback_module, "time", FakeTime)

    def fail_first_applied_status(runtime_dir, proposal, status):
        nonlocal failed_once
        if status == "applied" and not failed_once:
            failed_once = True
            raise OSError("simulated status persistence failure")
        return original_set_status(runtime_dir, proposal, status)

    monkeypatch.setattr(
        writeback_module,
        "_set_proposal_status",
        fail_first_applied_status,
    )
    with pytest.raises(OSError, match="status persistence failure"):
        resolve_writeback_proposal(runtime, staged["request_id"], "approve")
    assert target.is_file()
    assert load_writeback_proposal(runtime, staged["request_id"])["status"] == "pending"

    monkeypatch.setattr(writeback_module, "_set_proposal_status", original_set_status)
    recovered = resolve_writeback_proposal(runtime, staged["request_id"], "approve")
    assert recovered["applied"] is True
    assert recovered["recovered"] is True
    assert recovered["bytes_written"] == len(target.read_bytes())
    assert load_writeback_proposal(runtime, staged["request_id"])["status"] == "applied"
    audit_paths = list(
        (runtime / "writeback-runs" / staged["request_id"]).glob("*.json")
    )
    assert len(audit_paths) == 1


def test_publication_recovery_rejects_changed_target_bytes(tmp_path, monkeypatch):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="Only exact published bytes may complete recovery.",
    )
    target = vault / staged["relative_path"]
    original_set_status = writeback_module._set_proposal_status
    failed_once = False

    def fail_first_applied_status(runtime_dir, proposal, status):
        nonlocal failed_once
        if status == "applied" and not failed_once:
            failed_once = True
            raise OSError("simulated status persistence failure")
        return original_set_status(runtime_dir, proposal, status)

    monkeypatch.setattr(writeback_module, "_set_proposal_status", fail_first_applied_status)
    with pytest.raises(OSError, match="status persistence failure"):
        resolve_writeback_proposal(runtime, staged["request_id"], "approve")
    target.write_text("different bytes after interrupted publication", encoding="utf-8")

    monkeypatch.setattr(writeback_module, "_set_proposal_status", original_set_status)
    with pytest.raises(WritebackError, match="different contents"):
        resolve_writeback_proposal(runtime, staged["request_id"], "approve")
    assert target.read_text(encoding="utf-8") == "different bytes after interrupted publication"
    assert load_writeback_proposal(runtime, staged["request_id"])["status"] == "pending"


def test_publication_recovery_rechecks_target_after_hash(tmp_path, monkeypatch):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="Recovery must recheck bytes after the initial hash.",
    )
    target = vault / staged["relative_path"]
    original_set_status = writeback_module._set_proposal_status
    failed_once = False

    def fail_first_applied_status(runtime_dir, proposal, status):
        nonlocal failed_once
        if status == "applied" and not failed_once:
            failed_once = True
            raise OSError("simulated status persistence failure")
        return original_set_status(runtime_dir, proposal, status)

    monkeypatch.setattr(writeback_module, "_set_proposal_status", fail_first_applied_status)
    with pytest.raises(OSError, match="status persistence failure"):
        resolve_writeback_proposal(runtime, staged["request_id"], "approve")
    monkeypatch.setattr(writeback_module, "_set_proposal_status", original_set_status)

    original_hash = writeback_module.workspace_file_sha256
    changed = False

    def hash_then_change(workspace_root, relative_path, **kwargs):
        nonlocal changed
        result = original_hash(workspace_root, relative_path, **kwargs)
        if relative_path == staged["relative_path"] and not changed:
            changed = True
            target.write_text("changed after recovery hash", encoding="utf-8")
        return result

    monkeypatch.setattr(writeback_module, "workspace_file_sha256", hash_then_change)
    with pytest.raises(WritebackError, match="published bytes"):
        resolve_writeback_proposal(runtime, staged["request_id"], "approve")

    assert changed is True
    assert target.read_text(encoding="utf-8") == "changed after recovery hash"
    assert load_writeback_proposal(runtime, staged["request_id"])["status"] == "pending"


def test_exact_external_target_without_audit_is_not_recovered(tmp_path):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="Matching bytes without an audit are not DevFrame publication proof.",
    )
    proposal = load_writeback_proposal(runtime, staged["request_id"])
    assert proposal is not None
    target = vault / staged["relative_path"]
    target.write_bytes(proposal["contents"].encode("utf-8"))

    with pytest.raises(WritebackError, match="without a matching audit"):
        resolve_writeback_proposal(runtime, staged["request_id"], "approve")

    assert not list((runtime / "writeback-runs" / staged["request_id"]).glob("*.json"))
    assert load_writeback_proposal(runtime, staged["request_id"])["status"] == "pending"


def test_create_only_recovery_rejects_forged_audit(tmp_path):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="Exact bytes alone are not publication proof.",
    )
    proposal = load_writeback_proposal(runtime, staged["request_id"])
    assert proposal is not None
    target = vault / staged["relative_path"]
    data = proposal["contents"].encode("utf-8")
    target.write_bytes(data)
    audit_dir = runtime / "writeback-runs" / staged["request_id"]
    audit_dir.mkdir(parents=True)
    (audit_dir / "forged.json").write_text(
        json.dumps(
            {
                "applied": True,
                "action_id": staged["request_id"],
                "kind": "writeback_apply_file",
                "relative_path": staged["relative_path"],
                "operation": "created",
                "bytes_written": len(data),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(WritebackError, match="audit"):
        resolve_writeback_proposal(runtime, staged["request_id"], "approve")

    assert json.loads(
        (runtime / "writeback-proposals" / f"{staged['request_id']}.json").read_text(
            encoding="utf-8"
        )
    )["status"] == "pending"


def test_malformed_proposal_is_rejected_as_controlled_writeback_error(tmp_path):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="Malformed runtime state must fail closed.",
    )
    proposal_path = runtime / "writeback-proposals" / f"{staged['request_id']}.json"
    proposal_path.write_text("[]", encoding="utf-8")

    with pytest.raises(WritebackError):
        resolve_writeback_proposal(runtime, staged["request_id"], "approve")

    assert not (vault / staged["relative_path"]).exists()
    assert writeback_module.list_pending_writeback_proposals(runtime) == []


def test_shared_resolver_rechecks_applied_project_plan_bytes(tmp_path):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="Shared approval retries must verify exact published bytes.",
    )
    resolve_writeback_proposal(runtime, staged["request_id"], "approve")
    target = vault / staged["relative_path"]
    target.write_text("different bytes after approval", encoding="utf-8")

    with pytest.raises(WritebackError, match="published bytes no longer match"):
        resolve_writeback_proposal(runtime, staged["request_id"], "approve")
    assert target.read_text(encoding="utf-8") == "different bytes after approval"


def test_recall_rejects_timestamp_that_disagrees_with_immutable_version(tmp_path):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    older = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="Older current plan.",
    )
    resolve_writeback_proposal(runtime, older["request_id"], "approve")
    newer = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="Newer current plan.",
    )
    resolve_writeback_proposal(runtime, newer["request_id"], "approve")
    assert recall_project_plan(
        vault_root=vault,
        project_root=project,
        project_id="demo",
    )["plan"] == "Newer current plan."

    older_target = vault / older["relative_path"]
    contents = older_target.read_text(encoding="utf-8")
    forged = re.sub(
        r'^updated_at: ".*"$',
        'updated_at: "2999-01-01T00:00:00.000000+00:00"',
        contents,
        count=1,
        flags=re.MULTILINE,
    )
    assert forged != contents
    older_target.write_text(forged, encoding="utf-8")

    with pytest.raises(ObsidianMemoryError, match="version metadata is invalid"):
        recall_project_plan(vault_root=vault, project_root=project, project_id="demo")


def test_recall_reads_latest_from_bounded_window_after_65_versions(tmp_path):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    latest_plan = ""
    version_ids: list[str] = []
    for index in range(65):
        latest_plan = f"Working plan version {index:02d}."
        staged = stage_project_plan(
            runtime,
            vault_root=vault,
            project_root=project,
            project_id="demo",
            plan_markdown=latest_plan,
        )
        version_ids.append(staged["version_id"])
        resolve_writeback_proposal(runtime, staged["request_id"], "approve")
    assert version_ids == sorted(version_ids)
    assert len(list((vault / "wiki" / "memories").glob("demo-now-*.md"))) == 65

    recalled = recall_project_plan(
        vault_root=vault,
        project_root=project,
        project_id="demo",
    )
    assert recalled["status"] == "current"
    assert recalled["plan"] == latest_plan


def test_project_id_rejects_case_aliases(tmp_path):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    with pytest.raises(ObsidianMemoryError, match="lower-case"):
        stage_project_plan(
            tmp_path / "runtime",
            vault_root=vault,
            project_root=project,
            project_id="Project-A",
            plan_markdown="No case-aliased target paths.",
        )


@pytest.mark.parametrize(
    "secret_plan",
    [
        "api_key = 'super-secret-token-value-12345'",
        "database.password = 'synthetic-password-value-12345'",
        "- password: synthetic-password-value-12345",
        "export PASSWORD=synthetic-password-value-12345",
        json.dumps({"password": "synthetic-password-value-12345"}),
        json.dumps({"api_key": "sk-" + "proj-" + "abcdefghijklmnopqrstuvwxyz1234567890"}),
        "https://example.invalid/callback?access_token=synthetic-access-token-value-1234567890",
        "xoxb-1234567890-synthetic-slack-token-value-1234567890",
        "gho_" + "A" * 36,
        "-----BEGIN ENCRYPTED PRIVATE KEY-----\nopaque-secret-material",
    ],
)
def test_secret_bearing_plan_is_rejected_before_staging(tmp_path, secret_plan):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    with pytest.raises(ObsidianMemoryError, match="secret") as captured:
        stage_project_plan(
            tmp_path / "runtime",
            vault_root=vault,
            project_root=project,
            project_id="demo",
            plan_markdown=secret_plan,
        )
    assert secret_plan not in str(captured.value)
    assert not list((tmp_path / "runtime").rglob("wb-*.json"))


@pytest.mark.parametrize(
    "secret_plan",
    [
        json.dumps({"password": "synthetic-password-value-12345"}),
        "database.password = 'synthetic-password-value-12345'",
        "- password: synthetic-password-value-12345",
        "export PASSWORD=synthetic-password-value-12345",
    ],
)
def test_recall_rejects_secret_with_consistent_hash_and_filename(tmp_path, secret_plan):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="Benign plan before a forged secret note.",
    )
    resolve_writeback_proposal(runtime, staged["request_id"], "approve")
    original_target = vault / staged["relative_path"]
    original = original_target.read_text(encoding="utf-8")
    secret_sha256 = hashlib.sha256(secret_plan.encode("utf-8")).hexdigest()
    forged = original.replace(
        f'plan_sha256: "{staged["plan_sha256"]}"',
        f'plan_sha256: "{secret_sha256}"',
        1,
    ).replace("Benign plan before a forged secret note.", secret_plan, 1)
    forged_target = vault / managed_plan_relative_path(
        "demo",
        staged["source_sha256"],
        secret_sha256,
        staged["version_id"],
    )
    original_target.unlink()
    forged_target.write_text(forged, encoding="utf-8")

    with pytest.raises(ObsidianMemoryError, match="secret"):
        recall_project_plan(vault_root=vault, project_root=project, project_id="demo")


@pytest.mark.parametrize(
    "control",
    ["\x1b", "\x07", "\x80"],
)
def test_terminal_control_plan_is_rejected_before_staging(tmp_path, control):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    with pytest.raises(ObsidianMemoryError, match="control") as captured:
        stage_project_plan(
            tmp_path / "runtime",
            vault_root=vault,
            project_root=project,
            project_id="demo",
            plan_markdown=f"Safe prefix{control}unsafe suffix",
        )
    assert f"Safe prefix{control}unsafe suffix" not in str(captured.value)
    assert not list((tmp_path / "runtime").rglob("wb-*.json"))


def test_tab_and_lf_remain_allowed_in_plan_body(tmp_path):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="Column\tValue\nnext\trow",
    )

    approve_project_plan(runtime, staged["request_id"], confirm=True)
    recalled = recall_project_plan(vault_root=vault, project_root=project, project_id="demo")
    assert recalled["plan"] == "Column\tValue\nnext\trow"


def test_recall_rejects_terminal_control_with_consistent_hash_and_filename(tmp_path):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="Benign plan before a forged control note.",
    )
    resolve_writeback_proposal(runtime, staged["request_id"], "approve")
    original_target = vault / staged["relative_path"]
    original = original_target.read_text(encoding="utf-8")
    forged_body = "Benign plan\x1b]51;evil\x07suffix"
    control_sha256 = hashlib.sha256(forged_body.encode("utf-8")).hexdigest()
    forged = original.replace(
        f'plan_sha256: "{staged["plan_sha256"]}"',
        f'plan_sha256: "{control_sha256}"',
        1,
    ).replace("Benign plan before a forged control note.", forged_body, 1)
    forged_target = vault / managed_plan_relative_path(
        "demo",
        staged["source_sha256"],
        control_sha256,
        staged["version_id"],
    )
    original_target.unlink()
    forged_target.write_text(forged, encoding="utf-8")

    with pytest.raises(ObsidianMemoryError, match="control"):
        recall_project_plan(vault_root=vault, project_root=project, project_id="demo")


def test_cli_plan_propose_exact_approve_and_recall(tmp_path, monkeypatch, capsys):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    plan_file = tmp_path / "plan.md"
    plan_file.write_text("## Goal\n\nUse one canonical memory path.\n", encoding="utf-8")
    base_args = [
        "devframe",
        "memory",
        "plan",
        "propose",
        "--project-root",
        str(project),
        "--project-id",
        "demo",
        "--vault-root",
        str(vault),
        "--contents-file",
        str(plan_file),
        "--runtime-dir",
        str(runtime),
        "--format",
        "json",
    ]
    monkeypatch.setattr(sys, "argv", base_args)
    assert cli_main() == 3
    proposed = json.loads(capsys.readouterr().out)
    target = vault / proposed["relativePath"]
    assert not target.exists()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "memory",
            "plan",
            "approve",
            "--request-id",
            proposed["requestId"],
            "--runtime-dir",
            str(runtime),
            "--format",
            "json",
            "--confirm",
        ],
    )
    assert cli_main() == 0
    written_output = capsys.readouterr().out
    assert str(vault) not in written_output
    assert str(project) not in written_output

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "memory",
            "plan",
            "recall",
            "--project-root",
            str(project),
            "--project-id",
            "demo",
            "--vault-root",
            str(vault),
            "--format",
            "json",
        ],
    )
    assert cli_main() == 0
    recalled = json.loads(capsys.readouterr().out)
    assert recalled["status"] == "current"
    assert "Use one canonical memory path" in recalled["plan"]


def test_cli_default_text_propose_emits_exact_request_id(tmp_path, monkeypatch, capsys):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    plan_file = tmp_path / "plan.md"
    plan_file.write_text("Default text mode must remain usable.", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "memory",
            "plan",
            "propose",
            "--project-root",
            str(project),
            "--project-id",
            "demo",
            "--vault-root",
            str(vault),
            "--contents-file",
            str(plan_file),
            "--runtime-dir",
            str(runtime),
        ],
    )
    assert cli_main() == 3
    proposed_text = capsys.readouterr().out
    request_line = next(
        line for line in proposed_text.splitlines() if line.startswith("requestId: ")
    )
    request_id = request_line.removeprefix("requestId: ")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "memory",
            "plan",
            "approve",
            "--request-id",
            request_id,
            "--runtime-dir",
            str(runtime),
            "--confirm",
        ],
    )
    assert cli_main() == 0
    approved_text = capsys.readouterr().out
    assert "status: applied" in approved_text
    assert "applied: True" in approved_text


def test_cli_rejected_request_cannot_report_successful_approval(tmp_path, monkeypatch, capsys):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="This request will be rejected.",
    )
    resolve_writeback_proposal(runtime, staged["request_id"], "reject")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "memory",
            "plan",
            "approve",
            "--request-id",
            staged["request_id"],
            "--runtime-dir",
            str(runtime),
            "--confirm",
            "--format",
            "json",
        ],
    )
    assert cli_main() == 2
    rejected = json.loads(capsys.readouterr().out)
    assert "already rejected" in rejected["detail"]
    assert not (vault / staged["relative_path"]).exists()


def test_cli_applied_request_rechecks_published_bytes_before_success(
    tmp_path,
    monkeypatch,
    capsys,
):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    staged = stage_project_plan(
        runtime,
        vault_root=vault,
        project_root=project,
        project_id="demo",
        plan_markdown="Applied retries must remain bound to these exact bytes.",
    )
    resolve_writeback_proposal(runtime, staged["request_id"], "approve")
    target = vault / staged["relative_path"]
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "memory",
            "plan",
            "approve",
            "--request-id",
            staged["request_id"],
            "--runtime-dir",
            str(runtime),
            "--confirm",
            "--format",
            "json",
        ],
    )

    assert cli_main() == 0
    exact_retry = json.loads(capsys.readouterr().out)
    assert exact_retry["alreadyResolved"] is True

    target.write_text("different bytes after the recorded approval", encoding="utf-8")
    assert cli_main() == 2
    rejected = json.loads(capsys.readouterr().out)
    assert "published bytes no longer match" in rejected["detail"]
    assert target.read_text(encoding="utf-8") == "different bytes after the recorded approval"


def test_cli_invalid_utf8_contents_file_returns_controlled_error(
    tmp_path,
    monkeypatch,
    capsys,
):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    plan_file = tmp_path / "invalid.md"
    plan_file.write_bytes(b"\xff\xfe")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "memory",
            "plan",
            "propose",
            "--project-root",
            str(project),
            "--project-id",
            "demo",
            "--vault-root",
            str(vault),
            "--contents-file",
            str(plan_file),
        ],
    )
    assert cli_main() == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cannot read --contents-file" in captured.err


def test_cli_approve_rejects_target_created_after_proposal(tmp_path, monkeypatch, capsys):
    project = _project(tmp_path)
    vault = _vault(tmp_path)
    runtime = tmp_path / "runtime"
    plan_file = tmp_path / "plan.md"
    plan_file.write_text("Do not overwrite newer bytes.", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "memory",
            "plan",
            "propose",
            "--project-root",
            str(project),
            "--project-id",
            "demo",
            "--vault-root",
            str(vault),
            "--contents-file",
            str(plan_file),
            "--runtime-dir",
            str(runtime),
            "--format",
            "json",
        ],
    )
    assert cli_main() == 3
    proposed = json.loads(capsys.readouterr().out)
    target = vault / proposed["relativePath"]
    target.write_text("newer user bytes", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "memory",
            "plan",
            "approve",
            "--request-id",
            proposed["requestId"],
            "--runtime-dir",
            str(runtime),
            "--format",
            "json",
            "--confirm",
        ],
    )
    assert cli_main() == 2
    assert target.read_text(encoding="utf-8") == "newer user bytes"
