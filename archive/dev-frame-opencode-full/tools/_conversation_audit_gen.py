"""Generate conversation authorization boundary audit reports."""
import json
from pathlib import Path
from datetime import datetime

D = Path('_reports/conversation-authorization-boundary-audit-v1-20260603')
NOW = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')

def W(n, c):
    (D / n).write_text(c, encoding='utf-8')

# 1. CONVERSATION_AUTHORIZATION_AUDIT_RESULT.json
W('CONVERSATION_AUTHORIZATION_AUDIT_RESULT.json', json.dumps({
    'task_id': 'conversation-authorization-boundary-audit-v1-20260603',
    'audit_type': 'conversation_authorization_boundary',
    'read_only_audit': True,
    'code_modified': False,
    'old_evidence_modified': False,
    'files_deleted': False, 'files_moved': False, 'files_renamed': False,
    'historical_evidence_overwritten': False,
    'new_gpt_conversation_trigger_found': True,
    'new_gpt_conversation_trigger_type': 'code',
    'original_conversation_binding_exists': False,
    'explicit_user_authorization_required': True,
    'current_behavior_safe': False,
    'guard_required': True,
    'recommended_final_status': 'fail_closed',
    'required_next_action': 'add_no_new_gpt_conversation_guard',
}, indent=2))

# 2. CONVERSATION_AUTHORIZATION_AUDIT_REPORT.md
report = '''# Conversation Authorization Boundary Audit Report

> Task ID: conversation-authorization-boundary-audit-v1-20260603
> Audit Type: conversation_authorization_boundary
> Verdict: FAIL_CLOSED -- guard required

## Root Cause

The workflow creates new GPT conversations through **code behavior + mutable configuration**.

### Trigger Chain

1. **TARGET_CHATGPT_URL.txt** is the sole binding to the GPT conversation.
2. Currently contains: `https://chatgpt.com/` (base URL, NO session ID).
3. ChatGPT base URL creates a **new conversation** every time it is navigated to.

### Trigger Path (code)

In `tools/oracle_gpt_full_review_flow.py` (lines 136-149):
- Hardcoded session_id `6a1d4a71-0064-83a2-b762-0987baccba8f` is used to find existing pages
- If no matching page found, `ctx.new_page()` creates a new page
- `page.goto(target_url)` navigates to whatever TARGET_CHATGPT_URL.txt contains
- If target_url is base URL (`https://chatgpt.com/`), a NEW conversation is created

### Affected Scripts (all share this pattern)

| Script | Weakness |
|--------|----------|
| oracle_gpt_full_review_flow.py | Hardcoded session_id, creates new page, reads mutable URL |
| oracle_gpt_reply_monitor.py | Same session_id + new_page() pattern |
| oracle_gpt_review_loop_once.py | Same pattern |
| _v4_gpt_submit.py | Fallback to base URL |
| _v5_gpt_submit.py | Fallback to base URL |
| _v4_gpt_auto_submit.py | Fallback to base URL |

### No Original Conversation Binding

- TARGET_CHATGPT_URL.txt is unprotected, mutable text
- session_id is hardcoded, not configurable
- If session mismatch, new page created automatically
- No authorized conversation record exists

### Previously Documented in _execution_audit.py

- `"new_gpt_page_opened": True`
- `"new_page_purpose": "formal_review_retry_after_timeout"`
- Known but accepted as operational practice, not treated as authorization violation.

## Investigation Answers

| # | Question | Answer |
|---|----------|--------|
| 1 | Code that opens new GPT conversation? | YES: oracle_gpt_full_review_flow.py lines 144-147 |
| 2 | Browser automation related to GPT? | YES: Playwright CDP + page.goto() |
| 3 | GPT review = start new conversation? | YES when target URL is base URL |
| 4 | Current GPT conversation ID represented? | PARTIAL: only in mutable TARGET_CHATGPT_URL.txt |
| 5 | How does workflow know where to return? | It does not: target URL can change anytime |
| 6 | @Go distinguish authorized vs new? | NO: no conversation binding mechanism |
| 7 | OpenCode send results directly to GPT? | NO: uses CDP/Playwright independently |
| 8 | Codex/Claude call GPT as reviewer? | NO: GPT interaction is via CDP, not agent dispatch |
| 9 | Fallback creates new conversation? | YES: base URL fallback = new conversation |
| 10 | Caused by code, prompt, or habit? | CODE + OPERATIONAL PRACTICE |
| 11 | Guarded Steady State Freeze cover this? | NO |
| 12 | What new guard is required? | See REQUIRED_GUARD_PROPOSAL.md |
'''
W('CONVERSATION_AUTHORIZATION_AUDIT_REPORT.md', report)

# 3. SUSPECTED_TRIGGER_PATHS.md
W('SUSPECTED_TRIGGER_PATHS.md', '''# Suspected Trigger Paths

## Path 1: TARGET_CHATGPT_URL.txt Overwrite (PRIMARY)
- File: `_reports/browser-cdp-handoff/TARGET_CHATGPT_URL.txt`
- Current: `https://chatgpt.com/`
- Effect: Navigation creates NEW conversation

## Path 2: Hardcoded session_id Mismatch
- File: `oracle_gpt_full_review_flow.py` line 136
- Value: `6a1d4a71-0064-83a2-b762-0987baccba8f`
- Effect: No match = new page created

## Path 3: Default Target Fallback
- File: `oracle_gpt_full_review_flow.py` lines 53-56
- Writes DEFAULT_TARGET if file missing/invalid

## Path 4: Base URL Fallback in Submit Scripts
- Files: `_v4_gpt_submit.py`, `_v5_gpt_submit.py`, `_v4_gpt_auto_submit.py`
- `go_url = target_url or "https://chatgpt.com/"`

## Path 5: Explicit new_page() in Remediation
- Agent code: `browser.contexts[0].new_page()` + `page.goto(base_url)`
- Used to bypass overloaded session
''')

# 4. REQUIRED_GUARD_PROPOSAL.md
W('REQUIRED_GUARD_PROPOSAL.md', '''# Required Guard Proposal

## Guard: NO_NEW_GPT_CONVERSATION

### Implementation

1. Immutable TARGET_CHATGPT_URL.txt: no agent may overwrite without user authorization
2. Fail-closed on new conversation: verify target URL before page.goto()
3. Remove all base URL fallbacks: replace with human_required
4. AUTHORIZED_GPT_CONVERSATION.json: protected binding record
5. Audit log: every submission logs target_url, session_id, page_reused vs page_created

### Code Changes

| File | Change |
|------|--------|
| oracle_gpt_full_review_flow.py | Authorized-only read_target_url() |
| oracle_gpt_reply_monitor.py | Same |
| oracle_chatgpt_cdp_handoff.py | Remove --url override |
| _v4_gpt_submit.py | Remove base URL fallback |
| _v5_gpt_submit.py | Remove base URL fallback |
| _v4_gpt_auto_submit.py | Remove base URL fallback |

### Break-Glass

User explicitly authorizes new conversation via AUTHORIZED_GPT_CONVERSATION.json.
No automated creation under any other circumstances.
''')

# 5. NO_NEW_GPT_CONVERSATION_POLICY.md
W('NO_NEW_GPT_CONVERSATION_POLICY.md', '''# NO_NEW_GPT_CONVERSATION Policy

> Status: PROPOSED (requires GPT review before enforcement)

## Rule

No agent, script, workflow, browser automation, or dispatch chain may create,
open, redirect to, or rely on a new GPT / ChatGPT conversation unless the user
explicitly authorizes that action.

The current GPT conversation is the ONLY authorized GPT review context.
If the workflow cannot return to the current conversation, stop with
final_status = human_required.

## Prohibited

1. Writing base URL to TARGET_CHATGPT_URL.txt
2. page.goto() to unauthorized URL
3. new_page() + navigate without authorization
4. Base URL fallback when file missing
5. Creating new conversation because original is overloaded

## Required on Failure

If original conversation unreachable:
1. Stop: final_status = human_required
2. Record: CDP_SUBMISSION_STATUS = not_submitted
3. Do NOT create new conversation
4. Wait for user to provide new authorized URL

## Enforcement

- Pre-submit: verify target URL matches authorized binding
- Post-submit: verify no unauthorized page_created events
- Governance: any new conversation = human_required
''')

print('Audit complete: 5 files generated')
print('Verdict: FAIL_CLOSED -- guard required')
print('Path:', D.resolve())
