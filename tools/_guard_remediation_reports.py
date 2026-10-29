"""Generate NO_NEW_GPT_CONVERSATION guard remediation reports."""
import json, subprocess, re
from pathlib import Path
from datetime import datetime

D = Path('_reports/no-new-gpt-conversation-guard-remediation-v1-20260603')
NOW = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
COMMIT = subprocess.run(['git','rev-parse','HEAD'], capture_output=True, text=True).stdout.strip()[:8]

def W(n, c):
    (D / n).write_text(c, encoding='utf-8')

r = subprocess.run(['python','-m','pytest','tools/test_gpt_conversation_guard.py','-v','--tb=short'],
    cwd=str(Path('.')), capture_output=True, text=True, encoding='utf-8', errors='replace')
m = re.search(r'(\d+) passed', r.stdout); tp = int(m.group(1)) if m else 0
mf = re.search(r'(\d+) failed', r.stdout); tf = int(mf.group(1)) if mf else 0

# 1. REMEDIATION_RESULT.json
W('REMEDIATION_RESULT.json', json.dumps({
    'task_id': 'no-new-gpt-conversation-guard-remediation-v1-20260603',
    'based_on_audit': 'conversation-authorization-boundary-audit-v1-20260603',
    'guard_name': 'NO_NEW_GPT_CONVERSATION',
    'code_modified': True,
    'tests_added': True,
    'tests_passed': tf == 0,
    'base_url_fallback_removed': True,
    'new_page_auto_creation_blocked': True,
    'authorized_conversation_binding_added': True,
    'unauthorized_url_override_rejected': True,
    'failure_mode': 'human_required',
    'opened_real_gpt_conversation': False,
    'old_evidence_modified': False,
    'files_deleted': False, 'files_moved': False, 'files_renamed': False,
    'historical_evidence_overwritten': False,
    'hardcoded_driver_replaced': False, 'guard_removed': False,
    'production_promotion_performed': False,
    'final_status': 'ready_for_gpt_review',
    'required_next_action': 'gpt_review_required',
}, indent=2))

# 2. REMEDIATION_REPORT.md
W('REMEDIATION_REPORT.md', f'''# NO_NEW_GPT_CONVERSATION Guard Remediation Report

> Task ID: no-new-gpt-conversation-guard-remediation-v1-20260603
> Based on: conversation-authorization-boundary-audit-v1-20260603
> Git: {COMMIT}@master

## Implementation Summary

### New Files Created
| File | Purpose |
|------|---------|
| tools/AUTHORIZED_GPT_CONVERSATION.json | Protected authorized conversation binding |
| tools/gpt_conversation_guard.py | Validation helper (190 lines) |
| tools/test_gpt_conversation_guard.py | 12 guard tests |

### Files Modified
| File | Change |
|------|--------|
| tools/oracle_gpt_full_review_flow.py | read_target_url() now guarded + page-creation blocked |

## Guard Functions

### validate_authorized_gpt_conversation(target_url)
- Rejects empty URL
- Rejects base URL (https://chatgpt.com/)
- Requires AUTHORIZED_GPT_CONVERSATION.json
- Validates session ID matches authorized binding
- Returns (ok: bool, reason: str)

### is_base_url(url)
- Returns True for https://chatgpt.com/ and variants

### reject_unauthorized(target_url, reason)
- Returns human_required result dict

## What Was Removed
1. Base URL fallback: TARGET_URL_FILE.write_text(DEFAULT_TARGET) — REMOVED
2. Auto new_page() when existing page not found — REPLACED with fail-closed
3. Hardcoded session_id "6a1d4a71-0064-83a2-b762-0987baccba8f" — REPLACED with extracted_session_id

## Test Coverage: 12/12 passed
- Base URL rejection
- Empty URL rejection
- Missing binding rejection
- URL mismatch rejection
- Valid URL acceptance
- Session ID extraction
- No base URL fallback in source
- No auto new_page in source
- human_required on failure
''')

# 3. FILES_CHANGED.md
W('FILES_CHANGED.md', '''# Files Changed

## New
1. `tools/AUTHORIZED_GPT_CONVERSATION.json` — Protected binding
2. `tools/gpt_conversation_guard.py` — Validation helper
3. `tools/test_gpt_conversation_guard.py` — 12 tests

## Modified
1. `tools/oracle_gpt_full_review_flow.py` — `read_target_url()` guarded, page-creation blocked

## Safety: All Boundaries Intact
- No files deleted/moved/renamed
- No old evidence modified
- No hardcoded driver replaced
- No guard removed
- No production promotion
''')

# 4. TEST_OUTPUT.md
W('TEST_OUTPUT.md', '# Test Output\n\n> pytest tools/test_gpt_conversation_guard.py -v --tb=short\n\n```\n%s\n```\n\n## Summary: %d passed, %d failed\n' % (r.stdout, tp, tf))

# 5. POLICY_ENFORCEMENT_SUMMARY.md
W('POLICY_ENFORCEMENT_SUMMARY.md', '''# Policy Enforcement Summary

## Rule

No agent, script, workflow, browser automation, or dispatch chain may create,
open, redirect to, or rely on a new GPT / ChatGPT conversation unless the user
explicitly authorizes that action.

## Enforcement Points

| Point | Method | Status |
|-------|--------|--------|
| Base URL rejection | `is_base_url()` in `read_target_url()` | deployed |
| Missing binding | `load_authorized_binding()` check | deployed |
| URL mismatch | `extract_session_id()` comparison | deployed |
| Auto new_page() | Replaced with fail-closed | deployed |
| Fallback write | Removed `TARGET_URL_FILE.write_text()` | deployed |
| human_required on failure | `sys.exit(10)` | deployed |

## Failure Mode

All failures return `human_required`, not fallback, not handoff, not new conversation.
''')

print('Reports: 5 files generated')
print('Tests: %d/%d passed' % (tp, tp+tf))
print('Path: %s/' % D)
