from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


def _prepare_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "Obsidian-Codex-Memory"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / "memory.md").write_text("# Memory\n\nKeep recall bounded.\n", encoding="utf-8")
    return vault


def _link_runtime_ready(_python: Path, package: str) -> bool:
    return package == "link-mcp@1.7.0"


def _runtime_unavailable(_python: Path, _package: str) -> bool:
    return False


def test_confirmed_activation_writes_only_secret_free_managed_state(tmp_path: Path) -> None:
    from control_plane.obsidian_memory_activation import activate_obsidian_memory

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    config_path = codex_home / "config.toml"
    agents_path = codex_home / "AGENTS.md"
    hooks_path = codex_home / "hooks.json"
    config_path.write_text('model = "test-model"\n', encoding="utf-8")
    agents_path.write_text("# Existing global guidance\n", encoding="utf-8")
    hooks_path.write_text(
        json.dumps(
            {
                "description": "existing hooks",
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "resume",
                            "hooks": [{"type": "command", "command": "existing-hook"}],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    state_dir = tmp_path / "devframe-state"

    result = activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=Path("C:/Python/python.exe"),
        confirm=True,
        runtime_probe=_link_runtime_ready,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )

    assert result == {
        "status": "active",
        "activated": True,
        "changed": True,
        "vaultName": "Obsidian-Codex-Memory",
        "serverName": "devframe-obsidian-memory",
        "upstream": "link-mcp@1.7.0",
        "restartRequired": True,
    }

    state_text = (state_dir / "managed-activation.json").read_text(encoding="utf-8")
    config_text = config_path.read_text(encoding="utf-8")
    agents_text = agents_path.read_text(encoding="utf-8")
    hooks_text = hooks_path.read_text(encoding="utf-8")
    combined_public_text = result.__repr__() + config_text + agents_text + hooks_text

    assert str(vault.resolve()) not in combined_public_text
    assert 'model = "test-model"' in config_text
    assert "# devframe:obsidian-memory-config:start" in config_text
    assert 'enabled_tools = ["status", "recall"]' in config_text
    assert 'default_tools_approval_mode = "auto"' in config_text
    assert "# Existing global guidance" in agents_text
    assert "<!-- devframe:obsidian-memory-instructions:start -->" in agents_text
    assert "SessionStart" in agents_text
    assert "propose_obsidian_memory" in agents_text

    hooks = json.loads(hooks_text)
    session_start = hooks["hooks"]["SessionStart"]
    assert session_start[0]["hooks"][0]["command"] == "existing-hook"
    managed_hook = session_start[1]
    assert managed_hook["matcher"] == "startup|resume|clear|compact"
    assert "memory recall-hook" in managed_hook["hooks"][0]["command"]

    wiki = vault / "wiki"
    assert (vault / "raw").is_dir()
    assert (wiki / "memories").is_dir()
    assert (wiki / "index.md").read_text(encoding="utf-8").startswith("# Memory Index")
    assert json.loads((wiki / "_backlinks.json").read_text(encoding="utf-8")) == {
        "backlinks": {},
        "forward": {},
    }
    assert json.loads((wiki / "_link_schema.json").read_text(encoding="utf-8"))[
        "schema"
    ] == "link-wiki"

    state = json.loads(state_text)
    assert state["state"] == "active"
    assert state["vaultRoot"] == str(vault.resolve())
    assert state["wikiRoot"] == str(wiki.resolve())
    assert state["enabledTools"] == ["status", "recall"]
    assert state["upstreamPackage"] == "link-mcp@1.7.0"
    assert state["upstreamWheelSha256"] == (
        "7dde41ba2c5e678404a0f716809aa808cb1f245694bac126e8ee5ae7a478970f"
    )
    assert len(state["runtimeLockSha256"]) == 64
    assert state["codexHome"] == str(codex_home.resolve())


def test_confirmed_activation_is_idempotent(tmp_path: Path) -> None:
    from control_plane.obsidian_memory_activation import activate_obsidian_memory

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "devframe-state"
    runtime_python = Path("C:/Python/python.exe")
    runtime_probe = _link_runtime_ready

    first = activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=runtime_python,
        confirm=True,
        runtime_probe=runtime_probe,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )
    paths = [
        codex_home / "config.toml",
        codex_home / "AGENTS.md",
        codex_home / "hooks.json",
        state_dir / "managed-activation.json",
    ]
    before = {path: path.read_bytes() for path in paths}

    second = activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=runtime_python,
        confirm=True,
        runtime_probe=runtime_probe,
        now=lambda: "2026-07-18T01:00:00+00:00",
    )

    assert first["changed"] is True
    assert second["changed"] is False
    assert second["restartRequired"] is False
    assert {path: path.read_bytes() for path in paths} == before


def test_activation_rolls_back_all_files_when_final_state_write_fails(
    tmp_path: Path,
) -> None:
    from control_plane.obsidian_memory_activation import (
        ObsidianMemoryActivationError,
        activate_obsidian_memory,
    )

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    originals = {
        codex_home / "config.toml": b'model = "existing"\n',
        codex_home / "AGENTS.md": b"# Existing guidance\n",
        codex_home / "hooks.json": b'{"description":"keep formatting"}\n',
    }
    for path, contents in originals.items():
        path.write_bytes(contents)
    state_dir = tmp_path / "devframe-state"
    state_dir.mkdir()
    (state_dir / f".managed-activation.json.{os.getpid()}.tmp").mkdir()

    with pytest.raises(ObsidianMemoryActivationError, match="could not be completed"):
        activate_obsidian_memory(
            vault_root=vault,
            codex_home=codex_home,
            state_dir=state_dir,
            runtime_python=Path("C:/Python/python.exe"),
            confirm=True,
            runtime_probe=_link_runtime_ready,
            now=lambda: "2026-07-18T00:00:00+00:00",
        )

    assert {path: path.read_bytes() for path in originals} == originals
    assert not (vault / "wiki").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows junction policy")
def test_activation_rejects_vault_below_a_junction_ancestor(tmp_path: Path) -> None:
    from control_plane.obsidian_memory_activation import (
        ObsidianMemoryActivationError,
        activate_obsidian_memory,
    )

    actual_parent = tmp_path / "actual-parent"
    vault = _prepare_vault(actual_parent)
    junction = tmp_path / "redirected-parent"
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(actual_parent)],
        capture_output=True,
        text=True,
        check=False,
    )
    if created.returncode != 0:
        pytest.skip("junction creation is unavailable on this host")
    try:
        with pytest.raises(ObsidianMemoryActivationError, match="link or reparse"):
            activate_obsidian_memory(
                vault_root=junction / vault.name,
                codex_home=tmp_path / "codex-home",
                state_dir=tmp_path / "state",
                runtime_python=Path("C:/Python/python.exe"),
                confirm=False,
                runtime_probe=_link_runtime_ready,
                now=lambda: "2026-07-18T00:00:00+00:00",
            )
    finally:
        os.rmdir(junction)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction policy")
def test_activation_rejects_codex_home_below_a_junction_ancestor(
    tmp_path: Path,
) -> None:
    from control_plane.obsidian_memory_activation import (
        ObsidianMemoryActivationError,
        activate_obsidian_memory,
    )

    vault = _prepare_vault(tmp_path)
    actual_parent = tmp_path / "actual-codex-parent"
    (actual_parent / "codex-home").mkdir(parents=True)
    junction = tmp_path / "redirected-codex-parent"
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(actual_parent)],
        capture_output=True,
        text=True,
        check=False,
    )
    if created.returncode != 0:
        pytest.skip("junction creation is unavailable on this host")
    try:
        with pytest.raises(ObsidianMemoryActivationError, match="link or reparse"):
            activate_obsidian_memory(
                vault_root=vault,
                codex_home=junction / "codex-home",
                state_dir=tmp_path / "state",
                runtime_python=Path("C:/Python/python.exe"),
                confirm=True,
                runtime_probe=_link_runtime_ready,
                now=lambda: "2026-07-18T00:00:00+00:00",
            )
    finally:
        os.rmdir(junction)


def test_deactivation_removes_only_managed_activation(tmp_path: Path) -> None:
    from control_plane.obsidian_memory_activation import (
        activate_obsidian_memory,
        deactivate_obsidian_memory,
    )

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    config_path = codex_home / "config.toml"
    agents_path = codex_home / "AGENTS.md"
    hooks_path = codex_home / "hooks.json"
    config_before = 'model = "existing"\n'
    agents_before = "# Existing guidance\n"
    hooks_before = {
        "description": "existing hooks",
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "resume",
                    "hooks": [{"type": "command", "command": "existing-hook"}],
                }
            ]
        },
    }
    config_path.write_text(config_before, encoding="utf-8")
    agents_path.write_text(agents_before, encoding="utf-8")
    hooks_path.write_text(json.dumps(hooks_before), encoding="utf-8")
    state_dir = tmp_path / "devframe-state"

    activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=Path("C:/Python/python.exe"),
        confirm=True,
        runtime_probe=_link_runtime_ready,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )

    result = deactivate_obsidian_memory(
        codex_home=codex_home,
        state_dir=state_dir,
        confirm=True,
    )

    assert result == {
        "status": "inactive",
        "deactivated": True,
        "changed": True,
        "restartRequired": True,
    }
    assert config_path.read_text(encoding="utf-8") == config_before
    assert agents_path.read_text(encoding="utf-8") == agents_before
    assert json.loads(hooks_path.read_text(encoding="utf-8")) == hooks_before
    assert not (state_dir / "managed-activation.json").exists()
    assert (vault / "wiki" / "index.md").is_file()


def test_deactivation_restores_original_codex_file_bytes(tmp_path: Path) -> None:
    from control_plane.obsidian_memory_activation import (
        activate_obsidian_memory,
        deactivate_obsidian_memory,
    )

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    originals = {
        codex_home / "config.toml": b'model = "existing"\r\nmodel_reasoning_effort = "high"\r\n',
        codex_home / "AGENTS.md": b"# Existing guidance\r\n\r\nKeep this formatting.\r\n",
        codex_home / "hooks.json": (
            b'{"description":"compact","hooks":{"SessionStart":'
            b'[{"matcher":"resume","hooks":[{"type":"command",'
            b'"command":"existing-hook"}]}]}}'
        ),
    }
    for path, contents in originals.items():
        path.write_bytes(contents)
    state_dir = tmp_path / "state"

    activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=Path("C:/Python/python.exe"),
        confirm=True,
        runtime_probe=_link_runtime_ready,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )
    deactivate_obsidian_memory(
        codex_home=codex_home,
        state_dir=state_dir,
        confirm=True,
    )

    assert {path: path.read_bytes() for path in originals} == originals


@pytest.mark.skipif(os.name != "nt", reason="Windows junction policy")
def test_activation_rejects_existing_junction_inside_managed_wiki(
    tmp_path: Path,
) -> None:
    from control_plane.obsidian_memory_activation import (
        ObsidianMemoryActivationError,
        activate_obsidian_memory,
    )

    vault = _prepare_vault(tmp_path)
    wiki = vault / "wiki"
    wiki.mkdir()
    outside = tmp_path / "outside-memories"
    outside.mkdir()
    junction = wiki / "memories"
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        capture_output=True,
        text=True,
        check=False,
    )
    if created.returncode != 0:
        pytest.skip("junction creation is unavailable on this host")
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    try:
        with pytest.raises(ObsidianMemoryActivationError, match="link or reparse"):
            activate_obsidian_memory(
                vault_root=vault,
                codex_home=codex_home,
                state_dir=tmp_path / "state",
                runtime_python=Path("C:/Python/python.exe"),
                confirm=True,
                runtime_probe=_link_runtime_ready,
                now=lambda: "2026-07-18T00:00:00+00:00",
            )
    finally:
        os.rmdir(junction)


def test_status_revalidates_activation_without_exposing_private_paths(
    tmp_path: Path,
) -> None:
    from control_plane.obsidian_memory_activation import (
        activate_obsidian_memory,
        obsidian_memory_status,
    )

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "devframe-state"
    runtime_python = Path("C:/Python/python.exe")
    runtime_probe = _link_runtime_ready
    activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=runtime_python,
        confirm=True,
        runtime_probe=runtime_probe,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )

    result = obsidian_memory_status(
        state_dir=state_dir,
        runtime_probe=runtime_probe,
    )

    assert result == {
        "status": "active",
        "ready": True,
        "vaultName": "Obsidian-Codex-Memory",
        "serverName": "devframe-obsidian-memory",
        "upstream": "link-mcp@1.7.0",
        "enabledTools": ["status", "recall"],
    }
    assert str(vault.resolve()) not in json.dumps(result)


def test_recall_uses_only_read_tool_and_redacts_vault_path(tmp_path: Path) -> None:
    from control_plane.obsidian_memory_activation import (
        activate_obsidian_memory,
        recall_obsidian_memory,
    )

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "devframe-state"
    runtime_probe = _link_runtime_ready
    activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=Path("C:/Python/python.exe"),
        confirm=True,
        runtime_probe=runtime_probe,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )
    observed: dict[str, object] = {}

    def upstream_call(runtime_python, wiki, tool, arguments):
        observed.update(
            runtime=runtime_python,
            wiki=wiki,
            tool=tool,
            arguments=arguments,
        )
        return json.dumps(
            {
                "surface": "slim",
                "tool": "recall",
                "found": True,
                "recall_capsule": "Keep recall bounded.",
                "wiki": str(wiki),
            }
        )

    result_text = recall_obsidian_memory(
        state_dir=state_dir,
        query="bounded recall",
        budget="micro",
        limit=3,
        runtime_probe=runtime_probe,
        upstream_call=upstream_call,
    )
    result = json.loads(result_text)

    assert observed["tool"] == "recall"
    assert observed["arguments"] == {
        "query": "bounded recall",
        "budget": "micro",
        "project": "",
        "mode": "auto",
        "limit": 3,
        "context_path": "",
    }
    assert result["recall_capsule"] == "Keep recall bounded."
    assert result["wiki"] == "<redacted-memory-path>"
    assert str(vault.resolve()) not in result_text


def test_memory_server_exposes_only_status_and_recall(tmp_path: Path) -> None:
    import anyio

    from control_plane.obsidian_memory_activation import (
        activate_obsidian_memory,
        create_obsidian_memory_server,
    )

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "devframe-state"
    probe_calls: list[tuple[Path, str]] = []

    def runtime_probe(runtime: Path, package: str) -> bool:
        probe_calls.append((runtime, package))
        return True
    activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=Path("C:/Python/python.exe"),
        confirm=True,
        runtime_probe=runtime_probe,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )

    def upstream_call(_runtime_python, _wiki, tool, _arguments):
        if tool == "status":
            return json.dumps({"ready": True, "wiki": str(vault / "wiki")})
        return json.dumps(
            {"tool": "recall", "recall_capsule": "Bounded context."}
        )

    server = create_obsidian_memory_server(
        state_dir=state_dir,
        runtime_probe=runtime_probe,
        upstream_call=upstream_call,
    )
    tools = anyio.run(server.list_tools)
    anyio.run(server.call_tool, "status", {})

    assert {tool.name for tool in tools} == {"status", "recall"}
    assert not {"remember", "ingest", "review", "admin"} & {
        tool.name for tool in tools
    }
    assert len(probe_calls) == 3


def test_session_start_hook_injects_one_bounded_untrusted_brief(tmp_path: Path) -> None:
    from control_plane.obsidian_memory_activation import (
        activate_obsidian_memory,
        recall_hook_output,
    )

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "devframe-state"
    runtime_probe = _link_runtime_ready
    activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=Path("C:/Python/python.exe"),
        confirm=True,
        runtime_probe=runtime_probe,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )
    observed: dict[str, object] = {}
    context_path = str(tmp_path / "current-project")

    def upstream_call(_runtime_python, wiki, tool, arguments):
        observed.update(tool=tool, arguments=arguments)
        return json.dumps(
            {
                "mode": "brief",
                "brief": {
                    "summary": "Keep startup recall bounded.",
                    "wiki": str(wiki),
                    "context": context_path,
                },
            }
        )

    output = recall_hook_output(
        state_dir=state_dir,
        hook_input={"source": "startup", "cwd": context_path},
        runtime_probe=runtime_probe,
        upstream_call=upstream_call,
    )

    assert observed["tool"] == "recall"
    assert observed["arguments"] == {
        "query": "",
        "budget": "micro",
        "project": "",
        "mode": "brief",
        "limit": 6,
        "context_path": context_path,
    }
    assert "untrusted guidance" in output
    assert "Keep startup recall bounded." in output
    assert str(vault.resolve()) not in output
    assert context_path not in output
    assert len(output) <= 6_000


def test_recall_removes_upstream_write_guidance_from_read_only_surface(tmp_path: Path) -> None:
    from control_plane.obsidian_memory_activation import (
        activate_obsidian_memory,
        recall_obsidian_memory,
    )

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "devframe-state"
    runtime_probe = _link_runtime_ready
    activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=Path("C:/Python/python.exe"),
        confirm=True,
        runtime_probe=runtime_probe,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )

    def upstream_call(_runtime_python, _wiki, _tool, _arguments):
        return json.dumps(
            {
                "surface": "slim",
                "tool": "recall",
                "follow_up": [
                    {"tool": "admin", "arguments": {"action": "context"}}
                ],
                "agent_guidance": ["Call admin(action='context')."],
                "brief": {
                    "relevant_memories": [{"summary": "Keep recall bounded."}],
                    "agent_guidance": ["Use propose_memories for candidates."],
                    "captures": {"next_action": "capture_inbox()"},
                    "backlog": {"command": "lnk consolidate /private/path"},
                    "review": {
                        "items": [
                            {
                                "title": "Needs review",
                                "issues": [
                                    {
                                        "message": "Unknown metadata.",
                                        "suggested_action": "Use a different type.",
                                    }
                                ],
                                "actions": [
                                    {
                                        "command": "$EDITOR private.md",
                                        "tool": "edit_memory_file",
                                    }
                                ],
                            }
                        ]
                    },
                },
            }
        )

    result = recall_obsidian_memory(
        state_dir=state_dir,
        runtime_probe=runtime_probe,
        upstream_call=upstream_call,
    )

    assert "Keep recall bounded." in result
    assert "propose_memories" not in result
    assert "capture_inbox" not in result
    assert "lnk consolidate" not in result
    assert "admin" not in result
    assert "edit_memory_file" not in result
    assert "$EDITOR" not in result
    assert "Use a different type" not in result


def test_activation_preview_requires_no_runtime_and_writes_nothing(tmp_path: Path) -> None:
    from control_plane.obsidian_memory_activation import activate_obsidian_memory

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    config_path = codex_home / "config.toml"
    config_path.write_text('model = "unchanged"\n', encoding="utf-8")
    state_dir = tmp_path / "devframe-state"
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    result = activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=tmp_path / "runtime" / "python.exe",
        confirm=False,
        runtime_probe=_runtime_unavailable,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )

    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert result["status"] == "preview"
    assert result["activated"] is False
    assert before == after
    assert not (vault / "raw").exists()
    assert not (vault / "wiki").exists()
    assert not state_dir.exists()


def test_runtime_provisioning_installs_exact_link_version_in_isolated_venv(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import shutil

    from control_plane.obsidian_memory_activation import (
        provision_obsidian_memory_runtime,
    )

    state_dir = tmp_path / "state"
    legacy_runtime = state_dir / "runtime"
    legacy_runtime.mkdir(parents=True)
    legacy_audit = legacy_runtime / "mcp-audit.jsonl"
    legacy_audit.write_text('{"legacy":true}\n', encoding="utf-8")
    source_package = tmp_path / "control-plane-source"
    source_package.mkdir()
    (source_package / "setup.py").write_text("# package marker\n", encoding="utf-8")
    package_source = source_package / "control_plane"
    package_source.mkdir()
    (package_source / "__init__.py").write_text("# facade\n", encoding="utf-8")
    calls: list[list[str]] = []
    runner_environments: list[dict[str, str] | None] = []
    installed = False
    lock_contents = ""
    monkeypatch.setenv("PYTHONPATH", "C:/unsafe/source")
    monkeypatch.setenv("PYTHONHOME", "C:/unsafe/python")
    monkeypatch.setenv("VIRTUAL_ENV", "C:/unsafe/venv")

    def runner(arguments, **_kwargs):
        nonlocal installed, lock_contents
        command = [str(value) for value in arguments]
        calls.append(command)
        runner_environments.append(_kwargs.get("env"))
        if command[1:3] == ["-m", "venv"]:
            runtime_python = Path(command[3]) / "Scripts" / "python.exe"
            runtime_python.parent.mkdir(parents=True)
            runtime_python.write_bytes(b"")
        if "pip" in command and "install" in command:
            installed = True
        staged = next(
            (Path(value) for value in command if ".obsidian-memory-source-" in value),
            None,
        )
        if staged is not None:
            installed_package = (
                state_dir
                / "isolated-runtime"
                / "Lib"
                / "site-packages"
                / "control_plane"
            )
            installed_package.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(staged / "control_plane", installed_package)
        if "-r" in command:
            lock_contents = Path(command[command.index("-r") + 1]).read_text(
                encoding="utf-8"
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def runtime_probe(_python, package):
        return installed and package == "link-mcp@1.7.0"

    runtime_python = provision_obsidian_memory_runtime(
        state_dir=state_dir,
        source_package=source_package,
        base_python=Path(sys.executable),
        runner=runner,
        runtime_probe=runtime_probe,
    )

    assert runtime_python == state_dir / "isolated-runtime" / "Scripts" / "python.exe"
    assert (state_dir / "isolated-runtime" / "runtime-manifest.json").is_file()
    assert legacy_audit.read_text(encoding="utf-8") == '{"legacy":true}\n'
    source_install = next(
        command
        for command in calls
        if any(".obsidian-memory-source-" in value for value in command)
    )
    locked_install = next(command for command in calls if "-r" in command)
    assert "--upgrade" not in source_install + locked_install
    assert "--system-site-packages" not in next(
        command for command in calls if command[1:3] == ["-m", "venv"]
    )
    assert "--no-deps" in source_install
    assert "--force-reinstall" in source_install
    assert "--force-reinstall" not in locked_install
    assert str(source_package.resolve()) not in source_install
    assert "--only-binary=:all:" in locked_install
    assert "--require-hashes" in locked_install
    assert "mcp==1.28.1 --hash=sha256:2726bca5" in lock_contents
    assert "link-mcp==1.7.0 --hash=sha256:7dde41ba" in lock_contents
    assert runner_environments
    assert all(environment is not None for environment in runner_environments)
    assert all(
        forbidden not in environment
        for environment in runner_environments
        if environment is not None
        for forbidden in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV")
    )
    assert not list(state_dir.glob(".obsidian-memory-runtime-lock-*.txt"))


def test_runtime_provisioning_refreshes_legacy_same_version_facade(
    tmp_path: Path,
) -> None:
    import shutil

    from control_plane.obsidian_memory_activation import (
        ObsidianMemoryActivationError,
        RUNTIME_MARKER,
        provision_obsidian_memory_runtime,
    )

    state_dir = tmp_path / "state"
    source_package = tmp_path / "control-plane-source"
    package_source = source_package / "control_plane"
    package_source.mkdir(parents=True)
    (source_package / "setup.py").write_text("# package marker\n", encoding="utf-8")
    source_payload = package_source / "__init__.py"
    source_payload.write_text("PAYLOAD = 'old'\n", encoding="utf-8")
    source_installs = 0

    def runner(arguments, **_kwargs):
        nonlocal source_installs
        command = [str(value) for value in arguments]
        runtime_root = state_dir / "isolated-runtime"
        if command[1:3] == ["-m", "venv"]:
            runtime_python = runtime_root / "Scripts" / "python.exe"
            runtime_python.parent.mkdir(parents=True)
            runtime_python.write_bytes(b"")
        staged = next(
            (Path(value) for value in command if ".obsidian-memory-source-" in value),
            None,
        )
        if staged is not None:
            installed_package = runtime_root / "Lib" / "site-packages" / "control_plane"
            if installed_package.exists():
                shutil.rmtree(installed_package)
            installed_package.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(staged / "control_plane", installed_package)
            source_installs += 1
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def runtime_probe(_python, package):
        installed_payload = (
            state_dir
            / "isolated-runtime"
            / "Lib"
            / "site-packages"
            / "control_plane"
            / "__init__.py"
        )
        return package == "link-mcp@1.7.0" and installed_payload.is_file()

    runtime_python = provision_obsidian_memory_runtime(
        state_dir=state_dir,
        source_package=source_package,
        base_python=Path(sys.executable),
        runner=runner,
        runtime_probe=runtime_probe,
    )
    marker_path = runtime_python.parent.parent / RUNTIME_MARKER
    legacy_marker = json.loads(marker_path.read_text(encoding="utf-8"))
    legacy_marker.pop("controlPlanePayloadSha256", None)
    legacy_marker["schemaVersion"] = 1
    marker_path.write_text(json.dumps(legacy_marker), encoding="utf-8")
    source_payload.write_text("PAYLOAD = 'new'\n", encoding="utf-8")

    refreshed_python = provision_obsidian_memory_runtime(
        state_dir=state_dir,
        source_package=source_package,
        base_python=Path(sys.executable),
        runner=runner,
        runtime_probe=runtime_probe,
    )

    refreshed_marker = json.loads(marker_path.read_text(encoding="utf-8"))
    installed_payload = (
        refreshed_python.parent.parent
        / "Lib"
        / "site-packages"
        / "control_plane"
        / "__init__.py"
    )
    assert refreshed_python == runtime_python
    assert source_installs == 2
    assert installed_payload.read_text(encoding="utf-8") == "PAYLOAD = 'new'\n"
    assert refreshed_marker["schemaVersion"] == 2
    assert len(refreshed_marker["controlPlanePayloadSha256"]) == 64

    refreshed_marker["mcpVersion"] = "0.0.0"
    marker_path.write_text(json.dumps(refreshed_marker), encoding="utf-8")
    source_payload.write_text("PAYLOAD = 'untrusted-refresh'\n", encoding="utf-8")
    with pytest.raises(
        ObsidianMemoryActivationError,
        match="provenance is unavailable",
    ):
        provision_obsidian_memory_runtime(
            state_dir=state_dir,
            source_package=source_package,
            base_python=Path(sys.executable),
            runner=runner,
            runtime_probe=runtime_probe,
        )
    assert source_installs == 2
    assert installed_payload.read_text(encoding="utf-8") == "PAYLOAD = 'new'\n"


def test_runtime_probe_uses_in_process_contract_for_facade_server(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import control_plane
    from control_plane import obsidian_memory_activation as activation

    runtime_root = tmp_path / "isolated-runtime"
    runtime_python = runtime_root / "Scripts" / "python.exe"
    runtime_python.parent.mkdir(parents=True)
    runtime_python.write_bytes(b"")
    control_root = runtime_root / "Lib" / "site-packages" / "control_plane"
    link_root = runtime_root / "Lib" / "site-packages" / "link_mcp"
    control_root.mkdir(parents=True)
    link_root.mkdir(parents=True)
    control_init = control_root / "__init__.py"
    link_init = link_root / "__init__.py"
    control_init.write_text("# control plane\n", encoding="utf-8")
    link_init.write_text("# link\n", encoding="utf-8")
    (runtime_root / "pyvenv.cfg").write_text(
        "include-system-site-packages = false\n",
        encoding="utf-8",
    )
    base_prefix = tmp_path / "base-python"
    base_prefix.mkdir()
    expected_payload = activation._control_plane_payload_sha256(control_root)

    monkeypatch.setattr(sys, "executable", str(runtime_python))
    monkeypatch.setattr(sys, "prefix", str(runtime_root))
    monkeypatch.setattr(sys, "base_prefix", str(base_prefix))
    monkeypatch.setattr(control_plane, "__file__", str(control_init))
    monkeypatch.setitem(sys.modules, "link_mcp", SimpleNamespace(__file__=str(link_init)))
    monkeypatch.setattr(
        activation.importlib.metadata,
        "version",
        lambda name: {
            "link-mcp": "1.7.0",
            "mcp": "1.28.1",
            "devframe-control-plane": "0.1.0",
        }[name],
    )

    def reject_subprocess(*_args, **_kwargs):
        raise AssertionError("in-process runtime validation must not spawn itself")

    monkeypatch.setattr(activation.subprocess, "run", reject_subprocess)

    assert activation._default_runtime_probe(
        runtime_python,
        activation.UPSTREAM_PACKAGE,
        expected_control_plane_payload_sha256=expected_payload,
    ) is True


def test_production_cli_activation_preview_is_zero_write(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from control_plane.cli import main as devframe_cli_main

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "state"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "memory",
            "activate",
            "--vault",
            str(vault),
            "--codex-home",
            str(codex_home),
            "--state-dir",
            str(state_dir),
            "--format",
            "json",
        ],
    )

    assert devframe_cli_main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "preview"
    assert output["activated"] is False
    assert str(vault.resolve()) not in json.dumps(output)
    assert not state_dir.exists()
    assert not (vault / "wiki").exists()


def test_production_cli_activation_rejection_removes_new_runtime(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from control_plane.cli import main as devframe_cli_main
    from control_plane import obsidian_memory_activation as activation

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "state"
    runtime_root = state_dir / "isolated-runtime"
    runtime_python = runtime_root / "Scripts" / "python.exe"

    def provision(**_kwargs):
        runtime_python.parent.mkdir(parents=True)
        runtime_python.write_bytes(b"")
        return runtime_python

    def reject(**_kwargs):
        raise activation.ObsidianMemoryActivationError("managed config conflict")

    monkeypatch.setattr(activation, "provision_obsidian_memory_runtime", provision)
    monkeypatch.setattr(activation, "_activate_obsidian_memory_unlocked", reject)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "memory",
            "activate",
            "--vault",
            str(vault),
            "--codex-home",
            str(codex_home),
            "--state-dir",
            str(state_dir),
            "--confirm",
        ],
    )

    assert devframe_cli_main() == 2
    assert "managed config conflict" in capsys.readouterr().err
    assert not runtime_root.exists()


def test_production_cli_preserves_new_runtime_for_transaction_recovery(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from control_plane.cli import main as devframe_cli_main
    from control_plane import obsidian_memory_activation as activation

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "state"
    state_path = state_dir / activation.STATE_FILE
    runtime_root = state_dir / activation.ISOLATED_RUNTIME_DIR
    runtime_python = runtime_root / "Scripts" / "python.exe"
    hooks_path = codex_home / "hooks.json"

    def provision(**_kwargs):
        runtime_python.parent.mkdir(parents=True)
        runtime_python.write_bytes(b"")
        return runtime_python

    real_atomic_write = activation._atomic_write
    state_writes = 0

    def fail_final_state_write(path, contents):
        nonlocal state_writes
        if path == state_path:
            state_writes += 1
            if state_writes == 2:
                raise OSError("simulated final state failure")
        real_atomic_write(path, contents)

    real_unlink = Path.unlink

    def fail_hook_rollback(self, *args, **kwargs):
        if self == hooks_path:
            raise OSError("simulated rollback failure")
        return real_unlink(self, *args, **kwargs)

    with monkeypatch.context() as faults:
        faults.setattr(activation, "provision_obsidian_memory_runtime", provision)
        faults.setattr(activation, "_default_runtime_probe", lambda *_args: True)
        faults.setattr(activation, "_runtime_marker_matches", lambda _runtime: True)
        faults.setattr(activation, "_atomic_write", fail_final_state_write)
        faults.setattr(Path, "unlink", fail_hook_rollback)
        faults.setattr(
            sys,
            "argv",
            [
                "devframe",
                "memory",
                "activate",
                "--vault",
                str(vault),
                "--codex-home",
                str(codex_home),
                "--state-dir",
                str(state_dir),
                "--confirm",
            ],
        )

        assert devframe_cli_main() == 2
        assert "could not be completed" in capsys.readouterr().err

    assert json.loads(state_path.read_text(encoding="utf-8"))["state"] == "transaction"
    assert runtime_python.is_file()

    recovered = activation.activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=runtime_python,
        confirm=True,
        runtime_probe=_link_runtime_ready,
        now=lambda: "2026-07-18T01:00:00+00:00",
    )
    assert recovered["status"] == "active"
    assert activation.obsidian_memory_status(
        state_dir=state_dir,
        runtime_probe=_link_runtime_ready,
    )["ready"] is True


def test_production_cli_repair_refreshes_legacy_runtime_before_config_recovery(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from control_plane.cli import main as devframe_cli_main
    from control_plane import obsidian_memory_activation as activation

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "state"
    runtime_root = state_dir / activation.ISOLATED_RUNTIME_DIR
    runtime_python = runtime_root / "Scripts" / "python.exe"
    runtime_python.parent.mkdir(parents=True)
    runtime_python.write_bytes(b"")
    activation.activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=runtime_python,
        confirm=True,
        runtime_probe=_link_runtime_ready,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )
    config_path = codex_home / "config.toml"
    config_path.unlink()
    marker_path = runtime_root / activation.RUNTIME_MARKER
    marker_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "runtimeLockSha256": activation.RUNTIME_LOCK_SHA256,
                "upstreamPackage": activation.UPSTREAM_PACKAGE,
                "upstreamVersion": activation.UPSTREAM_VERSION,
                "mcpVersion": activation.MCP_VERSION,
            }
        ),
        encoding="utf-8",
    )
    provision_calls = 0

    def refresh_runtime(**_kwargs):
        nonlocal provision_calls
        provision_calls += 1
        activation._atomic_write(
            marker_path,
            json.dumps(
                activation._runtime_marker_payload(
                    activation._current_control_plane_payload_sha256()
                ),
                sort_keys=True,
            )
            + "\n",
        )
        return runtime_python

    with monkeypatch.context() as runtime:
        runtime.setattr(activation, "provision_obsidian_memory_runtime", refresh_runtime)
        runtime.setattr(activation, "_default_runtime_probe", lambda *_args: True)
        repair_arguments = [
            "devframe",
            "memory",
            "repair",
            "--codex-home",
            str(codex_home),
            "--state-dir",
            str(state_dir),
            "--format",
            "json",
        ]
        runtime.setattr(sys, "argv", repair_arguments)

        assert devframe_cli_main() == 3
        preview = json.loads(capsys.readouterr().out)
        assert preview["status"] == "repairable"
        assert preview["runtimeRefreshRequired"] is True
        assert provision_calls == 0
        assert not config_path.exists()

        runtime.setattr(sys, "argv", [*repair_arguments, "--confirm"])

        assert devframe_cli_main() == 0
        output = json.loads(capsys.readouterr().out)
        assert config_path.read_text(encoding="utf-8").count(
            "# devframe:obsidian-memory-config:start"
        ) == 1

        managed_hashes = {
            path: path.read_bytes()
            for path in (
                config_path,
                codex_home / "AGENTS.md",
                codex_home / "hooks.json",
                state_dir / activation.STATE_FILE,
                marker_path,
            )
        }
        runtime.setattr(sys, "argv", repair_arguments)
        assert devframe_cli_main() == 0
        settled = json.loads(capsys.readouterr().out)
        assert settled["status"] == "active"
        assert settled["runtimeRefreshRequired"] is False
        assert provision_calls == 1
        assert all(path.read_bytes() == contents for path, contents in managed_hashes.items())

        config_path.unlink()
        assert devframe_cli_main() == 3
        current_runtime_preview = json.loads(capsys.readouterr().out)
        assert current_runtime_preview["status"] == "repairable"
        assert current_runtime_preview["runtimeRefreshRequired"] is False

    assert output["status"] == "active"
    assert output["repaired"] is True
    assert provision_calls == 1
    assert not config_path.exists()


def test_status_rejects_missing_managed_codex_files(tmp_path: Path) -> None:
    from control_plane.obsidian_memory_activation import (
        ObsidianMemoryActivationError,
        activate_obsidian_memory,
        obsidian_memory_status,
    )

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "state"
    activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=Path("C:/Python/python.exe"),
        confirm=True,
        runtime_probe=_link_runtime_ready,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )
    (codex_home / "config.toml").unlink()

    with pytest.raises(ObsidianMemoryActivationError, match="drifted"):
        obsidian_memory_status(
            state_dir=state_dir,
            runtime_probe=_link_runtime_ready,
        )


def test_repair_restores_only_missing_config_and_preserves_exact_deactivation(
    tmp_path: Path,
) -> None:
    from control_plane.obsidian_memory_activation import (
        activate_obsidian_memory,
        deactivate_obsidian_memory,
        obsidian_memory_status,
        repair_obsidian_memory,
    )

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    config_path = codex_home / "config.toml"
    config_path.write_text('model = "before-activation"\n', encoding="utf-8")
    state_dir = tmp_path / "state"
    activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=Path("C:/Python/python.exe"),
        confirm=True,
        runtime_probe=_link_runtime_ready,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )

    external_config = (
        'model = "after-external-rewrite"\n\n'
        "[mcp_servers.unrelated]\n"
        'command = "unrelated"\n'
    )
    config_path.write_text(external_config, encoding="utf-8")
    agents_before = (codex_home / "AGENTS.md").read_bytes()
    hooks_before = (codex_home / "hooks.json").read_bytes()
    state_path = state_dir / "managed-activation.json"
    state_before = state_path.read_bytes()

    preview = repair_obsidian_memory(
        codex_home=codex_home,
        state_dir=state_dir,
        confirm=False,
        runtime_probe=_link_runtime_ready,
        now=lambda: "2026-07-18T01:00:00+00:00",
    )

    assert preview == {
        "status": "repairable",
        "repaired": False,
        "changed": False,
        "serverName": "devframe-obsidian-memory",
        "enabledTools": ["status", "recall"],
        "missingManaged": ["config"],
        "restartRequired": False,
    }
    assert config_path.read_text(encoding="utf-8") == external_config
    assert state_path.read_bytes() == state_before

    repaired = repair_obsidian_memory(
        codex_home=codex_home,
        state_dir=state_dir,
        confirm=True,
        runtime_probe=_link_runtime_ready,
        now=lambda: "2026-07-18T01:00:00+00:00",
    )

    assert repaired == {
        "status": "active",
        "repaired": True,
        "changed": True,
        "serverName": "devframe-obsidian-memory",
        "enabledTools": ["status", "recall"],
        "missingManaged": ["config"],
        "restartRequired": True,
    }
    config_after = config_path.read_text(encoding="utf-8")
    assert config_after.startswith(external_config)
    assert config_after.count("# devframe:obsidian-memory-config:start") == 1
    assert config_after.count("# devframe:obsidian-memory-config:end") == 1
    assert (codex_home / "AGENTS.md").read_bytes() == agents_before
    assert (codex_home / "hooks.json").read_bytes() == hooks_before
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["configAddedText"] == config_after[len(external_config) :]
    assert state["lastRepairedAt"] == "2026-07-18T01:00:00+00:00"
    assert obsidian_memory_status(
        state_dir=state_dir,
        runtime_probe=_link_runtime_ready,
    )["status"] == "active"

    deactivated = deactivate_obsidian_memory(
        codex_home=codex_home,
        state_dir=state_dir,
        confirm=True,
    )
    assert deactivated["status"] == "inactive"
    assert config_path.read_text(encoding="utf-8") == external_config
    assert not state_path.exists()


def test_repair_rejects_unmanaged_or_partial_config_conflicts(tmp_path: Path) -> None:
    from control_plane.obsidian_memory_activation import (
        ObsidianMemoryActivationError,
        activate_obsidian_memory,
        repair_obsidian_memory,
    )

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "state"
    activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=Path("C:/Python/python.exe"),
        confirm=True,
        runtime_probe=_link_runtime_ready,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )
    config_path = codex_home / "config.toml"

    config_path.write_text(
        '[mcp_servers."devframe-obsidian-memory"]\ncommand = "other"\n',
        encoding="utf-8",
    )
    with pytest.raises(ObsidianMemoryActivationError, match="unmanaged"):
        repair_obsidian_memory(
            codex_home=codex_home,
            state_dir=state_dir,
            confirm=True,
            runtime_probe=_link_runtime_ready,
            now=lambda: "2026-07-18T01:00:00+00:00",
        )

    config_path.write_text(
        "# devframe:obsidian-memory-config:start\n",
        encoding="utf-8",
    )
    with pytest.raises(ObsidianMemoryActivationError, match="partial"):
        repair_obsidian_memory(
            codex_home=codex_home,
            state_dir=state_dir,
            confirm=True,
            runtime_probe=_link_runtime_ready,
            now=lambda: "2026-07-18T01:00:00+00:00",
        )


@pytest.mark.parametrize(
    "unmanaged_config",
    [
        'mcp_servers.devframe-obsidian-memory = { command = "other" }\n',
        'mcp_servers = { devframe-obsidian-memory = { command = "other" } }\n',
        '[[mcp_servers.devframe-obsidian-memory]]\ncommand = "other"\n',
        '["mcp_servers"."devframe-obsidian-memory"]\ncommand = "other"\n',
        "['mcp_servers'.'devframe-obsidian-memory']\ncommand = 'other'\n",
    ],
)
def test_repair_rejects_every_toml_form_of_unmanaged_server(
    tmp_path: Path,
    unmanaged_config: str,
) -> None:
    from control_plane.obsidian_memory_activation import (
        ObsidianMemoryActivationError,
        activate_obsidian_memory,
        repair_obsidian_memory,
    )

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "state"
    activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=Path("C:/Python/python.exe"),
        confirm=True,
        runtime_probe=_link_runtime_ready,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )
    config_path = codex_home / "config.toml"
    config_path.write_text(unmanaged_config, encoding="utf-8")
    before = config_path.read_bytes()

    with pytest.raises(ObsidianMemoryActivationError, match="unmanaged"):
        repair_obsidian_memory(
            codex_home=codex_home,
            state_dir=state_dir,
            confirm=True,
            runtime_probe=_link_runtime_ready,
            now=lambda: "2026-07-18T01:00:00+00:00",
        )

    assert config_path.read_bytes() == before


def test_repair_rolls_back_config_when_state_write_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from control_plane import obsidian_memory_activation as activation

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "state"
    activation.activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=Path("C:/Python/python.exe"),
        confirm=True,
        runtime_probe=_link_runtime_ready,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )
    config_path = codex_home / "config.toml"
    config_path.unlink()
    state_path = state_dir / "managed-activation.json"
    state_before = state_path.read_bytes()
    real_atomic_write = activation._atomic_write

    def fail_state_write(path: Path, contents: str) -> None:
        if path == state_path:
            raise OSError("simulated state write failure")
        real_atomic_write(path, contents)

    monkeypatch.setattr(activation, "_atomic_write", fail_state_write)

    with pytest.raises(
        activation.ObsidianMemoryActivationError,
        match="repair could not be completed",
    ):
        activation.repair_obsidian_memory(
            codex_home=codex_home,
            state_dir=state_dir,
            confirm=True,
            runtime_probe=_link_runtime_ready,
            now=lambda: "2026-07-18T01:00:00+00:00",
        )

    assert not config_path.exists()
    assert state_path.read_bytes() == state_before


def test_repair_rejects_an_unavailable_fixed_runtime_without_writes(
    tmp_path: Path,
) -> None:
    from control_plane.obsidian_memory_activation import (
        ObsidianMemoryActivationError,
        activate_obsidian_memory,
        repair_obsidian_memory,
    )

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "state"
    activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=Path("C:/Python/python.exe"),
        confirm=True,
        runtime_probe=_link_runtime_ready,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )
    config_path = codex_home / "config.toml"
    config_path.unlink()
    protected = [
        codex_home / "AGENTS.md",
        codex_home / "hooks.json",
        state_dir / "managed-activation.json",
    ]
    before = {path: path.read_bytes() for path in protected}

    for confirm in (False, True):
        with pytest.raises(ObsidianMemoryActivationError, match="runtime is unavailable"):
            repair_obsidian_memory(
                codex_home=codex_home,
                state_dir=state_dir,
                confirm=confirm,
                runtime_probe=lambda _runtime, _package: False,
                now=lambda: "2026-07-18T01:00:00+00:00",
            )

    assert not config_path.exists()
    assert {path: path.read_bytes() for path in protected} == before


def test_status_rejects_tampered_managed_chunks_in_activation_state(
    tmp_path: Path,
) -> None:
    from control_plane.obsidian_memory_activation import (
        ObsidianMemoryActivationError,
        activate_obsidian_memory,
        obsidian_memory_status,
    )

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "state"
    activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=Path("C:/Python/python.exe"),
        confirm=True,
        runtime_probe=_link_runtime_ready,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )
    state_path = state_dir / "managed-activation.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["configChunk"] = state["configChunk"].replace(
        'enabled_tools = ["status", "recall"]',
        'enabled_tools = ["status", "recall", "write"]',
    )
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    with pytest.raises(ObsidianMemoryActivationError, match="incompatible"):
        obsidian_memory_status(
            state_dir=state_dir,
            runtime_probe=_link_runtime_ready,
        )


def test_repair_recovers_after_process_exit_during_commit(tmp_path: Path) -> None:
    from control_plane.obsidian_memory_activation import (
        activate_obsidian_memory,
        obsidian_memory_status,
        repair_obsidian_memory,
    )

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "state"
    activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=Path("C:/Python/python.exe"),
        confirm=True,
        runtime_probe=_link_runtime_ready,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )
    config_path = codex_home / "config.toml"
    config_path.unlink()
    state_path = state_dir / "managed-activation.json"
    script = r"""
import os
import sys
from pathlib import Path
from control_plane import obsidian_memory_activation as activation

codex_home = Path(sys.argv[1])
state_dir = Path(sys.argv[2])
state_path = state_dir / activation.STATE_FILE
real_atomic_write = activation._atomic_write
state_writes = 0

def exit_during_commit(path, contents):
    global state_writes
    if path == state_path:
        state_writes += 1
        if state_writes == 2:
            os._exit(91)
    real_atomic_write(path, contents)

activation._atomic_write = exit_during_commit
activation.repair_obsidian_memory(
    codex_home=codex_home,
    state_dir=state_dir,
    confirm=True,
    runtime_probe=lambda _runtime, _package: True,
    now=lambda: "2026-07-18T01:00:00+00:00",
)
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    interrupted = subprocess.run(
        [sys.executable, "-c", script, str(codex_home), str(state_dir)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert interrupted.returncode == 91
    transaction = json.loads(state_path.read_text(encoding="utf-8"))
    assert transaction["state"] == "transaction"
    recovered = repair_obsidian_memory(
        codex_home=codex_home,
        state_dir=state_dir,
        confirm=True,
        runtime_probe=_link_runtime_ready,
        now=lambda: "2026-07-18T02:00:00+00:00",
    )
    assert recovered["status"] == "active"
    assert obsidian_memory_status(
        state_dir=state_dir,
        runtime_probe=_link_runtime_ready,
    )["ready"] is True
    assert json.loads(state_path.read_text(encoding="utf-8"))["state"] == "active"
    assert config_path.read_text(encoding="utf-8").count(
        "# devframe:obsidian-memory-config:start"
    ) == 1


def test_activation_recovers_after_process_exit_during_commit(tmp_path: Path) -> None:
    from control_plane.obsidian_memory_activation import (
        activate_obsidian_memory,
        obsidian_memory_status,
    )

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "state"
    script = r"""
import os
import sys
from pathlib import Path
from control_plane import obsidian_memory_activation as activation

vault = Path(sys.argv[1])
codex_home = Path(sys.argv[2])
state_dir = Path(sys.argv[3])
state_path = state_dir / activation.STATE_FILE
real_atomic_write = activation._atomic_write
state_writes = 0

def exit_during_commit(path, contents):
    global state_writes
    if path == state_path:
        state_writes += 1
        if state_writes == 2:
            os._exit(92)
    real_atomic_write(path, contents)

activation._atomic_write = exit_during_commit
activation.activate_obsidian_memory(
    vault_root=vault,
    codex_home=codex_home,
    state_dir=state_dir,
    runtime_python=Path("C:/Python/python.exe"),
    confirm=True,
    runtime_probe=lambda _runtime, _package: True,
    now=lambda: "2026-07-18T00:00:00+00:00",
)
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    interrupted = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(vault),
            str(codex_home),
            str(state_dir),
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert interrupted.returncode == 92
    state_path = state_dir / "managed-activation.json"
    assert json.loads(state_path.read_text(encoding="utf-8"))["state"] == "transaction"
    recovered = activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=Path("C:/Python/python.exe"),
        confirm=True,
        runtime_probe=_link_runtime_ready,
        now=lambda: "2026-07-18T01:00:00+00:00",
    )
    assert recovered["status"] == "active"
    assert obsidian_memory_status(
        state_dir=state_dir,
        runtime_probe=_link_runtime_ready,
    )["ready"] is True
    assert (vault / "wiki" / "index.md").is_file()


def test_two_activation_processes_serialize_one_managed_lifecycle(tmp_path: Path) -> None:
    from control_plane.obsidian_memory_activation import obsidian_memory_status

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "state"
    barrier = tmp_path / "start"
    script = r"""
import sys
import time
from pathlib import Path
from control_plane.obsidian_memory_activation import activate_obsidian_memory

vault = Path(sys.argv[1])
codex_home = Path(sys.argv[2])
state_dir = Path(sys.argv[3])
barrier = Path(sys.argv[4])
deadline = time.monotonic() + 10
while not barrier.exists():
    if time.monotonic() >= deadline:
        raise SystemExit(98)
    time.sleep(0.01)
result = activate_obsidian_memory(
    vault_root=vault,
    codex_home=codex_home,
    state_dir=state_dir,
    runtime_python=Path("C:/Python/python.exe"),
    confirm=True,
    runtime_probe=lambda _runtime, _package: True,
    now=lambda: "2026-07-18T00:00:00+00:00",
)
raise SystemExit(0 if result["status"] == "active" else 97)
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    command = [
        sys.executable,
        "-c",
        script,
        str(vault),
        str(codex_home),
        str(state_dir),
        str(barrier),
    ]
    processes = [
        subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        for _ in range(2)
    ]
    barrier.write_text("go", encoding="utf-8")
    completed = [process.communicate(timeout=20) for process in processes]

    assert [process.returncode for process in processes] == [0, 0], completed
    assert (codex_home / "config.toml").read_text(encoding="utf-8").count(
        "# devframe:obsidian-memory-config:start"
    ) == 1
    assert json.loads((state_dir / "managed-activation.json").read_text(encoding="utf-8"))[
        "state"
    ] == "active"
    assert obsidian_memory_status(
        state_dir=state_dir,
        runtime_probe=_link_runtime_ready,
    )["ready"] is True


def test_two_state_directories_cannot_race_one_codex_home(tmp_path: Path) -> None:
    vaults = [
        _prepare_vault(tmp_path / "vault-a"),
        _prepare_vault(tmp_path / "vault-b"),
    ]
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    barrier = tmp_path / "start"
    state_dirs = [tmp_path / "state-a", tmp_path / "state-b"]
    script = r"""
import sys
import time
from pathlib import Path
from control_plane import obsidian_memory_activation as activation

vault, codex_home, state_dir, barrier = map(Path, sys.argv[1:])
deadline = time.monotonic() + 10
while not barrier.exists():
    if time.monotonic() >= deadline:
        raise SystemExit(98)
    time.sleep(0.01)
real_atomic_write = activation._atomic_write
def delayed_config_write(path, contents):
    if path == codex_home / "config.toml":
        time.sleep(0.5)
    real_atomic_write(path, contents)
activation._atomic_write = delayed_config_write
try:
    activation.activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=Path("C:/Python/python.exe"),
        confirm=True,
        runtime_probe=lambda _runtime, _package: True,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )
except activation.ObsidianMemoryActivationError:
    raise SystemExit(2)
raise SystemExit(0)
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                script,
                str(vault),
                str(codex_home),
                str(state_dir),
                str(barrier),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        for vault, state_dir in zip(vaults, state_dirs)
    ]
    barrier.write_text("go", encoding="utf-8")
    completed = [process.communicate(timeout=20) for process in processes]

    assert sorted(process.returncode for process in processes) == [0, 2], completed
    active_states = [
        state_dir / "managed-activation.json"
        for state_dir in state_dirs
        if (state_dir / "managed-activation.json").is_file()
    ]
    assert len(active_states) == 1
    config_text = (codex_home / "config.toml").read_text(encoding="utf-8")
    assert config_text.count("# devframe:obsidian-memory-config:start") == 1
    assert json.dumps(str(active_states[0].parent)) in config_text


def test_deactivation_recovers_after_process_exit_during_commit(tmp_path: Path) -> None:
    from control_plane.obsidian_memory_activation import (
        activate_obsidian_memory,
        deactivate_obsidian_memory,
    )

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "state"
    activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=Path("C:/Python/python.exe"),
        confirm=True,
        runtime_probe=_link_runtime_ready,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )
    state_path = state_dir / "managed-activation.json"
    script = r"""
import os
import sys
from pathlib import Path
from control_plane import obsidian_memory_activation as activation

codex_home = Path(sys.argv[1])
state_dir = Path(sys.argv[2])
state_path = state_dir / activation.STATE_FILE
real_unlink = Path.unlink

def exit_before_state_delete(self, *args, **kwargs):
    if self == state_path:
        os._exit(93)
    return real_unlink(self, *args, **kwargs)

Path.unlink = exit_before_state_delete
activation.deactivate_obsidian_memory(
    codex_home=codex_home,
    state_dir=state_dir,
    confirm=True,
)
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    interrupted = subprocess.run(
        [sys.executable, "-c", script, str(codex_home), str(state_dir)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert interrupted.returncode == 93
    assert json.loads(state_path.read_text(encoding="utf-8"))["state"] == "transaction"
    recovered = deactivate_obsidian_memory(
        codex_home=codex_home,
        state_dir=state_dir,
        confirm=True,
    )
    assert recovered["status"] == "inactive"
    assert not state_path.exists()
    assert not (codex_home / "config.toml").exists()
    assert not (codex_home / "AGENTS.md").exists()
    assert not (codex_home / "hooks.json").exists()


def test_activation_rejects_orphaned_managed_blocks_without_state(
    tmp_path: Path,
) -> None:
    from control_plane.obsidian_memory_activation import (
        ObsidianMemoryActivationError,
        activate_obsidian_memory,
    )

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "state"
    arguments = {
        "vault_root": vault,
        "codex_home": codex_home,
        "state_dir": state_dir,
        "runtime_python": Path("C:/Python/python.exe"),
        "confirm": True,
        "runtime_probe": _link_runtime_ready,
        "now": lambda: "2026-07-18T00:00:00+00:00",
    }
    activate_obsidian_memory(**arguments)
    (state_dir / "managed-activation.json").unlink()

    with pytest.raises(ObsidianMemoryActivationError, match="orphaned"):
        activate_obsidian_memory(**arguments)


def test_recall_and_hook_block_secret_bearing_upstream_output(tmp_path: Path) -> None:
    from control_plane.obsidian_memory_activation import (
        activate_obsidian_memory,
        recall_hook_output,
        recall_obsidian_memory,
    )

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "state"
    runtime_probe = _link_runtime_ready
    activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=Path("C:/Python/python.exe"),
        confirm=True,
        runtime_probe=runtime_probe,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )
    secret = "api_key: sk-abcdefghijklmnopqrstuvwxyz123456"

    def upstream_call(_runtime_python, wiki, _tool, _arguments):
        return json.dumps({"recall_capsule": secret, "wiki": str(wiki)})

    recalled = recall_obsidian_memory(
        state_dir=state_dir,
        runtime_probe=runtime_probe,
        upstream_call=upstream_call,
    )
    hook = recall_hook_output(
        state_dir=state_dir,
        hook_input={},
        runtime_probe=runtime_probe,
        upstream_call=upstream_call,
    )

    assert json.loads(recalled)["blocked"] is True
    assert secret not in recalled
    assert secret not in hook
    assert str(vault.resolve()) not in recalled + hook


def test_recall_rejects_oversized_upstream_output_before_parsing(tmp_path: Path) -> None:
    from control_plane.obsidian_memory_activation import (
        MAX_UPSTREAM_READ_CHARS,
        ObsidianMemoryActivationError,
        activate_obsidian_memory,
        recall_obsidian_memory,
    )

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "state"
    activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=Path("C:/Python/python.exe"),
        confirm=True,
        runtime_probe=_link_runtime_ready,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )

    def upstream_call(_runtime_python, _wiki, _tool, _arguments):
        return '{"recall_capsule":"' + ("x" * MAX_UPSTREAM_READ_CHARS) + '"}'

    with pytest.raises(ObsidianMemoryActivationError, match="input limit"):
        recall_obsidian_memory(
            state_dir=state_dir,
            runtime_probe=_link_runtime_ready,
            upstream_call=upstream_call,
        )


def test_activation_rejects_existing_managed_wiki_with_invalid_utf8(
    tmp_path: Path,
) -> None:
    from control_plane.obsidian_memory_activation import (
        ObsidianMemoryActivationError,
        activate_obsidian_memory,
    )

    vault = _prepare_vault(tmp_path)
    wiki = vault / "wiki"
    wiki.mkdir()
    (wiki / "index.md").write_bytes(b"\xff\xfe")
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()

    with pytest.raises(ObsidianMemoryActivationError, match="UTF-8"):
        activate_obsidian_memory(
            vault_root=vault,
            codex_home=codex_home,
            state_dir=tmp_path / "state",
            runtime_python=Path("C:/Python/python.exe"),
            confirm=True,
            runtime_probe=_link_runtime_ready,
            now=lambda: "2026-07-18T00:00:00+00:00",
        )
    assert not (vault / "raw").exists()
    assert not (wiki / "memories").exists()
    assert not (wiki / "log.md").exists()


def test_status_rejects_managed_wiki_encoding_drift(tmp_path: Path) -> None:
    from control_plane.obsidian_memory_activation import (
        ObsidianMemoryActivationError,
        activate_obsidian_memory,
        obsidian_memory_status,
    )

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "state"
    runtime_probe = _link_runtime_ready
    activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=Path("C:/Python/python.exe"),
        confirm=True,
        runtime_probe=runtime_probe,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )
    (vault / "wiki" / "index.md").write_bytes(b"\xff\xfe")

    with pytest.raises(ObsidianMemoryActivationError, match="UTF-8"):
        obsidian_memory_status(
            state_dir=state_dir,
            runtime_probe=runtime_probe,
        )


def test_activation_rejects_relative_runtime_python_path(tmp_path: Path) -> None:
    from control_plane.obsidian_memory_activation import (
        ObsidianMemoryActivationError,
        activate_obsidian_memory,
    )

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()

    with pytest.raises(ObsidianMemoryActivationError, match="absolute"):
        activate_obsidian_memory(
            vault_root=vault,
            codex_home=codex_home,
            state_dir=tmp_path / "state",
            runtime_python=Path("runtime/python.exe"),
            confirm=True,
            runtime_probe=_link_runtime_ready,
            now=lambda: "2026-07-18T00:00:00+00:00",
        )


def test_activation_state_stages_exact_human_approved_link_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from control_plane.obsidian_memory import stage_obsidian_memory_proposal
    from control_plane.obsidian_memory_activation import activate_obsidian_memory
    from control_plane.writeback import resolve_writeback_proposal

    vault = _prepare_vault(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "state"
    activate_obsidian_memory(
        vault_root=vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=Path("C:/Python/python.exe"),
        confirm=True,
        runtime_probe=_link_runtime_ready,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )
    monkeypatch.setenv("DEVFRAME_OBSIDIAN_MEMORY_STATE_DIR", str(state_dir))
    monkeypatch.delenv("DEVFRAME_OBSIDIAN_MEMORY_ROOT", raising=False)
    monkeypatch.delenv("DEVFRAME_OBSIDIAN_MEMORY_ALLOWLIST", raising=False)
    monkeypatch.delenv("DEVFRAME_OBSIDIAN_MEMORY_INBOX", raising=False)
    proposal_runtime = tmp_path / "proposal-runtime"

    staged = stage_obsidian_memory_proposal(
        proposal_runtime,
        project_id="demo",
        title="Approved bounded recall",
        lesson="Load one bounded memory capsule before broad search.",
        memory_type="workflow_rule",
        source_refs=["manual-test"],
        thread_id="session-1",
    )

    target = vault / staged["relativePath"]
    assert staged["relativePath"].startswith("wiki/memories/")
    assert not target.exists()
    from control_plane.writeback import load_writeback_proposal

    pending = load_writeback_proposal(proposal_runtime, staged["requestId"])
    assert pending is not None
    assert pending["contents"] == pending["apply_contents"]
    assert "authority: reviewed" in pending["contents"]
    assert "status: active" in pending["contents"]
    assert "review_status: reviewed" in pending["contents"]
    assert 'memory_type: "procedure"' in pending["contents"]
    assert 'devframe_memory_type: "workflow_rule"' in pending["contents"]
    assert pending["content_sha256"] == pending["apply_content_sha256"]
    assert staged["contentSha256"] == pending["apply_content_sha256"]
    applied = resolve_writeback_proposal(
        proposal_runtime,
        staged["requestId"],
        "approve",
        expected_thread_id="session-1",
    )

    text = target.read_text(encoding="utf-8")
    assert applied["applied"] is True
    assert "status: active" in text
    assert "review_status: reviewed" in text
    assert "authority: reviewed" in text
    assert "type: memory" in text
    assert 'title: "Approved bounded recall"' in text
    assert 'source: "devframe-approved:manual-test"' in text
    assert "> **TLDR:** Load one bounded memory capsule before broad search." in text
    assert "## Memory" in text
    assert "## Source" in text


def test_explicit_legacy_memory_environment_never_mixes_activation_authority(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from control_plane.obsidian_memory import stage_obsidian_memory_proposal
    from control_plane.obsidian_memory_activation import activate_obsidian_memory

    activated_vault = _prepare_vault(tmp_path / "activated")
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    state_dir = tmp_path / "state"
    activate_obsidian_memory(
        vault_root=activated_vault,
        codex_home=codex_home,
        state_dir=state_dir,
        runtime_python=Path("C:/Python/python.exe"),
        confirm=True,
        runtime_probe=_link_runtime_ready,
        now=lambda: "2026-07-18T00:00:00+00:00",
    )
    legacy_vault = tmp_path / "legacy-vault"
    legacy_vault.mkdir()
    monkeypatch.setenv("DEVFRAME_OBSIDIAN_MEMORY_STATE_DIR", str(state_dir))
    monkeypatch.setenv("DEVFRAME_OBSIDIAN_MEMORY_ROOT", str(legacy_vault))
    monkeypatch.setenv("DEVFRAME_OBSIDIAN_MEMORY_ALLOWLIST", '["memory.md"]')
    monkeypatch.delenv("DEVFRAME_OBSIDIAN_MEMORY_INBOX", raising=False)

    staged = stage_obsidian_memory_proposal(
        tmp_path / "proposal-runtime",
        project_id="demo",
        title="Legacy boundary",
        lesson="Explicit legacy configuration must remain independent.",
        memory_type="lesson",
        source_refs=["legacy-test"],
        thread_id="legacy-session",
    )

    assert staged["relativePath"].startswith("_devframe/memory-inbox/")
