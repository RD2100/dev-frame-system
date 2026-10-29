#!/usr/bin/env python3
"""Submit batch review pack to GPT — single clean submission."""
import asyncio, json, sys; from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.submission_guard import pre_submit_gate
from tools.submission_guard import record_submission_result
D = ROOT / "_reports/conversation-authorization/low-risk-enhancements-batch-v1"
ZIP = D / "low-risk-enhancements-batch-v1-20260604.zip"
PROMPT = (D / "GPT_REVIEW_PROMPT.md").read_text(encoding="utf-8")
RID = "low-risk-enhancements-batch-v1-20260604"
async def main():
    pre_submit_gate(D, RID)
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://localhost:9222")
        pg = next((pg for ctx in b.contexts for pg in ctx.pages if "6a212fda" in pg.url), None)
        if not pg: return print("ERR: no page")
        await pg.bring_to_front(); await asyncio.sleep(1)
        fi = await pg.query_selector('input[type="file"]')
        if fi: await fi.set_input_files(str(ZIP)); await asyncio.sleep(4); print("[OK] ZIP")
        el = await pg.query_selector('div[contenteditable="true"].ProseMirror')
        if el: await el.click(); await asyncio.sleep(0.5); await pg.evaluate(f"navigator.clipboard.writeText({json.dumps(PROMPT)})"); await asyncio.sleep(0.5); await pg.keyboard.press("Control+v"); await asyncio.sleep(1.5); print("[OK] prompt")
        ms_before = await pg.evaluate('() => document.querySelectorAll("[data-message-author-role=assistant]").length')
        btn = await pg.query_selector('button[data-testid="send-button"]')
        if btn: await btn.click(); print(f"[OK] sent (msgs before: {ms_before})")
        else: await pg.keyboard.press("Enter"); print(f"[OK] sent via Enter (msgs before: {ms_before})")
        await asyncio.sleep(2)
        for attempt in range(3):
            wait = 40 if attempt == 0 else 25
            print(f"[POLL] {attempt+1}/3, wait {wait}s..."); await asyncio.sleep(wait)
            ms_now = await pg.evaluate('() => document.querySelectorAll("[data-message-author-role=assistant]").length')
            if ms_now > ms_before:
                msgs = await pg.evaluate("() => Array.from(document.querySelectorAll('[data-message-author-role=assistant]')).map((m,i) => ({i, t: m.textContent||'', l: (m.textContent||'').length}))")
                last = msgs[-1]
                print(f"[OK] New msg! idx={last['i']}, {last['l']} chars, RID={'YES' if RID in last['t'] else 'NO'}")
                if last['l'] < 100: print("WARN: SHORT")
                out = D / "GPT_REPLY.md"; out.write_text(last['t'], encoding="utf-8")
                print("="*60); print(last['t'][:4000])
                logged = record_submission_result(D, RID, success=True)
                if not logged:
                    print('FATAL: submission not logged. review_unverified.')
                    sys.exit(11)
                return
            print(f"[WAIT] msgs={ms_now} (no change)")
        print("[FAIL] No response after 3 polls")
        logged = record_submission_result(D, RID, success=False, detail="no_response_after_3_polls")
        if not logged:
            print('FATAL: submission not logged. review_unverified.')
            sys.exit(11)
asyncio.run(main())
