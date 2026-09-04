import json
from pathlib import Path

from control_plane.web_ai_browser_launcher import (
    BrowserLaunchConfig,
    ensure_web_ai_browser,
    load_browser_launch_config,
    write_browser_launch_config,
)


def test_browser_binding_config_roundtrip_is_dsh_managed(tmp_path):
    runtime_dir = tmp_path / "runtime"
    config = BrowserLaunchConfig(
        browser="dsh",
        cdp_endpoint="http://127.0.0.1:9222",
        url="https://chatgpt.com/",
    )

    path = write_browser_launch_config(config, runtime_dir=runtime_dir)
    loaded = load_browser_launch_config(runtime_dir=runtime_dir)

    assert path == runtime_dir / "browser-profiles" / "web-ai-browser.json"
    assert loaded.profile_policy == "dsh_managed"
    assert loaded.browser == "dsh"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "browser_exe" not in payload
    assert "profile_dir" not in payload
    assert payload["login_policy"] == "dsh_owned"


def test_legacy_profile_fields_are_ignored_and_not_exposed(tmp_path):
    runtime_dir = tmp_path / "runtime"
    config_path = runtime_dir / "browser-profiles" / "web-ai-browser.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "browser": "chrome",
                "browser_exe": "C:/private/chrome.exe",
                "profile_dir": "C:/private/profile",
                "cdp_endpoint": "http://127.0.0.1:9222",
                "url": "https://chatgpt.com/",
            }
        ),
        encoding="utf-8",
    )

    loaded = load_browser_launch_config(runtime_dir=runtime_dir)

    assert loaded.browser == "dsh"
    assert loaded.profile_policy == "dsh_managed"
    assert not (runtime_dir / "profile").exists()


def test_ensure_browser_reuses_existing_cdp_without_launching(tmp_path, monkeypatch):
    import control_plane.web_ai_browser_launcher as launcher_module

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
    )

    assert result["status"] == "already_running"
    assert result["started"] is False
    assert result["opened_url"] is True
    assert result["profile_policy"] == "dsh_managed"


def test_ensure_browser_fails_closed_without_starting_when_dsh_cdp_missing(tmp_path, monkeypatch):
    import control_plane.web_ai_browser_launcher as launcher_module

    monkeypatch.setattr(
        launcher_module,
        "probe_cdp",
        lambda endpoint: {"reachable": False, "endpoint": endpoint, "error": "refused", "browser": "", "targets": []},
    )

    result = ensure_web_ai_browser(
        runtime_dir=tmp_path / "runtime",
    )

    assert result["status"] == "blocked"
    assert result["started"] is False
    assert result["opened_url"] is False
    assert result["reason"] == "dsh_cdp_endpoint_unreachable"
    assert not (tmp_path / "runtime" / "browser-profiles").exists()


def test_ensure_browser_write_config_records_dsh_owned_policy(tmp_path, monkeypatch):
    import control_plane.web_ai_browser_launcher as launcher_module

    monkeypatch.setattr(
        launcher_module,
        "probe_cdp",
        lambda endpoint: {"reachable": True, "endpoint": endpoint, "browser": "Chrome/149", "targets": []},
    )
    monkeypatch.setattr(launcher_module, "_open_url_via_cdp", lambda _endpoint, _url: False)

    result = ensure_web_ai_browser(
        runtime_dir=tmp_path / "runtime",
        write_config=True,
    )

    config = json.loads(Path(result["config_written"]).read_text(encoding="utf-8"))
    assert config["profile_policy"] == "dsh_managed"
    assert config["login_policy"] == "dsh_owned"
    assert "browser_exe" not in config
    assert "profile_dir" not in config
