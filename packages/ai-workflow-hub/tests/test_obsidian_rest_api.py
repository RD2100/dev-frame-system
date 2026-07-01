import json

from ai_workflow_hub.context_layer.adapters.obsidian_rest_api import (
    MANAGED_BLOCK_END,
    MANAGED_BLOCK_START,
    build_obsidian_rest_sync_apply_report,
    build_obsidian_rest_sync_plan_report,
    build_obsidian_rest_probe_report,
    sync_markdown_files_to_obsidian_rest,
)


class FakeResponse:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text
        self.content = text.encode("utf-8")


class FakeHttpClient:
    def __init__(self, *, remote_status: int = 200, remote_text: str = ""):
        self.calls = []
        self.remote_status = remote_status
        self.remote_text = remote_text

    def request(self, method, url, **kwargs):
        self.calls.append({
            "method": method,
            "url": url,
            "headers": dict(kwargs.get("headers") or {}),
            "content": kwargs.get("content"),
        })
        if url.endswith("/.devframe-probe/auth-check-do-not-create.md"):
            return FakeResponse(404)
        if method == "PUT":
            return FakeResponse(204)
        if method == "POST":
            return FakeResponse(204)
        if method == "GET" and "/vault/" in url:
            return FakeResponse(self.remote_status, self.remote_text)
        return FakeResponse(200)


def _paper_note(managed: str, user: str = "") -> str:
    return "\n".join([
        "---",
        'schema_type: "research_paper"',
        "---",
        "",
        MANAGED_BLOCK_START,
        managed,
        MANAGED_BLOCK_END,
        "",
        user,
    ])


def test_probe_blocks_without_token():
    client = FakeHttpClient()
    report = build_obsidian_rest_probe_report(
        token_env="MISSING_OBSIDIAN_TOKEN",
        http_client=client,
    )

    assert report["service_status"] == "PASS"
    assert report["auth_status"] == "BLOCKED_MISSING_TOKEN"
    assert report["overall_status"] == "BLOCKED_MISSING_TOKEN"
    assert report["token_present"] is False
    assert report["token_persisted"] is False


def test_probe_can_write_and_open_without_persisting_token():
    client = FakeHttpClient()
    report = build_obsidian_rest_probe_report(
        token="secret-value",
        write_probe=True,
        open_probe=True,
        http_client=client,
    )

    assert report["overall_status"] == "PASS"
    assert report["auth_status"] == "PASS"
    assert report["write_status"] == "PASS"
    assert report["open_status"] == "PASS"
    assert report["token_present"] is True
    assert report["token_persisted"] is False
    assert "secret-value" not in json.dumps(report)
    assert any(call["method"] == "PUT" for call in client.calls)
    assert any(call["method"] == "POST" for call in client.calls)


def test_sync_writes_files_and_opens_dashboard(tmp_path):
    note = tmp_path / "note.md"
    note.write_text("# Note\n", encoding="utf-8")
    dashboard = tmp_path / "dashboard.md"
    dashboard.write_text("# Dashboard\n", encoding="utf-8")
    client = FakeHttpClient()

    summary = sync_markdown_files_to_obsidian_rest(
        files=[
            ("Papers/note.md", note),
            ("Papers/dashboard.md", dashboard),
        ],
        token="secret-value",
        open_relative_path="Papers/dashboard.md",
        http_client=client,
    )

    assert summary["status"] == "PASS"
    assert summary["write_count"] == 2
    assert summary["open_called"] is True
    assert summary["token_persisted"] is False
    assert "secret-value" not in json.dumps(summary)
    assert [call["method"] for call in client.calls].count("PUT") == 2
    assert [call["method"] for call in client.calls].count("POST") == 1


def test_sync_rejects_unsafe_vault_relative_path(tmp_path):
    note = tmp_path / "note.md"
    note.write_text("# Note\n", encoding="utf-8")
    client = FakeHttpClient()

    summary = sync_markdown_files_to_obsidian_rest(
        files=[("../outside.md", note)],
        token="secret-value",
        http_client=client,
    )

    assert summary["status"] == "FAILED_RUNTIME"
    assert summary["write_count"] == 0
    assert summary["error_count"] == 1
    assert summary["first_error"] == "ValueError"
    assert not any(call["method"] == "PUT" for call in client.calls)


def test_sync_plan_blocks_missing_token_without_reading_remote(tmp_path):
    note = tmp_path / "note.md"
    note.write_text(_paper_note("managed"), encoding="utf-8")
    client = FakeHttpClient(remote_text=_paper_note("managed"))

    report = build_obsidian_rest_sync_plan_report(
        local_path=note,
        remote_relative_path="Papers/note.md",
        token_env="MISSING_OBSIDIAN_TOKEN",
        http_client=client,
    )

    assert report["plan_status"] == "BLOCKED_MISSING_TOKEN"
    assert report["token_present"] is False
    assert report["token_persisted"] is False
    assert report["local"]["exists"] is True
    assert not client.calls


def test_sync_plan_creates_when_remote_missing(tmp_path):
    note = tmp_path / "note.md"
    note.write_text(_paper_note("managed"), encoding="utf-8")
    client = FakeHttpClient(remote_status=404)

    report = build_obsidian_rest_sync_plan_report(
        local_path=note,
        remote_relative_path="Papers/note.md",
        token="secret-value",
        http_client=client,
    )

    assert report["remote_status"] == "MISSING"
    assert report["plan_status"] == "PLAN_CREATE_REMOTE"
    assert report["plan_action"] == "CREATE_REMOTE"
    assert [call["method"] for call in client.calls] == ["GET"]


def test_sync_plan_noop_when_local_and_remote_match(tmp_path):
    text = _paper_note("managed", "user notes")
    note = tmp_path / "note.md"
    note.write_text(text, encoding="utf-8")
    client = FakeHttpClient(remote_text=text)

    report = build_obsidian_rest_sync_plan_report(
        local_path=note,
        remote_relative_path="Papers/note.md",
        token="secret-value",
        http_client=client,
    )

    assert report["plan_status"] == "PASS_NOOP"
    assert report["plan_action"] == "NOOP"
    assert report["local"]["managed_block_present"] is True
    assert report["remote"]["managed_block_present"] is True


def test_sync_plan_preserves_remote_user_content_when_managed_matches(tmp_path):
    local_text = _paper_note("managed", "local user text")
    remote_text = _paper_note("managed", "remote user text")
    note = tmp_path / "note.md"
    note.write_text(local_text, encoding="utf-8")
    client = FakeHttpClient(remote_text=remote_text)

    report = build_obsidian_rest_sync_plan_report(
        local_path=note,
        remote_relative_path="Papers/note.md",
        token="secret-value",
        http_client=client,
    )

    assert report["plan_status"] == "PLAN_PRESERVE_REMOTE_USER_CONTENT"
    assert report["plan_action"] == "PRESERVE_REMOTE_USER_CONTENT"
    report_json = json.dumps(report)
    assert "local user text" not in report_json
    assert "remote user text" not in report_json
    assert str(note) not in report_json


def test_sync_plan_updates_managed_block_when_both_notes_are_managed(tmp_path):
    note = tmp_path / "note.md"
    note.write_text(_paper_note("new managed", "local user text"), encoding="utf-8")
    client = FakeHttpClient(remote_text=_paper_note("old managed", "remote user text"))

    report = build_obsidian_rest_sync_plan_report(
        local_path=note,
        remote_relative_path="Papers/note.md",
        token="secret-value",
        http_client=client,
    )

    assert report["plan_status"] == "PLAN_UPDATE_REMOTE_MANAGED_BLOCK"
    assert report["plan_action"] == "UPDATE_REMOTE_MANAGED_BLOCK"
    assert report["conflict"] is False


def test_sync_plan_conflicts_when_marker_is_missing(tmp_path):
    note = tmp_path / "note.md"
    note.write_text("# Plain local note\n", encoding="utf-8")
    client = FakeHttpClient(remote_text="# Plain remote note\n")

    report = build_obsidian_rest_sync_plan_report(
        local_path=note,
        remote_relative_path="Papers/note.md",
        token="secret-value",
        http_client=client,
    )

    assert report["plan_status"] == "CONFLICT_UNMANAGED_NOTE"
    assert report["plan_action"] == "REQUIRE_MANUAL_REVIEW"
    assert report["conflict"] is True


def test_sync_plan_rejects_unsafe_remote_path_before_http(tmp_path):
    note = tmp_path / "note.md"
    note.write_text(_paper_note("managed"), encoding="utf-8")
    client = FakeHttpClient(remote_text=_paper_note("managed"))

    report = build_obsidian_rest_sync_plan_report(
        local_path=note,
        remote_relative_path="../outside.md",
        token="secret-value",
        http_client=client,
    )

    assert report["plan_status"] == "BLOCKED_INVALID_REMOTE_PATH"
    assert not client.calls


def test_sync_apply_creates_when_remote_missing(tmp_path):
    note = tmp_path / "note.md"
    note.write_text(_paper_note("managed", "my user notes"), encoding="utf-8")
    client = FakeHttpClient(remote_status=404)

    report = build_obsidian_rest_sync_apply_report(
        local_path=note,
        remote_relative_path="Papers/note.md",
        token="secret-value",
        http_client=client,
    )

    assert report["apply_status"] == "APPLIED_CREATE"
    assert report["apply_action"] == "CREATED_REMOTE"
    methods = [call["method"] for call in client.calls]
    assert methods == ["GET", "PUT"]


def test_sync_apply_get_before_put_and_preserves_user_content(tmp_path):
    remote_user = "remote user notes"
    local_user = "local user notes"
    local_text = _paper_note("managed", local_user)
    remote_text = _paper_note("other managed", remote_user)
    note = tmp_path / "note.md"
    note.write_text(local_text, encoding="utf-8")
    client = FakeHttpClient(remote_text=remote_text)

    report = build_obsidian_rest_sync_apply_report(
        local_path=note,
        remote_relative_path="Papers/note.md",
        token="secret-value",
        http_client=client,
    )

    assert report["apply_status"] == "APPLIED_UPDATE"
    assert report["apply_action"] == "UPDATED_MANAGED_BLOCK"
    methods = [call["method"] for call in client.calls]
    assert methods == ["GET", "PUT"]
    put_content = client.calls[1]["content"]
    assert MANAGED_BLOCK_START in put_content
    assert "managed" in put_content
    assert remote_user in put_content
    assert local_user not in put_content
    report_json = json.dumps(report)
    assert remote_user not in report_json
    assert local_user not in report_json
    assert "secret-value" not in report_json
    assert str(note) not in report_json


def test_sync_apply_blocks_when_unmanaged_local(tmp_path):
    note = tmp_path / "note.md"
    note.write_text("# No managed block\n", encoding="utf-8")
    client = FakeHttpClient(remote_text=_paper_note("managed", "user"))

    report = build_obsidian_rest_sync_apply_report(
        local_path=note,
        remote_relative_path="Papers/note.md",
        token="secret-value",
        http_client=client,
    )

    assert report["apply_status"] == "BLOCKED_UNMANAGED_NOTE"
    assert report["apply_action"] == "REQUIRE_MANUAL_REVIEW"
    assert [call["method"] for call in client.calls] == ["GET"]


def test_sync_apply_blocks_when_unmanaged_remote(tmp_path):
    note = tmp_path / "note.md"
    note.write_text(_paper_note("managed"), encoding="utf-8")
    client = FakeHttpClient(remote_text="# No managed block\n")

    report = build_obsidian_rest_sync_apply_report(
        local_path=note,
        remote_relative_path="Papers/note.md",
        token="secret-value",
        http_client=client,
    )

    assert report["apply_status"] == "BLOCKED_UNMANAGED_NOTE"
    assert report["apply_action"] == "REQUIRE_MANUAL_REVIEW"
    assert [call["method"] for call in client.calls] == ["GET"]


def test_sync_apply_noop_when_managed_blocks_match(tmp_path):
    text = _paper_note("managed", "user notes")
    note = tmp_path / "note.md"
    note.write_text(text, encoding="utf-8")
    client = FakeHttpClient(remote_text=text)

    report = build_obsidian_rest_sync_apply_report(
        local_path=note,
        remote_relative_path="Papers/note.md",
        token="secret-value",
        http_client=client,
    )

    assert report["apply_status"] == "PASS_NOOP"
    assert report["apply_action"] == "NOOP"
    assert [call["method"] for call in client.calls] == ["GET"]


def test_sync_apply_blocks_missing_token(tmp_path):
    note = tmp_path / "note.md"
    note.write_text(_paper_note("managed"), encoding="utf-8")
    client = FakeHttpClient(remote_text=_paper_note("managed"))

    report = build_obsidian_rest_sync_apply_report(
        local_path=note,
        remote_relative_path="Papers/note.md",
        token_env="MISSING_TOKEN",
        http_client=client,
    )

    assert report["apply_status"] == "BLOCKED_MISSING_TOKEN"
    assert report["token_present"] is False
    assert not client.calls


def test_sync_apply_rejects_unsafe_path(tmp_path):
    note = tmp_path / "note.md"
    note.write_text(_paper_note("managed"), encoding="utf-8")
    client = FakeHttpClient()

    report = build_obsidian_rest_sync_apply_report(
        local_path=note,
        remote_relative_path="../outside.md",
        token="secret-value",
        http_client=client,
    )

    assert report["apply_status"] == "BLOCKED_INVALID_REMOTE_PATH"
    assert not client.calls


def test_sync_apply_blocks_missing_local(tmp_path):
    note = tmp_path / "nonexistent.md"

    report = build_obsidian_rest_sync_apply_report(
        local_path=note,
        remote_relative_path="Papers/note.md",
        token="secret-value",
    )

    assert report["apply_status"] == "BLOCKED_LOCAL_MISSING"
