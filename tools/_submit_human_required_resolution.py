#!/usr/bin/env python3
"""Submit s2-human-required-resolution-pack.zip to GPT, monitor, parse."""
import hashlib, json, sys, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ZIP = ROOT / "s2-human-required-resolution-pack.zip"
PROMPT = ROOT / "_reports/s2-human-required-resolution/GPT_REVIEW_PROMPT.md"
TARGET = "https://chatgpt.com/c/6a1d4a71-0064-83a2-b762-0987baccba8f"

def ts(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
log = []
def L(e,d=""): log.append(f"| {ts()} | {e} | {d} |"); print(f"  [{e}] {d}")

print("="*60); print("S2 Human-required Resolution — Submit"); print("="*60)
L("start", f"zip={ZIP.name}({ZIP.stat().st_size}b)")

from playwright.sync_api import sync_playwright
pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")

page = None
for ctx in b.contexts:
    for p in ctx.pages:
        if "6a1d4a71" in p.url: page = p; break
if not page: page = b.contexts[0].new_page(); page.goto(TARGET, wait_until="domcontentloaded", timeout=30000); time.sleep(2)
L("page", page.url[:80])

prompt_text = PROMPT.read_text(encoding="utf-8")
try:
    el = page.wait_for_selector("#prompt-textarea", timeout=5000, state="visible")
    el.click(); time.sleep(0.3); el.fill(prompt_text); L("paste", f"{len(prompt_text)} chars")
except: page.keyboard.press("Control+v"); L("paste", "fallback")

zs = "manual"
try:
    fi = page.query_selector("input[type='file']")
    if fi: fi.set_input_files(str(ZIP)); zs = "auto_success"
except: pass
L("zip", zs)

ab = len(page.query_selector_all('[data-message-author-role="assistant"]'))
L("baseline", f"asst={ab}")

try:
    btn = page.query_selector('button[data-testid="send-button"]')
    if btn: btn.click()
    else: page.keyboard.press("Enter")
except: page.keyboard.press("Enter")
st = ts(); L("submit", st)

dl = time.time() + 600; nv = False; rt = ""; cs = "timeout"; lt = ""; stable = 0
while time.time() < dl:
    time.sleep(3)
    am = page.query_selector_all('[data-message-author-role="assistant"]')
    aa = len(am)
    if aa > ab and not nv: nv = True; L("new_reply", f"{ab}->{aa}"); print(f"  New: {ab}->{aa}")
    if nv and am:
        cur = am[-1].inner_text()
        if cur == lt: stable += 1
        else: stable = 0; lt = cur
        if not page.query_selector('button[data-testid="stop-button"]') and stable >= 3 and len(cur) > 100:
            cs = "complete"; rt = cur; L("complete", f"{len(cur)} chars"); break

OUT = ROOT / "_reports/s2-human-required-resolution"
(OUT/"GPT_REVIEW_RESULT.md").write_text(f"---\ntask: s2-human-required-resolution\nsource: cdp\nsubmitted_at: {st}\nnew_reply_verified: {str(nv).lower()}\ncompletion: {cs}\n---\n\n{rt}", encoding="utf-8")
L("saved", f"GPT_REVIEW_RESULT.md ({len(rt)} chars)")

sys.path.insert(0, str(ROOT/"tools"))
from oracle_gpt_reply_monitor import parse_decision
from oracle_flow_state import FlowState, save_state, write_outcome, outcome_path

d = parse_decision(rt); t = rt.lower()
accepted = "accepted" if ("accepted" in t and ("claim accepted" in t or "overall judgment: accepted" in t)) else "unknown"
if "human_required" in t: accepted = "human_required"
if "blocked" in t and accepted != "human_required": accepted = "blocked"

s3a = "yes" if "s3 allowed: yes" in t or "s3 is allowed" in t else "no"
allow = accepted == "accepted" and s3a == "yes"

(OUT/"GPT_REVIEW_DECISION.md").write_text(f"""# GPT Review Decision — S2 Human-required Resolution

## Overall Judgment
{accepted}

## Pre-existing Claim Accepted
{'yes' if accepted == 'accepted' else 'no'}

## S3 Allowed
{s3a}

## allow_next_stage
{str(allow).lower()}
""", encoding="utf-8")

state = FlowState("s2", round_num=1)
state.business_decision = accepted
state.dispatch_status = "ready_to_dispatch" if allow else ("manual_confirm_required" if accepted == "human_required" else "stopped")
state.transport_status = "success"; state.compute_statuses()
state.new_reply_verified = nv; state.completion_status = cs
save_state(state); write_outcome(outcome_path("s2"), state.to_outcome())
L("decision", f"judgment={accepted} s3={s3a} allow={allow}")
print(f"\nDone. Judgment: {accepted}, S3: {s3a}, allow_next_stage: {allow}")
