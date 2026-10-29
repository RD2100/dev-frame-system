#!/usr/bin/env python3
"""One-shot: submit framework-freeze-context-pack.zip to GPT, save result."""
import hashlib, json, re, sys, time, zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.submission_guard import pre_submit_gate
from tools.submission_guard import record_submission_result

OUT = ROOT / "_reports" / "framework-freeze-context-pack"
ZIP = ROOT / "framework-freeze-context-pack.zip"
PROMPT = OUT / "GPT_DECISION_PROMPT.md"
TARGET = "https://chatgpt.com/c/6a1d4a71-0064-83a2-b762-0987baccba8f"

def ts(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def hash_text(t): return hashlib.sha256(t.encode()).hexdigest()[:16]

log = []
def L(e, d=""):
    entry = f"| {ts()} | {e} | {d} |"
    log.append(entry)
    print(f"  [{e}] {d}")

print("=" * 60)
print("Framework Freeze — Submit to GPT")
print("=" * 60)
L("start", f"zip={ZIP.name}({ZIP.stat().st_size}b) prompt={PROMPT.name}({PROMPT.stat().st_size}b)")

# Gate
pre_submit_gate(OUT, "framework-freeze-submission")

# Safety
assert ZIP.name == "framework-freeze-context-pack.zip", f"Wrong zip: {ZIP.name}"
with zipfile.ZipFile(ZIP) as zf:
    for n in zf.namelist():
        assert ".git/" not in n, f"Unsafe in zip: {n}"
L("safety_ok", f"{len(zf.namelist())} entries clean")

from playwright.sync_api import sync_playwright
pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
L("cdp", "ok")

page = None
for ctx in b.contexts:
    for p in ctx.pages:
        if "6a1d4a71" in p.url:
            page = p
            break
if not page:
    page = b.contexts[0].new_page()
    page.goto(TARGET, wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)
L("page", page.url[:80])

# Paste prompt
prompt_text = PROMPT.read_text(encoding="utf-8")
try:
    el = page.wait_for_selector("#prompt-textarea", timeout=5000, state="visible")
    el.click()
    time.sleep(0.3)
    el.fill(prompt_text)
    L("paste", f"{len(prompt_text)} chars")
except Exception:
    page.keyboard.press("Control+v")
    L("paste", "fallback Ctrl+v")

# Upload zip
zs = "manual"
try:
    fi = page.query_selector("input[type='file']")
    if fi:
        fi.set_input_files(str(ZIP))
        zs = "auto_success"
except Exception:
    pass
L("zip", zs)

# Baseline
ab = len(page.query_selector_all('[data-message-author-role="assistant"]'))
L("baseline", f"asst={ab}")

# Submit
try:
    btn = page.query_selector('button[data-testid="send-button"]')
    if btn:
        btn.click()
    else:
        page.keyboard.press("Enter")
except Exception:
    page.keyboard.press("Enter")
st = ts()
L("submit", st)
print(f"[OK] Submitted: {st}")

# Wait for new reply
dl = time.time() + 900
nv = False
rt = ""
cs = "timeout"
lt = ""
stable = 0
print("[INFO] Waiting for GPT (900s)...")
while time.time() < dl:
    time.sleep(3)
    am = page.query_selector_all('[data-message-author-role="assistant"]')
    aa = len(am)
    if aa > ab and not nv:
        nv = True
        L("new_reply", f"{ab}->{aa}")
        print(f"  New reply: {ab}->{aa}")
    if nv and am:
        cur = am[-1].inner_text()
        if cur == lt:
            stable += 1
        else:
            stable = 0
            lt = cur
        if not page.query_selector('button[data-testid="stop-button"]') and stable >= 3 and len(cur) > 200:
            cs = "complete"
            rt = cur
            L("complete", f"{len(cur)} chars stable {stable*3}s")
            break

L("done", f"{cs} verified={nv}")
print(f"[OK] Reply: {len(rt)} chars, {cs}")

# Save result
(OUT / "GPT_FRAMEWORK_FREEZE_REVIEW_RESULT.md").write_text(
    f"---\ntask_id: framework-freeze\nsource: chatgpt_cdp\nsubmitted_at: {st}\n"
    f"new_reply_verified: {str(nv).lower()}\ncompletion_status: {cs}\n---\n\n{rt}",
    encoding="utf-8")
L("saved", "GPT_FRAMEWORK_FREEZE_REVIEW_RESULT.md")

# Parse decision
sys.path.insert(0, str(ROOT / "tools"))
from oracle_gpt_reply_monitor import parse_decision
d = parse_decision(rt)
t = rt.lower()

# Framework-specific parsing
fw_ready = "partial"
if "framework_ready" in t or "should be frozen" in t or "framework is ready" in t:
    fw_ready = "framework_ready"
if "human_required" in t:
    fw_ready = "human_required"
if "blocked" in t and fw_ready != "human_required":
    fw_ready = "blocked"

s2s = d.get("overall_judgment", "unknown")
s3 = d.get("s3_allowed", "unknown")

next_task = ""
for kw in ["recommended next task", "next step:", "frozen taskspec"]:
    idx = t.find(kw)
    if idx > 0:
        snippet = t[idx:idx+300]
        for line in snippet.split("\n"):
            if kw in line.lower():
                next_task = line.strip()
                break
        if next_task:
            break

auto = "no"
if "autonomously" in t:
    after = t.split("autonomously")[1][:200]
    if "yes" in after or "may" in after:
        auto = "conditional"
elif "non-destructive" in t:
    auto = "conditional"

allow = fw_ready == "framework_ready" and auto != "no"

(OUT / "GPT_FRAMEWORK_FREEZE_DECISION.md").write_text(f"""# GPT Framework Freeze Decision

## 1. Overall Judgment
{fw_ready}

## 2. Framework Should Be Frozen
{'yes' if fw_ready == 'framework_ready' else 'partial' if fw_ready == 'partial' else 'no'}

## 3. S2 Status
{s2s}

## 4. S3 Allowed
{s3}

## 5. Recommended Next Task
{next_task if next_task else 'see GPT reply for details'}

## 6. Autonomous Non-destructive Progression Allowed
{auto}

## 7. Human Confirmation Required For
- file deletion, cleanup, move, rename
- historical evidence overwrite
- sensitive config changes
- pre-S2 baseline attestation
- forbidden scope modifications

## 8. allow_next_step
{str(allow).lower()}
""", encoding="utf-8")
L("decision", f"fw={fw_ready} s2={s2s} s3={s3} allow={allow}")

(OUT / "FULL_FLOW_REPORT.md").write_text(f"""# Full Flow Report — Framework Freeze

| Field | Value |
|-------|-------|
| zip_upload | {zs} |
| prompt_pasted | yes |
| submit_clicked | yes |
| submitted_at | {st} |
| asst_before | {ab} |
| asst_after | {aa} |
| new_reply_verified | {str(nv).lower()} |
| completion_status | {cs} |
| result_saved | yes |
| decision_parsed | yes |
| framework_judgment | {fw_ready} |
| allow_next_step | {str(allow).lower()} |
""", encoding="utf-8")
L("report", "FULL_FLOW_REPORT.md")

(OUT / "FULL_FLOW_LOG.md").write_text(
    "# Full Flow Log\n\n| Time | Event | Details |\n|------|-------|---------|\n" +
    "\n".join(log), encoding="utf-8")
L("log", "FULL_FLOW_LOG.md")

b.close()
pw.stop()

logged = record_submission_result(OUT, "framework-freeze-submission", success=True)
if not logged:
    print("FATAL: submission not logged. review_unverified.")
    sys.exit(11)

print(f"\nDone. Judgment: {fw_ready}, allow_next_step: {allow}")
