#!/usr/bin/env python3
"""Poll GPT response for diagnosis round."""
import asyncio, json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CDP_URL = "http://localhost:9222"
REVIEW_RUN_ID = "smoke-timeout-diagnosis-remediation-v1-20260604"
OUTPUT_DIR = ROOT / "_reports" / "smoke-timeout-diagnosis"

async def poll():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        target_page = None
        for context in browser.contexts:
            for page in context.pages:
                if "/c/6a212fda-6c04-83a8-82fa-0fa036f762f9" in page.url:
                    target_page = page
                    break
        if not target_page:
            print("ERROR: Page not found", file=sys.stderr)
            return
        await target_page.bring_to_front()
        await asyncio.sleep(2)
        messages = await target_page.evaluate("""
            () => {
                const msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
                return Array.from(msgs).map((m, idx) => ({
                    index: idx, text: m.textContent || m.innerText || '', length: (m.textContent || '').length
                }));
            }
        """)
        if not messages:
            print("WARN: No assistant messages", file=sys.stderr)
            return
        last = messages[-1]
        text = last["text"]
        print(f"[INFO] {len(messages)} messages, last: {len(text)} chars, idx={last['index']}", file=sys.stderr)
        if len(text) < 100:
            print(f"WARN: Short capture ({len(text)} chars)", file=sys.stderr)
        if REVIEW_RUN_ID not in text:
            print(f"WARN: REVIEW_RUN_ID not found", file=sys.stderr)
        print(text)
        out_path = OUTPUT_DIR / "GPT_REPLY_DIAGNOSIS.md"
        out_path.write_text(text, encoding="utf-8")
        print(f"[SAVED] {out_path}", file=sys.stderr)

if __name__ == "__main__":
    asyncio.run(poll())
