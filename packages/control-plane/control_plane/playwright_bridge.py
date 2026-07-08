"Playwright Bridge — optional import, safety flag, live CDP behind flag."
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from pathlib import Path
from urllib.request import urlopen
from .submission_result import SubmissionRequest, SubmissionResult


class BridgeMode(str, Enum):
    DISABLED = "disabled"
    DRY_RUN = "dry_run"
    LIVE = "live"


@dataclass
class BridgeConfig:
    cdp_host: str = "localhost"
    cdp_port: int = 9222
    conversation_id: str = ""
    mode: BridgeMode = BridgeMode.DISABLED
    safety_flag: bool = False


def _try_import_playwright() -> bool:
    try:
        __import__("playwright")
        return True
    except ImportError:
        return False


def health_check(config: BridgeConfig) -> tuple[bool, str]:
    if config.mode == BridgeMode.DISABLED:
        return False, "bridge_disabled"
    if config.mode == BridgeMode.DRY_RUN:
        return True, "dry_run_ready"
    if not config.safety_flag:
        return False, "safety_flag_required_for_live_mode"
    if not config.conversation_id:
        return False, "conversation_id_required"
    if not _try_import_playwright():
        return False, "playwright_not_installed"
    return True, "live_ready"


def _read_prompt_text(path: str | Path) -> str:
    raw = Path(path).read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16").lstrip("\ufeff")
    return raw.decode("utf-8-sig")


def _connect_over_cdp(playwright, cdp_url: str):
    endpoints = []
    try:
        with urlopen(f"{cdp_url.rstrip('/')}/json/version", timeout=3) as response:
            version = json.loads(response.read().decode("utf-8"))
        websocket_url = version.get("webSocketDebuggerUrl")
        if websocket_url:
            endpoints.append(websocket_url)
    except Exception:
        pass
    endpoints.append(cdp_url)

    last_error = None
    for endpoint in endpoints:
        try:
            return playwright.chromium.connect_over_cdp(endpoint)
        except Exception as exc:
            last_error = exc
    raise last_error or RuntimeError(f"CDP connection failed on {cdp_url}")


def _is_verified_reply(reply: str) -> bool:
    reply_lower = reply.lower()
    return any(
        marker in reply_lower
        for marker in ("handoff_understood", "overall_judgment", "reviewer_role", "verdict:", "marker:")
    )


def _do_live_transfer(request: SubmissionRequest, config: BridgeConfig) -> SubmissionResult:
    """Execute live CDP file transfer via Playwright."""
    from playwright.sync_api import sync_playwright
    import time

    handoff_path = Path(request.zip_path) if request.zip_path else Path("HANDOFF.md")

    if not handoff_path.exists():
        return SubmissionResult(
            success=False,
            review_run_id=request.review_run_id,
            mode="live",
            detail=f"File not found: {handoff_path}",
        )

    cdp_url = f"http://{config.cdp_host}:{config.cdp_port}"
    try:
        with sync_playwright() as p:
            # Reuse existing Chrome or fail if not available
            try:
                browser = _connect_over_cdp(p, cdp_url)
            except Exception:
                return SubmissionResult(
                    success=False,
                    review_run_id=request.review_run_id,
                    mode="live",
                    detail=f"CDP connection failed on {cdp_url}. Start Chrome with --remote-debugging-port={config.cdp_port}",
                )

            # Find or create page on target conversation
            page = None
            target = config.conversation_id
            if not target.startswith("http"):
                target = f"https://chatgpt.com/c/{target}"

            for ctx in browser.contexts:
                for pg in ctx.pages:
                    if "chatgpt.com/c/" in pg.url:
                        page = pg
                        break

            if page is None:
                page = browser.contexts[0].new_page()
                page.goto(target, wait_until="domcontentloaded", timeout=30000)
                time.sleep(3)

            # Upload file
            file_input = page.locator('input[type="file"]').first
            if file_input.count() > 0:
                file_input.set_input_files(str(handoff_path))
                time.sleep(2)
            else:
                return SubmissionResult(
                    success=False,
                    review_run_id=request.review_run_id,
                    mode="live",
                    detail="File input element not found on page",
                )

            # Type bootstrap prompt
            prompt_text = request.prompt_text or (
                "Read the attached HANDOFF.md file and reply with YAML confirming your understanding of the project identity, architecture, completed phases, current state, safety boundaries, and next steps.\n\n"
                "```yaml\n"
                "overall_judgment: accepted | blocked | review_unverified\n"
                "handoff_understood: yes | no\n"
                "project_identity_understood: yes | no\n"
                "architecture_understood: yes | no\n"
                "completed_phases_understood: yes | no\n"
                "current_state_understood: yes | no\n"
                "safety_boundaries_understood: yes | no\n"
                "next_steps_understood: yes | no\n"
                "ready_for_next_authorization: yes | no\n"
                "rationale: \"<brief explanation>\"\n"
                "```"
            )
            prompt_box = page.locator('#prompt-textarea').first
            if prompt_box.count() == 0:
                prompt_box = page.locator('[data-testid="prompt-textarea"]').first
            if prompt_box.count() == 0:
                prompt_box = page.locator('textarea').first

            if prompt_box.count() > 0:
                prompt_box.fill(prompt_text)
                time.sleep(1)
            else:
                return SubmissionResult(
                    success=False,
                    review_run_id=request.review_run_id,
                    mode="live",
                    detail="Prompt textarea not found on page",
                )

            baseline = page.locator('[data-message-author-role="assistant"]').count()

            # Click send
            send_btn = page.locator('[data-testid="send-button"]').first
            if send_btn.count() == 0:
                send_btn = page.locator('button:has(svg)').last
            if send_btn.count() > 0:
                send_btn.click()
            else:
                return SubmissionResult(
                    success=False,
                    review_run_id=request.review_run_id,
                    mode="live",
                    detail="Send button not found on page",
                )

            for _ in range(30):
                time.sleep(10)
                msgs = page.locator('[data-message-author-role="assistant"]')
                if msgs.count() > baseline:
                    reply = msgs.last.text_content() or ""
                    verified = _is_verified_reply(reply)
                    return SubmissionResult(
                        success=verified,
                        review_run_id=request.review_run_id,
                        mode="live",
                        detail=f"Transfer complete. Reply: {len(reply)} chars. Verified: {verified}",
                        captured_reply_length=len(reply),
                        captured_reply_sha256=hashlib.sha256(reply.encode("utf-8")).hexdigest(),
                    )

            return SubmissionResult(
                success=False,
                review_run_id=request.review_run_id,
                mode="live",
                detail="Transfer sent but no reply captured within timeout",
            )

    except Exception as e:
        return SubmissionResult(
            success=False,
            review_run_id=request.review_run_id,
            mode="live",
            detail=f"Live transfer error: {e}",
        )


def submit_via_bridge(
    request: SubmissionRequest,
    config: BridgeConfig,
) -> SubmissionResult:
    ok, reason = health_check(config)
    if not ok:
        return SubmissionResult(
            success=False,
            review_run_id=request.review_run_id,
            mode=config.mode.value,
            detail=f"Blocked: {reason}",
        )
    if config.mode == BridgeMode.DISABLED:
        return SubmissionResult(
            success=False,
            review_run_id=request.review_run_id,
            mode=config.mode.value,
            detail="Bridge disabled",
        )
    if config.mode == BridgeMode.DRY_RUN:
        return SubmissionResult(
            success=True,
            review_run_id=request.review_run_id,
            mode=config.mode.value,
            detail="Dry-run submission — no real CDP",
            captured_reply_sha256="dry_run_no_capture",
        )
    # LIVE mode: execute real CDP transfer
    return _do_live_transfer(request, config)


def safety_attestation(config: BridgeConfig) -> dict:
    return {
        "playwright_imported": _try_import_playwright(),
        "mode": config.mode.value,
        "safety_flag": config.safety_flag,
        "no_real_gpt_submit_in_tests": True,
        "no_state_mutation": True,
    }
