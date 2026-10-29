#!/usr/bin/env python3
"""Submit long-run v4 review pack to GPT via existing CDP Chrome."""

import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN_ID = "long-run-1-20260602-133438"
V4_DIR = ROOT / "_reports" / "long-run-test" / "runs" / RUN_ID
V4_ZIP = V4_DIR / "long-run-review-pack-v4.zip"
V4_PROMPT = V4_DIR / "GPT_REVIEW_PROMPT.md"
TARGET_URL_FILE = ROOT / "_reports" / "browser-cdp-handoff" / "TARGET_CHATGPT_URL.txt"
CDP_PORT = 9222


def check_cdp():
    try:
        url = f"http://127.0.0.1:{CDP_PORT}/json/version"
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=3)
        data = json.loads(resp.read())
        return data.get("webSocketDebuggerUrl", "")
    except Exception as e:
        return None


def read_target_url():
    if TARGET_URL_FILE.exists():
        return TARGET_URL_FILE.read_text(encoding="utf-8").strip()
    return None


def main():
    print("=" * 60)
    print(f"Long-run v4 GPT Submission — {RUN_ID}")
    print("=" * 60)

    # Check files
    if not V4_ZIP.exists():
        print(f"FAIL: zip not found: {V4_ZIP}")
        sys.exit(1)
    if not V4_PROMPT.exists():
        print(f"FAIL: prompt not found: {V4_PROMPT}")
        sys.exit(1)

    print(f"  Zip: {V4_ZIP} ({V4_ZIP.stat().st_size} bytes)")
    print(f"  Prompt: {V4_PROMPT} ({len(V4_PROMPT.read_text(encoding='utf-8'))} chars)")

    # Check CDP
    ws = check_cdp()
    if not ws:
        print(f"\nFAIL: Chrome CDP not available at port {CDP_PORT}")
        print("  Start Chrome with: chrome --remote-debugging-port=9222")
        sys.exit(1)
    print(f"  CDP: connected (port {CDP_PORT})")

    # Read target URL
    target = read_target_url()
    if target:
        print(f"  Target: {target}")
    else:
        print(f"  Target: NOT SET (will open default ChatGPT)")

    # Connect via Playwright CDP
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")

    contexts = browser.contexts
    context = contexts[0] if contexts else browser.new_context()
    pages = context.pages
    page = pages[0] if pages else context.new_page()

    # Navigate to target URL
    chat_url = target or "https://chatgpt.com/"
    print(f"\n[1] Navigating to {chat_url}...")
    page.goto(chat_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)

    # Paste prompt
    prompt_text = V4_PROMPT.read_text(encoding="utf-8")
    print(f"[2] Pasting review prompt ({len(prompt_text)} chars)...")

    input_selectors = [
        "#prompt-textarea",
        "textarea[placeholder*='Message']",
        "div[contenteditable='true']",
        "p[data-placeholder]",
    ]

    pasted = False
    for sel in input_selectors:
        try:
            el = page.wait_for_selector(sel, timeout=3000, state="visible")
            if el:
                el.click()
                time.sleep(0.5)
                # Clear existing text
                page.keyboard.press("Control+a")
                time.sleep(0.1)
                # Use clipboard paste
                import pyperclip
                pyperclip.copy(prompt_text)
                page.keyboard.press("Control+v")
                time.sleep(1)
                pasted = True
                print(f"  Pasted via selector: {sel}")
                break
        except Exception:
            continue

    if not pasted:
        print("  Auto-paste failed. Prompt copied to clipboard.")
        try:
            import pyperclip
            pyperclip.copy(prompt_text)
            print("  Manually: click ChatGPT input and press Ctrl+V")
        except Exception:
            pass

    # Upload hint
    print(f"\n[3] UPLOAD REQUIRED: {V4_ZIP.name}")
    print(f"    Path: {V4_ZIP}")
    print(f"    Drag-and-drop the zip file into ChatGPT")

    print(f"\n{'='*60}")
    print("MANUAL STEPS (in Chrome):")
    print("  1. Confirm you're in the right ChatGPT conversation")
    print(f"  2. Upload: {V4_ZIP.name} (drag from file explorer)")
    print("  3. Verify prompt is pasted in the input box")
    print("  4. Click Send")
    print("  5. Wait for GPT reply")
    print(f"  6. Save reply to: {V4_DIR}/GPT_REVIEW_RESULT.md")
    print(f"  7. Replace NOT_AVAILABLE_FOR_LONG_RUN_V4 with GPT's reply")
    print(f"{'='*60}")

    try:
        input("\nPress Enter when done (browser stays open)...")
    except EOFError:
        print("\nNon-interactive mode. Browser left open for manual completion.")

    pw.stop()
    print("Done.")


if __name__ == "__main__":
    main()
