#!/usr/bin/env python3
"""Submit diagnosis pack to GPT via CDP."""
import asyncio, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ZIP_PATH = ROOT / "_reports" / "smoke-timeout-diagnosis" / "smoke-timeout-diagnosis-remediation-v1-20260604.zip"
PROMPT_PATH = ROOT / "_reports" / "smoke-timeout-diagnosis" / "GPT_REVIEW_PROMPT.md"
CDP_URL = "http://localhost:9222"
PROMPT_TEXT = PROMPT_PATH.read_text(encoding="utf-8")

async def submit():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        print(f"[OK] Connected to CDP at {CDP_URL}")

        target_page = None
        for context in browser.contexts:
            for page in context.pages:
                if "/c/6a212fda-6c04-83a8-82fa-0fa036f762f9" in page.url:
                    target_page = page
                    break

        if not target_page:
            print("ERROR: ChatGPT page not found")
            return

        await target_page.bring_to_front()
        print(f"[OK] On page: {target_page.url[:100]}")
        await asyncio.sleep(1)

        file_input = await target_page.query_selector('input[type="file"]')
        if file_input:
            await file_input.set_input_files(str(ZIP_PATH))
            print(f"[OK] ZIP uploaded: {ZIP_PATH.name}")
            await asyncio.sleep(5)

        input_sel = 'div[contenteditable="true"].ProseMirror'
        input_el = await target_page.query_selector(input_sel)
        if input_el:
            await input_el.click()
            await asyncio.sleep(0.5)
            await target_page.evaluate(f"navigator.clipboard.writeText({json.dumps(PROMPT_TEXT)})")
            await asyncio.sleep(0.5)
            await target_page.keyboard.press("Control+v")
            await asyncio.sleep(1)
            print(f"[OK] Prompt pasted ({len(PROMPT_TEXT)} chars)")

        send_btn = await target_page.query_selector('button[data-testid="send-button"]')
        if send_btn:
            await send_btn.click()
            print("[OK] Submitted!")

        await asyncio.sleep(2)
        print("[DONE]")

if __name__ == "__main__":
    asyncio.run(submit())
