"""Tests for the governed write-back executor (M8.2 slice 1).

These lock the security contract: a write can never escape the workspace root,
sensitive paths are refused, symlink escapes are blocked, and every applied
write returns an honest audit record.
"""
from __future__ import annotations

import hashlib
import json
import multiprocessing
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


def _approve_create_only_proposal_in_child(
    runtime_dir: str,
    request_id: str,
    start_gate,
    ready_queue,
    result_queue,
) -> None:
    """Exercise the real proposal resolver from an independent process."""
    from control_plane.writeback import resolve_writeback_proposal

    ready_queue.put("ready")
    if not start_gate.wait(timeout=10):
        result_queue.put({"error": "start_gate_timeout"})
        return
    try:
        result = resolve_writeback_proposal(
            runtime_dir,
            request_id,
            "approve",
            expected_thread_id="memory-session",
        )
        result_queue.put(
            {
                "applied": bool(result.get("applied")),
                "status": str(result.get("status") or ""),
                "already_resolved": bool(result.get("already_resolved")),
            }
        )
    except Exception as exc:  # noqa: BLE001 - return child failure to parent assertion
        result_queue.put({"error": type(exc).__name__, "detail": str(exc)})


def _approve_with_claim_link_paused(
    runtime_dir: str,
    request_id: str,
    claim_visible,
    resume_owner,
    result_queue,
) -> None:
    """Pause the live owner immediately after its claim becomes visible."""
    import control_plane.writeback as writeback_module

    original_link = writeback_module.os.link

    def link_then_pause(source, target, *args, **kwargs):
        result = original_link(source, target, *args, **kwargs)
        if str(target).endswith(".applying.json"):
            claim_visible.set()
            if not resume_owner.wait(timeout=10):
                raise RuntimeError("resume_owner_timeout")
        return result

    writeback_module.os.link = link_then_pause
    try:
        result = writeback_module.resolve_writeback_proposal(
            runtime_dir,
            request_id,
            "approve",
            expected_thread_id="memory-session",
        )
        result_queue.put(
            {
                "role": "owner",
                "applied": bool(result.get("applied")),
                "status": str(result.get("status") or ""),
            }
        )
    except Exception as exc:  # noqa: BLE001 - return child failure to parent assertion
        result_queue.put(
            {"role": "owner", "error": type(exc).__name__, "detail": str(exc)}
        )


def _approve_while_live_claim_is_paused(
    runtime_dir: str,
    request_id: str,
    claim_visible,
    result_queue,
) -> None:
    """Attempt recovery while the original claim owner is still alive."""
    from control_plane.writeback import resolve_writeback_proposal

    if not claim_visible.wait(timeout=10):
        result_queue.put({"role": "contender", "error": "claim_visible_timeout"})
        return
    try:
        result = resolve_writeback_proposal(
            runtime_dir,
            request_id,
            "approve",
            expected_thread_id="memory-session",
        )
        result_queue.put(
            {
                "role": "contender",
                "applied": bool(result.get("applied")),
                "status": str(result.get("status") or ""),
                "already_resolved": bool(result.get("already_resolved")),
            }
        )
    except Exception as exc:  # noqa: BLE001 - return child failure to parent assertion
        result_queue.put(
            {"role": "contender", "error": type(exc).__name__, "detail": str(exc)}
        )


def test_safe_resolve_accepts_simple_relative(tmp_path):
    resolved = safe_resolve_workspace_path(tmp_path, "src/app.py")
    assert resolved == (tmp_path.resolve() / "src" / "app.py")


def test_safe_resolve_missing_root_error_redacts_absolute_path(tmp_path):
    missing = tmp_path / "private-vault-that-does-not-exist"
    with pytest.raises(WritebackError) as caught:
        safe_resolve_workspace_path(missing, "note.md")
    assert str(missing) not in str(caught.value)
    assert missing.name not in str(caught.value)


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


def test_stage_rejects_distinct_apply_contents(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    rt = tmp_path / "rt"

    with pytest.raises(WritebackError, match="must match approved contents"):
        stage_writeback_proposal(
            rt,
            ws,
            "approved.txt",
            "visible approved content",
            apply_contents="hidden applied content",
        )

    assert not (ws / "approved.txt").exists()


def test_resolve_rejects_legacy_distinct_apply_contents(tmp_path):
    from control_plane.writeback import _proposal_digest

    ws = tmp_path / "ws"
    ws.mkdir()
    rt = tmp_path / "rt"
    staged = stage_writeback_proposal(
        rt,
        ws,
        "approved.txt",
        "visible approved content",
    )
    proposal_path = rt / "writeback-proposals" / f"{staged['request_id']}.json"
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    proposal["apply_contents"] = "hidden applied content"
    proposal["apply_content_sha256"] = hashlib.sha256(
        proposal["apply_contents"].encode("utf-8")
    ).hexdigest()
    proposal["proposal_digest"] = _proposal_digest(proposal)
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")

    with pytest.raises(WritebackError, match="approved contents"):
        resolve_writeback_proposal(rt, staged["request_id"], "approve")

    assert not (ws / "approved.txt").exists()
    assert load_writeback_proposal(rt, staged["request_id"])["status"] == "pending"


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


def test_memory_proposal_requires_bound_thread_at_resolve(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    rt = tmp_path / "rt"
    staged = stage_writeback_proposal(
        rt,
        ws,
        "inbox/memory.md",
        "candidate",
        thread_id="memory-session",
        require_absent=True,
        proposal_kind="obsidian_memory_candidate",
    )

    with pytest.raises(WritebackError, match="thread mismatch"):
        resolve_writeback_proposal(rt, staged["request_id"], "approve")

    assert not (ws / "inbox" / "memory.md").exists()
    assert load_writeback_proposal(rt, staged["request_id"])["status"] == "pending"


def test_resolve_rejects_proposal_with_missing_integrity_digest(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    rt = tmp_path / "rt"
    staged = stage_writeback_proposal(rt, ws, "a.txt", "data")
    proposal_path = rt / "writeback-proposals" / f"{staged['request_id']}.json"
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    proposal.pop("proposal_digest")
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")

    with pytest.raises(WritebackError, match="integrity"):
        resolve_writeback_proposal(rt, staged["request_id"], "approve")

    assert not (ws / "a.txt").exists()


def test_create_only_proposal_fails_if_target_appears_before_approval(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    rt = tmp_path / "rt"
    staged = stage_writeback_proposal(
        rt,
        ws,
        "inbox/memory.md",
        "candidate",
        thread_id="memory-session",
        require_absent=True,
        redact_preview_root=True,
        proposal_kind="writeback",
    )
    assert "workspace_root" not in staged["preview"]
    target = ws / "inbox" / "memory.md"
    target.parent.mkdir(parents=True)
    target.write_text("user content", encoding="utf-8")

    with pytest.raises(WritebackError, match="create-only target already exists"):
        resolve_writeback_proposal(
            rt,
            staged["request_id"],
            "approve",
            expected_thread_id="memory-session",
        )

    assert target.read_text(encoding="utf-8") == "user content"
    assert load_writeback_proposal(rt, staged["request_id"])["status"] == "failed"


def test_create_only_proposal_is_claimed_exactly_once(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    ws = tmp_path / "ws"
    ws.mkdir()
    rt = tmp_path / "rt"
    staged = stage_writeback_proposal(
        rt,
        ws,
        "inbox/memory.md",
        "candidate",
        thread_id="memory-session",
        require_absent=True,
        proposal_kind="writeback",
    )

    def approve():
        return resolve_writeback_proposal(
            rt,
            staged["request_id"],
            "approve",
            expected_thread_id="memory-session",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: approve(), range(2)))

    assert sum(bool(item.get("applied")) for item in outcomes) == 1
    assert (ws / "inbox" / "memory.md").read_text(encoding="utf-8") == "candidate"


def test_create_only_proposal_claim_is_exactly_once_across_processes(tmp_path):
    """A separate-process race must not overwrite the active claim file."""
    ws = tmp_path / "ws"
    ws.mkdir()
    rt = tmp_path / "rt"
    staged = stage_writeback_proposal(
        rt,
        ws,
        "inbox/memory.md",
        "candidate",
        thread_id="memory-session",
        require_absent=True,
        proposal_kind="writeback",
    )

    context = multiprocessing.get_context("spawn")
    start_gate = context.Event()
    ready_queue = context.Queue()
    result_queue = context.Queue()
    processes = [
        context.Process(
            target=_approve_create_only_proposal_in_child,
            args=(str(rt), staged["request_id"], start_gate, ready_queue, result_queue),
        )
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    for _ in processes:
        assert ready_queue.get(timeout=10) == "ready"
    start_gate.set()
    for process in processes:
        process.join(timeout=15)
        assert process.exitcode == 0

    outcomes = [result_queue.get(timeout=10) for _ in processes]
    assert not [item for item in outcomes if item.get("error")]
    assert sum(bool(item.get("applied")) for item in outcomes) == 1
    assert sum(bool(item.get("already_resolved")) for item in outcomes) == 1
    assert (ws / "inbox" / "memory.md").read_text(encoding="utf-8") == "candidate"
    assert load_writeback_proposal(rt, staged["request_id"])["status"] == "applied"
    audit_files = list((rt / "writeback-runs" / staged["request_id"]).glob("*.json"))
    assert len(audit_files) == 1


def test_live_cross_process_claim_cannot_be_recovered_before_owner_metadata(
    tmp_path,
    monkeypatch,
):
    """A visible claim must already identify its still-running owner."""
    from control_plane.obsidian_memory import memory_authority_fingerprint

    ws = tmp_path / "ws"
    ws.mkdir()
    rt = tmp_path / "rt"
    monkeypatch.setenv("DEVFRAME_OBSIDIAN_MEMORY_ROOT", str(ws))
    monkeypatch.setenv("DEVFRAME_OBSIDIAN_MEMORY_ALLOWLIST", '["existing.md"]')
    staged = stage_writeback_proposal(
        rt,
        ws,
        "inbox/memory.md",
        "candidate",
        thread_id="memory-session",
        project_id="demo",
        require_absent=True,
        proposal_kind="obsidian_memory_candidate",
        authority_fingerprint=memory_authority_fingerprint("demo"),
    )

    context = multiprocessing.get_context("spawn")
    claim_visible = context.Event()
    resume_owner = context.Event()
    result_queue = context.Queue()
    owner = context.Process(
        target=_approve_with_claim_link_paused,
        args=(str(rt), staged["request_id"], claim_visible, resume_owner, result_queue),
    )
    contender = context.Process(
        target=_approve_while_live_claim_is_paused,
        args=(str(rt), staged["request_id"], claim_visible, result_queue),
    )
    owner.start()
    contender.start()

    contender.join(timeout=15)
    assert contender.exitcode == 0
    contender_result = result_queue.get(timeout=10)
    assert contender_result["role"] == "contender"
    assert not contender_result.get("error")
    assert contender_result["applied"] is False
    assert contender_result["already_resolved"] is True
    assert contender_result["status"] == "applying"

    resume_owner.set()
    owner.join(timeout=15)
    assert owner.exitcode == 0
    owner_result = result_queue.get(timeout=10)
    assert owner_result == {"role": "owner", "applied": True, "status": "applied"}
    assert (ws / "inbox" / "memory.md").read_text(encoding="utf-8") == "candidate"
    assert load_writeback_proposal(rt, staged["request_id"])["status"] == "applied"
    audit_files = list((rt / "writeback-runs" / staged["request_id"]).glob("*.json"))
    assert len(audit_files) == 1


@pytest.mark.parametrize(
    "relative_path",
    ["note.md ", "note.md.", "note.md:stream", "CON.md", ".obsidian/config.json"],
)
def test_writeback_rejects_windows_alias_and_obsidian_config_paths(tmp_path, relative_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    with pytest.raises(WritebackError):
        stage_writeback_proposal(tmp_path / "rt", ws, relative_path, "x")
