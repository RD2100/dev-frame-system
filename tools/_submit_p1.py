#!/usr/bin/env python3
"""Phase 1 submit — closure pack (pilot: submission guard integration)."""
import asyncio, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.submission_guard import pre_submit_gate
from tools.submission_guard import record_submission_result

# P14 Config Canary — set to True to use config-driven conversation ID
USE_CONFIG_CANARY = False
CONFIG_CONVERSATION_ID = None
if USE_CONFIG_CANARY:
    from tools.submit_target import load_config, from_config
    _cfg = load_config(ROOT / "tools" / "submit_config.example.json")
    _target = from_config(_cfg)
    CONFIG_CONVERSATION_ID = _target.conversation_id

D = ROOT / "_reports/conversation-authorization/smoke-timeout-remediation-final-closure-v1"
ZIP = D / "smoke-timeout-remediation-final-closure-v1-20260604.zip"
PROMPT = (D / "GPT_REVIEW_PROMPT.md").read_text(encoding="utf-8")
RID = "smoke-timeout-remediation-final-closure-v1-20260604"
ACTIVE_CONVERSATION = CONFIG_CONVERSATION_ID if USE_CONFIG_CANARY else "6a212fda"

async def submit():
    # Pre-submission gate
    pre_submit_gate(D, RID)

    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp("http://localhost:9222")
        pg = next((pg for ctx in b.contexts for pg in ctx.pages if ACTIVE_CONVERSATION in pg.url), None)
        if not pg:
            record_submission_result(D, RID, success=False, detail="page_not_found")
            print("FATAL: authorized ChatGPT page not found")
            sys.exit(10)

        await pg.bring_to_front()
        await asyncio.sleep(1)
        fi = await pg.query_selector('input[type="file"]')
        if fi: await fi.set_input_files(str(ZIP)); print("[OK] ZIP"); await asyncio.sleep(3)
        el = await pg.query_selector('div[contenteditable="true"].ProseMirror')
        if el: await el.click(); await asyncio.sleep(0.3); await pg.evaluate(f"navigator.clipboard.writeText({json.dumps(PROMPT)})"); await asyncio.sleep(0.3); await pg.keyboard.press("Control+v"); await asyncio.sleep(1)
        btn = await pg.query_selector('button[data-testid="send-button"]')
        if btn: await btn.click(); print("[OK] sent")
        else: await pg.keyboard.press("Enter"); print("[OK] sent via Enter")
        await asyncio.sleep(2)

    # Post-submission entrypoint (fail-closed)
    logged = record_submission_result(D, RID, success=True)
    if not logged:
        print("FATAL: submission sent but not logged. review_unverified.")
        sys.exit(11)

asyncio.run(submit())
