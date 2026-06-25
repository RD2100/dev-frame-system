import json
import sys

import pytest

from control_plane.cli import main as devframe_cli_main
from control_plane.provider_binding_probe import build_provider_binding_probe
from control_plane.visual_state import validate_web_ai_session_summary


def test_codexpro_probe_builds_summary_only_session():
    probe = build_provider_binding_probe(
        "codexpro",
        "http://127.0.0.1:3978/mcp",
        project_id="Demo Project",
    )

    binding = probe["provider_binding"]
    session = probe["session_summary"]
    action = probe["next_action"]

    assert binding["provider"] == "codexpro"
    assert binding["mode"] == "mcp_app"
    assert binding["health"] == "needs_login"
    assert session["provider"] == "codexpro"
    assert session["project_id"] == "demo-project"
    assert session["status"] == "needs_human"
    assert session["native_refs"]["runtime"] == "provider-binding-probe"
    assert session["native_refs"]["endpoint"] == "http://127.0.0.1:3978/mcp"
    assert set(session["messages"][0]) == {"message_id", "role", "content_summary"}
    assert action["source_type"] == "session"
    validate_web_ai_session_summary(session)


def test_devspace_probe_uses_local_mcp_bridge_mode():
    probe = build_provider_binding_probe(
        "devspace",
        "https://devspace.example.test/mcp",
        project_id="demo",
        health="ready",
    )

    assert probe["provider_binding"]["provider"] == "devspace"
    assert probe["provider_binding"]["mode"] == "local_mcp_bridge"
    assert probe["provider_binding"]["health"] == "ready"
    assert probe["session_summary"]["status"] == "idle"
    assert "open_workspace" in probe["session_summary"]["actions"][0]


def test_provider_binding_probe_rejects_unsafe_endpoint():
    with pytest.raises(ValueError, match="credentials, query strings, or fragments"):
        build_provider_binding_probe("codexpro", "https://token@example.test/mcp?secret=1")


def test_provider_binding_probe_rejects_unknown_provider():
    with pytest.raises(ValueError, match="unsupported provider"):
        build_provider_binding_probe("unknown-ai", "http://127.0.0.1:9000/mcp")


def test_web_ai_probe_cli_outputs_json(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "probe",
        "codexpro",
        "--endpoint",
        "http://127.0.0.1:3978/mcp",
        "--project",
        "demo",
        "--format",
        "json",
    ])

    exit_code = devframe_cli_main()
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["provider_binding"]["provider"] == "codexpro"
    assert output["session_summary"]["project_id"] == "demo"


def test_web_ai_probe_cli_outputs_importable_session_json(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "probe",
        "devspace",
        "--endpoint",
        "https://devspace.example.test/mcp",
        "--project",
        "demo",
        "--format",
        "session-json",
    ])

    exit_code = devframe_cli_main()
    session_summary = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert session_summary["provider"] == "devspace"
    assert session_summary["project_id"] == "demo"
    validate_web_ai_session_summary(session_summary)


def test_web_ai_probe_cli_rejects_bad_endpoint(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "probe",
        "devspace",
        "--endpoint",
        "file:///tmp/socket",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr()

    assert exit_code == 2
    assert "endpoint must be an http or https URL" in output.err
