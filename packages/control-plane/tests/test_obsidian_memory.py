"""Tests for the bounded Obsidian-to-Codex memory adapter."""
from __future__ import annotations

import hashlib
import json

import pytest

import control_plane.writeback as writeback_module
from control_plane.obsidian_memory import (
    MAX_FRONTMATTER_CHARS,
    MAX_FRONTMATTER_LINES,
    MEMORY_ALLOWLIST_ENV,
    MEMORY_INBOX_ENV,
    MEMORY_ROOT_ENV,
    ObsidianMemoryError,
    search_obsidian_memory,
    stage_obsidian_memory_proposal,
)
from control_plane.writeback import (
    WritebackError,
    list_pending_writeback_proposals,
    load_writeback_proposal,
    resolve_writeback_proposal,
)


def _configure(monkeypatch, vault, paths):
    monkeypatch.setenv(MEMORY_ROOT_ENV, str(vault))
    monkeypatch.setenv(MEMORY_ALLOWLIST_ENV, json.dumps(paths))


def test_search_returns_bounded_chinese_match_with_governance_metadata(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "memory.md"
    note.write_text(
        """---
project_id: demo
authority: reviewed
freshness: current
---
# Codex 记忆

永久记忆应当只从显式允许的笔记中检索，并保留来源哈希。
""",
        encoding="utf-8",
    )
    _configure(monkeypatch, vault, ["memory.md"])

    payload = search_obsidian_memory(
        project_id="demo",
        query="永久记忆",
        relative_paths=["memory.md"],
    )

    assert payload["authorityBoundary"] == "untrusted_guidance_only"
    assert payload["limitations"]
    assert len(payload["results"]) == 1
    result = payload["results"][0]
    assert result["relativePath"] == "memory.md"
    assert result["sha256"] == hashlib.sha256(note.read_bytes()).hexdigest()
    assert "永久记忆" in result["excerpt"]
    assert result["untrustedReference"] is True
    assert result["authority"] == {"declared": "reviewed", "effective": "guidance_only"}
    assert result["freshness"]["state"] == "current"
    assert str(vault) not in str(payload)


def test_search_omits_secret_bearing_note_without_echoing_secret_or_path(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
    (vault / "private.md").write_text(
        f"永久记忆配置\napi_key: {secret}\n",
        encoding="utf-8",
    )
    _configure(monkeypatch, vault, ["private.md"])

    payload = search_obsidian_memory(
        project_id="demo",
        query="永久记忆",
        relative_paths=["private.md"],
    )

    serialized = str(payload)
    assert payload["results"] == []
    assert payload["selection"]["omitted"]["secretBearing"] == 1
    assert secret not in serialized
    assert "private.md" not in serialized
    assert str(vault) not in serialized


@pytest.mark.parametrize(
    "assignment",
    [
        "client_secret: client-secret-value-123456",
        "refresh_token=refresh-token-value-123456",
        "credential: credential-value-123456",
        "private-key: private-key-value-123456",
        "aws_secret_access_key: synthetic-secret-value-123456",
        "github_token=synthetic-token-value-123456",
        "token: eyJhbGciOiJIUzI1NiJ9.payload.signature",
    ],
)
def test_search_omits_recognized_secret_assignments(tmp_path, monkeypatch, assignment):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "private.md").write_text(
        f"needle\n{assignment}\n",
        encoding="utf-8",
    )
    _configure(monkeypatch, vault, ["private.md"])

    payload = search_obsidian_memory(
        project_id="demo", query="needle", relative_paths=["private.md"]
    )

    serialized = str(payload)
    assert payload["results"] == []
    assert payload["selection"]["omitted"]["secretBearing"] == 1
    assert assignment not in serialized
    assert str(vault) not in serialized


def test_search_allows_non_secret_token_discussion(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "guidance.md").write_text(
        "Token: short\nUse a token budget when planning a task.\n",
        encoding="utf-8",
    )
    _configure(monkeypatch, vault, ["guidance.md"])

    payload = search_obsidian_memory(
        project_id="demo", query="token budget", relative_paths=["guidance.md"]
    )

    assert len(payload["results"]) == 1


def test_search_requires_caller_paths_to_be_server_allowlist_subset(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "allowed.md").write_text("永久记忆", encoding="utf-8")
    (vault / "guessed.md").write_text("不应读取", encoding="utf-8")
    _configure(monkeypatch, vault, ["allowed.md"])

    with pytest.raises(ObsidianMemoryError, match="outside the server"):
        search_obsidian_memory(
            project_id="demo",
            query="不应读取",
            relative_paths=["guessed.md"],
        )


@pytest.mark.parametrize(
    "relative_path",
    [
        ".",
        "../x.md",
        "note.md ",
        "note.md.",
        "note.md:stream",
        "CON.md",
        ".obsidian/config.md",
        "C:\\vault\\note.md",
        "\\\\server\\share\\note.md",
        "*.md",
    ],
)
def test_search_rejects_unsafe_configured_paths(tmp_path, monkeypatch, relative_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    _configure(monkeypatch, vault, [relative_path])
    with pytest.raises(ObsidianMemoryError):
        search_obsidian_memory(
            project_id="demo",
            query="memory",
            relative_paths=[relative_path],
        )


def test_search_omits_other_project_memory(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "other.md").write_text(
        "---\nproject_id: other\n---\n# Memory\nshared-looking lesson",
        encoding="utf-8",
    )
    _configure(monkeypatch, vault, ["other.md"])
    payload = search_obsidian_memory(
        project_id="demo", query="shared-looking", relative_paths=["other.md"]
    )
    assert payload["results"] == []
    assert payload["selection"]["omitted"]["scopeMismatch"] == 1


@pytest.mark.parametrize(
    "frontmatter",
    [
        'title: "unterminated',
        "title: [unterminated",
        "custom_property: one\ncustom_property: two",
        'title: memory\n"title": other',
        "tags:\n  - *shared",
        "title: &shared memory\ncustom_property: *shared",
        "tags:\n  - !private memory",
        "- title",
        "title: memory",
        "\n".join(
            f"custom_{index}: value" for index in range(MAX_FRONTMATTER_LINES)
        )
        + "\n---\nneedle",
        "custom_property: " + ("x" * 501),
        "custom_property: " + ("x" * (MAX_FRONTMATTER_CHARS + 1)),
    ],
    ids=[
        "unterminated-quote",
        "malformed-flow-value",
        "duplicate-custom-property",
        "duplicate-quoted-property",
        "alias-list-item",
        "anchor-and-alias",
        "custom-tag-list-item",
        "non-mapping-root",
        "unclosed",
        "line-limit",
        "value-limit",
        "character-limit",
    ],
)
def test_search_omits_invalid_frontmatter_without_disclosing_vault_path(
    tmp_path, monkeypatch, frontmatter
):
    vault = tmp_path / "private-vault"
    vault.mkdir()
    note = vault / "invalid.md"
    if frontmatter.endswith("---\nneedle"):
        note_text = f"---\n{frontmatter}"
    elif frontmatter == "title: memory":
        note_text = f"---\n{frontmatter}\nneedle"
    else:
        note_text = f"---\n{frontmatter}\n---\nneedle"
    note.write_text(note_text, encoding="utf-8")
    _configure(monkeypatch, vault, ["invalid.md"])

    payload = search_obsidian_memory(
        project_id="demo", query="needle", relative_paths=["invalid.md"]
    )

    assert payload["results"] == []
    assert payload["selection"]["omitted"]["unavailable"] == 1
    assert str(vault) not in str(payload)


def test_search_accepts_flat_custom_properties_and_plain_tag_list(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "valid.md").write_text(
        """---
project_id: demo
title: "Use !important for Memory: retrieval"
custom property: preserved by Obsidian
tags: [memory, retrieval]
---
needle
""",
        encoding="utf-8",
    )
    _configure(monkeypatch, vault, ["valid.md"])

    payload = search_obsidian_memory(
        project_id="demo", query="needle", relative_paths=["valid.md"]
    )

    assert len(payload["results"]) == 1
    assert payload["results"][0]["title"] == "Use !important for Memory: retrieval"


def test_search_accepts_one_leading_utf8_bom_and_hashes_original_bytes(
    tmp_path, monkeypatch
):
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "bom.md"
    data = b"\xef\xbb\xbf---\nproject_id: demo\n---\nneedle\n"
    note.write_bytes(data)
    _configure(monkeypatch, vault, ["bom.md"])

    payload = search_obsidian_memory(
        project_id="demo", query="needle", relative_paths=["bom.md"]
    )

    assert len(payload["results"]) == 1
    assert payload["results"][0]["sha256"] == hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize(
    "data",
    [
        b"needle\xff",
        b"needle\x00hidden",
        b"needle\xef\xbb\xbfhidden",
        b"\xef\xbb\xbf\xef\xbb\xbfneedle",
    ],
    ids=["invalid-utf8", "nul", "embedded-bom", "duplicate-leading-bom"],
)
def test_search_omits_invalid_utf8_or_text_markers_without_disclosing_vault_path(
    tmp_path, monkeypatch, data
):
    vault = tmp_path / "private-vault"
    vault.mkdir()
    (vault / "invalid.md").write_bytes(data)
    _configure(monkeypatch, vault, ["invalid.md"])

    payload = search_obsidian_memory(
        project_id="demo", query="needle", relative_paths=["invalid.md"]
    )

    assert payload["results"] == []
    assert payload["selection"]["omitted"]["unavailable"] == 1
    assert str(vault) not in str(payload)


def test_missing_memory_root_error_does_not_disclose_absolute_path(tmp_path, monkeypatch):
    missing_root = tmp_path / "private-vault-does-not-exist"
    _configure(monkeypatch, missing_root, ["memory.md"])

    with pytest.raises(ObsidianMemoryError) as exc_info:
        search_obsidian_memory(
            project_id="demo", query="needle", relative_paths=["memory.md"]
        )

    assert str(missing_root) not in str(exc_info.value)


@pytest.mark.parametrize("location", ["title", "frontmatter", "body"])
@pytest.mark.parametrize(
    "variant_name",
    ["native", "posix", "json-native", "json-posix-slashes"],
)
def test_search_omits_note_containing_absolute_vault_root_variants(
    tmp_path, monkeypatch, location, variant_name
):
    vault = tmp_path / "私人-vault"
    vault.mkdir()
    variants = {
        "native": str(vault),
        "posix": vault.as_posix(),
        "json-native": json.dumps(str(vault)),
        "json-posix-slashes": json.dumps(vault.as_posix()).replace("/", r"\/"),
    }
    leaked_root = variants[variant_name]
    title = f"needle {leaked_root}" if location == "title" else "Memory"
    custom_property = leaked_root if location == "frontmatter" else "safe"
    body = f"needle {leaked_root}" if location == "body" else "needle"
    (vault / "leaking.md").write_text(
        "\n".join(
            [
                "---",
                "project_id: demo",
                f"title: {title}",
                f"custom_property: {custom_property}",
                "---",
                body,
            ]
        ),
        encoding="utf-8",
    )
    _configure(monkeypatch, vault, ["leaking.md"])

    payload = search_obsidian_memory(
        project_id="demo", query="needle", relative_paths=["leaking.md"]
    )

    serialized = json.dumps(payload, ensure_ascii=False)
    assert payload["results"] == []
    assert payload["selection"]["omitted"]["unavailable"] == 1
    assert str(vault) not in serialized
    assert vault.as_posix() not in serialized
    assert json.dumps(str(vault))[1:-1] not in serialized


def test_proposal_stages_create_only_bound_note_without_writing_vault(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    runtime = tmp_path / "runtime"
    _configure(monkeypatch, vault, ["existing.md"])

    payload = stage_obsidian_memory_proposal(
        runtime,
        project_id="demo",
        title="最小化改动",
        lesson="修改前先读取相关文件，只做目标要求的精确变化。",
        memory_type="workflow_rule",
        source_refs=["docs/agent-runtime/agent-coding-discipline.md#agent-discipline-006"],
        thread_id="mcp-session-1",
    )

    assert payload["staged"] is True
    assert payload["threadId"] == "mcp-session-1"
    assert payload["operation"] == "created"
    assert str(vault) not in str(payload)
    assert not (vault / payload["relativePath"]).exists()
    pending = list_pending_writeback_proposals(runtime)
    assert len(pending) == 1
    assert "workspace_root" not in pending[0]["preview"]
    proposal = load_writeback_proposal(runtime, payload["requestId"])
    assert proposal["require_absent"] is True
    assert proposal["thread_id"] == "mcp-session-1"

    with pytest.raises(WritebackError, match="thread mismatch"):
        resolve_writeback_proposal(
            runtime,
            payload["requestId"],
            "approve",
            expected_thread_id="other-session",
        )
    result = resolve_writeback_proposal(
        runtime,
        payload["requestId"],
        "approve",
        expected_thread_id="mcp-session-1",
    )
    assert result["applied"] is True
    assert str(vault) not in str(result)
    note = vault / payload["relativePath"]
    text = note.read_text(encoding="utf-8")
    assert "authority: candidate" in text
    assert "status: proposed" in text
    assert "最小化改动" in text


@pytest.mark.parametrize("drift", ["root", "inbox", "allowlist"])
def test_proposal_approval_rejects_memory_authority_drift(
    tmp_path,
    monkeypatch,
    drift,
):
    vault = tmp_path / "vault"
    vault.mkdir()
    runtime = tmp_path / "runtime"
    _configure(monkeypatch, vault, ["existing.md"])
    payload = stage_obsidian_memory_proposal(
        runtime,
        project_id="demo",
        title="Authority-bound memory",
        lesson="Approval must use the same server-owned memory configuration.",
        memory_type="lesson",
        source_refs=["run-1"],
        thread_id="mcp-session-1",
    )

    if drift == "root":
        replacement = tmp_path / "replacement-vault"
        replacement.mkdir()
        monkeypatch.setenv(MEMORY_ROOT_ENV, str(replacement))
    elif drift == "inbox":
        monkeypatch.setenv(MEMORY_INBOX_ENV, "_devframe/other-inbox")
    else:
        monkeypatch.setenv(MEMORY_ALLOWLIST_ENV, '["other.md"]')

    with pytest.raises(WritebackError, match="authority changed"):
        resolve_writeback_proposal(
            runtime,
            payload["requestId"],
            "approve",
            expected_thread_id="mcp-session-1",
        )

    assert not (vault / payload["relativePath"]).exists()
    assert load_writeback_proposal(runtime, payload["requestId"])["status"] == "pending"


def test_memory_proposal_recovers_after_crash_before_apply(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    runtime = tmp_path / "runtime"
    _configure(monkeypatch, vault, ["existing.md"])
    payload = stage_obsidian_memory_proposal(
        runtime,
        project_id="demo",
        title="Recover before apply",
        lesson="A claimed proposal must be retryable after a process crash.",
        memory_type="lesson",
        source_refs=["run-before"],
        thread_id="mcp-session-1",
    )
    original_apply = writeback_module.apply_writeback_with_audit

    def crash_before_apply(*_args, **_kwargs):
        raise SystemExit("simulated crash before apply")

    monkeypatch.setattr(writeback_module, "apply_writeback_with_audit", crash_before_apply)
    with pytest.raises(SystemExit):
        resolve_writeback_proposal(
            runtime,
            payload["requestId"],
            "approve",
            expected_thread_id="mcp-session-1",
        )
    assert load_writeback_proposal(runtime, payload["requestId"])["status"] == "applying"

    monkeypatch.setattr(writeback_module, "_PROCESS_INSTANCE_ID", "restarted-instance")
    monkeypatch.setattr(writeback_module, "_PROCESS_PID", 999_999_999)
    monkeypatch.setattr(writeback_module, "_process_is_alive", lambda _pid: False)
    monkeypatch.setattr(writeback_module, "apply_writeback_with_audit", original_apply)
    result = resolve_writeback_proposal(
        runtime,
        payload["requestId"],
        "approve",
        expected_thread_id="mcp-session-1",
    )
    assert result["applied"] is True
    assert (vault / payload["relativePath"]).exists()
    assert load_writeback_proposal(runtime, payload["requestId"])["status"] == "applied"


def test_memory_proposal_recovers_after_crash_after_create_before_audit(
    tmp_path,
    monkeypatch,
):
    vault = tmp_path / "vault"
    vault.mkdir()
    runtime = tmp_path / "runtime"
    _configure(monkeypatch, vault, ["existing.md"])
    payload = stage_obsidian_memory_proposal(
        runtime,
        project_id="demo",
        title="Recover after create",
        lesson="A created target must be verified idempotently before recovery.",
        memory_type="lesson",
        source_refs=["run-after"],
        thread_id="mcp-session-1",
    )
    original_apply = writeback_module.apply_writeback_with_audit

    def create_then_crash(workspace_root, relative_path, contents, **kwargs):
        writeback_module.apply_single_file_writeback(
            workspace_root,
            relative_path,
            contents,
            require_absent=True,
        )
        raise SystemExit("simulated crash after create")

    monkeypatch.setattr(writeback_module, "apply_writeback_with_audit", create_then_crash)
    with pytest.raises(SystemExit):
        resolve_writeback_proposal(
            runtime,
            payload["requestId"],
            "approve",
            expected_thread_id="mcp-session-1",
        )
    assert (vault / payload["relativePath"]).exists()
    assert not (runtime / "writeback-runs" / payload["requestId"]).exists()

    monkeypatch.setattr(writeback_module, "_PROCESS_INSTANCE_ID", "restarted-instance")
    monkeypatch.setattr(writeback_module, "_PROCESS_PID", 999_999_999)
    monkeypatch.setattr(writeback_module, "_process_is_alive", lambda _pid: False)
    monkeypatch.setattr(writeback_module, "apply_writeback_with_audit", original_apply)
    result = resolve_writeback_proposal(
        runtime,
        payload["requestId"],
        "approve",
        expected_thread_id="mcp-session-1",
    )
    assert result["applied"] is True
    audit_files = list(
        (runtime / "writeback-runs" / payload["requestId"]).glob("*.json")
    )
    assert len(audit_files) == 1
    assert json.loads(audit_files[0].read_text(encoding="utf-8"))["recovered"] is True


def test_secret_proposal_is_rejected_before_runtime_persistence(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    runtime = tmp_path / "runtime"
    _configure(monkeypatch, vault, ["existing.md"])
    with pytest.raises(ObsidianMemoryError, match="secret policy"):
        stage_obsidian_memory_proposal(
            runtime,
            project_id="demo",
            title="secret",
            lesson="api_key: sk-abcdefghijklmnopqrstuvwxyz123456",
            memory_type="lesson",
            source_refs=["run-1"],
            thread_id="mcp-session-1",
        )
    assert not (runtime / "writeback-proposals").exists()


@pytest.mark.parametrize(
    "assignment",
    [
        "client_secret: client-secret-value-123456",
        "refresh_token=refresh-token-value-123456",
        "credential: credential-value-123456",
        "private_key: private-key-value-123456",
        "aws_secret_access_key: synthetic-secret-value-123456",
        "github_token=synthetic-token-value-123456",
        "token: eyJhbGciOiJIUzI1NiJ9.payload.signature",
    ],
)
@pytest.mark.parametrize("field", ["title", "lesson", "source_ref"])
def test_recognized_secret_proposal_is_rejected_before_runtime_persistence(
    tmp_path, monkeypatch, assignment, field
):
    vault = tmp_path / "vault"
    vault.mkdir()
    runtime = tmp_path / "runtime"
    _configure(monkeypatch, vault, ["existing.md"])

    with pytest.raises(ObsidianMemoryError, match="secret policy"):
        stage_obsidian_memory_proposal(
            runtime,
            project_id="demo",
            title=assignment if field == "title" else "secret candidate",
            lesson=assignment if field == "lesson" else "safe lesson",
            memory_type="lesson",
            source_refs=[assignment if field == "source_ref" else "run-1"],
            thread_id="mcp-session-1",
        )

    assert not (runtime / "writeback-proposals").exists()
