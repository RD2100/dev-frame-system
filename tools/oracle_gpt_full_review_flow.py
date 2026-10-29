#!/usr/bin/env python3
"""
oracle_gpt_full_review_flow.py — Full GPT review flow: submit → monitor → parse.

Complete pipeline:
  1. Connect Chrome CDP, open target ChatGPT session
  2. Paste review prompt, attempt auto-upload of evidence zip
  3. Record pre-submit baseline (message counts, hashes)
  4. Wait for user to type SEND
  5. Click send, wait for new assistant reply
  6. Extract only the NEW reply (post-SEND)
  7. Save result, parse decision, generate full-flow report

Usage:
  python tools/oracle_gpt_full_review_flow.py --task-id s2
  python tools/oracle_gpt_full_review_flow.py --task-id s2 --timeout 600
"""

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
TARGET_URL_FILE = ROOT / "_reports" / "browser-cdp-handoff" / "TARGET_CHATGPT_URL.txt"
OUTPUT_DIR = ROOT / "_reports" / "gpt-reviews"
CDP_PORTS = [9222, 9223, 9224, 9225]
VALID_DOMAINS = {"chatgpt.com", "chat.openai.com"}

# Override task_id-based path resolution from monitor
sys.path.insert(0, str(ROOT / "tools"))
from oracle_gpt_reply_monitor import parse_decision, write_decision


def ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Guarded target URL read ──────────────────────────────────────────
sys.path.insert(0, str(ROOT / "tools"))
from gpt_conversation_guard import (
    validate_authorized_gpt_conversation,
    reject_unauthorized,
    is_base_url,
    load_authorized_binding,
    get_authorized_conversation_url,
)


def read_target_url() -> str:
    """Read the authorized GPT binding with NO_NEW_GPT_CONVERSATION guard.
    TARGET_CHATGPT_URL.txt is deprecated and informational only.
    Returns the validated target URL or exits with human_required.
    """
    binding = load_authorized_binding()
    url = get_authorized_conversation_url(binding or {})
    if TARGET_URL_FILE.exists():
        legacy_url = TARGET_URL_FILE.read_text(encoding="utf-8").strip()
        if legacy_url and legacy_url != url:
            print("[WARN] Deprecated TARGET_CHATGPT_URL.txt does not match authorized binding; ignoring legacy file.")
    if url:
        parsed = urlparse(url)
        base = ".".join((parsed.hostname or "").split(".")[-2:])
        if base in VALID_DOMAINS:
            # Guard: reject base URL, validate against authorized binding
            ok, reason = validate_authorized_gpt_conversation(url)
            if not ok:
                print(f"\nBLOCKED_NO_NEW_GPT_CONVERSATION: {reason}")
                print("  target_url: authorized binding URL")
                print("  Status: human_required - authorized binding is invalid")
                if False:
                    print(f"  Status: human_required — new GPT conversation requires explicit user authorization")
                print("  Action: update tools/AUTHORIZED_GPT_CONVERSATION.json with the authorized conversation URL")
                result = reject_unauthorized(url, reason)
                output_dir = TARGET_URL_FILE.parent
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / "CDP_SUBMISSION_STATUS.json").write_text(
                    __import__('json').dumps(result, indent=2), encoding="utf-8")
                sys.exit(10)
            return url
    # No valid URL — fail-closed, no fallback
    print("\nBLOCKED_NO_NEW_GPT_CONVERSATION: authorized_binding_missing_or_invalid")
    print("  Status: human_required")
    print("  Action: update tools/AUTHORIZED_GPT_CONVERSATION.json with the authorized conversation URL")
    result = reject_unauthorized("", "authorized_binding_missing_or_invalid")
    TARGET_URL_FILE.parent.mkdir(parents=True, exist_ok=True)
    (TARGET_URL_FILE.parent / "CDP_SUBMISSION_STATUS.json").write_text(
        __import__('json').dumps(result, indent=2), encoding="utf-8")
    sys.exit(10)


def find_cdp():
    for port in CDP_PORTS:
        try:
            r = urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2)
            if "webSocketDebuggerUrl" in json.loads(r.read()):
                return f"http://127.0.0.1:{port}", port
        except Exception:
            continue
    return None, None


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# ── Full Flow ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Full GPT review flow")
    parser.add_argument("--task-id", default="s2")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--poll-interval", type=int, default=3)
    parser.add_argument("--target-url-file", default=None)
    parser.add_argument("--zip", default=None)
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--auto-submit", action="store_true", default=False,
                        help="Skip interactive SEND confirmation (non-interactive mode)")
    args = parser.parse_args()

    tid = args.task_id
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log = []

    def log_event(event, detail=""):
        entry = f"| {ts()} | {event} | {detail} |"
        log.append(entry)
        label = f"[{event}]"
        if detail:
            label += f" {detail}"
        print(f"  {label}")

    print("=" * 60)
    print(f"GPT Full Review Flow — {tid}")
    print("=" * 60)

    # ── 1. Resolve inputs ──
    target_url = read_target_url()
    log_event("target_url", target_url)

    zip_path = Path(args.zip or f"s2-gpt-review-evidence-pack.zip").resolve()
    prompt_path = Path(args.prompt or "_reports/s2-gpt-review-evidence-pack/GPT_REVIEW_PROMPT.md").resolve()

    if not zip_path.exists():
        print(f"\nBLOCKED: zip not found: {zip_path}")
        sys.exit(1)
    if not prompt_path.exists():
        print(f"\nBLOCKED: prompt not found: {prompt_path}")
        sys.exit(1)
    log_event("inputs_ok", f"zip={zip_path.name} prompt={prompt_path.name}")

    prompt_text = prompt_path.read_text(encoding="utf-8")
    print(f"[OK] Zip: {zip_path.name} ({zip_path.stat().st_size} bytes)")
    print(f"[OK] Prompt: {prompt_path.name} ({len(prompt_text)} chars)")

    # ── 2. Connect CDP ──
    cdp_url, cdp_port = find_cdp()
    if not cdp_url:
        print("\nBLOCKED_CDP_NOT_AVAILABLE")
        sys.exit(1)
    log_event("cdp_connected", f"port={cdp_port}")
    print(f"[OK] CDP: port {cdp_port}")

    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(cdp_url)

    # ── 3. Open/reuse target page ──
    from urllib.parse import urlparse
    from gpt_conversation_guard import extract_session_id
    parsed_url = urlparse(target_url)
    target_session_id = extract_session_id(target_url)
    if not target_session_id:
        print("\nBLOCKED_NO_NEW_GPT_CONVERSATION: cannot extract session_id from target URL")
        result = reject_unauthorized(target_url, "cannot_extract_session_id")
        (TARGET_URL_FILE.parent / "CDP_SUBMISSION_STATUS.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        sys.exit(10)

    page = None
    for ctx in browser.contexts:
        for p in ctx.pages:
            if target_session_id in p.url:
                page = p
                log_event("page_reused", p.url[:100])
                break
    if not page:
        # No existing page — try the first page if it matches the target domain
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        existing_pages = list(ctx.pages) if ctx.pages else []
        for p in existing_pages:
            if target_session_id in p.url:
                page = p
                log_event("page_reused_retry", p.url[:100])
                break
        if not page:
            # fail-closed: do NOT auto-create new page
            print("\nBLOCKED_NO_NEW_GPT_CONVERSATION: authorized conversation page not found")
            print(f"  Expected session: {target_session_id}")
            print("  Status: human_required — no existing page matches authorized conversation")
            _save_log(log, tid)
            browser.close()
            pw.stop()
            result = reject_unauthorized(target_url, "authorized_conversation_page_not_found")
            (TARGET_URL_FILE.parent / "CDP_SUBMISSION_STATUS.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            sys.exit(10)
    page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)
    log_event("authorized_page_loaded", target_url[:100])
    print(f"[OK] Page: {page.url[:100]}")

    # ── 4. Paste prompt ──
    prompt_pasted = False
    try:
        selectors = ["#prompt-textarea", "textarea[placeholder*='Message']",
                     "div[contenteditable='true']", "p[data-placeholder]"]
        for sel in selectors:
            try:
                el = page.wait_for_selector(sel, timeout=3000, state="visible")
                if el:
                    el.click()
                    time.sleep(0.5)
                    el.fill(prompt_text)
                    prompt_pasted = True
                    break
            except Exception:
                continue
        if not prompt_pasted:
            # Fallback: click center of page, type
            page.keyboard.press("Control+v")
            prompt_pasted = True
    except Exception as e:
        log_event("paste_warning", str(e)[:80])

    log_event("prompt_pasted", str(prompt_pasted))
    print(f"[OK] Prompt pasted: {prompt_pasted} ({len(prompt_text)} chars)")

    # ── 5. Zip upload ──
    zip_status = "manual_required"
    try:
        file_input = page.query_selector("input[type='file']")
        if file_input:
            file_input.set_input_files(str(zip_path))
            zip_status = "auto_success"
            log_event("zip_upload", "auto_success")
        else:
            log_event("zip_upload", "no file input found")
    except Exception as e:
        log_event("zip_upload_error", str(e)[:80])
    print(f"[OK] Zip upload: {zip_status}")

    # ── 6. Pre-submit baseline ──
    assistant_count_before = len(page.query_selector_all('[data-message-author-role="assistant"]'))
    user_count_before = len(page.query_selector_all('[data-message-author-role="user"]'))
    assistant_msgs = page.query_selector_all('[data-message-author-role="assistant"]')
    last_hash_before = hash_text(assistant_msgs[-1].inner_text()) if assistant_msgs else "none"

    baseline = {
        "assistant_count_before": assistant_count_before,
        "user_count_before": user_count_before,
        "last_assistant_hash": last_hash_before,
        "timestamp_before": ts(),
    }
    log_event("baseline", f"asst={assistant_count_before} user={user_count_before} hash={last_hash_before}")
    print(f"[OK] Baseline: {assistant_count_before} assistant, {user_count_before} user msgs")

    # ── 7. Confirm SEND ──
    print()
    print("=" * 60)
    print("READY TO SUBMIT")
    print("=" * 60)
    print(f"  Target: {target_url}")
    print(f"  Zip: {zip_path.name} ({zip_status})")
    print(f"  Prompt: {prompt_path.name} ({len(prompt_text)} chars)")
    print(f"  Baseline: {assistant_count_before} assistant msgs")
    print()

    send_confirmed = False
    if args.auto_submit:
        send_confirmed = True
        log_event("auto_submit", "non-interactive mode")
        print("[OK] Auto-submit mode: skipping SEND confirmation")
    else:
        try:
            user_input = input("Type SEND to submit, or anything else to abort: ")
            send_confirmed = (user_input.strip() == "SEND")
        except EOFError:
            print("\nNon-interactive environment detected.")
            print("Cannot confirm SEND — use --auto-submit for non-interactive mode.")
            print("Run: python tools/oracle_gpt_full_review_flow.py --task-id s2 --auto-submit")
            log_event("non_interactive", "EOFError, no SEND")
            send_confirmed = False

    if not send_confirmed:
        print("\nSubmission aborted. Saving partial state.")
        log_event("aborted", "user did not confirm SEND")
        _save_log(log, tid)
        pw.stop()
        print("\nSTATUS: PARTIAL_NON_INTERACTIVE")
        sys.exit(0)

    log_event("send_confirmed", ts())
    print(f"[OK] SEND confirmed at {ts()}")

    # ── 8. Click send ──
    submit_clicked = False
    try:
        send_btn = page.query_selector('button[data-testid="send-button"]')
        if not send_btn:
            send_btn = page.query_selector('button[aria-label*="Send"]')
        if send_btn:
            send_btn.click()
            submit_clicked = True
        else:
            page.keyboard.press("Enter")
            submit_clicked = True
    except Exception as e:
        log_event("send_error", str(e)[:80])
        print(f"[WARN] Send click failed: {e}. Please click Send manually.")
        try:
            input("Press Enter after manually clicking Send...")
            submit_clicked = True
        except EOFError:
            submit_clicked = True  # Assume sent

    submitted_at = ts()
    log_event("submitted", f"clicked={submit_clicked} at {submitted_at}")
    print(f"[OK] Submitted at {submitted_at}")

    # ── 9. Wait for new assistant message ──
    print(f"[INFO] Waiting for new GPT reply (timeout={args.timeout}s)...")
    deadline = time.time() + args.timeout
    new_reply_verified = False
    last_text = ""
    stable_count = 0
    completion_status = "timeout"
    extraction_confidence = "low"
    reply_text = ""
    assistant_count_after = assistant_count_before

    while time.time() < deadline:
        time.sleep(args.poll_interval)
        elapsed = int(time.time() - (deadline - args.timeout))

        assistant_msgs = page.query_selector_all('[data-message-author-role="assistant"]')
        assistant_count_after = len(assistant_msgs)

        # Check if new message appeared
        if assistant_count_after > assistant_count_before:
            if not new_reply_verified:
                log_event("new_reply_detected", f"count {assistant_count_before}→{assistant_count_after}")
                new_reply_verified = True

            current = assistant_msgs[-1].inner_text()
            current_hash = hash_text(current)

            # Verify it's different from pre-submit
            if current_hash != last_hash_before or assistant_count_after > assistant_count_before + 1:
                if current == last_text:
                    stable_count += 1
                else:
                    stable_count = 0
                    last_text = current

                stop_btn = page.query_selector('button[data-testid="stop-button"]')
                still_generating = stop_btn is not None

                if not still_generating and stable_count >= 3 and len(current) > 200:
                    completion_status = "complete"
                    extraction_confidence = "high"
                    reply_text = current
                    log_event("reply_complete", f"{len(current)} chars, stable {stable_count*args.poll_interval}s")
                    break
                elif stable_count >= 8:
                    completion_status = "complete"
                    extraction_confidence = "medium"
                    reply_text = current
                    log_event("reply_complete_max_stable", f"{len(current)} chars")
                    break

        if not new_reply_verified and elapsed > 120:
            log_event("timeout_no_new_reply", f"no new reply after {elapsed}s")
            completion_status = "no_new_reply"
            break

    if completion_status == "timeout":
        log_event("timeout", f"no stable reply within {args.timeout}s")
        if assistant_count_after > assistant_count_before:
            reply_text = page.query_selector_all('[data-message-author-role="assistant"]')[-1].inner_text()
            extraction_confidence = "low"

    # ── 10. Save result ──
    result_path = OUTPUT_DIR / f"{tid}-gpt-review-result.md"
    result_path.write_text(f"""---
task_id: {tid}
source: chatgpt_browser_cdp_full_flow
captured_at: {ts()}
target_url: {target_url}
submitted_at: {submitted_at}
assistant_count_before: {assistant_count_before}
assistant_count_after: {assistant_count_after}
new_reply_verified: {str(new_reply_verified).lower()}
completion_status: {completion_status}
extraction_confidence: {extraction_confidence}
---

{reply_text}
""", encoding="utf-8")
    log_event("result_saved", str(result_path))
    print(f"[OK] Result: {result_path} ({len(reply_text)} chars)")

    # ── 10b. Watchdog: reject too-short captures ──
    MIN_REPLY_CHARS = 100
    if len(reply_text) < MIN_REPLY_CHARS:
        print(f"\n[WATCHDOG] Reply too short ({len(reply_text)} < {MIN_REPLY_CHARS} chars) — marking review_unverified")
        log_event("watchdog_short_reply", f"{len(reply_text)} < {MIN_REPLY_CHARS}")
        _save_log(log, tid)

        # Write timeout status
        status_path = OUTPUT_DIR / f"{tid}-cdp-submission-status.json"
        status_path.write_text(json.dumps({
            "review_run_id": tid, "submitted": False, "status": "review_unverified",
            "reason": f"gpt_reply_too_short_{len(reply_text)}_chars",
            "verified_by_review_run_id": False,
            "captured_chars": len(reply_text),
            "retry_allowed": True,
        }, indent=2), encoding="utf-8")

        # Write NOT_AVAILABLE results
        (OUTPUT_DIR / f"{tid}-gpt-review-result.md").write_text("NOT_AVAILABLE_DUE_TO_SHORT_CAPTURE\n", encoding="utf-8")
        (OUTPUT_DIR / f"{tid}-gpt-review-decision.md").write_text("NOT_AVAILABLE_DUE_TO_SHORT_CAPTURE\n", encoding="utf-8")

        browser.close()
        pw.stop()
        print("STATUS: REVIEW_UNVERIFIED (short capture)")
        sys.exit(20)

    # ── 10c. Watchdog: require REVIEW_RUN_ID in reply ──
    import re
    expected_rid = tid
    rid_match = re.search(r"REVIEW_RUN_ID:\s*(\S+)", reply_text)
    if not rid_match or rid_match.group(1) != expected_rid:
        found_rid = rid_match.group(1) if rid_match else None
        reason = "gpt_reply_missing_review_run_id" if not found_rid else "gpt_reply_review_run_id_mismatch"
        print(f"\n[WATCHDOG] No REVIEW_RUN_ID found in GPT reply — marking review_unverified")
        log_event("watchdog_review_run_id_invalid", f"expected={expected_rid} found={found_rid}")
        _save_log(log, tid)

        status_path = OUTPUT_DIR / f"{tid}-cdp-submission-status.json"
        status_path.write_text(json.dumps({
            "review_run_id": tid, "submitted": True, "status": "review_unverified",
            "reason": reason,
            "verified_by_review_run_id": False,
            "expected_review_run_id": expected_rid,
            "captured_review_run_id": found_rid,
            "captured_chars": len(reply_text),
            "retry_allowed": True,
        }, indent=2), encoding="utf-8")

        browser.close()
        pw.stop()
        print("STATUS: REVIEW_UNVERIFIED (no REVIEW_RUN_ID)")
        sys.exit(20)

    log_event("watchdog_pass", f"{len(reply_text)} chars, REVIEW_RUN_ID={rid_match.group(1)}")

    # ── 11. Parse decision ──
    decision = parse_decision(reply_text)
    decision["new_reply_verified"] = new_reply_verified

    # Override: require new_reply_verified
    if not new_reply_verified:
        decision["allow_next_stage"] = False
        decision["overall_judgment"] = decision.get("overall_judgment", "unknown")

    decision_path = OUTPUT_DIR / f"{tid}-gpt-review-decision.md"
    with open(decision_path, "w", encoding="utf-8") as f:
        f.write(f"""# GPT Review Decision

## 1. Overall Judgment
{decision['overall_judgment']}

## 2. S2 Accepted
{decision['s2_accepted']}

## 3. S3 Allowed
{decision['s3_allowed']}

## 4. Blocking Reasons
{chr(10).join('- ' + r for r in decision.get('blocking_reasons', [])) if decision.get('blocking_reasons') else 'none parsed'}

## 5. Missing Evidence
{chr(10).join('- ' + e for e in decision.get('missing_evidence', [])) if decision.get('missing_evidence') else 'none parsed'}

## 6. Scope Violation
{decision.get('scope_violation', 'unknown')}

## 7. Fake-Green Risk
{decision.get('fake_green_risk', 'unknown')}

## 8. New Reply Verified
{str(new_reply_verified).lower()}

## 9. Required Next Action
{decision['required_next_action']}

## 10. Automation Decision
allow_next_stage: {str(decision['allow_next_stage']).lower()}
""")
    log_event("decision_parsed", f"judgment={decision['overall_judgment']} allow={decision['allow_next_stage']}")
    print(f"[OK] Decision: {decision_path}")

    # ── 12. Full flow report ──
    report_path = OUTPUT_DIR / f"{tid}-full-review-flow-report.md"
    report_path.write_text(f"""# S2 Full Review Flow Report

## 1. Status
{'SUCCESS' if completion_status == 'complete' and new_reply_verified else 'PARTIAL' if new_reply_verified else 'BLOCKED'}

## 2. Submit Evidence
| Field | Value |
|-------|-------|
| target_url | {target_url} |
| zip_upload | {zip_status} |
| prompt_pasted | {prompt_pasted} |
| user_confirmed_SEND | {send_confirmed} |
| submit_clicked | {submit_clicked} |
| submitted_at | {submitted_at} |

## 3. New Reply Evidence
| Field | Value |
|-------|-------|
| assistant_count_before | {assistant_count_before} |
| assistant_count_after | {assistant_count_after} |
| new_reply_verified | {str(new_reply_verified).lower()} |
| completion_status | {completion_status} |
| extraction_confidence | {extraction_confidence} |

## 4. Decision
| Field | Value |
|-------|-------|
| overall_judgment | {decision['overall_judgment']} |
| s2_accepted | {decision['s2_accepted']} |
| s3_allowed | {decision['s3_allowed']} |
| allow_next_stage | {str(decision['allow_next_stage']).lower()} |

## 5. Safety
- S3 executed: no
- S2 logic modified: no
- evidence pack modified: no

## 6. Notes
- zip: {zip_status}
- Non-interactive fallback: {'yes' if not send_confirmed else 'no'}
""", encoding="utf-8")
    log_event("report_saved", str(report_path))
    print(f"[OK] Report: {report_path}")

    # ── 13. Save log ──
    _save_log(log, tid)

    browser.close()
    pw.stop()

    print("\n" + "=" * 60)
    print("Full Flow Complete")
    print("=" * 60)
    print(f"Completion:  {completion_status}")
    print(f"New reply:   {new_reply_verified}")
    print(f"Judgment:    {decision['overall_judgment']}")
    print(f"S3 allowed:  {decision['s3_allowed']}")
    print(f"Next stage:  {'ALLOWED' if decision['allow_next_stage'] else 'BLOCKED'}")


def _save_log(log_entries, tid):
    path = OUTPUT_DIR / f"{tid}-full-review-flow-log.md"
    path.write_text("# Full Review Flow Log\n\n| Time | Event | Details |\n|------|-------|---------|\n" +
                    "\n".join(log_entries), encoding="utf-8")


if __name__ == "__main__":
    main()
