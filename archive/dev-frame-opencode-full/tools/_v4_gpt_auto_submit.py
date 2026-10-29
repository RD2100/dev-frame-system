#!/usr/bin/env python3
"""Fully automated v4 GPT submission via CDP Chrome.
1. Verify page exists and is ChatGPT
2. Upload zip + paste prompt
3. Click send
4. Wait for reply, capture it
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN_ID = "long-run-1-20260602-133438"
V4_DIR = ROOT / "_reports" / "long-run-test" / "runs" / RUN_ID
V4_ZIP = V4_DIR / "long-run-review-pack-v4.zip"
V4_PROMPT = V4_DIR / "GPT_REVIEW_PROMPT.md"
TARGET_URL_FILE = ROOT / "_reports" / "browser-cdp-handoff" / "TARGET_CHATGPT_URL.txt"
CDP_PORT = 9222


def main():
    print("=" * 60)
    print(f"v4 GPT Auto-Submit — {RUN_ID}")
    print("=" * 60)

    # ── Pre-flight ──
    assert V4_ZIP.exists(), f"Zip not found: {V4_ZIP}"
    assert V4_PROMPT.exists(), f"Prompt not found: {V4_PROMPT}"
    prompt_text = V4_PROMPT.read_text(encoding="utf-8")
    zip_path_str = str(V4_ZIP.resolve())
    print(f"  Zip: {zip_path_str} ({V4_ZIP.stat().st_size} bytes)")
    print(f"  Prompt: {len(prompt_text)} chars")

    # ── Connect CDP ──
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")

    contexts = browser.contexts
    context = contexts[0] if contexts else browser.new_context()
    pages = context.pages

    # ── Step 1: Find or open ChatGPT page ──
    target_url = None
    if TARGET_URL_FILE.exists():
        target_url = TARGET_URL_FILE.read_text(encoding="utf-8").strip()

    chat_page = None
    for p in pages:
        current_url = p.url
        if "chatgpt.com" in current_url or "chat.openai.com" in current_url:
            chat_page = p
            print(f"\n[1] Found existing ChatGPT page: {current_url[:80]}...")
            break

    if not chat_page:
        chat_page = pages[0] if pages else context.new_page()
        go_url = target_url or "https://chatgpt.com/"
        print(f"\n[1] Opening ChatGPT: {go_url}...")
        chat_page.goto(go_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)
    else:
        chat_page.bring_to_front()

    # Verify we're on ChatGPT
    current_url = chat_page.url
    assert "chatgpt.com" in current_url or "chat.openai.com" in current_url, \
        f"Not on ChatGPT: {current_url}"
    print(f"  Verified: ChatGPT page active")

    # ── Step 2: Upload zip ──
    print(f"\n[2] Uploading zip file...")

    # Try to find file input and set files
    upload_success = False

    # Method 1: Look for hidden file input
    try:
        file_input = chat_page.locator("input[type='file']").first
        if file_input.count() > 0:
            file_input.set_input_files(zip_path_str)
            upload_success = True
            print("  Uploaded via file input")
    except Exception as e:
        print(f"  File input method failed: {e}")

    # Method 2: Click paperclip/attach button then file input
    if not upload_success:
        attach_selectors = [
            "button[aria-label*='Attach']",
            "button[aria-label*='Upload']",
            "button[aria-label*='attach']",
            "button[data-testid='attach-file-button']",
            "[data-testid='file-upload']",
        ]
        for sel in attach_selectors:
            try:
                btn = chat_page.wait_for_selector(sel, timeout=2000, state="visible")
                if btn:
                    btn.click()
                    time.sleep(0.5)
                    # After clicking attach, try file input
                    file_input = chat_page.locator("input[type='file']").first
                    if file_input.count() > 0:
                        file_input.set_input_files(zip_path_str)
                        upload_success = True
                        print(f"  Uploaded via attach button: {sel}")
                        break
            except Exception:
                continue

    if not upload_success:
        print("  WARNING: Auto-upload failed. Please drag zip manually.")
        print(f"  Zip path: {zip_path_str}")

    time.sleep(2)

    # ── Step 3: Paste prompt into input ──
    print(f"\n[3] Pasting review prompt...")

    input_selectors = [
        "#prompt-textarea",
        "textarea[placeholder*='Message']",
        "div[contenteditable='true']",
        "p[data-placeholder]",
    ]

    pasted = False
    for sel in input_selectors:
        try:
            el = chat_page.wait_for_selector(sel, timeout=3000, state="visible")
            if el:
                el.click()
                time.sleep(0.3)
                # Clear existing
                chat_page.keyboard.press("Control+a")
                time.sleep(0.1)
                # Fill
                el.fill(prompt_text)
                pasted = True
                print(f"  Pasted via fill(): {sel}")
                break
        except Exception:
            continue

    if not pasted:
        # Fallback: clipboard + Ctrl+V
        try:
            import pyperclip
            pyperclip.copy(prompt_text)
            # Try to find the input
            for sel in input_selectors:
                try:
                    el = chat_page.wait_for_selector(sel, timeout=2000, state="visible")
                    if el:
                        el.click()
                        time.sleep(0.3)
                        chat_page.keyboard.press("Control+a")
                        time.sleep(0.1)
                        chat_page.keyboard.press("Control+v")
                        pasted = True
                        print(f"  Pasted via Ctrl+V: {sel}")
                        break
                except Exception:
                    continue
        except ImportError:
            pass

    if not pasted:
        print("  WARNING: Could not paste prompt automatically.")

    time.sleep(1)

    # ── Step 4: Click Send ──
    print(f"\n[4] Clicking Send...")

    send_selectors = [
        "button[data-testid='send-button']",
        "button[aria-label*='Send']",
        "button[type='submit']",
        "button svg[aria-label]",
        "button:has(svg)",
    ]

    sent = False
    for sel in send_selectors:
        try:
            btn = chat_page.wait_for_selector(sel, timeout=3000, state="visible")
            if btn:
                # Check if disabled
                disabled = btn.get_attribute("disabled")
                if disabled is not None:
                    print(f"  Send button found ({sel}) but disabled — waiting for enable...")
                    time.sleep(3)
                    disabled = btn.get_attribute("disabled")
                if disabled is None:
                    btn.click()
                    sent = True
                    print(f"  Sent via: {sel}")
                    break
        except Exception:
            continue

    if not sent:
        # Try pressing Enter
        print("  Trying Enter key...")
        chat_page.keyboard.press("Enter")
        sent = True
        print("  Sent via Enter key")

    # ── Step 5: Wait for GPT reply ──
    print(f"\n[5] Waiting for GPT reply...")

    # Record message count before waiting
    try:
        initial_msgs = chat_page.locator("div[data-message-author-role]").count()
        print(f"  Initial messages: {initial_msgs}")
    except Exception:
        initial_msgs = 0

    # Wait for new assistant message (max 10 minutes)
    timeout = 600
    deadline = time.time() + timeout
    reply_text = ""
    last_count = initial_msgs

    while time.time() < deadline:
        time.sleep(10)
        elapsed = int(time.time() - (deadline - timeout))
        print(f"  Waiting... {elapsed}s / {timeout}s", end="\r")

        # Check for assistant messages
        try:
            assistant_msgs = chat_page.locator("div[data-message-author-role='assistant']")
            count = assistant_msgs.count()
            if count > initial_msgs:
                print(f"\n  New assistant message detected! (total: {count})")
                # Get the last assistant message text
                last_msg = assistant_msgs.last
                reply_text = last_msg.inner_text()
                break
        except Exception:
            pass

        # Also check for stop button disappearance (means generation is done)
        try:
            stop_btn = chat_page.locator("button[data-testid='stop-button']")
            if stop_btn.count() == 0 and initial_msgs > 0:
                # Might be done - check for assistant messages again
                try:
                    assistant_msgs = chat_page.locator("div[data-message-author-role='assistant']")
                    count = assistant_msgs.count()
                    if count > initial_msgs:
                        last_msg = assistant_msgs.last
                        reply_text = last_msg.inner_text()
                        break
                except Exception:
                    pass
        except Exception:
            pass

    print()

    # ── Step 6: Save reply ──
    result_path = V4_DIR / "GPT_REVIEW_RESULT.md"
    decision_path = V4_DIR / "GPT_REVIEW_DECISION.md"

    if reply_text:
        result_path.write_text(reply_text, encoding="utf-8")
        print(f"\n[6] GPT reply saved ({len(reply_text)} chars):")
        print(f"    {result_path}")

        # Try to parse decision
        decision = "unknown"
        lower = reply_text.lower()
        if "accepted" in lower and ("rejected" not in lower or "not rejected" in lower):
            decision = "accepted"
        elif "rejected" in lower:
            decision = "rejected"
        elif "blocked" in lower:
            decision = "blocked"
        elif "human_required" in lower:
            decision = "human_required"

        decision_json = {
            "review_run_id": RUN_ID,
            "decision": decision,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "reply_length": len(reply_text),
        }
        decision_path.write_text(json.dumps(decision_json, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"    Parsed decision: {decision}")
        print(f"    Decision saved: {decision_path}")
    else:
        print(f"\n[6] WARNING: No reply captured within {timeout}s timeout.")
        print(f"    Check ChatGPT manually and save reply to:")
        print(f"    {result_path}")

    pw.stop()

    # ── Summary ──
    print(f"\n{'='*60}")
    print("Submission Complete")
    print(f"{'='*60}")
    print(f"  Upload: {'auto' if upload_success else 'MANUAL_REQUIRED'}")
    print(f"  Paste:  {'auto' if pasted else 'MANUAL_REQUIRED'}")
    print(f"  Send:   {'auto' if sent else 'MANUAL_REQUIRED'}")
    print(f"  Reply:  {'captured' if reply_text else 'NOT_CAPTURED'}")
    if reply_text:
        print(f"  Decision: {decision}")
        print(f"  Result: {result_path}")


if __name__ == "__main__":
    main()
