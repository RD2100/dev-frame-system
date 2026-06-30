"""Tests for the governed write-back executor (M8.2 slice 1).

These lock the security contract: a write can never escape the workspace root,
sensitive paths are refused, symlink escapes are blocked, and every applied
write returns an honest audit record.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from control_plane.writeback import (  # noqa: E402
    WritebackError,
    apply_single_file_writeback,
    safe_resolve_workspace_path,
)


def test_safe_resolve_accepts_simple_relative(tmp_path):
    resolved = safe_resolve_workspace_path(tmp_path, "src/app.py")
    assert resolved == (tmp_path.resolve() / "src" / "app.py")


def test_safe_resolve_rejects_absolute(tmp_path):
    with pytest.raises(WritebackError, match="absolute"):
        safe_resolve_workspace_path(tmp_path, str(tmp_path / "x.txt"))


def test_safe_resolve_rejects_parent_traversal(tmp_path):
    with pytest.raises(WritebackError, match="'\\.\\.'"):
        safe_resolve_workspace_path(tmp_path, "../escape.txt")


def test_safe_resolve_rejects_nested_parent_traversal(tmp_path):
    with pytest.raises(WritebackError, match="'\\.\\.'"):
        safe_resolve_workspace_path(tmp_path, "src/../../escape.txt")


def test_safe_resolve_rejects_empty(tmp_path):
    with pytest.raises(WritebackError, match="required"):
        safe_resolve_workspace_path(tmp_path, "   ")


@pytest.mark.parametrize(
    "rel",
    [
        ".git/config",
        ".env",
        ".env.local",
        "config/.env",
        "node_modules/pkg/index.js",
        ".ssh/id_rsa",
        ".devframe-runtime/state.json",
        ".git /config",
        ".git./config",
        ".GIT/config",
        ".env ",
        ".ENV.LOCAL",
        "node_modules./x.js",
    ],
)
def test_safe_resolve_rejects_sensitive_paths(tmp_path, rel):
    with pytest.raises(WritebackError, match="sensitive"):
        safe_resolve_workspace_path(tmp_path, rel)


def test_safe_resolve_rejects_drive_relative(tmp_path):
    with pytest.raises(WritebackError, match="absolute"):
        safe_resolve_workspace_path(tmp_path, "C:evil.txt")


def test_safe_resolve_rejects_unc(tmp_path):
    with pytest.raises(WritebackError, match="absolute"):
        safe_resolve_workspace_path(tmp_path, r"\\server\share\evil.txt")


def test_safe_resolve_rejects_symlink_escape(tmp_path):
    outside = tmp_path.parent / "outside_target"
    outside.mkdir()
    link = tmp_path / "link"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported in this environment")
    with pytest.raises(WritebackError, match="symlink"):
        safe_resolve_workspace_path(tmp_path, "link/evil.txt")


def test_apply_creates_new_file(tmp_path):
    record = apply_single_file_writeback(tmp_path, "src/new.txt", "hello")
    written = tmp_path / "src" / "new.txt"
    assert written.read_text(encoding="utf-8") == "hello"
    assert record["operation"] == "created"
    assert record["relative_path"] == "src/new.txt"
    assert record["bytes_written"] == 5
    assert record["kind"] == "writeback_apply_file"


def test_apply_modifies_existing_file(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("old", encoding="utf-8")
    record = apply_single_file_writeback(tmp_path, "a.txt", "newer content")
    assert f.read_text(encoding="utf-8") == "newer content"
    assert record["operation"] == "modified"
    assert record["bytes_before"] == 3


def test_apply_rejects_oversize(tmp_path):
    with pytest.raises(WritebackError, match="max write-back size"):
        apply_single_file_writeback(tmp_path, "big.txt", "x" * 100, max_bytes=10)


def test_apply_rejects_non_string_contents(tmp_path):
    with pytest.raises(WritebackError, match="string"):
        apply_single_file_writeback(tmp_path, "a.txt", b"bytes")  # type: ignore[arg-type]


def test_apply_rejects_escape_does_not_write(tmp_path):
    with pytest.raises(WritebackError):
        apply_single_file_writeback(tmp_path, "../escape.txt", "nope")
    assert not (tmp_path.parent / "escape.txt").exists()


def test_apply_leaves_no_temp_file(tmp_path):
    apply_single_file_writeback(tmp_path, "dir/x.txt", "data")
    leftovers = list((tmp_path / "dir").glob("*.devframe-writeback.tmp"))
    assert leftovers == []


from control_plane.writeback import (  # noqa: E402
    apply_writeback_with_audit,
    preview_single_file_writeback,
)


def test_preview_does_not_write(tmp_path):
    preview = preview_single_file_writeback(tmp_path, "p/x.txt", "data")
    assert preview["operation"] == "created"
    assert preview["bytes"] == 4
    assert not (tmp_path / "p" / "x.txt").exists()


def test_preview_rejects_unsafe(tmp_path):
    with pytest.raises(WritebackError):
        preview_single_file_writeback(tmp_path, "../x.txt", "data")


def test_with_audit_without_confirm_is_gate_and_writes_nothing(tmp_path):
    runtime = tmp_path / "rt"
    result = apply_writeback_with_audit(
        tmp_path, "a.txt", "hello", runtime_dir=runtime, confirm=False
    )
    assert result["applied"] is False
    assert result["human_required"] is True
    assert not (tmp_path / "a.txt").exists()
    assert not (runtime / "writeback-runs").exists()


def test_with_audit_confirm_applies_and_records(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    runtime = tmp_path / "rt"
    result = apply_writeback_with_audit(
        workspace, "a.txt", "hello", runtime_dir=runtime, action_id="act-1", confirm=True
    )
    assert result["applied"] is True
    assert (workspace / "a.txt").read_text(encoding="utf-8") == "hello"
    audit_path = Path(result["audit_path"])
    assert audit_path.exists()
    import json as _json

    audit = _json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["applied"] is True
    assert audit["operation"] == "created"
    assert audit["action_id"] == "act-1"


def test_with_audit_confirm_rejects_unsafe_without_writing(tmp_path):
    runtime = tmp_path / "rt"
    with pytest.raises(WritebackError):
        apply_writeback_with_audit(
            tmp_path, ".git/config", "x", runtime_dir=runtime, confirm=True
        )
    assert not (runtime / "writeback-runs").exists()


def test_cli_writeback_preview_then_apply(tmp_path, monkeypatch, capsys):
    from control_plane.cli._writeback import cmd_writeback_apply

    workspace = tmp_path / "ws"
    workspace.mkdir()
    runtime = tmp_path / "rt"
    contents_file = tmp_path / "contents.txt"
    contents_file.write_text("from cli", encoding="utf-8")

    base_argv = [
        "devframe", "writeback", "apply",
        "--workspace", str(workspace),
        "--path", "out.txt",
        "--contents-file", str(contents_file),
        "--runtime-dir", str(runtime),
        "--format", "json",
    ]

    # Preview (no --confirm): gate stop, exit 3, nothing written.
    monkeypatch.setattr(sys, "argv", list(base_argv))
    code = cmd_writeback_apply()
    assert code == 3
    assert not (workspace / "out.txt").exists()

    # Apply (--confirm): exit 0, file written.
    monkeypatch.setattr(sys, "argv", list(base_argv) + ["--confirm"])
    code = cmd_writeback_apply()
    assert code == 0
    assert (workspace / "out.txt").read_text(encoding="utf-8") == "from cli"


def test_cli_writeback_rejects_unsafe(tmp_path, monkeypatch):
    from control_plane.cli._writeback import cmd_writeback_apply

    workspace = tmp_path / "ws"
    workspace.mkdir()
    contents_file = tmp_path / "c.txt"
    contents_file.write_text("x", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "devframe", "writeback", "apply",
        "--workspace", str(workspace),
        "--path", "../escape.txt",
        "--contents-file", str(contents_file),
        "--runtime-dir", str(tmp_path / "rt"),
        "--confirm",
    ])
    code = cmd_writeback_apply()
    assert code == 2
    assert not (tmp_path / "escape.txt").exists()


from control_plane.writeback import (  # noqa: E402
    load_writeback_proposal,
    resolve_writeback_proposal,
    stage_writeback_proposal,
)


def test_stage_proposal_does_not_write(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    rt = tmp_path / "rt"
    staged = stage_writeback_proposal(rt, ws, "a.txt", "hello")
    assert staged["request_id"].startswith("wb-")
    assert staged["preview"]["operation"] == "created"
    assert not (ws / "a.txt").exists()
    loaded = load_writeback_proposal(rt, staged["request_id"])
    assert loaded["status"] == "pending"


def test_stage_then_approve_writes_once(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    rt = tmp_path / "rt"
    staged = stage_writeback_proposal(rt, ws, "dir/a.txt", "approved content")
    rid = staged["request_id"]
    result = resolve_writeback_proposal(rt, rid, "approve")
    assert result["applied"] is True
    assert (ws / "dir" / "a.txt").read_text(encoding="utf-8") == "approved content"
    # Second resolve is a no-op (already applied) and must not re-write.
    again = resolve_writeback_proposal(rt, rid, "approve")
    assert again["applied"] is False
    assert again.get("already_resolved") is True


def test_stage_then_reject_does_not_write(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    rt = tmp_path / "rt"
    staged = stage_writeback_proposal(rt, ws, "a.txt", "nope")
    result = resolve_writeback_proposal(rt, staged["request_id"], "reject")
    assert result["applied"] is False
    assert result["status"] == "rejected"
    assert not (ws / "a.txt").exists()


def test_stage_rejects_unsafe_proposal(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    rt = tmp_path / "rt"
    with pytest.raises(WritebackError):
        stage_writeback_proposal(rt, ws, "../escape.txt", "x")


def test_resolve_rejects_invalid_request_id(tmp_path):
    with pytest.raises(WritebackError, match="invalid write-back request id"):
        resolve_writeback_proposal(tmp_path, "../../etc/passwd", "approve")


def test_resolve_missing_proposal_raises(tmp_path):
    with pytest.raises(WritebackError, match="not found"):
        resolve_writeback_proposal(tmp_path, "wb-00112233445566aa", "approve")


def test_resolve_rejects_thread_mismatch(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    rt = tmp_path / "rt"
    staged = stage_writeback_proposal(rt, ws, "a.txt", "data", thread_id="thread-A")
    with pytest.raises(WritebackError, match="thread mismatch"):
        resolve_writeback_proposal(rt, staged["request_id"], "approve", expected_thread_id="thread-B")
    # The proposal stays pending and nothing was written.
    assert not (ws / "a.txt").exists()
    assert load_writeback_proposal(rt, staged["request_id"])["status"] == "pending"


def test_resolve_allows_matching_thread(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    rt = tmp_path / "rt"
    staged = stage_writeback_proposal(rt, ws, "a.txt", "data", thread_id="thread-A")
    result = resolve_writeback_proposal(rt, staged["request_id"], "approve", expected_thread_id="thread-A")
    assert result["applied"] is True
    assert (ws / "a.txt").read_text(encoding="utf-8") == "data"
