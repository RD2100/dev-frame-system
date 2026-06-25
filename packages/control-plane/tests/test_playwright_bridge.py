import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from control_plane.playwright_bridge import (
    _read_prompt_text,
    _connect_over_cdp,
    _is_verified_reply,
    _do_live_transfer,
    BridgeConfig,
    BridgeMode,
    SubmissionRequest,
)


class _FakePlaywright:
    def __init__(self, browser):
        self.chromium = MagicMock(connect_over_cdp=MagicMock(return_value=browser))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def test_read_prompt_text_strips_bom_and_preserves_chinese(tmp_path):
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_bytes("\ufeff中文提示词\n".encode("utf-8"))
    text = _read_prompt_text(prompt_file)
    assert not text.startswith("\ufeff")
    assert "中文提示词" in text


def test_read_prompt_text_accepts_powershell_utf16_bom(tmp_path):
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("中文提示词\n", encoding="utf-16")
    text = _read_prompt_text(prompt_file)
    assert not text.startswith("\ufeff")
    assert "中文提示词" in text


def test_connect_over_cdp_prefers_websocket_debugger_url(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return b'{"webSocketDebuggerUrl":"ws://localhost:9222/devtools/browser/abc"}'

    fake_playwright = MagicMock()
    fake_playwright.chromium.connect_over_cdp.return_value = "browser"
    monkeypatch.setattr("control_plane.playwright_bridge.urlopen", lambda *_args, **_kwargs: FakeResponse())

    assert _connect_over_cdp(fake_playwright, "http://127.0.0.1:9222") == "browser"
    fake_playwright.chromium.connect_over_cdp.assert_called_once_with(
        "ws://localhost:9222/devtools/browser/abc"
    )


def test_is_verified_reply_accepts_review_verdict_with_chinese_context():
    reply = "marker: UTF8_SMOKE_DEVFRAME\nverdict: pass\n说明：中文已正常显示。"
    assert _is_verified_reply(reply)


def test_do_live_transfer_uses_zip_path_for_upload(tmp_path):
    zip_file = tmp_path / "review.zip"
    zip_file.write_bytes(b"fake zip content")
    req = SubmissionRequest(zip_path=str(zip_file), prompt_text="Hello")
    config = BridgeConfig(mode=BridgeMode.LIVE, safety_flag=True, conversation_id="conv-1")

    mock_page = MagicMock()
    mock_page.url = "https://chatgpt.com/c/test"
    mock_file_input = MagicMock()
    mock_file_input.count.return_value = 1
    mock_page.locator.return_value.first = mock_file_input

    mock_browser = MagicMock()
    mock_browser.contexts = [MagicMock(pages=[mock_page])]

    fake_pw = _FakePlaywright(mock_browser)

    with patch("playwright.sync_api.sync_playwright", return_value=fake_pw), \
         patch("time.sleep", return_value=None):
        result = _do_live_transfer(req, config)

    assert result.mode == "live"
    assert result.success is False
    mock_file_input.set_input_files.assert_called_once_with(str(zip_file))


def test_do_live_transfer_falls_back_to_handoff_md_without_zip_path():
    req = SubmissionRequest(zip_path="", prompt_text="Hello")
    config = BridgeConfig(mode=BridgeMode.LIVE, safety_flag=True, conversation_id="conv-1")

    mock_browser = MagicMock()
    fake_pw = _FakePlaywright(mock_browser)

    with patch("playwright.sync_api.sync_playwright", return_value=fake_pw), \
         patch("time.sleep", return_value=None):
        result = _do_live_transfer(req, config)

    assert result.mode == "live"
    assert result.success is False
    assert "HANDOFF.md" in result.detail
