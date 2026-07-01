import pytest

from control_plane.chrome_binding_probe import (
    ChromeBindingError,
    build_chrome_chatgpt_session_summary,
)
from control_plane.visual_state import validate_web_ai_session_summary


def test_chrome_chatgpt_binding_builds_summary_only_session():
    summary = build_chrome_chatgpt_session_summary(
        project_id="Demo Project",
        version={"Browser": "Chrome/149.0.7827.155"},
        tabs=[
            {
                "type": "page",
                "title": "ChatGPT",
                "url": "https://chatgpt.com/c/example-conversation?temporary-chat=true",
            }
        ],
    )

    assert summary["provider"] == "chatgpt"
    assert summary["project_id"] == "demo-project"
    assert summary["status"] == "active"
    assert summary["native_refs"]["runtime"] == "chrome-cdp-binding"
    assert summary["native_refs"]["provider_url"] == "https://chatgpt.com/c/example-conversation"
    assert summary["native_refs"]["browser"] == "Chrome/149.0.7827.155"
    assert set(summary["messages"][0]) == {"message_id", "role", "content_summary", "created_at"}
    assert "raw transcript" in summary["messages"][0]["content_summary"]
    validate_web_ai_session_summary(summary)


def test_chrome_chatgpt_binding_rejects_login_page():
    with pytest.raises(ChromeBindingError, match="not ready"):
        build_chrome_chatgpt_session_summary(
            version={"Browser": "Chrome/149.0.7827.155"},
            tabs=[{"type": "page", "title": "ChatGPT", "url": "https://chatgpt.com/auth/login"}],
        )


def test_chrome_chatgpt_binding_requires_loopback_cdp_endpoint():
    with pytest.raises(ChromeBindingError, match="loopback-only"):
        build_chrome_chatgpt_session_summary(
            cdp_endpoint="https://example.test:9222",
            version={"Browser": "Chrome/149.0.7827.155"},
            tabs=[{"type": "page", "title": "ChatGPT", "url": "https://chatgpt.com/"}],
        )
