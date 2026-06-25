import json
import sys
import threading
from pathlib import Path
from threading import Thread
from urllib.request import urlopen

from control_plane.cli import main as devframe_cli_main
from control_plane.client_launcher import (
    _analyze_renderer_state,
    _check_boot_shell_element,
    _cleanup_stale_t3_processes,
    _discover_t3_root,
    _enumerate_processes,
    _find_stale_t3_processes,
    _terminate_process_tree,
    build_client_launch_plan,
    check_client_readiness,
    serve_t3_desktop_client,
)
from control_plane.dashboard import build_dashboard_server


def test_client_launch_plan_maps_t3_bridge_and_opencode_executor(tmp_path, monkeypatch):
    def fake_which(command):
        paths = {
            "t3": "",
            "t3code": "C:\\Tools\\t3code.cmd",
            "opencode": "C:\\Tools\\opencode.cmd",
        }
        return paths.get(command) or None

    monkeypatch.setattr("control_plane.client_launcher.shutil.which", fake_which)

    plan = build_client_launch_plan(
        runtime_dir=tmp_path / "runtime",
        host="127.0.0.1",
        port=8788,
        lang="zh-CN",
    )

    assert plan["launch"]["url"] == "http://127.0.0.1:8788/?lang=zh-CN"
    assert plan["launch"]["primarySurface"] == "t3code-native-client"
    assert plan["launch"]["auxiliarySurface"] == "lightweight-web-dashboard"
    assert plan["surfaces"]["primary"] == {
        "id": "t3code-native-client",
        "candidate": "t3code",
        "kind": "native-client",
        "bridgeEndpoint": "http://127.0.0.1:8788/t3-bridge.json",
        "shellEndpoint": "http://127.0.0.1:8788/t3-shell.json",
        "purpose": "Primary T3 Code native client integration for project, thread, session, and gated action workflows.",
    }
    assert plan["surfaces"]["auxiliary"] == [
        {
            "id": "lightweight-web-dashboard",
            "kind": "web-dashboard",
            "url": "http://127.0.0.1:8788/?lang=zh-CN",
            "purpose": "Support-only loopback dashboard for snapshots, diagnostics, and public-surface checks.",
        }
    ]
    assert plan["reuse"]["visualClient"]["candidate"] == "t3code"
    assert plan["reuse"]["visualClient"]["license"] == "MIT"
    assert plan["reuse"]["visualClient"]["status"] == "bridge-ready"
    assert plan["reuse"]["visualClient"]["command"]["name"] == "t3code"
    assert "primary native client" in plan["reuse"]["visualClient"]["boundary"]
    assert plan["reuse"]["executor"]["candidate"] == "opencode"
    assert plan["reuse"]["executor"]["status"] == "ready"
    assert plan["endpoints"]["manifest"] == "http://127.0.0.1:8788/client-manifest.json"
    assert plan["endpoints"]["t3Bridge"] == "http://127.0.0.1:8788/t3-bridge.json"
    assert plan["endpoints"]["t3Shell"] == "http://127.0.0.1:8788/t3-shell.json"
    assert plan["endpoints"]["goDispatch"] == "http://127.0.0.1:8788/go/dispatch"
    assert plan["endpoints"]["actionExecute"] == "http://127.0.0.1:8788/actions/execute"
    assert plan["endpoints"]["approvalResponse"] == "http://127.0.0.1:8788/api/t3/approval-response"
    assert plan["reviewGate"]["id"] == "web-gpt-review-gate"
    assert plan["reviewGate"]["defaultMode"] == "dry-run"
    assert "--execute" not in plan["reviewGate"]["dryRunCommand"]
    assert "--execute" in plan["reviewGate"]["executeCommand"]
    assert plan["reviewGate"]["promptFileEncodings"] == ["utf-8", "utf-8-sig", "utf-16-bom"]
    assert plan["reviewGate"]["reviewedInputs"] == [
        "diff.patch",
        "test-output.md",
        "safety-report.json",
        "chain-evidence.json",
    ]
    assert plan["writePolicy"]["default"] == "read-only"
    assert plan["writePolicy"]["blockedMethods"] == ["PUT", "PATCH", "DELETE"]
    assert plan["writePolicy"]["allowedMutationEndpoints"] == [
        "/go/dispatch",
        "/actions/execute",
        "/api/t3/approval-response",
    ]
    assert "web_gpt_task_intake_dispatch" in plan["writePolicy"]["allowedActionKinds"]
    assert plan["governance"]["reconReceipt"] == "docs/status/recon-receipt-local-agent-client-mainline.md"
    assert plan["governance"]["rkrRulePath"] == "rules/recon.md"
    assert plan["governance"]["reuseAssessment"] == "docs/status/t3code-client-mainline-reuse-assessment.md"
    assert "T3Code" in plan["governance"]["primaryClientDecision"]
    assert "OpenCode" in plan["governance"]["workerDecision"]
    assert "ZIP/report is fallback" in plan["governance"]["webAiAdapterDecision"]
    assert plan["governance"]["nextApprovedSlice"]
    assert plan.get("t3RendererCdp") is not None
    assert plan["t3RendererCdp"]["port"] == 8315
    assert "9222" not in plan["t3RendererCdp"]["endpoint"]
    assert plan["t3RendererCdp"]["endpoint"] == "http://127.0.0.1:8315"
    assert plan["t3RendererCdp"]["rendererOrigin"] == "http://127.0.0.1:5733"


def test_client_dry_run_outputs_zero_config_plan(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "--dry-run",
        "--runtime-dir",
        str(tmp_path / "runtime"),
        "--port",
        "8788",
    ])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "DevFrame Local Agent Client" in output
    assert "Primary T3 Code desktop/native client + DevFrame read model + /go orchestration via OpenCode workers" in output
    assert "Dashboard    : http://127.0.0.1:8788/?lang=zh-CN (auxiliary)" in output
    assert "http://127.0.0.1:8788/?lang=zh-CN" in output
    assert "t3 shell" in output
    assert "/go page" in output
    assert "Review gate  : web-gpt-review-gate (dry-run default)" in output
    assert "Write policy : read-only" in output


def test_client_plan_json_output(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "plan",
        "--runtime-dir",
        str(tmp_path / "runtime"),
        "--format",
        "json",
    ])

    assert devframe_cli_main() == 0

    data = json.loads(capsys.readouterr().out)
    assert data["name"] == "devframe-local-agent-client"
    assert data["launch"]["primarySurface"] == "t3code-native-client"
    assert data["launch"]["auxiliarySurface"] == "lightweight-web-dashboard"
    assert data["surfaces"]["primary"]["kind"] == "native-client"
    assert data["surfaces"]["primary"]["shellEndpoint"].endswith("/t3-shell.json")
    assert data["surfaces"]["auxiliary"][0]["kind"] == "web-dashboard"
    assert data["reuse"]["visualClient"]["candidate"] == "t3code"
    assert data["reuse"]["executor"]["candidate"] == "opencode"
    assert data["reviewGate"]["provider"] == "chatgpt"
    assert data["reviewGate"]["role"] == "external-reviewer"
    assert data["endpoints"]["clientPlan"].endswith("/client-plan.json")
    assert data["endpoints"]["t3Bridge"].endswith("/t3-bridge.json")
    assert data["endpoints"]["goDispatch"].endswith("/go/dispatch")
    assert data["governance"]["reconReceipt"] == "docs/status/recon-receipt-local-agent-client-mainline.md"
    assert data["governance"]["primaryClientDecision"]
    assert data["governance"]["workerDecision"]


def test_dashboard_serves_client_plan_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    server = build_dashboard_server(runtime_dir=tmp_path / "runtime", port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with urlopen(f"http://127.0.0.1:{server.server_address[1]}/client-plan.json?lang=zh-CN", timeout=5) as response:
            plan = json.loads(response.read().decode("utf-8"))

        assert plan["launch"]["url"].endswith("/?lang=zh-CN")
        assert plan["launch"]["primarySurface"] == "t3code-native-client"
        assert plan["launch"]["auxiliarySurface"] == "lightweight-web-dashboard"
        assert plan["surfaces"]["primary"]["bridgeEndpoint"].endswith("/t3-bridge.json")
        assert plan["surfaces"]["auxiliary"][0]["url"].endswith("/?lang=zh-CN")
        assert plan["reuse"]["visualClient"]["status"] == "bridge-ready"
        assert plan["reuse"]["executor"]["status"] == "ready"
        assert plan["endpoints"]["t3Bridge"].endswith("/t3-bridge.json")
        assert plan["endpoints"]["t3Shell"].endswith("/t3-shell.json")
        assert plan["endpoints"]["goDispatch"].endswith("/go/dispatch")
        assert plan["reviewGate"]["id"] == "web-gpt-review-gate"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_client_t3desktop_installs_bundle_and_prints_launch_plan(tmp_path, monkeypatch, capsys):
    t3_root = tmp_path / "t3code"
    (t3_root / "apps/web").mkdir(parents=True)
    (t3_root / "package.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr("control_plane.dashboard.serve_dashboard", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "control_plane.client_launcher.subprocess.run",
        lambda *args, **kwargs: type("CompletedProcess", (), {"returncode": 0})(),
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "t3desktop",
        "--runtime-dir",
        str(tmp_path / "runtime"),
        "--port",
        "8788",
        "--t3-root",
        str(t3_root),
    ])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "DevFrame Local Agent Client" in output
    assert "Primary T3 Code desktop/native client" in output
    assert "DevFrame T3 Code bridge bundle" in output
    assert "Auxiliary dashboard" in output
    assert "wrote" in output
    assert (t3_root / "devframe.t3desktop.mjs").exists()
    assert (t3_root / "apps/web/src/devframe/devframeShellBridge.ts").exists()


def test_client_t3desktop_requires_t3_root(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(str(tmp_path))
    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr("control_plane.dashboard.serve_dashboard", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "control_plane.client_launcher.subprocess.run",
        lambda *args, **kwargs: type("CompletedProcess", (), {"returncode": 0})(),
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "t3desktop",
        "--runtime-dir",
        str(tmp_path / "runtime"),
        "--port",
        "8788",
    ])

    devframe_cli_main()

    output = capsys.readouterr()
    assert "T3 desktop launcher not found" in output.err


def test_client_t3desktop_forwards_refresh_seconds_to_dashboard(tmp_path, monkeypatch):
    t3_root = tmp_path / "t3code"
    (t3_root / "apps/web").mkdir(parents=True)
    (t3_root / "package.json").write_text("{}", encoding="utf-8")

    calls = []
    start_event = threading.Event()

    def fake_serve_dashboard(*args, **kwargs):
        calls.append(kwargs)
        start_event.set()
        return None

    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr("control_plane.dashboard.serve_dashboard", fake_serve_dashboard)
    monkeypatch.setattr(
        "control_plane.client_launcher.subprocess.run",
        lambda *args, **kwargs: type("CompletedProcess", (), {"returncode": 0})(),
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "t3desktop",
        "--runtime-dir",
        str(tmp_path / "runtime"),
        "--port",
        "8788",
        "--t3-root",
        str(t3_root),
        "--refresh-seconds",
        "12",
    ])

    assert devframe_cli_main() == 0
    start_event.wait(timeout=5)
    assert len(calls) == 1
    assert calls[0].get("refresh_seconds") == 12


def test_client_t3desktop_propagates_node_nonzero_exit(tmp_path, monkeypatch):
    t3_root = tmp_path / "t3code"
    (t3_root / "apps/web").mkdir(parents=True)
    (t3_root / "package.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr("control_plane.dashboard.serve_dashboard", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "control_plane.client_launcher.subprocess.run",
        lambda *args, **kwargs: type("CompletedProcess", (), {"returncode": 42})(),
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "t3desktop",
        "--runtime-dir",
        str(tmp_path / "runtime"),
        "--port",
        "8788",
        "--t3-root",
        str(t3_root),
    ])

    assert devframe_cli_main() == 42


def test_client_t3desktop_env_discovery(tmp_path, monkeypatch, capsys):
    t3_root = tmp_path / "t3code"
    (t3_root / "apps/web").mkdir(parents=True)
    (t3_root / "package.json").write_text("{}", encoding="utf-8")

    monkeypatch.setenv("DEVFRAME_T3_ROOT", str(t3_root))
    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr("control_plane.dashboard.serve_dashboard", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "control_plane.client_launcher.subprocess.run",
        lambda *args, **kwargs: type("CompletedProcess", (), {"returncode": 0})(),
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "t3desktop",
        "--runtime-dir",
        str(tmp_path / "runtime"),
        "--port",
        "8788",
    ])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "DevFrame T3 Code bridge bundle" in output
    assert "wrote" in output
    assert (t3_root / "devframe.t3desktop.mjs").exists()


def test_client_t3desktop_cwd_discovery(tmp_path, monkeypatch, capsys):
    t3_root = tmp_path / "t3code"
    (t3_root / "apps/web").mkdir(parents=True)
    (t3_root / "package.json").write_text("{}", encoding="utf-8")

    monkeypatch.chdir(str(t3_root))
    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr("control_plane.dashboard.serve_dashboard", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "control_plane.client_launcher.subprocess.run",
        lambda *args, **kwargs: type("CompletedProcess", (), {"returncode": 0})(),
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "t3desktop",
        "--runtime-dir",
        str(tmp_path / "runtime"),
        "--port",
        "8788",
    ])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "DevFrame T3 Code bridge bundle" in output
    assert "wrote" in output


def test_client_t3desktop_parent_cwd_discovery(tmp_path, monkeypatch, capsys):
    t3_root = tmp_path / "t3code"
    (t3_root / "apps/web").mkdir(parents=True)
    (t3_root / "package.json").write_text("{}", encoding="utf-8")
    subdir = t3_root / "subdir"
    subdir.mkdir()

    monkeypatch.chdir(str(subdir))
    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr("control_plane.dashboard.serve_dashboard", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "control_plane.client_launcher.subprocess.run",
        lambda *args, **kwargs: type("CompletedProcess", (), {"returncode": 0})(),
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "t3desktop",
        "--runtime-dir",
        str(tmp_path / "runtime"),
        "--port",
        "8788",
    ])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "DevFrame T3 Code bridge bundle" in output
    assert "wrote" in output


def test_client_t3desktop_discovery_failure_diagnostic(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(str(tmp_path))
    monkeypatch.setenv("DEVFRAME_T3_ROOT", "/private/fake/t3")
    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr("control_plane.dashboard.serve_dashboard", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "control_plane.client_launcher.subprocess.run",
        lambda *args, **kwargs: type("CompletedProcess", (), {"returncode": 0})(),
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "t3desktop",
        "--runtime-dir",
        str(tmp_path / "runtime"),
        "--port",
        "8788",
    ])

    assert devframe_cli_main() == 1

    output = capsys.readouterr()
    err = output.err
    assert "T3 desktop launcher not found" in err
    assert "--t3-root" in err
    assert "DEVFRAME_T3_ROOT" in err
    assert "T3CODE_ROOT" in err
    assert "T3_ROOT" in err
    assert "<set, invalid T3 checkout>" in err
    assert "<unset>" in err
    assert "/private/fake/t3" not in err
    assert "current directory and parents were checked" in err


def test_client_t3desktop_missing_t3_root_does_not_start_dashboard(tmp_path, monkeypatch):
    monkeypatch.chdir(str(tmp_path))

    calls = []

    def fake_serve_dashboard(*args, **kwargs):
        calls.append(kwargs)
        return None

    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr("control_plane.dashboard.serve_dashboard", fake_serve_dashboard)
    monkeypatch.setattr(
        "control_plane.client_launcher.subprocess.run",
        lambda *args, **kwargs: type("CompletedProcess", (), {"returncode": 0})(),
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "t3desktop",
        "--runtime-dir",
        str(tmp_path / "runtime"),
        "--port",
        "8788",
    ])

    assert devframe_cli_main() == 1
    assert calls == []


def test_client_smoke_text_success(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "smoke",
        "--runtime-dir",
        str(tmp_path / "runtime"),
        "--port",
        "0",
        "--format",
        "text",
    ])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "DevFrame Client Smoke" in output
    assert "status       : pass" in output
    assert "t3code-native-client" in output
    assert "lightweight-web-dashboard" in output
    assert "projects" in output
    assert "threads" in output


def test_client_smoke_json_success(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "smoke",
        "--runtime-dir",
        str(tmp_path / "runtime"),
        "--port",
        "0",
        "--format",
        "json",
    ])

    assert devframe_cli_main() == 0

    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "pass"
    assert data["primarySurface"] == "t3code-native-client"
    assert data["auxiliarySurface"] == "lightweight-web-dashboard"
    assert data["projects"] >= 0
    assert data["threads"] >= 0
    assert "endpoints" in data
    assert "team" in data


def test_client_smoke_invalid_t3_root(tmp_path, monkeypatch, capsys):
    invalid_root = tmp_path / "invalid"
    invalid_root.mkdir()
    (invalid_root / "README.md").write_text("not a t3 checkout", encoding="utf-8")

    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "smoke",
        "--runtime-dir",
        str(tmp_path / "runtime"),
        "--t3-root",
        str(invalid_root),
    ])

    assert devframe_cli_main() == 1

    output = capsys.readouterr()
    assert "invalid T3 root" in output.err


def test_client_smoke_t3_root_bridge_file_checks(tmp_path, monkeypatch, capsys):
    t3_root = tmp_path / "t3code"
    (t3_root / "apps/web").mkdir(parents=True)
    (t3_root / "package.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "smoke",
        "--runtime-dir",
        str(tmp_path / "runtime"),
        "--port",
        "0",
        "--t3-root",
        str(t3_root),
    ])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "T3 bridge" in output
    assert "ok" in output


def test_client_smoke_port_zero_writes_real_port_to_env(tmp_path, monkeypatch, capsys):
    t3_root = tmp_path / "t3code"
    (t3_root / "apps/web").mkdir(parents=True)
    (t3_root / "package.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "smoke",
        "--runtime-dir",
        str(tmp_path / "runtime"),
        "--port",
        "0",
        "--t3-root",
        str(t3_root),
    ])

    assert devframe_cli_main() == 0

    env_file = t3_root / ".env.devframe.local"
    assert env_file.exists()
    env_text = env_file.read_text(encoding="utf-8")
    assert ":0/" not in env_text
    for line in env_text.splitlines():
        if "=" in line:
            value = line.split("=", 1)[1]
            assert ":0/" not in value


def test_client_smoke_remote_without_allow_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "smoke",
        "--runtime-dir",
        str(tmp_path / "runtime"),
        "--host",
        "0.0.0.0",
        "--port",
        "8788",
    ])

    assert devframe_cli_main() == 1

    output = capsys.readouterr()
    assert "use --allow-remote to bind outside loopback" in output.out


def test_client_smoke_remote_with_allow_accepts_parser(tmp_path, monkeypatch):
    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr(
        "control_plane.client_launcher.smoke_local_agent_client",
        lambda *args, **kwargs: 0,
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "smoke",
        "--runtime-dir",
        str(tmp_path / "runtime"),
        "--host",
        "0.0.0.0",
        "--port",
        "8788",
        "--allow-remote",
    ])

    assert devframe_cli_main() == 0


def test_client_doctor_missing_electron_returns_blocked(tmp_path, monkeypatch, capsys):
    t3_root = tmp_path / "t3code"
    (t3_root / "apps/web").mkdir(parents=True)
    (t3_root / "package.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "doctor",
        "--t3-root",
        str(t3_root),
        "--format",
        "json",
    ])

    assert devframe_cli_main() == 1

    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "blocked"
    electron_checks = [check for check in data["checks"] if check.get("name") == "electron-runtime"]
    assert len(electron_checks) == 1
    assert electron_checks[0]["status"] == "fail"
    assert electron_checks[0]["electronExe"] is None
    assert any("pnpm install" in hint for hint in data["fixHints"])


def test_client_doctor_with_electron_returns_pass(tmp_path, monkeypatch, capsys):
    t3_root = tmp_path / "t3code"
    (t3_root / "apps/web").mkdir(parents=True)
    (t3_root / "package.json").write_text("{}", encoding="utf-8")
    electron_root = t3_root / "node_modules" / ".pnpm" / "electron@41.5.0" / "node_modules" / "electron"
    electron_dist = electron_root / "dist"
    electron_dist.mkdir(parents=True)
    (electron_dist / "electron.exe").write_text("", encoding="utf-8")
    (electron_root / "path.txt").write_text("C:\\fake\\electron.exe\n", encoding="utf-8")

    rendered_targets = [
        {
            "id": "page-1",
            "type": "page",
            "title": "DevFrame Dashboard",
            "url": "http://127.0.0.1:8765/?lang=zh-CN",
        }
    ]

    def fake_probe_cdp(cdp_endpoint, timeout=3):
        return {"reachable": True, "targets": rendered_targets}

    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr("control_plane.client_launcher._probe_cdp_targets", fake_probe_cdp)
    monkeypatch.setattr("control_plane.client_launcher._enumerate_processes", lambda: [])
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "doctor",
        "--t3-root",
        str(t3_root),
        "--format",
        "json",
    ])

    assert devframe_cli_main() == 0

    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "pass"
    electron_checks = [check for check in data["checks"] if check.get("name") == "electron-runtime"]
    assert len(electron_checks) == 1
    assert electron_checks[0]["status"] == "pass"
    assert electron_checks[0]["electronExe"].endswith("electron.exe")
    assert electron_checks[0]["pathTxt"].endswith("path.txt")


def test_client_doctor_remote_host_guard(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "doctor",
        "--host",
        "0.0.0.0",
        "--port",
        "8788",
        "--format",
        "json",
    ])

    assert devframe_cli_main() == 1

    output = capsys.readouterr()
    assert "use --allow-remote to bind outside loopback" in output.out


def test_client_doctor_text_format(tmp_path, monkeypatch, capsys):
    t3_root = tmp_path / "t3code"
    (t3_root / "apps/web").mkdir(parents=True)
    (t3_root / "package.json").write_text("{}", encoding="utf-8")
    electron_root = t3_root / "node_modules" / ".pnpm" / "electron@41.5.0" / "node_modules" / "electron"
    electron_dist = electron_root / "dist"
    electron_dist.mkdir(parents=True)
    (electron_dist / "electron.exe").write_text("", encoding="utf-8")
    (electron_root / "path.txt").write_text("C:\\fake\\electron.exe\n", encoding="utf-8")

    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "doctor",
        "--t3-root",
        str(t3_root),
        "--format",
        "text",
    ])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "DevFrame Client Doctor" in output
    assert "status" in output
    assert "Checks" in output
    assert "PASS" in output


def test_client_doctor_only_dist_path_txt_does_not_pass(tmp_path, monkeypatch, capsys):
    t3_root = tmp_path / "t3code"
    (t3_root / "apps/web").mkdir(parents=True)
    (t3_root / "package.json").write_text("{}", encoding="utf-8")
    electron_dist = t3_root / "node_modules" / ".pnpm" / "electron@41.5.0" / "node_modules" / "electron" / "dist"
    electron_dist.mkdir(parents=True)
    (electron_dist / "path.txt").write_text("C:\\fake\\electron.exe\n", encoding="utf-8")

    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "doctor",
        "--t3-root",
        str(t3_root),
        "--format",
        "json",
    ])

    assert devframe_cli_main() == 1

    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "blocked"
    electron_checks = [check for check in data["checks"] if check.get("name") == "electron-runtime"]
    assert len(electron_checks) == 1
    assert electron_checks[0]["status"] == "fail"
    assert electron_checks[0]["electronExe"] is None


def test_client_doctor_electron_dist_path_txt_false_pass_regression(tmp_path, monkeypatch, capsys):
    t3_root = tmp_path / "t3code"
    (t3_root / "apps/web").mkdir(parents=True)
    (t3_root / "package.json").write_text("{}", encoding="utf-8")
    electron_dist = t3_root / "node_modules" / ".pnpm" / "electron@41.5.0" / "node_modules" / "electron" / "dist"
    electron_dist.mkdir(parents=True)
    (electron_dist / "electron.exe").write_text("", encoding="utf-8")
    (electron_dist / "path.txt").write_text("C:\\fake\\electron.exe\n", encoding="utf-8")

    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "doctor",
        "--t3-root",
        str(t3_root),
        "--format",
        "json",
    ])

    assert devframe_cli_main() == 1

    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "blocked"
    electron_checks = [check for check in data["checks"] if check.get("name") == "electron-runtime"]
    assert len(electron_checks) == 1
    assert electron_checks[0]["status"] == "fail"
    assert electron_checks[0]["electronExe"].endswith("electron.exe")
    assert electron_checks[0]["pathTxt"] is None


def test_client_doctor_missing_t3_root_returns_fail(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("DEVFRAME_T3_ROOT", raising=False)
    monkeypatch.delenv("T3CODE_ROOT", raising=False)
    monkeypatch.delenv("T3_ROOT", raising=False)
    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "doctor",
        "--t3-root",
        str(tmp_path / "nonexistent"),
        "--format",
        "json",
    ])

    assert devframe_cli_main() == 1

    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "fail"
    t3_checks = [check for check in data["checks"] if check.get("name") == "t3-root"]
    assert len(t3_checks) == 1
    assert t3_checks[0]["status"] == "fail"


def test_windows_shell_check_pwsh_present_returns_pass(monkeypatch):
    from control_plane.client_launcher import _check_windows_shell

    def fake_which(cmd):
        if cmd == "pwsh.exe":
            return "C:\\tools\\pwsh.exe"
        return ""

    monkeypatch.setattr("control_plane.client_launcher.shutil.which", fake_which)
    result = _check_windows_shell()
    assert result["status"] == "pass"
    assert result["ok"] is True


def test_windows_shell_check_pwsh_missing_powershell_present_returns_pass_with_warnings(monkeypatch):
    from control_plane.client_launcher import _check_windows_shell

    def fake_which(cmd):
        if cmd == "powershell.exe":
            return "C:\\windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
        return ""

    monkeypatch.setattr("control_plane.client_launcher.shutil.which", fake_which)
    result = _check_windows_shell()
    assert result["status"] == "pass-with-warnings"
    assert result["ok"] is True
    assert result["fixHint"] is not None


def test_windows_shell_check_both_missing_returns_fail(monkeypatch):
    from control_plane.client_launcher import _check_windows_shell

    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda cmd: "")
    result = _check_windows_shell()
    assert result["status"] == "fail"
    assert result["ok"] is False
    assert result["fixHint"] is not None


def test_client_doctor_cdp_rendered_page(tmp_path, monkeypatch, capsys):
    t3_root = tmp_path / "t3code"
    (t3_root / "apps/web").mkdir(parents=True)
    (t3_root / "package.json").write_text("{}", encoding="utf-8")
    electron_root = t3_root / "node_modules" / ".pnpm" / "electron@41.5.0" / "node_modules" / "electron"
    electron_dist = electron_root / "dist"
    electron_dist.mkdir(parents=True)
    (electron_dist / "electron.exe").write_text("", encoding="utf-8")
    (electron_root / "path.txt").write_text("C:\\fake\\electron.exe\n", encoding="utf-8")

    rendered_targets = [
        {
            "id": "page-1",
            "type": "page",
            "title": "DevFrame Dashboard - Projects",
            "url": "http://127.0.0.1:8765/?lang=zh-CN",
        }
    ]

    def fake_probe_cdp(cdp_endpoint, timeout=3):
        return {"reachable": True, "targets": rendered_targets}

    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr("control_plane.client_launcher._probe_cdp_targets", fake_probe_cdp)
    monkeypatch.setattr("control_plane.client_launcher._enumerate_processes", lambda: [])
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "doctor",
        "--t3-root",
        str(t3_root),
        "--cdp-endpoint",
        "http://127.0.0.1:9222",
        "--format",
        "json",
    ])

    assert devframe_cli_main() == 0

    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "pass"
    renderer_checks = [c for c in data["checks"] if c.get("name") == "t3-renderer-state"]
    assert len(renderer_checks) == 1
    assert renderer_checks[0]["status"] == "pass"
    assert renderer_checks[0]["rendererState"] == "rendered"


def test_client_doctor_cdp_boot_shell(tmp_path, monkeypatch, capsys):
    t3_root = tmp_path / "t3code"
    (t3_root / "apps/web").mkdir(parents=True)
    (t3_root / "package.json").write_text("{}", encoding="utf-8")
    electron_root = t3_root / "node_modules" / ".pnpm" / "electron@41.5.0" / "node_modules" / "electron"
    electron_dist = electron_root / "dist"
    electron_dist.mkdir(parents=True)
    (electron_dist / "electron.exe").write_text("", encoding="utf-8")
    (electron_root / "path.txt").write_text("C:\\fake\\electron.exe\n", encoding="utf-8")

    splash_targets = [
        {
            "id": "page-1",
            "type": "page",
            "title": "",
            "url": "http://127.0.0.1:8765/?lang=zh-CN",
        },
        {
            "id": "page-2",
            "type": "page",
            "title": "T3 Code",
            "url": "",
        },
    ]

    def fake_probe_cdp(cdp_endpoint, timeout=3):
        return {"reachable": True, "targets": splash_targets}

    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr("control_plane.client_launcher._probe_cdp_targets", fake_probe_cdp)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "doctor",
        "--t3-root",
        str(t3_root),
        "--cdp-endpoint",
        "http://127.0.0.1:9222",
        "--format",
        "json",
    ])

    assert devframe_cli_main() == 0

    data = json.loads(capsys.readouterr().out)
    assert data["status"] in {"pass-with-warnings", "pass"}
    renderer_checks = [c for c in data["checks"] if c.get("name") == "t3-renderer-state"]
    assert len(renderer_checks) == 1
    assert renderer_checks[0]["status"] == "warning"
    assert renderer_checks[0]["rendererState"] == "boot-shell"
    assert renderer_checks[0]["fixHint"] is not None


def test_client_doctor_cdp_unreachable(tmp_path, monkeypatch, capsys):
    t3_root = tmp_path / "t3code"
    (t3_root / "apps/web").mkdir(parents=True)
    (t3_root / "package.json").write_text("{}", encoding="utf-8")
    electron_root = t3_root / "node_modules" / ".pnpm" / "electron@41.5.0" / "node_modules" / "electron"
    electron_dist = electron_root / "dist"
    electron_dist.mkdir(parents=True)
    (electron_dist / "electron.exe").write_text("", encoding="utf-8")
    (electron_root / "path.txt").write_text("C:\\fake\\electron.exe\n", encoding="utf-8")

    def fake_probe_cdp(cdp_endpoint, timeout=3):
        return {"reachable": False, "error": "Connection refused"}

    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr("control_plane.client_launcher._probe_cdp_targets", fake_probe_cdp)
    monkeypatch.setattr("control_plane.client_launcher._enumerate_processes", lambda: [])
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "doctor",
        "--t3-root",
        str(t3_root),
        "--cdp-endpoint",
        "http://127.0.0.1:9222",
        "--format",
        "json",
    ])

    assert devframe_cli_main() == 0

    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "pass"
    renderer_checks = [c for c in data["checks"] if c.get("name") == "t3-renderer-state"]
    assert len(renderer_checks) == 1
    assert renderer_checks[0]["status"] == "unknown"
    assert renderer_checks[0]["ok"] is True
    assert "Connection refused" in renderer_checks[0].get("error", "")


def test_client_doctor_cdp_not_supplied_uses_default_endpoint(tmp_path, monkeypatch, capsys):
    t3_root = tmp_path / "t3code"
    (t3_root / "apps/web").mkdir(parents=True)
    (t3_root / "package.json").write_text("{}", encoding="utf-8")
    electron_root = t3_root / "node_modules" / ".pnpm" / "electron@41.5.0" / "node_modules" / "electron"
    electron_dist = electron_root / "dist"
    electron_dist.mkdir(parents=True)
    (electron_dist / "electron.exe").write_text("", encoding="utf-8")
    (electron_root / "path.txt").write_text("C:\\fake\\electron.exe\n", encoding="utf-8")

    def fake_probe_cdp(cdp_endpoint, timeout=3):
        assert "9222" not in cdp_endpoint
        return {"reachable": False, "error": "ECONNREFUSED"}

    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr("control_plane.client_launcher._probe_cdp_targets", fake_probe_cdp)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "doctor",
        "--t3-root",
        str(t3_root),
        "--format",
        "json",
    ])

    assert devframe_cli_main() == 0

    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "pass-with-warnings"
    renderer_checks = [c for c in data["checks"] if c.get("name") == "t3-renderer-state"]
    assert len(renderer_checks) == 1
    assert renderer_checks[0]["status"] == "warning"
    assert renderer_checks[0]["ok"] is False
    assert renderer_checks[0]["cdpEndpoint"] is not None
    assert "8315" in renderer_checks[0]["cdpEndpoint"]
    assert renderer_checks[0]["cdpSource"] == "default"
    assert "9222" not in renderer_checks[0]["cdpEndpoint"]
    assert any("T3 renderer CDP endpoint is unreachable" in hint for hint in data.get("fixHints", []))


def test_client_doctor_cdp_explicit_overrides_default(tmp_path, monkeypatch, capsys):
    t3_root = tmp_path / "t3code"
    (t3_root / "apps/web").mkdir(parents=True)
    (t3_root / "package.json").write_text("{}", encoding="utf-8")
    electron_root = t3_root / "node_modules" / ".pnpm" / "electron@41.5.0" / "node_modules" / "electron"
    electron_dist = electron_root / "dist"
    electron_dist.mkdir(parents=True)
    (electron_dist / "electron.exe").write_text("", encoding="utf-8")
    (electron_root / "path.txt").write_text("C:\\fake\\electron.exe\n", encoding="utf-8")

    def fake_probe_cdp(cdp_endpoint, timeout=3):
        return {"reachable": False, "error": "Connection refused"}

    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr("control_plane.client_launcher._probe_cdp_targets", fake_probe_cdp)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "doctor",
        "--t3-root",
        str(t3_root),
        "--cdp-endpoint",
        "http://127.0.0.1:9223",
        "--format",
        "json",
    ])

    assert devframe_cli_main() == 0

    data = json.loads(capsys.readouterr().out)
    renderer_checks = [c for c in data["checks"] if c.get("name") == "t3-renderer-state"]
    assert len(renderer_checks) == 1
    assert renderer_checks[0]["cdpSource"] == "explicit"
    assert "9223" in renderer_checks[0]["cdpEndpoint"]
    assert "8315" not in renderer_checks[0]["cdpEndpoint"]


def test_client_doctor_cdp_unrelated_page(tmp_path, monkeypatch, capsys):
    t3_root = tmp_path / "t3code"
    (t3_root / "apps/web").mkdir(parents=True)
    (t3_root / "package.json").write_text("{}", encoding="utf-8")
    electron_root = t3_root / "node_modules" / ".pnpm" / "electron@41.5.0" / "node_modules" / "electron"
    electron_dist = electron_root / "dist"
    electron_dist.mkdir(parents=True)
    (electron_dist / "electron.exe").write_text("", encoding="utf-8")
    (electron_root / "path.txt").write_text("C:\\fake\\electron.exe\n", encoding="utf-8")

    unrelated_targets = [
        {
            "id": "page-1",
            "type": "page",
            "title": "ChatGPT",
            "url": "https://chatgpt.com/c/abc-123",
        },
    ]

    def fake_probe_cdp(cdp_endpoint, timeout=3):
        return {"reachable": True, "targets": unrelated_targets}

    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr("control_plane.client_launcher._probe_cdp_targets", fake_probe_cdp)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "doctor",
        "--t3-root",
        str(t3_root),
        "--cdp-endpoint",
        "http://127.0.0.1:9222",
        "--format",
        "json",
    ])

    assert devframe_cli_main() == 0

    data = json.loads(capsys.readouterr().out)
    assert data["status"] in {"pass", "pass-with-warnings"}
    renderer_checks = [c for c in data["checks"] if c.get("name") == "t3-renderer-state"]
    assert len(renderer_checks) == 1
    assert renderer_checks[0]["status"] != "pass"
    assert renderer_checks[0]["rendererState"] != "rendered"
    assert renderer_checks[0]["rendererState"] in {"unknown-page", "warning", "unknown"}


def test_client_doctor_cdp_t3_renderer_page_matches_renderer_origin(tmp_path, monkeypatch, capsys):
    t3_root = tmp_path / "t3code"
    (t3_root / "apps/web").mkdir(parents=True)
    (t3_root / "package.json").write_text("{}", encoding="utf-8")
    electron_root = t3_root / "node_modules" / ".pnpm" / "electron@41.5.0" / "node_modules" / "electron"
    electron_dist = electron_root / "dist"
    electron_dist.mkdir(parents=True)
    (electron_dist / "electron.exe").write_text("", encoding="utf-8")
    (electron_root / "path.txt").write_text("C:\\fake\\electron.exe\n", encoding="utf-8")

    t3_targets = [
        {
            "id": "page-1",
            "type": "page",
            "title": "T3 Code (Dev)",
            "url": "http://127.0.0.1:5733/",
        },
    ]

    def fake_probe_cdp(cdp_endpoint, timeout=3):
        return {"reachable": True, "targets": t3_targets}

    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr("control_plane.client_launcher._probe_cdp_targets", fake_probe_cdp)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "doctor",
        "--t3-root",
        str(t3_root),
        "--cdp-endpoint",
        "http://127.0.0.1:8315",
        "--format",
        "json",
    ])

    assert devframe_cli_main() == 0

    data = json.loads(capsys.readouterr().out)
    renderer_checks = [c for c in data["checks"] if c.get("name") == "t3-renderer-state"]
    assert len(renderer_checks) == 1
    assert renderer_checks[0]["status"] == "pass"
    assert renderer_checks[0]["rendererState"] == "rendered"


def test_client_doctor_cdp_t3_renderer_page_default_endpoint(tmp_path, monkeypatch, capsys):
    t3_root = tmp_path / "t3code"
    (t3_root / "apps/web").mkdir(parents=True)
    (t3_root / "package.json").write_text("{}", encoding="utf-8")
    electron_root = t3_root / "node_modules" / ".pnpm" / "electron@41.5.0" / "node_modules" / "electron"
    electron_dist = electron_root / "dist"
    electron_dist.mkdir(parents=True)
    (electron_dist / "electron.exe").write_text("", encoding="utf-8")
    (electron_root / "path.txt").write_text("C:\\fake\\electron.exe\n", encoding="utf-8")

    t3_targets = [
        {
            "id": "page-1",
            "type": "page",
            "title": "T3 Code (Dev)",
            "url": "http://127.0.0.1:5733/",
        },
        {
            "id": "page-2",
            "type": "page",
            "title": "ChatGPT",
            "url": "https://chatgpt.com/c/abc-123",
        },
    ]

    def fake_probe_cdp(cdp_endpoint, timeout=3):
        return {"reachable": True, "targets": t3_targets}

    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr("control_plane.client_launcher._probe_cdp_targets", fake_probe_cdp)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "doctor",
        "--t3-root",
        str(t3_root),
        "--format",
        "json",
    ])

    assert devframe_cli_main() == 0

    data = json.loads(capsys.readouterr().out)
    renderer_checks = [c for c in data["checks"] if c.get("name") == "t3-renderer-state"]
    assert len(renderer_checks) == 1
    assert renderer_checks[0]["status"] == "pass"
    assert renderer_checks[0]["rendererState"] == "rendered"


def test_analyze_renderer_state_blank_splash_title_returns_boot_shell():
    targets = [
        {
            "id": "page-1",
            "type": "page",
            "title": "",
            "url": "http://127.0.0.1:5733/",
        },
        {
            "id": "page-2",
            "type": "page",
            "title": "T3 Code",
            "url": "http://127.0.0.1:5733/",
        },
    ]
    result = _analyze_renderer_state(
        targets,
        dashboard_url="http://127.0.0.1:8765/?lang=zh-CN",
        t3_renderer_origins=["http://127.0.0.1:5733"],
    )
    assert result["status"] == "boot-shell"
    assert result["pageCount"] == 2


def test_analyze_renderer_state_rendered_mounted_returns_rendered():
    targets = [
        {
            "id": "page-1",
            "type": "page",
            "title": "T3 Code - Projects",
            "url": "http://127.0.0.1:5733/",
        },
    ]
    result = _analyze_renderer_state(
        targets,
        dashboard_url="http://127.0.0.1:8765/?lang=zh-CN",
        t3_renderer_origins=["http://127.0.0.1:5733"],
    )
    assert result["status"] == "rendered"
    assert result["pageCount"] == 1


def test_analyze_renderer_state_t3_code_loopback_dynamic_port_returns_rendered():
    targets = [
        {
            "id": "page-1",
            "type": "page",
            "title": "T3 Code - Projects",
            "url": "http://127.0.0.1:5734/",
        },
    ]
    result = _analyze_renderer_state(
        targets,
        dashboard_url="http://127.0.0.1:8788/?lang=zh-CN",
        t3_renderer_origins=["http://127.0.0.1:5733"],
    )
    assert result["status"] == "rendered"
    assert result["pageCount"] == 1


def test_check_boot_shell_element_returns_unavailable_without_websocket():
    result = _check_boot_shell_element(
        "http://127.0.0.1:8315",
        [{"id": "page-1", "type": "page", "webSocketDebuggerUrl": "ws://127.0.0.1:8315/devtools/page/page-1"}],
    )
    assert result["available"] is False


def test_check_boot_shell_element_forwards_origin(monkeypatch):
    calls = []

    def fake_create_connection(url, **kwargs):
        calls.append({"url": url, **kwargs})
        ws = type("FakeWS", (), {})()
        ws.send = lambda data: None
        ws.recv = lambda: json.dumps({"result": {"result": {"value": False}}})
        ws.close = lambda: None
        return ws

    fake_websocket = type("mod", (), {"create_connection": fake_create_connection})
    monkeypatch.setitem(sys.modules, "websocket", fake_websocket)

    targets = [
        {
            "id": "page-1",
            "type": "page",
            "webSocketDebuggerUrl": "ws://127.0.0.1:8315/devtools/page/page-1",
        }
    ]
    result = _check_boot_shell_element(
        "http://127.0.0.1:8315",
        targets,
        origin="http://127.0.0.1:5733",
    )
    assert result == {"available": True, "present": False}
    assert len(calls) == 1
    assert calls[0]["url"] == "ws://127.0.0.1:8315/devtools/page/page-1"
    assert calls[0]["origin"] == "http://127.0.0.1:5733"


def test_check_boot_shell_element_without_origin_omits_origin(monkeypatch):
    calls = []

    def fake_create_connection(url, **kwargs):
        calls.append({"url": url, **kwargs})
        ws = type("FakeWS", (), {})()
        ws.send = lambda data: None
        ws.recv = lambda: json.dumps({"result": {"result": {"value": False}}})
        ws.close = lambda: None
        return ws

    fake_websocket = type("mod", (), {"create_connection": fake_create_connection})
    monkeypatch.setitem(sys.modules, "websocket", fake_websocket)

    targets = [
        {
            "id": "page-1",
            "type": "page",
            "webSocketDebuggerUrl": "ws://127.0.0.1:8315/devtools/page/page-1",
        }
    ]
    result = _check_boot_shell_element(
        "http://127.0.0.1:8315",
        targets,
    )
    assert result == {"available": True, "present": False}
    assert len(calls) == 1
    assert calls[0]["url"] == "ws://127.0.0.1:8315/devtools/page/page-1"
    assert "origin" not in calls[0]


def test_client_doctor_cdp_not_mounted_with_origin(tmp_path, monkeypatch, capsys):
    t3_root = tmp_path / "t3code"
    (t3_root / "apps/web").mkdir(parents=True)
    (t3_root / "package.json").write_text("{}", encoding="utf-8")
    electron_root = t3_root / "node_modules" / ".pnpm" / "electron@41.5.0" / "node_modules" / "electron"
    electron_dist = electron_root / "dist"
    electron_dist.mkdir(parents=True)
    (electron_dist / "electron.exe").write_text("", encoding="utf-8")
    (electron_root / "path.txt").write_text("C:\\fake\\electron.exe\n", encoding="utf-8")

    not_mounted_targets = [
        {
            "id": "page-1",
            "type": "page",
            "title": "My App",
            "url": "http://127.0.0.1:5733/",
            "webSocketDebuggerUrl": "ws://127.0.0.1:8315/devtools/page/page-1",
        }
    ]

    def fake_probe_cdp(cdp_endpoint, timeout=3):
        return {"reachable": True, "targets": not_mounted_targets}

    calls = []

    def fake_create_connection(url, **kwargs):
        calls.append({"url": url, **kwargs})
        ws = type("FakeWS", (), {})()
        ws.send = lambda data: None
        ws.recv = lambda: json.dumps({
            "id": 1,
            "result": {
                "result": {"value": True}
            }
        })
        ws.close = lambda: None
        return ws

    fake_websocket = type("mod", (), {"create_connection": fake_create_connection})
    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr("control_plane.client_launcher._probe_cdp_targets", fake_probe_cdp)
    monkeypatch.setitem(sys.modules, "websocket", fake_websocket)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "doctor",
        "--t3-root",
        str(t3_root),
        "--cdp-endpoint",
        "http://127.0.0.1:8315",
        "--format",
        "json",
    ])

    assert devframe_cli_main() == 0

    data = json.loads(capsys.readouterr().out)
    assert data["status"] in {"pass-with-warnings", "pass"}
    renderer_checks = [c for c in data["checks"] if c.get("name") == "t3-renderer-state"]
    assert len(renderer_checks) == 1
    assert renderer_checks[0]["status"] == "warning"
    assert renderer_checks[0]["rendererState"] == "not-mounted"
    assert renderer_checks[0]["fixHint"] is not None
    assert len(calls) == 1
    assert calls[0]["origin"] == "http://127.0.0.1:5733"


def test_discover_t3_root_finds_runtime_external_t3code(tmp_path, monkeypatch):
    runtime_t3 = tmp_path / ".devframe-runtime" / "external" / "t3code"
    runtime_t3.mkdir(parents=True)
    (runtime_t3 / "package.json").write_text("{}", encoding="utf-8")
    (runtime_t3 / "apps" / "web").mkdir(parents=True)

    monkeypatch.chdir(str(tmp_path))
    assert _discover_t3_root() == str(runtime_t3)


def test_discover_t3_root_finds_runtime_external_t3code_from_subdirectory(tmp_path, monkeypatch):
    runtime_t3 = tmp_path / ".devframe-runtime" / "external" / "t3code"
    runtime_t3.mkdir(parents=True)
    (runtime_t3 / "package.json").write_text("{}", encoding="utf-8")
    (runtime_t3 / "apps" / "web").mkdir(parents=True)

    subdir = tmp_path / "src" / "subdir"
    subdir.mkdir(parents=True)
    monkeypatch.chdir(str(subdir))
    assert _discover_t3_root() == str(runtime_t3)


def test_check_client_readiness_existing_bridge_files_without_force(tmp_path, monkeypatch):
    runtime_t3 = tmp_path / ".devframe-runtime" / "external" / "t3code"
    runtime_t3.mkdir(parents=True)
    (runtime_t3 / "package.json").write_text("{}", encoding="utf-8")
    (runtime_t3 / "apps" / "web").mkdir(parents=True)
    (runtime_t3 / "devframe.t3desktop.mjs").write_text("", encoding="utf-8")
    (runtime_t3 / "devframe.t3web.mjs").write_text("", encoding="utf-8")
    (runtime_t3 / ".env.devframe.local").write_text("", encoding="utf-8")
    (runtime_t3 / "apps" / "web" / "src" / "devframe").mkdir(parents=True)
    (runtime_t3 / "apps" / "web" / "src" / "devframe" / "devframeShellBridge.ts").write_text("", encoding="utf-8")

    monkeypatch.chdir(str(tmp_path))
    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")

    result = check_client_readiness(runtime_dir=tmp_path / "runtime")

    bridge_checks = [check for check in result["checks"] if check.get("name") == "t3-bridge"]
    assert len(bridge_checks) == 1
    assert bridge_checks[0]["status"] != "fail"
    assert bridge_checks[0]["ok"] is True
    assert "already present" in bridge_checks[0].get("detail", "")


def test_client_doctor_no_t3_root_uses_runtime_external_t3code(tmp_path, monkeypatch, capsys):
    runtime_t3 = tmp_path / ".devframe-runtime" / "external" / "t3code"
    runtime_t3.mkdir(parents=True)
    (runtime_t3 / "package.json").write_text("{}", encoding="utf-8")
    (runtime_t3 / "apps" / "web").mkdir(parents=True)

    monkeypatch.chdir(str(tmp_path))
    monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "client",
        "doctor",
        "--format",
        "json",
    ])

    assert devframe_cli_main() == 1

    data = json.loads(capsys.readouterr().out)
    t3_checks = [check for check in data["checks"] if check.get("name") == "t3-root"]
    assert len(t3_checks) == 1
    assert t3_checks[0]["status"] == "pass"
    assert t3_checks[0]["path"] == str(runtime_t3)


class TestStaleT3Processes:
    def test_find_stale_t3_processes_filters_by_t3_root(self, tmp_path):
        t3_root = tmp_path / "t3code"
        t3_root.mkdir()
        processes = [
            {"pid": 1001, "name": "node.exe", "command_line": f"node {t3_root}\\devframe.t3desktop.mjs"},
            {"pid": 1002, "name": "electron.exe", "command_line": f"{t3_root}\\node_modules\\.pnpm\\electron@41.5.0\\node_modules\\electron\\dist\\electron.exe"},
            {"pid": 1003, "name": "node.exe", "command_line": "node C:\\other-project\\server.js"},
        ]
        stale = _find_stale_t3_processes(t3_root, processes=processes)
        assert len(stale) == 2
        assert stale[0]["pid"] == 1001
        assert stale[1]["pid"] == 1002

    def test_find_stale_t3_processes_ignores_browser_processes(self, tmp_path):
        t3_root = tmp_path / "t3code"
        t3_root.mkdir()
        processes = [
            {"pid": 1001, "name": "node.exe", "command_line": f"node {t3_root}\\devframe.t3desktop.mjs"},
            {"pid": 2001, "name": "chrome.exe", "command_line": f"chrome.exe --remote-debugging-port=8315 --user-data-dir={t3_root}\\chrome-profile"},
            {"pid": 2002, "name": "msedge.exe", "command_line": f"msedge.exe --user-data-dir={t3_root}\\edge-profile"},
        ]
        stale = _find_stale_t3_processes(t3_root, processes=processes)
        assert len(stale) == 1
        assert stale[0]["pid"] == 1001

    def test_find_stale_t3_processes_ignores_launcher_control_processes(self, tmp_path):
        t3_root = tmp_path / "t3code"
        t3_root.mkdir()
        processes = [
            {"pid": 1001, "name": "python.exe", "command_line": f"python -m control_plane.cli client t3desktop --t3-root {t3_root} --force"},
            {"pid": 1002, "name": "powershell.exe", "command_line": f"powershell -Command node {t3_root}\\devframe.t3desktop.mjs"},
            {"pid": 1003, "name": "node.exe", "command_line": f"node {t3_root}\\devframe.t3desktop.mjs"},
        ]
        stale = _find_stale_t3_processes(t3_root, processes=processes)
        assert [proc["pid"] for proc in stale] == [1003]

    def test_find_stale_t3_processes_requires_current_t3_root_even_with_markers(self, tmp_path):
        t3_root = tmp_path / "t3code"
        t3_root.mkdir()
        processes = [
            {"pid": 1001, "name": "node.exe", "command_line": "node devframe.t3desktop.mjs"},
            {"pid": 1002, "name": "node.exe", "command_line": "node C:\\other\\t3code\\devframe.t3web.mjs"},
            {"pid": 1003, "name": "node.exe", "command_line": f"node {t3_root}\\devframe.t3desktop.mjs"},
        ]
        stale = _find_stale_t3_processes(t3_root, processes=processes)
        assert [proc["pid"] for proc in stale] == [1003]

    def test_find_stale_t3_processes_ignores_unrelated_command_lines(self, tmp_path):
        t3_root = tmp_path / "t3code"
        t3_root.mkdir()
        processes = [
            {"pid": 1001, "name": "node.exe", "command_line": "node C:\\other-project\\server.js"},
            {"pid": 1002, "name": "python.exe", "command_line": "python -m http.server"},
            {"pid": 1003, "name": "cmd.exe", "command_line": "cmd.exe"},
        ]
        stale = _find_stale_t3_processes(t3_root, processes=processes)
        assert len(stale) == 0

    def test_find_stale_t3_processes_skips_pidless_entries(self, tmp_path):
        t3_root = tmp_path / "t3code"
        t3_root.mkdir()
        processes = [
            {"pid": 0, "name": "node.exe", "command_line": f"node {t3_root}\\devframe.t3desktop.mjs"},
            {"pid": None, "name": "node.exe", "command_line": f"node {t3_root}\\devframe.t3desktop.mjs"},
            {},
            {"pid": 1001, "name": "node.exe", "command_line": f"node {t3_root}\\devframe.t3desktop.mjs"},
        ]
        stale = _find_stale_t3_processes(t3_root, processes=processes)
        assert len(stale) == 1
        assert stale[0]["pid"] == 1001

    def test_find_stale_t3_processes_case_insensitive(self, tmp_path):
        t3_root = tmp_path / "T3Code"
        t3_root.mkdir()
        processes = [
            {"pid": 1001, "name": "node.exe", "command_line": f"node {str(t3_root).upper()}\\devframe.t3desktop.mjs"},
        ]
        stale = _find_stale_t3_processes(t3_root, processes=processes)
        assert len(stale) == 1
        assert stale[0]["pid"] == 1001

    def test_cleanup_stale_t3_processes_returns_structured_result(self, tmp_path, monkeypatch):
        t3_root = tmp_path / "t3code"
        t3_root.mkdir()
        fake_processes = [
            {"pid": 1001, "name": "node.exe", "command_line": f"node {t3_root}\\devframe.t3desktop.mjs"},
            {"pid": 1002, "name": "electron.exe", "command_line": f"{t3_root}\\electron.exe"},
        ]
        monkeypatch.setattr(
            "control_plane.client_launcher._enumerate_processes",
            lambda: fake_processes,
        )
        monkeypatch.setattr(
            "control_plane.client_launcher._terminate_process_tree",
            lambda pid: True,
        )
        result = _cleanup_stale_t3_processes(t3_root)
        assert result["stale_found"] == 2
        assert result["stale_pids"] == [1001, 1002]
        assert result["terminated"] == [1001, 1002]
        assert result["errors"] == []

    def test_cleanup_stale_t3_processes_reports_termination_failures(self, tmp_path, monkeypatch):
        t3_root = tmp_path / "t3code"
        t3_root.mkdir()
        fake_processes = [
            {"pid": 1001, "name": "node.exe", "command_line": f"node {t3_root}\\devframe.t3desktop.mjs"},
        ]
        monkeypatch.setattr(
            "control_plane.client_launcher._enumerate_processes",
            lambda: fake_processes,
        )
        monkeypatch.setattr(
            "control_plane.client_launcher._terminate_process_tree",
            lambda pid: False,
        )
        result = _cleanup_stale_t3_processes(t3_root)
        assert result["stale_found"] == 1
        assert result["terminated"] == []
        assert len(result["errors"]) == 1
        assert "1001" in result["errors"][0]

    def test_enumerate_processes_returns_empty_on_non_windows(self, monkeypatch):
        monkeypatch.setattr("control_plane.client_launcher.sys.platform", "linux")
        result = _enumerate_processes()
        assert result == []

    def test_terminate_process_tree_returns_true_on_success(self, monkeypatch):
        def fake_run(*args, **kwargs):
            return type("CompletedProcess", (), {"returncode": 0})()

        monkeypatch.setattr("control_plane.client_launcher.subprocess.run", fake_run)
        assert _terminate_process_tree(1234) is True

    def test_terminate_process_tree_returns_false_on_nonzero_exit(self, monkeypatch):
        def fake_run(*args, **kwargs):
            return type("CompletedProcess", (), {"returncode": 1})()

        monkeypatch.setattr("control_plane.client_launcher.subprocess.run", fake_run)
        assert _terminate_process_tree(1234) is False

    def test_terminate_process_tree_returns_true_on_oserror(self, monkeypatch):
        def fake_run(*args, **kwargs):
            raise OSError("access denied")

        monkeypatch.setattr("control_plane.client_launcher.subprocess.run", fake_run)
        assert _terminate_process_tree(1234) is False


class TestForceCleanupIntegration:
    def test_force_invokes_cleanup_before_launching(self, tmp_path, monkeypatch, capsys):
        t3_root = tmp_path / "t3code"
        (t3_root / "apps/web").mkdir(parents=True)
        (t3_root / "package.json").write_text("{}", encoding="utf-8")

        cleanup_calls = []
        def fake_cleanup(t3_root_path):
            cleanup_calls.append(str(t3_root_path))
            return {"stale_found": 2, "stale_pids": [1001, 1002], "terminated": [1001, 1002], "errors": []}

        subprocess_calls = []
        def fake_run(*args, **kwargs):
            subprocess_calls.append({"args": args, "kwargs": kwargs})
            return type("CompletedProcess", (), {"returncode": 0})()

        monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
        monkeypatch.setattr("control_plane.dashboard.serve_dashboard", lambda *args, **kwargs: None)
        monkeypatch.setattr("control_plane.client_launcher._cleanup_stale_t3_processes", fake_cleanup)
        monkeypatch.setattr("control_plane.client_launcher.subprocess.run", fake_run)

        assert serve_t3_desktop_client(
            runtime_dir=tmp_path / "runtime",
            t3_root=t3_root,
            force=True,
        ) == 0

        assert len(cleanup_calls) == 1
        assert cleanup_calls[0] == str(t3_root)

        output = capsys.readouterr().out
        assert "Force cleanup: found 2 stale T3 process(es)" in output
        assert "[1001, 1002]" in output
        assert "Terminated 2 process(es)" in output

    def test_force_without_stale_processes_prints_clean_message(self, tmp_path, monkeypatch, capsys):
        t3_root = tmp_path / "t3code"
        (t3_root / "apps/web").mkdir(parents=True)
        (t3_root / "package.json").write_text("{}", encoding="utf-8")

        def fake_cleanup(t3_root_path):
            return {"stale_found": 0, "stale_pids": [], "terminated": [], "errors": []}

        monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
        monkeypatch.setattr("control_plane.dashboard.serve_dashboard", lambda *args, **kwargs: None)
        monkeypatch.setattr("control_plane.client_launcher._cleanup_stale_t3_processes", fake_cleanup)
        monkeypatch.setattr(
            "control_plane.client_launcher.subprocess.run",
            lambda *args, **kwargs: type("CompletedProcess", (), {"returncode": 0})(),
        )

        assert serve_t3_desktop_client(
            runtime_dir=tmp_path / "runtime",
            t3_root=t3_root,
            force=True,
        ) == 0

        output = capsys.readouterr().out
        assert "Force cleanup: no stale T3 processes found" in output

    def test_force_without_flag_does_not_invoke_cleanup(self, tmp_path, monkeypatch, capsys):
        t3_root = tmp_path / "t3code"
        (t3_root / "apps/web").mkdir(parents=True)
        (t3_root / "package.json").write_text("{}", encoding="utf-8")

        cleanup_calls = []
        def fake_cleanup(t3_root_path):
            cleanup_calls.append(str(t3_root_path))
            return {"stale_found": 0, "stale_pids": [], "terminated": [], "errors": []}

        monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
        monkeypatch.setattr("control_plane.dashboard.serve_dashboard", lambda *args, **kwargs: None)
        monkeypatch.setattr("control_plane.client_launcher._cleanup_stale_t3_processes", fake_cleanup)
        monkeypatch.setattr(
            "control_plane.client_launcher.subprocess.run",
            lambda *args, **kwargs: type("CompletedProcess", (), {"returncode": 0})(),
        )

        assert serve_t3_desktop_client(
            runtime_dir=tmp_path / "runtime",
            t3_root=t3_root,
            force=False,
        ) == 0

        assert len(cleanup_calls) == 0
        output = capsys.readouterr().out
        assert "Force cleanup" not in output


class TestDoctorStaleProcessCheck:
    def test_doctor_includes_stale_warning_when_processes_exist(self, tmp_path, monkeypatch):
        t3_root = tmp_path / "t3code"
        (t3_root / "apps/web").mkdir(parents=True)
        (t3_root / "package.json").write_text("{}", encoding="utf-8")
        electron_root = t3_root / "node_modules" / ".pnpm" / "electron@41.5.0" / "node_modules" / "electron"
        electron_dist = electron_root / "dist"
        electron_dist.mkdir(parents=True)
        (electron_dist / "electron.exe").write_text("", encoding="utf-8")
        (electron_root / "path.txt").write_text("C:\\fake\\electron.exe\n", encoding="utf-8")

        fake_processes = [
            {"pid": 1001, "name": "node.exe", "command_line": f"node {t3_root}\\devframe.t3desktop.mjs"},
        ]

        def fake_enumerate():
            return fake_processes

        monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
        monkeypatch.setattr("control_plane.client_launcher._enumerate_processes", fake_enumerate)

        result = check_client_readiness(runtime_dir=tmp_path / "runtime", t3_root=t3_root)

        stale_checks = [c for c in result["checks"] if c.get("name") == "stale-t3-processes"]
        assert len(stale_checks) == 1
        assert stale_checks[0]["ok"] is False
        assert stale_checks[0]["status"] == "warning"
        assert stale_checks[0]["staleCount"] == 1
        assert stale_checks[0]["stalePids"] == [1001]
        assert stale_checks[0]["fixHint"] is not None
        assert "1001" in stale_checks[0]["fixHint"]
        assert "pass-with-warnings" in result["status"]

    def test_doctor_treats_current_launcher_processes_as_active_not_stale(self, tmp_path, monkeypatch):
        t3_root = tmp_path / "t3code"
        (t3_root / "apps/web").mkdir(parents=True)
        (t3_root / "package.json").write_text("{}", encoding="utf-8")
        electron_root = t3_root / "node_modules" / ".pnpm" / "electron@41.5.0" / "node_modules" / "electron"
        electron_dist = electron_root / "dist"
        electron_dist.mkdir(parents=True)
        (electron_dist / "electron.exe").write_text("", encoding="utf-8")
        (electron_root / "path.txt").write_text("C:\\fake\\electron.exe\n", encoding="utf-8")

        fake_processes = [
            {"pid": 1001, "name": "node.exe", "command_line": f"node {t3_root}\\devframe.t3desktop.mjs"},
            {
                "pid": 1002,
                "name": "python.exe",
                "command_line": f"python -m control_plane.cli client t3desktop --runtime-dir runtime --port 8788 --t3-root {t3_root} --force",
            },
        ]

        monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
        monkeypatch.setattr("control_plane.client_launcher._enumerate_processes", lambda: fake_processes)

        result = check_client_readiness(runtime_dir=tmp_path / "runtime", t3_root=t3_root, port=8788)

        stale_checks = [c for c in result["checks"] if c.get("name") == "stale-t3-processes"]
        assert len(stale_checks) == 1
        assert stale_checks[0]["ok"] is True
        assert stale_checks[0]["status"] == "pass"
        assert stale_checks[0]["staleCount"] == 0
        assert stale_checks[0]["runtimeProcessCount"] == 1
        assert stale_checks[0]["activeLauncher"] is True

    def test_doctor_passes_when_no_stale_processes(self, tmp_path, monkeypatch):
        t3_root = tmp_path / "t3code"
        (t3_root / "apps/web").mkdir(parents=True)
        (t3_root / "package.json").write_text("{}", encoding="utf-8")
        electron_root = t3_root / "node_modules" / ".pnpm" / "electron@41.5.0" / "node_modules" / "electron"
        electron_dist = electron_root / "dist"
        electron_dist.mkdir(parents=True)
        (electron_dist / "electron.exe").write_text("", encoding="utf-8")
        (electron_root / "path.txt").write_text("C:\\fake\\electron.exe\n", encoding="utf-8")

        def fake_enumerate():
            return []

        monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
        monkeypatch.setattr("control_plane.client_launcher._enumerate_processes", fake_enumerate)

        result = check_client_readiness(runtime_dir=tmp_path / "runtime", t3_root=t3_root)

        stale_checks = [c for c in result["checks"] if c.get("name") == "stale-t3-processes"]
        assert len(stale_checks) == 1
        assert stale_checks[0]["ok"] is True
        assert stale_checks[0]["status"] == "pass"
        assert stale_checks[0]["staleCount"] == 0

    def test_doctor_ignores_browsers_in_stale_check(self, tmp_path, monkeypatch):
        t3_root = tmp_path / "t3code"
        (t3_root / "apps/web").mkdir(parents=True)
        (t3_root / "package.json").write_text("{}", encoding="utf-8")
        electron_root = t3_root / "node_modules" / ".pnpm" / "electron@41.5.0" / "node_modules" / "electron"
        electron_dist = electron_root / "dist"
        electron_dist.mkdir(parents=True)
        (electron_dist / "electron.exe").write_text("", encoding="utf-8")
        (electron_root / "path.txt").write_text("C:\\fake\\electron.exe\n", encoding="utf-8")

        fake_processes = [
            {"pid": 2001, "name": "chrome.exe", "command_line": f"chrome.exe --user-data-dir={t3_root}\\profile"},
        ]

        def fake_enumerate():
            return fake_processes

        monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")
        monkeypatch.setattr("control_plane.client_launcher._enumerate_processes", fake_enumerate)

        result = check_client_readiness(runtime_dir=tmp_path / "runtime", t3_root=t3_root)

        stale_checks = [c for c in result["checks"] if c.get("name") == "stale-t3-processes"]
        assert len(stale_checks) == 1
        assert stale_checks[0]["ok"] is True
        assert stale_checks[0]["staleCount"] == 0

    def test_doctor_stale_check_without_t3_root_is_absent(self, tmp_path, monkeypatch):
        monkeypatch.setattr("control_plane.client_launcher.shutil.which", lambda command: f"C:\\Tools\\{command}.cmd")

        result = check_client_readiness(runtime_dir=tmp_path / "runtime", t3_root=tmp_path / "nonexistent")

        stale_checks = [c for c in result["checks"] if c.get("name") == "stale-t3-processes"]
        assert len(stale_checks) == 0
