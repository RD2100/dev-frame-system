#!/usr/bin/env python3
"""
oracle_gpt_reply_monitor.py — Capture GPT reply from Chrome CDP session.

Connects to Chrome CDP, opens/reuses target ChatGPT conversation,
waits for GPT reply completion, extracts the latest assistant reply,
saves it, parses the decision, and generates a monitor log.

Usage:
  python tools/oracle_gpt_reply_monitor.py --task-id s2
  python tools/oracle_gpt_reply_monitor.py --task-id s2 --timeout 180 --poll-interval 3
"""

import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
TARGET_URL_FILE = ROOT / "_reports" / "browser-cdp-handoff" / "TARGET_CHATGPT_URL.txt"
OUTPUT_DIR = ROOT / "_reports" / "gpt-reviews"

VALID_DOMAINS = {"chatgpt.com", "chat.openai.com"}
CDP_PORTS = [9222, 9223, 9224, 9225]

sys.path.insert(0, str(ROOT / "tools"))
from gpt_conversation_guard import (
    extract_session_id,
    get_authorized_conversation_url,
    load_authorized_binding,
    reject_unauthorized,
    validate_authorized_gpt_conversation,
)


# ── Helpers ──────────────────────────────────────────────────────────

def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_target_url() -> tuple[str | None, str]:
    """Read the authorized GPT conversation binding. No base URL fallback."""
    binding = load_authorized_binding()
    raw = get_authorized_conversation_url(binding or {})
    if TARGET_URL_FILE.exists():
        legacy_url = TARGET_URL_FILE.read_text(encoding="utf-8").strip()
        if legacy_url and legacy_url != raw:
            print("[WARN] Deprecated TARGET_CHATGPT_URL.txt does not match authorized binding; ignoring legacy file.")
    if not raw:
        return None, "authorized_binding_missing_or_invalid"
    ok, reason = validate_authorized_gpt_conversation(raw)
    if not ok:
        return None, reason
    parsed = urlparse(raw)
    domain = parsed.hostname or ""
    base = ".".join(domain.split(".")[-2:]) if domain.count(".") >= 1 else domain
    if base not in VALID_DOMAINS:
        return None, f"invalid_domain: {base}"
    return raw, "valid"


def find_cdp() -> tuple[str | None, int | None]:
    """Returns (endpoint_url, port)."""
    for port in CDP_PORTS:
        url = f"http://127.0.0.1:{port}"
        try:
            req = urllib.request.Request(f"{url}/json/version")
            resp = urllib.request.urlopen(req, timeout=2)
            data = json.loads(resp.read())
            if "webSocketDebuggerUrl" in data:
                return url, port
        except Exception:
            continue
    return None, None


# ── Decision parsing ─────────────────────────────────────────────────

def parse_decision(reply_text: str) -> dict:
    """Parse GPT reply for structured decision fields."""
    text = reply_text.lower()
    decision = {
        "overall_judgment": "unknown",
        "s2_accepted": "unknown",
        "s3_allowed": "unknown",
        "blocking_reasons": [],
        "missing_evidence": [],
        "scope_violation": "unknown",
        "fake_green_risk": "unknown",
        "required_next_action": "unknown",
        "allow_next_stage": False,
    }

    # ── Overall judgment ──
    if "overall judgment: accepted" in text or "judgment: accepted" in text:
        decision["overall_judgment"] = "accepted"
    elif "overall judgment: rejected" in text or "judgment: rejected" in text:
        decision["overall_judgment"] = "rejected"
    elif "overall judgment: blocked" in text or "judgment: blocked" in text:
        decision["overall_judgment"] = "blocked"
    elif "overall judgment: human_required" in text or "judgment: human_required" in text:
        decision["overall_judgment"] = "human_required"
    elif "overall judgment" in text:
        # Has the field but unclear value
        decision["overall_judgment"] = "unknown"

    # ── S2 accepted ──
    if re.search(r"s2.accepted.*:\s*(true|yes)", text):
        decision["s2_accepted"] = "yes"
    elif re.search(r"s2.accepted.*:\s*(false|no)", text):
        decision["s2_accepted"] = "no"
    elif re.search(r"s2_accepted.*:\s*(yes|true)", text):
        decision["s2_accepted"] = "yes"
    elif re.search(r"s2_accepted.*:\s*(no|false)", text):
        decision["s2_accepted"] = "no"

    # ── S3 allowed ──
    if re.search(r"s3.allowed.*:\s*(true|yes)", text):
        decision["s3_allowed"] = "yes"
    elif re.search(r"s3.allowed.*:\s*(false|no)", text):
        decision["s3_allowed"] = "no"
    elif re.search(r"s3_allowed.*:\s*(yes|true)", text):
        decision["s3_allowed"] = "yes"
    elif re.search(r"s3_allowed.*:\s*(no|false)", text):
        decision["s3_allowed"] = "no"
    # Explicit phrases
    elif "s3 is not allowed" in text or "s3 not allowed" in text:
        decision["s3_allowed"] = "no"
    elif "s3 is allowed" in text or "s3 allowed" in text:
        decision["s3_allowed"] = "yes"

    # ── Blocking reasons ──
    for pattern in [r"reason[s]?\s*:\s*(.+?)(?:\n|$)", r"-\s*(conflicting_.+?)(?:\n|$)",
                     r"-\s*(evidence_.+?)(?:\n|$)", r"-\s*(forbidden_.+?)(?:\n|$)"]:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            reason = m.group(1).strip()
            if reason and reason not in decision["blocking_reasons"] and len(reason) > 5:
                decision["blocking_reasons"].append(reason)

    # ── Missing evidence ──
    if "missing evidence" in text or "evidence missing" in text or "evidence gap" in text:
        decision["missing_evidence"].append("missing evidence flagged by GPT")

    # ── Scope violation ──
    if "scope violation" in text or "scope clean" in text:
        decision["scope_violation"] = "yes" if "violation" in text else "no"
    else:
        decision["scope_violation"] = "unknown"

    # ── Fake-green risk ──
    if "fake-green" in text or "fake green" in text:
        decision["fake_green_risk"] = "yes"
    else:
        decision["fake_green_risk"] = "unknown"

    # ── Required next action ──
    if "s2" in text and "reconciliation" in text:
        decision["required_next_action"] = "s2_evidence_reconciliation_required"
    elif "human" in text and ("review" in text or "required" in text):
        decision["required_next_action"] = "human_review_required"
    elif "rerun" in text and "gpt" in text:
        decision["required_next_action"] = "rerun_gpt_review"
    elif decision["s3_allowed"] == "yes" and decision["overall_judgment"] == "accepted":
        decision["required_next_action"] = "proceed_to_s3_allowed"

    # ── allow_next_stage: only if explicitly accepted + S3 allowed ──
    if decision["overall_judgment"] == "accepted" and decision["s3_allowed"] == "yes":
        decision["allow_next_stage"] = True

    # Block keywords in DECISION section only (last 20% of text where conclusions live)
    conclusion_zone = text[int(len(text) * 0.8):] if len(text) > 100 else text
    for kw in ["blocked", "human_required", "not accepted", "rejected",
               "s3 is not allowed", "s3 not allowed", "cannot proceed",
               "do not proceed", "evidence insufficient", "missing evidence"]:
        if kw in conclusion_zone:
            # Only override if the overall judgment itself is explicitly blocked/rejected
            if decision["overall_judgment"] in ("blocked", "rejected", "human_required"):
                decision["allow_next_stage"] = False
                break

    return decision


# ── Decision report ──────────────────────────────────────────────────

def write_decision(decision: dict, path: Path):
    path.write_text(f"""# GPT Review Decision

## 1. Overall Judgment
{decision['overall_judgment']}

## 2. S2 Accepted
{decision['s2_accepted']}

## 3. S3 Allowed
{decision['s3_allowed']}

## 4. Blocking Reasons
{chr(10).join('- ' + r for r in decision['blocking_reasons']) if decision['blocking_reasons'] else 'none parsed'}

## 5. Missing Evidence
{chr(10).join('- ' + e for e in decision['missing_evidence']) if decision['missing_evidence'] else 'none parsed'}

## 6. Scope Violation
{decision['scope_violation']}

## 7. Fake-Green Risk
{decision['fake_green_risk']}

## 8. Required Next Action
{decision['required_next_action']}

## 9. Automation Decision
allow_next_stage: {decision['allow_next_stage']}
""", encoding="utf-8")


# ── Main monitor ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="GPT Reply Monitor — capture and parse GPT review")
    parser.add_argument("--task-id", default="s2", help="Task identifier")
    parser.add_argument("--timeout", type=int, default=180, help="Max wait seconds for reply")
    parser.add_argument("--poll-interval", type=int, default=3, help="Polling interval seconds")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log_lines = []
    task_id = args.task_id

    def log(event: str, details: str = ""):
        entry = f"| {ts()} | {event} | {details} |"
        log_lines.append(entry)
        print(f"  [{event}] {details}")

    print("=" * 60)
    print(f"GPT Reply Monitor — {task_id}")
    print("=" * 60)

    # ── 1. Resolve target URL ──
    target_url, url_status = read_target_url()
    if url_status != "valid":
        print(f"\nBLOCKED_INVALID_TARGET_URL: {url_status}")
        log("error", f"invalid target URL: {url_status}")
        result = reject_unauthorized(target_url or "", url_status)
        (OUTPUT_DIR / f"{task_id}-cdp-monitor-status.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8")
        log_lines.append(f"| {ts()} | result | BLOCKED_INVALID_TARGET_URL |")
        (OUTPUT_DIR / f"{task_id}-gpt-review-monitor-log.md").write_text(
            "# GPT Review Monitor Log\n\n" + "\n".join(log_lines), encoding="utf-8")
        sys.exit(1)

    log("target_url", target_url)
    print(f"[OK] Target URL: {target_url}")

    # ── 2. Connect CDP ──
    cdp_url, cdp_port = find_cdp()
    if not cdp_url:
        print("\nBLOCKED_CDP_NOT_AVAILABLE")
        log("error", "no CDP endpoint available")
        (OUTPUT_DIR / f"{task_id}-gpt-review-monitor-log.md").write_text(
            "# GPT Review Monitor Log\n\n" + "\n".join(log_lines), encoding="utf-8")
        sys.exit(1)

    log("cdp_connected", f"{cdp_url} (port {cdp_port})")
    print(f"[OK] CDP: {cdp_url}")

    # ── 3. Open/reuse target page ──
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(cdp_url)
    session_id = extract_session_id(target_url)
    if not session_id:
        print("\nBLOCKED_NO_NEW_GPT_CONVERSATION: cannot extract session_id from target URL")
        log("error", "cannot extract session_id")
        result = reject_unauthorized(target_url, "cannot_extract_session_id")
        (OUTPUT_DIR / f"{task_id}-cdp-monitor-status.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8")
        browser.close()
        pw.stop()
        sys.exit(10)

    page = None
    page_reused = False
    for ctx in browser.contexts:
        for p in ctx.pages:
            if session_id in p.url:
                page = p
                page_reused = True
                log("page_reused", p.url[:100])
                break
        if page:
            break

    if not page:
        print("\nBLOCKED_NO_NEW_GPT_CONVERSATION: authorized conversation page not found")
        log("error", "authorized_conversation_page_not_found")
        result = reject_unauthorized(target_url, "authorized_conversation_page_not_found")
        (OUTPUT_DIR / f"{task_id}-cdp-monitor-status.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8")
        (OUTPUT_DIR / f"{task_id}-gpt-review-monitor-log.md").write_text(
            "# GPT Review Monitor Log\n\n" + "\n".join(log_lines), encoding="utf-8")
        browser.close()
        pw.stop()
        sys.exit(10)
    print(f"[OK] Page: {page.url[:100]} ({'reused' if page_reused else 'new'})")

    # ── 4. Wait for GPT reply completion ──
    print(f"[INFO] Waiting for GPT reply (timeout={args.timeout}s, poll={args.poll_interval}s)...")
    deadline = time.time() + args.timeout
    last_text = ""
    stable_count = 0
    completion_status = "timeout"
    extraction_confidence = "low"

    while time.time() < deadline:
        time.sleep(args.poll_interval)
        elapsed = int(time.time() - (deadline - args.timeout))

        # Check stop button
        stop_btn = page.query_selector('button[data-testid="stop-button"]')
        still_generating = stop_btn is not None

        # Try to extract latest assistant reply
        assistant_msgs = page.query_selector_all('[data-message-author-role="assistant"]')
        if assistant_msgs:
            current = assistant_msgs[-1].inner_text()
            if current == last_text:
                stable_count += 1
            else:
                stable_count = 0
                last_text = current

            if not still_generating and stable_count >= 3 and len(current) > 200:
                completion_status = "complete"
                extraction_confidence = "high"
                log("reply_complete", f"{len(current)} chars, stable for {stable_count * args.poll_interval}s")
                break
            elif stable_count >= 6 and len(current) > 200:
                completion_status = "complete"
                extraction_confidence = "medium"
                log("reply_complete_stable", f"{len(current)} chars (still-generating={still_generating})")
                break

        if not still_generating and not assistant_msgs:
            # No assistant messages at all
            log("poll", f"no assistant message yet (t+{elapsed}s)")

    if completion_status == "timeout":
        log("timeout", f"no complete reply within {args.timeout}s")
        print(f"[WARN] Timeout after {args.timeout}s")

    # ── 5. Extract ──
    reply_text = ""
    assistant_msgs = page.query_selector_all('[data-message-author-role="assistant"]')
    if assistant_msgs:
        reply_text = assistant_msgs[-1].inner_text()
        extraction_confidence = "high" if completion_status == "complete" else "medium"

    if not reply_text:
        # Fallback: try to distinguish user vs assistant content
        # Look for turn markers or copy buttons near assistant messages
        main = page.query_selector("main")
        if main:
            # Try to get only the last message block (newest content)
            # ChatGPT uses article or div wrappers for each message
            articles = page.query_selector_all("article")
            if articles:
                # Last article is usually the most recent message
                reply_text = articles[-1].inner_text()
                # Check if it's likely a user message (starts with prompt-like text)
                if reply_text and len(reply_text) > 100:
                    extraction_confidence = "medium"
                    # Try to find assistant-specific markers
                    assistant_msgs_retry = articles[-1].query_selector_all('[data-message-author-role="assistant"]')
                    if not assistant_msgs_retry:
                        # Could be user message — try second-to-last
                        if len(articles) >= 2:
                            reply_text = articles[-2].inner_text()
                            extraction_confidence = "low"
                else:
                    extraction_confidence = "low"
            else:
                reply_text = main.inner_text()
                extraction_confidence = "low"
            log("extraction_fallback", f"main/article area, {len(reply_text)} chars")

    if not reply_text:
        print("\nBLOCKED_NO_ASSISTANT_MESSAGE")
        log("error", "no assistant message found")
        decision = parse_decision("")
        write_decision(decision, OUTPUT_DIR / f"{task_id}-gpt-review-decision.md")
        (OUTPUT_DIR / f"{task_id}-gpt-review-monitor-log.md").write_text(
            "# GPT Review Monitor Log\n\n" + "\n".join(log_lines), encoding="utf-8")
        pw.stop()
        sys.exit(0)

    # ── 5b. Validate extracted content is a GPT reply, not user prompt ──
    # Strong GPT markers: structured review fields with colons
    strong_gpt_markers = ["overall judgment:", "gate-by-gate review", "evidence sufficiency:",
                          "s2 accepted:", "s3 allowed:", "decision:", "missing evidence:",
                          "scope violation check:", "fake-green risk:", "recommended next",
                          "s2 review result", "conflicts", "blocked_by"]
    # User prompt markers: appear in the first 300 chars
    user_markers = ["你是 dev frame opencode", "当前任务", "frozen taskspec",
                    "hard rules", "不执行 s3", "不修改 s2", "你是本项目的",
                    "请基于", "请逐项", "请输出", "现在开始执行"]

    gpt_score = sum(1 for m in strong_gpt_markers if m in reply_text.lower())
    user_score = sum(1 for m in user_markers if m in reply_text.lower()[:300])

    is_gpt = gpt_score >= 3
    is_user = user_score >= 2

    if is_user and not is_gpt:
        log("extraction_warning", f"user prompt detected (score={user_score}), gpt_score={gpt_score}, scanning for GPT reply")
        # ChatGPT uses [data-message-author-role="assistant"] not <article>
        assistant_msgs = page.query_selector_all('[data-message-author-role="assistant"]')
        found_gpt = None
        # Scan from newest to oldest
        for el in reversed(assistant_msgs):
            text = el.inner_text()
            el_gpt_score = sum(1 for m in strong_gpt_markers if m in text.lower())
            if el_gpt_score >= 3:
                found_gpt = text
                log("assistant_scan", f"GPT reply found, score={el_gpt_score}, {len(text)} chars")
                break

        if found_gpt:
            reply_text = found_gpt
            extraction_confidence = "medium"
            log("extraction_corrected", f"found GPT reply at position in {len(assistant_msgs)} messages")
        else:
            # Check if any assistant message exists at all
            if assistant_msgs:
                # Use newest assistant message anyway
                reply_text = assistant_msgs[-1].inner_text()
                extraction_confidence = "low"
                log("extraction_fallback", f"using last of {len(assistant_msgs)} assistant msgs, {len(reply_text)} chars")
            else:
                extraction_confidence = "low"
                log("extraction_warning", "no assistant messages found at all")

    log("reply_extracted", f"{len(reply_text)} chars, confidence={extraction_confidence}")
    print(f"[OK] Reply: {len(reply_text)} chars, confidence={extraction_confidence}")

    # ── 6. Save result ──
    result_path = OUTPUT_DIR / f"{task_id}-gpt-review-result.md"
    result_path.write_text(f"""---
task_id: {task_id}
source: chatgpt_browser_cdp
captured_at: {ts()}
target_url: {target_url}
completion_status: {completion_status}
extraction_confidence: {extraction_confidence}
cdp_endpoint: {cdp_url}
---

{reply_text}
""", encoding="utf-8")
    log("result_saved", str(result_path))
    print(f"[OK] Result: {result_path}")

    # ── 7. Parse decision ──
    decision = parse_decision(reply_text)
    decision_path = OUTPUT_DIR / f"{task_id}-gpt-review-decision.md"
    write_decision(decision, decision_path)
    log("decision_parsed", f"judgment={decision['overall_judgment']}, s3={decision['s3_allowed']}, next={decision['allow_next_stage']}")
    print(f"[OK] Decision: {decision_path}")
    print(f"     Judgment: {decision['overall_judgment']}")
    print(f"     S3 allowed: {decision['s3_allowed']}")
    print(f"     allow_next_stage: {decision['allow_next_stage']}")

    # ── 8. Monitor log ──
    log_path = OUTPUT_DIR / f"{task_id}-gpt-review-monitor-log.md"
    log_path.write_text("# GPT Review Monitor Log\n\n| Time | Event | Details |\n|------|-------|---------|\n" +
                        "\n".join(log_lines), encoding="utf-8")
    log("monitor_log_saved", str(log_path))
    print(f"[OK] Log: {log_path}")

    browser.close()
    pw.stop()

    # ── Summary ──
    print("\n" + "=" * 60)
    print("Monitor Complete")
    print("=" * 60)
    print(f"Completion: {completion_status}")
    print(f"Confidence: {extraction_confidence}")
    print(f"Judgment:  {decision['overall_judgment']}")
    print(f"S3 allowed: {decision['s3_allowed']}")
    print(f"Next stage: {'ALLOWED' if decision['allow_next_stage'] else 'BLOCKED'}")


if __name__ == "__main__":
    main()
