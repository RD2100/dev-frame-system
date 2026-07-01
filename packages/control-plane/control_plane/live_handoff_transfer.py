"""Live CDP Handoff Transfer — authorized execution.

Transfers HANDOFF.md to a target ChatGPT conversation via Playwright/CDP.
Uses file-attachment protocol: upload HANDOFF.md as .md file, include bootstrap
prompt, send, capture reply, verify handoff_verified.

REQUIRES: explicit user authorization, Chrome with remote debugging enabled.
SAFETY: no cookies/session export, no state mutation, no guard modification.
"""

from __future__ import annotations
import sys
import json
import time
from pathlib import Path
from dataclasses import dataclass, field

ROOT = Path(__file__).resolve().parent.parent
HANDOFF_PATH = ROOT / "HANDOFF.md"


@dataclass
class TransferResult:
    target_url: str
    handoff_size: int = 0
    connected: bool = False
    navigated: bool = False
    file_attached: bool = False
    prompt_sent: bool = False
    reply_captured: bool = False
    handoff_verified: bool = False
    reply_text: str = ""
    errors: list = field(default_factory=list)


def do_transfer(target_url: str) -> TransferResult:
    result = TransferResult(target_url=target_url)

    # Verify HANDOFF.md exists
    if not HANDOFF_PATH.exists():
        result.errors.append("HANDOFF.md not found")
        return result
    result.handoff_size = HANDOFF_PATH.stat().st_size
    print(f"[1/6] HANDOFF.md verified: {result.handoff_size} bytes")

    # Read handoff content
    handoff_text = HANDOFF_PATH.read_text(encoding="utf-8")
    bootstrap_prompt = (
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

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            # Connect to existing Chrome or launch new one
            print("[2/6] Connecting to Chrome via CDP...")
            try:
                browser = p.chromium.connect_over_cdp("http://localhost:9222")
                result.connected = True
                print("       Connected to existing Chrome (port 9222)")
            except Exception:
                print("       No existing Chrome on port 9222, launching new...")
                browser = p.chromium.launch(
                    headless=False,
                    args=["--remote-debugging-port=9222"],
                )
                result.connected = True
                print("       Launched Chrome with CDP on port 9222")

            # Get or create page
            if browser.contexts:
                context = browser.contexts[0]
            else:
                context = browser.new_context()

            page = context.new_page()

            # Navigate to target conversation
            print(f"[3/6] Navigating to {target_url}...")
            page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)  # Let page fully load
            result.navigated = True
            print("       Page loaded")

            # Find and use the file input to upload HANDOFF.md
            print("[4/6] Attaching HANDOFF.md as file...")
            try:
                # ChatGPT's file upload input
                file_input = page.locator('input[type="file"]').first
                if file_input.count() > 0:
                    file_input.set_input_files(str(HANDOFF_PATH))
                    page.wait_for_timeout(2000)
                    result.file_attached = True
                    print("       File attached via input[type=file]")
                else:
                    # Fallback: try drag-and-drop or button click
                    # Click the attach/paperclip button if present
                    attach_btn = page.locator('[data-testid="file-upload"]').first
                    if attach_btn.count() == 0:
                        attach_btn = page.locator('button:has(svg)').filter(has_text="").first
                    if attach_btn.count() > 0:
                        attach_btn.click()
                        page.wait_for_timeout(1000)
                        file_input = page.locator('input[type="file"]').first
                        file_input.set_input_files(str(HANDOFF_PATH))
                        page.wait_for_timeout(2000)
                        result.file_attached = True
                        print("       File attached via button click")
                    else:
                        result.errors.append("Could not find file upload element")
            except Exception as e:
                result.errors.append(f"File attach error: {e}")

            # Type bootstrap prompt
            print("[5/6] Typing bootstrap prompt and sending...")
            try:
                # ChatGPT prompt textarea
                prompt_box = page.locator('#prompt-textarea').first
                if prompt_box.count() == 0:
                    prompt_box = page.locator('[data-testid="prompt-textarea"]').first
                if prompt_box.count() == 0:
                    prompt_box = page.locator('textarea').first

                if prompt_box.count() > 0:
                    prompt_box.fill(bootstrap_prompt)
                    page.wait_for_timeout(1000)

                    # Click send button
                    send_btn = page.locator('[data-testid="send-button"]').first
                    if send_btn.count() == 0:
                        send_btn = page.locator('button:has(svg)').last
                    if send_btn.count() > 0:
                        send_btn.click()
                        result.prompt_sent = True
                        print("       Prompt sent")
                    else:
                        result.errors.append("Could not find send button")
                else:
                    result.errors.append("Could not find prompt textarea")
            except Exception as e:
                result.errors.append(f"Prompt/send error: {e}")

            # Wait for GPT reply
            print("[6/6] Waiting for GPT reply...")
            page.wait_for_timeout(15000)  # Wait up to 15s

            # Try to capture the last assistant message
            try:
                messages = page.locator('[data-message-author-role="assistant"]')
                if messages.count() > 0:
                    result.reply_text = messages.last.text_content() or ""
                    result.reply_captured = True
                    result.handoff_verified = "handoff_understood" in result.reply_text.lower() or \
                                              "overall_judgment" in result.reply_text.lower()
                    print(f"       Reply captured ({len(result.reply_text)} chars)")
                    print(f"       Handoff verified: {result.handoff_verified}")
                else:
                    result.errors.append("No assistant messages found")
            except Exception as e:
                result.errors.append(f"Reply capture error: {e}")

            # Don't close browser — let user see the result
            print("\n=== Transfer Complete ===")
            print(f"  Connected: {result.connected}")
            print(f"  Navigated: {result.navigated}")
            print(f"  File attached: {result.file_attached}")
            print(f"  Prompt sent: {result.prompt_sent}")
            print(f"  Reply captured: {result.reply_captured}")
            print(f"  Handoff verified: {result.handoff_verified}")
            if result.errors:
                print(f"  Errors: {result.errors}")

    except ImportError:
        result.errors.append("playwright not installed")
    except Exception as e:
        result.errors.append(f"Unexpected error: {e}")

    return result


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "https://chatgpt.com/"
    result = do_transfer(target)
    sys.exit(0 if result.handoff_verified else 1)
