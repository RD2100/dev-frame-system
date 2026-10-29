#!/usr/bin/env python3
"""
_poll_gpt_response.py — Poll ChatGPT page via CDP for the latest assistant response.

Usage:
  python tools/_poll_gpt_response.py > _reports/smoke-test-failure-assessment/GPT_REPLY_RAW.md
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CDP_URL = "http://localhost:9222"
REVIEW_RUN_ID = "smoke-test-failure-assessment-v1-20260604"
OUTPUT_DIR = ROOT / "_reports" / "smoke-test-failure-assessment"


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
            print("ERROR: ChatGPT page not found", file=sys.stderr)
            return None

        await target_page.bring_to_front()
        await asyncio.sleep(2)

        # Extract all assistant messages
        messages = await target_page.evaluate("""
            () => {
                const msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
                const results = [];
                msgs.forEach((m, idx) => {
                    const text = m.textContent || m.innerText || '';
                    results.push({ index: idx, text: text, length: text.length });
                });
                return results;
            }
        """)

        if not messages:
            print("WARN: No assistant messages found", file=sys.stderr)
            return None

        # Get the last (most recent) message
        last = messages[-1]
        text = last["text"]
        print(f"[INFO] Found {len(messages)} assistant messages, last one: {len(text)} chars", file=sys.stderr)

        # Check quality
        if len(text) < 100:
            print(f"WARN: Last message too short ({len(text)} chars) — review_unverified", file=sys.stderr)
            print(f"SHORT_CAPTURE:{text}", file=sys.stderr)

        # Check for REVIEW_RUN_ID
        if REVIEW_RUN_ID not in text:
            print(f"WARN: REVIEW_RUN_ID not found in response — possible template echo or wrong reply", file=sys.stderr)

        # Output the full text
        print(f"# GPT Response — {datetime.now(timezone.utc).isoformat()}")
        print(f"# REVIEW_RUN_ID expected: {REVIEW_RUN_ID}")
        print(f"# Message length: {len(text)} chars")
        print(f"# Message index: {last['index']}")
        print()
        print(text)

        return text


if __name__ == "__main__":
    result = asyncio.run(poll())
    if result:
        # Also save to file
        out_path = OUTPUT_DIR / "GPT_REPLY_RAW.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(result, encoding="utf-8")
        print(f"\n[SAVED] {out_path}", file=sys.stderr)
