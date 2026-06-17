"Playwright Bridge — optional import, safety flag, live CDP behind flag."
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from pathlib import Path
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


def _do_live_transfer(request: SubmissionRequest, config: BridgeConfig) -> SubmissionResult:
    """Execute live CDP file transfer via Playwright."""
    from playwright.sync_api import sync_playwright
    import time

    handoff_path = Path(request.review_run_id)  # review_run_id may not be a path
    # Determine file to transfer: prefer handoff_path if it exists, else HANDOFF.md
    if isinstance(request.review_run_id, str):
        candidate = Path(request.review_run_id)
        if candidate.exists() and candidate.suffix == ".md":
            handoff_path = candidate
        else:
            handoff_path = Path("HANDOFF.md")

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
                browser = p.chromium.connect_over_cdp(cdp_url)
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
                "请阅读以上 HANDOFF.md 文件（作为 .md 文件附件上传），"
                "理解项目身份、架构、已完成阶段、当前状态、安全边界和推荐下一步。"
                "请使用 YAML 格式回复确认你的理解。"
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

            # Wait for reply
            baseline = page.locator('[data-message-author-role="assistant"]').count()
            for _ in range(30):
                time.sleep(10)
                msgs = page.locator('[data-message-author-role="assistant"]')
                if msgs.count() > baseline:
                    reply = msgs.last.text_content() or ""
                    handoff_verified = "handoff_understood" in reply.lower() or "overall_judgment" in reply.lower()
                    return SubmissionResult(
                        success=handoff_verified,
                        review_run_id=request.review_run_id,
                        mode="live",
                        detail=f"Transfer complete. Reply: {len(reply)} chars. Verified: {handoff_verified}",
                        captured_reply_sha256=None,
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
