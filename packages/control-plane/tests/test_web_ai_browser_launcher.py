import json
from pathlib import Path

from control_plane.web_ai_browser_launcher import (
    BrowserLaunchConfig,
    ensure_web_ai_browser,
    load_browser_launch_config,
    write_browser_launch_config,
)


def test_browser_launch_config_roundtrip_preserves_profile_dir(tmp_path):
    runtime_dir = tmp_path / "runtime"
    profile_dir = tmp_path / "existing-login-profile"
    browser_exe = tmp_path / "chrome.exe"
    browser_exe.write_text("", encoding="utf-8")
    config = BrowserLaunchConfig(
        browser="chrome",
        browser_exe=str(browser_exe),
        cdp_endpoint="http://127.0.0.1:9222",
        profile_dir=str(profile_dir),
        url="https://chatgpt.com/",
    )

    path = write_browser_launch_config(config, runtime_dir=runtime_dir)
    loaded = load_browser_launch_config(runtime_dir=runtime_dir)

    assert path == runtime_dir / "browser-profiles" / "web-ai-browser.json"
    assert loaded.profile_dir == str(profile_dir.resolve())
    assert loaded.browser_exe == str(browser_exe)


def test_ensure_browser_reuses_existing_cdp_without_launching(tmp_path, monkeypatch):
    import control_plane.web_ai_browser_launcher as launcher_module

    browser_exe = tmp_path / "chrome.exe"
    browser_exe.write_text("", encoding="utf-8")
    launched = []

    monkeypatch.setattr(
        launcher_module,
        "probe_cdp",
        lambda endpoint: {
            "reachable": True,
            "endpoint": endpoint,
            "browser": "Chrome/149",
            "targets": [],
        },
    )
    monkeypatch.setattr(launcher_module, "_open_url_via_cdp", lambda _endpoint, _url: True)

    result = ensure_web_ai_browser(
        runtime_dir=tmp_path / "runtime",
        browser_exe=str(browser_exe),
        profile_dir=tmp_path / "profile",
        launcher=lambda args: launched.append(args),
    )

    assert result["status"] == "already_running"
    assert result["started"] is False
    assert result["opened_url"] is True
    assert launched == []


def test_ensure_browser_starts_dedicated_profile_when_cdp_missing(tmp_path, monkeypatch):
    import control_plane.web_ai_browser_launcher as launcher_module

    browser_exe = tmp_path / "chrome.exe"
    browser_exe.write_text("", encoding="utf-8")
    profile_dir = tmp_path / "profile"
    probes = iter([
        {"reachable": False, "endpoint": "http://127.0.0.1:9222", "error": "refused", "browser": "", "targets": []},
        {"reachable": True, "endpoint": "http://127.0.0.1:9222", "browser": "Chrome/149", "targets": []},
    ])
    launched = []

    monkeypatch.setattr(launcher_module, "probe_cdp", lambda _endpoint: next(probes))

    result = ensure_web_ai_browser(
        runtime_dir=tmp_path / "runtime",
        browser_exe=str(browser_exe),
        profile_dir=profile_dir,
        launcher=lambda args: launched.append(args),
        wait_seconds=0,
    )

    assert result["status"] == "started"
    assert result["started"] is True
    assert profile_dir.exists()
    assert launched
    assert f"--user-data-dir={profile_dir.resolve()}" in launched[0]
    assert "--remote-debugging-port=9222" in launched[0]
    assert "taskkill" not in " ".join(launched[0]).lower()


def test_ensure_browser_write_config_records_login_once_policy(tmp_path, monkeypatch):
    import control_plane.web_ai_browser_launcher as launcher_module

    browser_exe = tmp_path / "chrome.exe"
    browser_exe.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        launcher_module,
        "probe_cdp",
        lambda endpoint: {"reachable": True, "endpoint": endpoint, "browser": "Chrome/149", "targets": []},
    )
    monkeypatch.setattr(launcher_module, "_open_url_via_cdp", lambda _endpoint, _url: False)

    result = ensure_web_ai_browser(
        runtime_dir=tmp_path / "runtime",
        browser_exe=str(browser_exe),
        profile_dir=tmp_path / "profile",
        write_config=True,
    )

    config = json.loads(Path(result["config_written"]).read_text(encoding="utf-8"))
    assert config["profile_policy"] == "dedicated_persistent_profile"
    assert config["login_policy"] == "login_once_then_reuse_profile"
