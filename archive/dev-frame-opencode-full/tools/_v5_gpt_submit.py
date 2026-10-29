#!/usr/bin/env python3
"""Fully automated v5 GPT submission via CDP Chrome.
1. Find ChatGPT page
2. Upload zip + paste prompt
3. Click send
4. Wait for reply, capture it
"""
import json, sys, time, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN_ID = "long-run-1-20260602-133438"
V5_DIR = ROOT / "_reports" / "long-run-test" / "runs" / RUN_ID
V5_ZIP = V5_DIR / "long-run-review-pack-v5.zip"
V5_PROMPT = V5_DIR / "GPT_REVIEW_PROMPT.md"
CDP_PORT = 9222


def main():
    assert V5_ZIP.exists(), f"Zip not found: {V5_ZIP}"
    assert V5_PROMPT.exists(), f"Prompt not found: {V5_PROMPT}"
    prompt_text = V5_PROMPT.read_text(encoding="utf-8")
    zip_path_str = str(V5_ZIP.resolve())
    print(f"v5 Submit: zip={V5_ZIP.stat().st_size}B, prompt={len(prompt_text)}chars")

    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    pages = context.pages

    # 1. Find ChatGPT page
    chat_page = None
    for p in pages:
        if "chatgpt.com" in p.url or "chat.openai.com" in p.url:
            chat_page = p
            print(f"[1] Found: {p.url[:80]}")
            break
    if not chat_page:
        chat_page = pages[0] if pages else context.new_page()
        chat_page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)
    else:
        chat_page.bring_to_front()

    # 2. Upload zip
    print("[2] Uploading zip...")
    try:
        fi = chat_page.locator("input[type='file']").first
        if fi.count() > 0:
            fi.set_input_files(zip_path_str)
            print("  uploaded")
    except Exception as e:
        print(f"  upload failed: {e}")

    time.sleep(2)

    # 3. Paste prompt
    print("[3] Pasting prompt...")
    for sel in ["#prompt-textarea", "textarea[placeholder*='Message']", "div[contenteditable='true']"]:
        try:
            el = chat_page.wait_for_selector(sel, timeout=3000, state="visible")
            if el:
                el.click(); time.sleep(0.3)
                el.fill(""); time.sleep(0.1)
                el.fill(prompt_text)
                print(f"  pasted via {sel}")
                break
        except: continue
    time.sleep(1)

    # 4. Click send
    print("[4] Sending...")
    sent = False
    for sel in ["button[data-testid='send-button']", "button[aria-label*='Send']"]:
        try:
            btn = chat_page.wait_for_selector(sel, timeout=5000, state="visible")
            if btn:
                # Wait for button to enable (file upload may take time)
                for _ in range(30):
                    disabled = btn.get_attribute("disabled")
                    if disabled is None:
                        break
                    time.sleep(1)
                btn.click()
                sent = True
                print(f"  sent via {sel}")
                break
        except: continue
    if not sent:
        chat_page.keyboard.press("Enter")
        print("  sent via Enter")

    # 5. Wait for reply
    print("[5] Waiting for GPT reply...")
    deadline = time.time() + 600
    reply_text = ""
    initial_count = 0
    try:
        initial_count = chat_page.locator("div[data-message-author-role='assistant']").count()
    except: pass
    print(f"  baseline assistant msgs: {initial_count}")

    while time.time() < deadline:
        time.sleep(15)
        elapsed = int(time.time() - (deadline - 600))
        try:
            msgs = chat_page.locator("div[data-message-author-role='assistant']")
            count = msgs.count()
            if count > initial_count:
                # New message appeared - wait for generation to finish
                print(f"\n  new msg detected ({count}), waiting for completion...")
                # Wait for stop button to disappear
                for _ in range(120):
                    try:
                        stop_btn = chat_page.locator("button[data-testid='stop-button']")
                        if stop_btn.count() == 0:
                            time.sleep(2)
                            reply_text = msgs.last.inner_text()
                            print(f"  captured {len(reply_text)} chars")
                            break
                    except: pass
                    time.sleep(2)
                if reply_text: break
        except: pass

        # Fallback: check for copy button
        try:
            copy_btns = chat_page.locator("button[aria-label='Copy']")
            if copy_btns.count() > initial_count:
                time.sleep(2)
                reply_text = chat_page.locator("div[data-message-author-role='assistant']").last.inner_text()
                print(f"  captured via copy button, {len(reply_text)} chars")
                break
        except: pass

        print(f"  {elapsed}s", end="\r")

    print()

    # 6. Save
    if reply_text:
        (V5_DIR / "GPT_REVIEW_RESULT.md").write_text(reply_text, encoding="utf-8")
        # Parse decision
        lower = reply_text.lower()
        if "overall judgment: accepted" in lower or "overall judgment: accepted" in lower:
            decision = "accepted"
        elif "overall judgment: rejected" in lower:
            decision = "rejected"
        elif "overall judgment: blocked" in lower:
            decision = "blocked"
        elif "overall judgment: human_required" in lower:
            decision = "human_required"
        else:
            decision = "partial" if "overall judgment: partial" in lower else "unknown"
        (V5_DIR / "GPT_REVIEW_DECISION.md").write_text(json.dumps({
            "review_run_id": RUN_ID, "decision": decision,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "reply_length": len(reply_text),
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[6] Saved: {len(reply_text)} chars, decision={decision}")
    else:
        print("[6] No reply captured within timeout")

    pw.stop()
    print("Done.")


if __name__ == "__main__":
    main()
