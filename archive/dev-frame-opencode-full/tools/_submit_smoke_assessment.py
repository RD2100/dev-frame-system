#!/usr/bin/env python3
"""
_submit_smoke_assessment.py — CDP-based submit of smoke test assessment pack to GPT.

Connects to Chrome over CDP (port 9222), finds the authorized ChatGPT conversation page,
uploads the evidence ZIP, pastes the review prompt, and submits.

Usage:
  python tools/_submit_smoke_assessment.py
"""

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ZIP_PATH = ROOT / "_reports" / "smoke-test-failure-assessment" / "smoke-test-failure-assessment-v1-20260604.zip"
PROMPT_PATH = ROOT / "_reports" / "smoke-test-failure-assessment" / "GPT_REVIEW_PROMPT.md"
AUTH_URL = "https://chatgpt.com/c/6a212fda-6c04-83a8-82fa-0fa036f762f9"
CDP_URL = "http://localhost:9222"

# Full prompt text
PROMPT_TEXT = PROMPT_PATH.read_text(encoding="utf-8")


async def submit():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        print(f"[OK] Connected to Chrome CDP at {CDP_URL}")

        # Find the ChatGPT conversation page
        target_page = None
        for context in browser.contexts:
            for page in context.pages:
                url = page.url
                print(f"  Page: {page.url[:100]}")
                if "/c/6a212fda-6c04-83a8-82fa-0fa036f762f9" in url:
                    target_page = page
                    break
            if target_page:
                break

        if not target_page:
            # Try to navigate
            print("[INFO] Authorized page not found in open pages, navigating...")
            context = browser.contexts[0]
            target_page = await context.new_page()
            await target_page.goto(AUTH_URL, wait_until="domcontentloaded")
            await asyncio.sleep(3)

        await target_page.bring_to_front()
        print(f"[OK] On page: {target_page.url[:100]}")
        await asyncio.sleep(1)

        # Strategy 1: Find the editor area and file input
        # ChatGPT uses a contenteditable div or textarea for input
        print("[STEP] Looking for input elements...")

        # Try to find file input (hidden) and trigger upload
        file_input = await target_page.query_selector('input[type="file"]')
        if file_input:
            print("[OK] Found file input, uploading ZIP...")
            await file_input.set_input_files(str(ZIP_PATH))
            print(f"[OK] ZIP uploaded: {ZIP_PATH.name}")
            await asyncio.sleep(3)  # Wait for upload to complete
        else:
            print("[WARN] No file input found directly, trying attachment button...")
            # Try clicking the attachment/plus button
            # Common selectors for ChatGPT attachment button
            attach_selectors = [
                'button[aria-label="Attach files"]',
                'button[aria-label="Upload file"]',
                'input[type="file"]',
                '[data-testid="file-input"]',
                'button[data-testid="attach-file"]',
            ]
            clicked = False
            for sel in attach_selectors:
                btn = await target_page.query_selector(sel)
                if btn:
                    print(f"  Found: {sel}")
                    try:
                        # For file inputs, directly set files
                        tag = await btn.evaluate("el => el.tagName")
                        if tag.upper() == "INPUT":
                            await btn.set_input_files(str(ZIP_PATH))
                            print(f"[OK] ZIP uploaded via {sel}")
                            clicked = True
                            break
                        else:
                            # Click to open file chooser, then handle dialog
                            file_chooser_promise = target_page.wait_for_event("filechooser", timeout=5000)
                            await btn.click()
                            file_chooser = await file_chooser_promise
                            await file_chooser.set_files(str(ZIP_PATH))
                            print(f"[OK] ZIP uploaded via file chooser")
                            clicked = True
                            break
                    except Exception as e:
                        print(f"  Failed: {e}")
                        continue

            if not clicked:
                print("[WARN] Could not find attachment button. Proceeding with text-only paste.")
                print("[WARN] ZIP at:", str(ZIP_PATH))
                print("[WARN] Manual upload may be needed.")

        await asyncio.sleep(2)

        # Paste the prompt text into the input area
        print("[STEP] Pasting prompt text...")

        # Find the input area - ChatGPT uses a rich text editor
        input_sel = None
        candidate_selectors = [
            'div[contenteditable="true"].ProseMirror',
            '#prompt-textarea',
            'textarea[data-id]',
            'div[contenteditable="true"]',
            'textarea',
        ]

        for sel in candidate_selectors:
            el = await target_page.query_selector(sel)
            if el:
                input_sel = sel
                print(f"  Found input: {sel}")
                break

        if input_sel:
            input_el = await target_page.query_selector(input_sel)
            await input_el.click()
            await asyncio.sleep(0.5)

            # Set text content for contenteditable, value for textarea
            tag = await input_el.evaluate("el => el.tagName")
            if tag.upper() in ("TEXTAREA", "INPUT"):
                await input_el.fill(PROMPT_TEXT)
            else:
                # contenteditable div
                await input_el.evaluate(
                    "el => { el.innerHTML = ''; el.focus(); }"
                )
                # Use keyboard to type the text - but this is slow for large text
                # Better: use clipboard
                await target_page.evaluate(f"""
                    navigator.clipboard.writeText({json.dumps(PROMPT_TEXT)});
                """)
                await asyncio.sleep(0.3)
                await target_page.keyboard.press("Control+v")
                await asyncio.sleep(1)

            print(f"[OK] Prompt text pasted ({len(PROMPT_TEXT)} chars)")
        else:
            print("[WARN] Could not find input element. Manual paste required.")
            print("[WARN] Prompt text available at:", str(PROMPT_PATH))

        await asyncio.sleep(1)

        # Submission: find and click the send button
        print("[STEP] Looking for send button...")
        send_selectors = [
            'button[data-testid="send-button"]',
            'button[aria-label="Send message"]',
            'button svg[aria-label="Send"]',
            'button:has-text("Send")',
        ]

        send_clicked = False
        for sel in send_selectors:
            btn = await target_page.query_selector(sel)
            if btn:
                print(f"  Found send: {sel}")
                await btn.click()
                send_clicked = True
                break

        if not send_clicked:
            # Fallback: press Enter
            print("  No send button found, pressing Enter...")
            await target_page.keyboard.press("Enter")

        print("[OK] Submitted!")
        await asyncio.sleep(2)
        print("[DONE] Check ChatGPT for response.")


if __name__ == "__main__":
    asyncio.run(submit())
