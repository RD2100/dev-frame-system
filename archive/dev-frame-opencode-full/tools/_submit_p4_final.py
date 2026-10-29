#!/usr/bin/env python3
"""Phase 4 final submit — single connection, submit + wait + poll."""
import asyncio, json, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "_reports/conversation-authorization/controlled-real-code-change-execution-v1"
ZIP = D / "controlled-real-code-change-execution-v1-20260604.zip"
PROMPT = (D / "GPT_REVIEW_PROMPT.md").read_text(encoding="utf-8")
RID = "controlled-real-code-change-execution-v1-20260604"

async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://localhost:9222")
        pages = [pg for ctx in b.contexts for pg in ctx.pages]
        print(f"[INFO] Found {len(pages)} pages")
        pg = None
        for p in pages:
            print(f"  {p.url[:100]}")
            if "6a212fda" in p.url:
                pg = p; break
        if not pg:
            print("[ERR] ChatGPT page not found among:")
            for p in pages: print(f"  {p.url}")
            return

        await pg.bring_to_front()
        await asyncio.sleep(1)

        # Upload ZIP
        fi = await pg.query_selector('input[type="file"]')
        if fi:
            await fi.set_input_files(str(ZIP))
            print(f"[OK] ZIP uploaded ({ZIP.stat().st_size} bytes)")
            await asyncio.sleep(4)

        # Type prompt
        el = await pg.query_selector('div[contenteditable="true"].ProseMirror')
        if el:
            await el.click()
            await asyncio.sleep(0.5)
            await pg.evaluate(f"navigator.clipboard.writeText({json.dumps(PROMPT)})")
            await asyncio.sleep(0.5)
            await pg.keyboard.press("Control+v")
            await asyncio.sleep(1.5)
            print(f"[OK] Prompt pasted ({len(PROMPT)} chars)")

        # Get message count before sending
        ms_before = await pg.evaluate('() => document.querySelectorAll("[data-message-author-role=assistant]").length')
        print(f"[INFO] Assistant messages before send: {ms_before}")

        # Send
        btn = await pg.query_selector('button[data-testid="send-button"]')
        if btn:
            await btn.click()
            print("[OK] SENT — waiting for response...")
        else:
            print("[ERR] No send button")
            return

        # Poll up to 3 times with 30s intervals
        for attempt in range(3):
            wait = 30 if attempt == 0 else 20
            print(f"[POLL] Attempt {attempt+1}/3, waiting {wait}s...")
            await asyncio.sleep(wait)
            ms_now = await pg.evaluate('() => document.querySelectorAll("[data-message-author-role=assistant]").length')
            print(f"[POLL] Assistant messages now: {ms_now} (was {ms_before})")

            if ms_now > ms_before:
                msgs = await pg.evaluate("""
                    () => Array.from(document.querySelectorAll('[data-message-author-role="assistant"]'))
                        .map((m,i) => ({i, t: m.textContent||"", l: (m.textContent||"").length}))
                """)
                last = msgs[-1]
                print(f"[OK] New response! idx={last['i']}, len={last['l']} chars")
                if RID in last['t']:
                    print(f"[OK] RID match")
                else:
                    print(f"[WARN] RID NOT FOUND in response")
                if last['l'] < 100:
                    print(f"[WARN] SHORT CAPTURE ({last['l']} chars)")

                out = D / "GPT_REPLY_P4_FINAL.md"
                out.write_text(last['t'], encoding="utf-8")
                print(f"[SAVED] {out}")
                print()
                print("="*60)
                print(last['t'][:3000])
                return
            else:
                print(f"[WARN] No new message yet")

        print("[FAIL] No response after 3 poll attempts")

asyncio.run(main())
