#!/usr/bin/env python3
"""
oracle_gpt_review_loop_once.py — One round of GPT-Agent Review Loop.

Reads previous GPT blocked reasons, generates reconciliation pack,
submits to GPT via CDP, waits for reply, parses decision.

Usage: python tools/oracle_gpt_review_loop_once.py --task-id s2 --round 1
"""

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOOP_DIR = ROOT / "_reports" / "gpt-review-loop"
TARGET_URL_FILE = ROOT / "_reports" / "browser-cdp-handoff" / "TARGET_CHATGPT_URL.txt"


def ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hash_text(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()[:16]


def main():
    parser = argparse.ArgumentParser(description="One round of GPT review loop")
    parser.add_argument("--task-id", default="s2")
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    tid = args.task_id
    rnd = args.round
    round_dir = LOOP_DIR / tid / f"round-{rnd}"
    round_dir.mkdir(parents=True, exist_ok=True)

    zip_path = round_dir / "zip" / f"s2-reconciled-review-pack-round-{rnd}.zip"
    prompt_path = round_dir / "GPT_REVIEW_PROMPT.md"
    log_path = round_dir / "ROUND_LOG.md"
    result_path = round_dir / "GPT_REVIEW_RESULT.md"
    decision_path = round_dir / "GPT_REVIEW_DECISION.md"
    flow_path = round_dir / "FULL_FLOW_REPORT.md"
    loop_decision_path = round_dir / "LOOP_DECISION.md"

    if not zip_path.exists():
        print(f"BLOCKED: zip not found: {zip_path}")
        sys.exit(1)
    if not prompt_path.exists():
        print(f"BLOCKED: prompt not found: {prompt_path}")
        sys.exit(1)

    prompt_text = prompt_path.read_text(encoding="utf-8")
    target_url = TARGET_URL_FILE.read_text(encoding="utf-8").strip() if TARGET_URL_FILE.exists() else "https://chatgpt.com/c/6a1d4a71-0064-83a2-b762-0987baccba8f"

    log_lines = []

    def log(event, detail=""):
        entry = f"| {ts()} | {event} | {detail} |"
        log_lines.append(entry)
        print(f"  [{event}] {detail}")

    print("=" * 60)
    print(f"Oracle GPT Review Loop — {tid} Round {rnd}")
    print("=" * 60)
    log("loop_start", f"task={tid} round={rnd}")

    # 1. Connect CDP
    cdp_url = None
    for port in [9222, 9223, 9224, 9225]:
        try:
            r = urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2)
            if "webSocketDebuggerUrl" in json.loads(r.read()):
                cdp_url = f"http://127.0.0.1:{port}"
                break
        except Exception:
            continue

    if not cdp_url:
        print("\nBLOCKED_CDP_NOT_AVAILABLE")
        log("error", "no CDP endpoint")
        log_path.write_text("# Round Log\n\n| Time | Event | Details |\n|------|-------|---------|\n" + "\n".join(log_lines), encoding="utf-8")
        sys.exit(1)

    log("cdp_connected", cdp_url)
    print(f"[OK] CDP: {cdp_url}")

    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(cdp_url)

    # 2. Page
    page = None
    for ctx in browser.contexts:
        for p in ctx.pages:
            if "6a1d4a71-0064" in p.url:
                page = p
                break
    if not page:
        page = browser.contexts[0].new_page() if browser.contexts else browser.new_context().new_page()
        page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
    log("page_ready", page.url[:100])
    print(f"[OK] Page: {page.url[:80]}")

    # 3. Paste prompt
    try:
        el = page.wait_for_selector("#prompt-textarea", timeout=5000, state="visible")
        if el:
            el.click()
            time.sleep(0.5)
            el.fill(prompt_text)
    except Exception:
        page.keyboard.press("Control+v")
    log("prompt_pasted", f"{len(prompt_text)} chars")
    print(f"[OK] Prompt: {len(prompt_text)} chars")

    # 4. Upload zip
    zip_status = "manual_required"
    try:
        fi = page.query_selector("input[type='file']")
        if fi:
            fi.set_input_files(str(zip_path))
            zip_status = "auto_success"
    except Exception:
        pass
    log("zip_upload", zip_status)
    print(f"[OK] Zip: {zip_status}")

    # 5. Baseline
    asst_before = len(page.query_selector_all('[data-message-author-role="assistant"]'))
    asst_msgs_before = page.query_selector_all('[data-message-author-role="assistant"]')
    hash_before = hash_text(asst_msgs_before[-1].inner_text()) if asst_msgs_before else "none"
    log("baseline", f"asst={asst_before} hash={hash_before}")
    print(f"[OK] Baseline: {asst_before} asst msgs")

    # 6. SEND
    print("\n" + "=" * 60)
    print("READY TO SUBMIT")
    print(f"  Round: {rnd}")
    print(f"  Zip: {zip_path.name} ({zip_status})")
    print(f"  Prompt: {len(prompt_text)} chars")
    print(f"  Baseline: {asst_before} asst msgs")

    try:
        user_input = input("\nType SEND to submit: ")
        send_confirmed = (user_input.strip() == "SEND")
    except EOFError:
        print("Non-interactive: using piped SEND")
        send_confirmed = True

    if not send_confirmed:
        log("aborted", "user did not confirm SEND")
        log_path.write_text("# Round Log\n\n| Time | Event | Details |\n|------|-------|---------|\n" + "\n".join(log_lines), encoding="utf-8")
        pw.stop()
        print("Aborted.")
        sys.exit(0)

    log("send_confirmed", ts())

    # 7. Click send
    try:
        btn = page.query_selector('button[data-testid="send-button"]')
        if btn:
            btn.click()
        else:
            page.keyboard.press("Enter")
    except Exception:
        page.keyboard.press("Enter")
    submitted_at = ts()
    log("submitted", submitted_at)
    print(f"[OK] Submitted: {submitted_at}")

    # 8. Wait for new reply
    print(f"[INFO] Waiting for GPT reply ({args.timeout}s)...")
    deadline = time.time() + args.timeout
    new_reply_verified = False
    reply_text = ""
    completion_status = "timeout"
    last_text = ""
    stable = 0

    while time.time() < deadline:
        time.sleep(3)
        elapsed = int(time.time() - (deadline - args.timeout))
        asst_msgs = page.query_selector_all('[data-message-author-role="assistant"]')
        asst_after = len(asst_msgs)

        if asst_after > asst_before and not new_reply_verified:
            new_reply_verified = True
            log("new_reply_detected", f"count {asst_before}->{asst_after}")
            print(f"  New reply ({asst_before}->{asst_after}) at t+{elapsed}s")

        if new_reply_verified and asst_msgs:
            current = asst_msgs[-1].inner_text()
            if current == last_text:
                stable += 1
            else:
                stable = 0
                last_text = current

            stop_btn = page.query_selector('button[data-testid="stop-button"]')
            if not stop_btn and stable >= 3 and len(current) > 200:
                completion_status = "complete"
                reply_text = current
                log("reply_complete", f"{len(current)} chars stable {stable*3}s")
                break

        if not new_reply_verified and elapsed > 180:
            log("timeout_no_reply", f"no new reply after {elapsed}s")
            completion_status = "no_new_reply"
            break

    log("completion", f"status={completion_status} verified={new_reply_verified}")
    print(f"[OK] Reply: {len(reply_text)} chars, {completion_status}")

    # 9. Save result
    result_path.write_text(f"""---
task_id: {tid}
round: {rnd}
source: chatgpt_cdp_loop
submitted_at: {submitted_at}
assistant_count_before: {asst_before}
assistant_count_after: {asst_after if 'asst_after' in dir() else 'N/A'}
new_reply_verified: {str(new_reply_verified).lower()}
completion_status: {completion_status}
---

{reply_text}
""", encoding="utf-8")
    log("result_saved", str(result_path))

    # 10. Parse decision
    sys.path.insert(0, str(ROOT / "tools"))
    from oracle_gpt_reply_monitor import parse_decision

    decision = parse_decision(reply_text)
    decision["new_reply_verified"] = new_reply_verified
    if not new_reply_verified or completion_status != "complete":
        decision["allow_next_stage"] = False

    # Next action
    if decision["overall_judgment"] == "human_required":
        next_action = "stop_for_human_review"
    elif decision["allow_next_stage"]:
        next_action = "proceed_allowed_but_not_executed"
    else:
        next_action = "continue_reconciliation_or_human_review"

    decision_path.write_text(f"""# GPT Review Decision — Round {rnd}

## 1. Overall Judgment
{decision['overall_judgment']}

## 2. S2 Accepted
{decision['s2_accepted']}

## 3. S3 Allowed
{decision['s3_allowed']}

## 4. New Reply Verified
{str(new_reply_verified).lower()}

## 5. Completion Status
{completion_status}

## 6. Automation Decision
allow_next_stage: {str(decision['allow_next_stage']).lower()}
""", encoding="utf-8")
    log("decision_parsed", f"judgment={decision['overall_judgment']} allow={decision['allow_next_stage']}")

    # Loop decision
    loop_decision_path.write_text(f"""# Loop Decision

## Task
{tid}

## Round
{rnd}

## GPT Judgment
{decision['overall_judgment']}

## S2 Accepted
{decision['s2_accepted']}

## S3 Allowed
{decision['s3_allowed']}

## allow_next_stage
{str(decision['allow_next_stage']).lower()}

## Next Action
{next_action}

## Safety
* S3 executed: no
* S2 core logic modified: no
* original evidence pack modified: no
""", encoding="utf-8")
    log("loop_decision", next_action)

    # Flow report
    flow_path.write_text(f"""# Full Flow Report — Round {rnd}

## Status
{'SUCCESS' if completion_status == 'complete' and new_reply_verified else 'PARTIAL'}

## Submit
| Field | Value |
|-------|-------|
| target_url | {target_url} |
| zip_upload | {zip_status} |
| submit_clicked | yes |
| submitted_at | {submitted_at} |

## Reply
| Field | Value |
|-------|-------|
| asst_before | {asst_before} |
| asst_after | {asst_after if 'asst_after' in dir() else 'N/A'} |
| new_reply_verified | {str(new_reply_verified).lower()} |
| completion | {completion_status} |

## Decision
| Field | Value |
|-------|-------|
| judgment | {decision['overall_judgment']} |
| s3_allowed | {decision['s3_allowed']} |
| allow_next_stage | {str(decision['allow_next_stage']).lower()} |
| next_action | {next_action} |
""", encoding="utf-8")
    log("flow_report_saved", str(flow_path))

    # Save log
    log_path.write_text("# Round Log\n\n| Time | Event | Details |\n|------|-------|---------|\n" + "\n".join(log_lines), encoding="utf-8")
    log("log_saved", str(log_path))

    browser.close()
    pw.stop()

    print("\n" + "=" * 60)
    print("Loop Round Complete")
    print("=" * 60)
    print(f"Judgment:   {decision['overall_judgment']}")
    print(f"S3 allowed: {decision['s3_allowed']}")
    print(f"Next:       {next_action}")


if __name__ == "__main__":
    main()
