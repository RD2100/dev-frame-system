from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


CONTROL_PLANE_ROOT = Path(__file__).resolve().parents[1]


def _run_stdio(
    project: Path,
    runtime: Path,
    vault: Path,
    messages: list[dict[str, object]],
    *,
    read_only: bool = False,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(CONTROL_PLANE_ROOT)
    env["DEVFRAME_OBSIDIAN_MEMORY_ROOT"] = str(vault)
    if read_only:
        env["DEVFRAME_OBSIDIAN_MEMORY_READ_ONLY"] = "true"
    command = [
        sys.executable,
        "-c",
        "from control_plane.cli import main; raise SystemExit(main())",
        "memory",
        "mcp-stdio",
        "--runtime-dir",
        str(runtime),
    ]
    stdin = "\n".join(json.dumps(message) for message in messages) + "\n"
    return subprocess.run(
        command,
        cwd=project,
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=10,
        check=False,
    )


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    handoff = project / "docs" / "status" / "HANDOFF.md"
    handoff.parent.mkdir(parents=True)
    handoff.write_text("# Execution Root\n\nCurrent milestone: stdio memory.\n", encoding="utf-8")
    return project


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    return vault


def test_stdio_subprocess_initializes_lists_memory_only_and_recalls_current_project(tmp_path):
    project = _project(tmp_path)
    runtime = tmp_path / "runtime"
    vault = _vault(tmp_path)
    result = _run_stdio(
        project,
        runtime,
        vault,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "recall_project_plan", "arguments": {}},
            },
        ],
    )

    assert result.returncode == 0, result.stderr
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert [response["id"] for response in responses] == [1, 2, 3]
    assert responses[0]["result"]["serverInfo"]["name"] == "devframe-memory"
    tools = responses[1]["result"]["tools"]
    names = {tool["name"] for tool in tools}
    assert names == {
        "propose_project_plan",
        "recall_project_plan",
        "list_project_lessons",
        "search_project_lessons",
        "capture_project_checkpoint",
        "create_project_lesson",
        "propose_global_playbook_promotion",
    }
    assert all("projectId" not in tool["inputSchema"].get("properties", {}) for tool in tools)
    recalled = json.loads(responses[2]["result"]["content"][0]["text"])
    assert responses[2]["result"]["isError"] is False
    assert recalled["status"] == "missing"
    assert recalled["projectId"]
    assert str(project) not in result.stdout
    assert str(runtime) not in result.stdout
    assert str(vault) not in result.stdout


def test_stdio_read_only_mode_hides_write_tools(tmp_path):
    result = _run_stdio(
        _project(tmp_path),
        tmp_path / "runtime",
        _vault(tmp_path),
        [{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}],
        read_only=True,
    )

    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    names = {tool["name"] for tool in response["result"]["tools"]}
    assert names == {
        "recall_project_plan",
        "list_project_lessons",
        "search_project_lessons",
    }


def test_stdio_rejects_explicit_cross_project_id(tmp_path):
    result = _run_stdio(
        _project(tmp_path),
        tmp_path / "runtime",
        _vault(tmp_path),
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "recall_project_plan",
                    "arguments": {"projectId": "another-project"},
                },
            }
        ],
    )

    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    payload = json.loads(response["result"]["content"][0]["text"])
    assert response["result"]["isError"] is True
    assert payload["error"] == "project_scope_rejected"


def test_stdio_returns_parse_error_and_keeps_stdout_json_only(tmp_path):
    project = _project(tmp_path)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(CONTROL_PLANE_ROOT)
    env["DEVFRAME_OBSIDIAN_MEMORY_ROOT"] = str(_vault(tmp_path))
    command = [
        sys.executable,
        "-c",
        "from control_plane.cli import main; raise SystemExit(main())",
        "memory",
        "mcp-stdio",
        "--runtime-dir",
        str(tmp_path / "runtime"),
    ]

    result = subprocess.run(
        command,
        cwd=project,
        env=env,
        input='not-json\n{"jsonrpc":"2.0","id":2,"method":"ping"}\n',
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert responses[0]["error"]["code"] == -32700
    assert responses[1] == {"jsonrpc": "2.0", "id": 2, "result": {}}


def test_stdio_ignores_idless_notifications_and_rejects_invalid_shapes(tmp_path):
    vault = _vault(tmp_path)
    result = _run_stdio(
        _project(tmp_path),
        tmp_path / "runtime",
        vault,
        [
            {"jsonrpc": "2.0", "method": "ping"},
            {"jsonrpc": "2.0", "method": "tools/list", "params": {}},
            {"jsonrpc": "1.0", "method": "ping"},
            {"method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "create_project_lesson",
                    "arguments": {
                        "idempotencyKey": "idless-must-not-run",
                        "title": "Must not exist",
                        "lesson": "An id-less notification must not write.",
                    },
                },
            },
            {"jsonrpc": "1.0", "id": 1, "method": "ping"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": []},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "recall_project_plan", "arguments": []},
            },
            {"jsonrpc": "2.0", "id": 4, "method": "ping"},
        ],
    )

    assert result.returncode == 0, result.stderr
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert [response["id"] for response in responses] == [None, 2, 3, 4]
    assert responses[0]["error"]["code"] == -32600
    assert responses[1]["error"]["code"] == -32602
    assert responses[2]["error"]["code"] == -32602
    assert responses[3] == {"jsonrpc": "2.0", "id": 4, "result": {}}
    assert list(vault.rglob("*.md")) == []


def test_portable_mcp_manifests_start_the_same_command_in_client_native_shapes():
    repository_root = CONTROL_PLANE_ROOT.parents[1]
    plugin_manifest = json.loads(
        (
            repository_root / "packages" / "devframe-memory" / ".mcp.json"
        ).read_text(encoding="utf-8")
    )
    bootstrap_manifest = json.loads(
        (
            repository_root
            / "templates"
            / "runtime-bootstrap"
            / "devframe-memory.mcp.json"
        ).read_text(encoding="utf-8")
    )
    packaged_bootstrap_manifest = json.loads(
        (
            repository_root
            / "packages"
            / "control-plane"
            / "templates"
            / "runtime-bootstrap"
            / "devframe-memory.mcp.json"
        ).read_text(encoding="utf-8")
    )

    assert packaged_bootstrap_manifest == bootstrap_manifest
    plugin_server = plugin_manifest["devframe-memory"]
    claude_server = bootstrap_manifest["mcpServers"]["devframe-memory"]
    assert plugin_server == {
        "command": "devframe",
        "args": ["memory", "mcp-stdio"],
    }
    assert claude_server == {
        "type": "stdio",
        "command": "devframe",
        "args": ["memory", "mcp-stdio"],
    }
