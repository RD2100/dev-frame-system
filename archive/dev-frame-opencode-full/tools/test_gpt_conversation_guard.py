"""Test NO_NEW_GPT_CONVERSATION guard — validates authorized conversation binding."""
import json, tempfile
from pathlib import Path
from unittest.mock import patch

from gpt_conversation_guard import (
    is_base_url, extract_session_id, validate_authorized_gpt_conversation,
    reject_unauthorized, load_authorized_binding,
)

VALID_URL = "https://chatgpt.com/c/6a212fda-6c04-83a8-82fa-0fa036f762f9"
BASE_URL = "https://chatgpt.com/"


class TestBaseUrlDetection:
    def test_base_url_rejected(self):
        assert is_base_url("https://chatgpt.com/") == True
        assert is_base_url("https://chatgpt.com") == True

    def test_conversation_url_not_base(self):
        assert is_base_url(VALID_URL) == False


class TestSessionExtraction:
    def test_extract_session_id(self):
        sid = extract_session_id(VALID_URL)
        assert sid == "6a212fda-6c04-83a8-82fa-0fa036f762f9"

    def test_base_url_no_session(self):
        assert extract_session_id(BASE_URL) is None
        assert extract_session_id("https://chatgpt.com/") is None


class TestValidateEmptyUrl:
    def test_empty_url_rejected(self):
        ok, reason = validate_authorized_gpt_conversation("")
        assert ok == False
        assert "empty" in reason or "missing" in reason


class TestValidateBaseUrl:
    def test_base_url_rejected(self):
        ok, reason = validate_authorized_gpt_conversation(BASE_URL)
        assert ok == False
        assert "base_url" in reason


class TestMissingBinding:
    def test_missing_binding_rejected(self):
        # Temporarily point to non-existent auth file
        with patch('gpt_conversation_guard.AUTH_FILE', Path('/nonexistent/auth.json')):
            ok, reason = validate_authorized_gpt_conversation(VALID_URL)
            assert ok == False
            assert "missing" in reason.lower() or "binding" in reason.lower()


class TestValidBinding:
    def test_valid_url_accepted(self):
        ok, reason = validate_authorized_gpt_conversation(VALID_URL)
        assert ok == True, f"Valid URL should pass: {reason}"

    def test_authorized_gpt_conversation_json_is_authority(self):
        binding = load_authorized_binding()
        assert binding["authorized_by_user"] is True
        assert binding["authorized_conversation_url"] == VALID_URL
        assert binding["allow_new_conversation"] is False
        assert binding["no_base_url_fallback"] is True


class TestUrlMismatch:
    def test_mismatched_url_rejected(self):
        # This URL has a different session ID than the authorized one
        other_url = "https://chatgpt.com/c/11111111-1111-1111-1111-111111111111"
        ok, reason = validate_authorized_gpt_conversation(other_url)
        assert ok == False
        assert "mismatch" in reason.lower()


class TestRejectUnauthorized:
    def test_reject_returns_human_required(self):
        result = reject_unauthorized(BASE_URL, "test_rejection")
        assert result["status"] == "human_required"
        assert result["submitted"] == False
        assert result["authorized_url_matched"] == False


class TestNoNewPageLogic:
    """Verify that page creation without authorization is blocked."""
    def test_guard_source_has_no_base_url_fallback(self):
        """Verify oracle_gpt_full_review_flow.py removed base URL fallback."""
        source = open("tools/oracle_gpt_full_review_flow.py", encoding="utf-8").read()
        # The old fallback pattern should NOT exist
        assert 'TARGET_URL_FILE.write_text(DEFAULT_TARGET' not in source, \
            "Base URL fallback write must be removed"
        # The guard import must exist
        assert 'gpt_conversation_guard' in source, \
            "Guard import must be present"

    def test_no_auto_new_page(self):
        """Verify new_page() is not auto-called for conversation creation."""
        source = open("tools/oracle_gpt_full_review_flow.py", encoding="utf-8").read()
        # After page-reuse logic, new_page() must NOT be called for conversation auth
        assert 'authorized_conversation_page_not_found' in source, \
            "Must block on missing authorized page"

    def test_target_chatgpt_url_txt_deprecated_not_blocking(self):
        source = open("tools/oracle_gpt_full_review_flow.py", encoding="utf-8").read()
        assert "TARGET_CHATGPT_URL.txt is deprecated and informational only" in source
        assert "load_authorized_binding()" in source
        assert "get_authorized_conversation_url" in source

    def test_full_review_flow_cleanup_no_default_target_or_page_created_log(self):
        source = open("tools/oracle_gpt_full_review_flow.py", encoding="utf-8").read()
        assert "DEFAULT_TARGET" not in source
        assert 'log_event("page_created"' not in source
        assert 'log_event("authorized_page_loaded"' in source

    def test_reply_monitor_uses_authorized_binding_and_no_base_fallback(self):
        source = open("tools/oracle_gpt_reply_monitor.py", encoding="utf-8").read()
        assert "load_authorized_binding()" in source
        assert "get_authorized_conversation_url" in source
        assert "validate_authorized_gpt_conversation(raw)" in source
        assert "TARGET_CHATGPT_URL.txt does not match authorized binding; ignoring legacy file" in source

    def test_reply_monitor_blocks_missing_authorized_page_without_new_page(self):
        source = open("tools/oracle_gpt_reply_monitor.py", encoding="utf-8").read()
        assert "authorized_conversation_page_not_found" in source
        assert "browser.contexts[0].new_page()" not in source
        assert "browser.new_context().new_page()" not in source
        assert "DEFAULT_SESSION_ID" not in source
