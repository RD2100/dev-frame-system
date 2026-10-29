#!/usr/bin/env python3
"""Phase 5 submit."""
import asyncio, json, sys; from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.submission_guard import pre_submit_gate
from tools.submission_guard import record_submission_result

D = ROOT / "_reports/conversation-authorization/production-readiness-gap-remediation-planning-v1"
ZIP = D / "production-readiness-gap-remediation-planning-v1-20260604.zip"
P = (D / "GPT_REVIEW_PROMPT.md").read_text(encoding="utf-8")
RID = ZIP.stem
async def s():
    pre_submit_gate(D, RID)
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://localhost:9222")
        pg = next((pg for ctx in b.contexts for pg in ctx.pages if "6a212fda" in pg.url), None)
        if not pg: return print("ERR")
        await pg.bring_to_front(); await asyncio.sleep(1)
        fi = await pg.query_selector('input[type="file"]')
        if fi: await fi.set_input_files(str(ZIP)); await asyncio.sleep(3); print("[OK] ZIP")
        el = await pg.query_selector('div[contenteditable="true"].ProseMirror')
        if el: await el.click(); await asyncio.sleep(0.3); await pg.evaluate(f"navigator.clipboard.writeText({json.dumps(P)})"); await asyncio.sleep(0.3); await pg.keyboard.press("Control+v"); await asyncio.sleep(1); print("[OK] prompt")
        btn = await pg.query_selector('button[data-testid="send-button"]')
        if btn: await btn.click(); print("[OK] sent")
        else: await pg.keyboard.press("Enter"); print("[OK] sent via Enter")
    # Post-submission entrypoint
    logged = record_submission_result(D, RID, success=True)
    if not logged:
        print('FATAL: submission not logged. review_unverified.')
        sys.exit(11)

asyncio.run(s())
