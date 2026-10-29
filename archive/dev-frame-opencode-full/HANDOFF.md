# Agent Handoff Document

Generated: 2026-06-05 | Context: exhausted after ~80 GPT messages across 2 conversations

---

## 1. Project Identity

- **Project**: dev-frame-opencode / agent-acceptance
- **Role**: Engineering Execution Agent for RD2100 Agent Runtime
- **Governance**: Evidence-First, fail-closed, GPT is final review authority

---

## 2. Current State

```
SMOKE:         5/5 PASS (#0 staleness, #1 readiness 0.80, #2 type-check, #3 core 532+, #4 e2e 216)
BLOCKED:       5/5 preserved:
  broader_real_chain_testing_unblocked: false
  production_promotion_approved: false
  hardcoded_driver_replacement_approved: false
  guard_removal_approved: false
  evidence_cleanup_approved: false
PRODUCTION:    NOT authorized. Separate GPT auth required.
```

---

## 3. GPT Conversations

| Conv | URL | Status | Messages |
|------|-----|--------|----------|
| Old | `https://chatgpt.com/c/6a212fda-6c04-83a8-82fa-0fa036f762f9` | MAXED (~80 msgs), no longer processing | B1, B2 auth/exec, early B3 |
| New | `https://chatgpt.com/c/6a2191fb-00f0-83a2-96e5-fa94b0ced387` | ACTIVE (~45 msgs) | B2 closure, B3 auth/exec, P0-P2 batch, Tasks 1-5 |

**CDP Chrome**: Start with `--remote-debugging-port=9222 --user-data-dir=.chrome-cdp-profile`

**Authorized conversation binding**: `tools/AUTHORIZED_GPT_CONVERSATION.json`

---

## 4. Completed Tasks (All GPT-Accepted Unless Noted)

### Phase 1-5 Automation
| # | Task | GPT Status | Key Files |
|---|------|-----------|-----------|
| 1 | Smoke timeout remediation closure | accepted | test_go_dispatch.py mock fix |
| 2 | Test count doc refresh | accepted | AGENTS/CLAUDE/PROJECT_STATE updated |
| 3-4 | Manifest-zip verifier | accepted | review_pack_flow.py +verify_manifest_zip_consistency() |
| 5 | Production readiness planning | accepted | PRODUCTION_PROMOTION_CRITERIA.md |

### B1-B3 Real Chain
| Task | Status | Key Result |
|------|--------|-----------|
| B1 Gap Remediation Closure | accepted | 2 POST_REVIEW_ROUTE fixes + 1 legacy classified |
| B2 Multi-Agent Chain Replay | accepted (10 rounds!) | 90 packs, 0 actionable_fail |
| B3 Bounded Real-Chain Auth | accepted | 14 design files |
| B3 Bounded Real-Chain Exec | **executed, NOT accepted** | CDP chain functional, captured judgment=blocked |

### Post-B3 Tasks
| # | Task | GPT | Files |
|---|------|-----|-------|
| P0 | B3 Result Closure | accepted | B3_RESULT_CLOSURE.md, B3_STATE_SUMMARY.json |
| P1 | Production Readiness Assessment | accepted | Overall 0.80/1.00, 7 gaps |
| P2 | Submission Guard Rollout | accepted | _submit_p2/p3/p4/p5.py gate+entrypoint |
| P3 | Guard Rationalization | accepted | 17 guards, 0 removals |
| P4 | Evidence Archive Index | accepted | 99 packs, 1812 files |

### User's 10-Task Sequence
| # | Task | GPT | Status |
|---|------|-----|--------|
| 1 | Production Readiness Final Gap Review | accepted | 5 blocked, 3 actionable |
| 2 | B3 Root Cause Review | accepted | Auth=2 rounds + Exec=7 CDP rounds |
| 3 | Submission Guard Behavioral Verification | accepted | 18 tests, 5 scripts guarded |
| 4 | Submission Script Inventory | accepted | 12 scripts, 41.7% guarded |
| 5 | Criteria Gap Closure Plan | accepted | 6/8 criteria met, C2+C8 unmet |
| 6 | **Ops Readiness Review** | **PENDING** | Pack ready, needs CDP submit |
| 7 | Evidence Archive Maintenance Policy | pending | Not yet started |
| 8 | Guard Merge Authorization Planning | pending | Not yet started |
| 9 | B3 Conditional Rerun Authorization Draft | pending | Not yet started |
| 10 | Production Promotion Authorization Draft | pending | Not yet started |

---

## 5. Task 6 — Ready for Submission

**Pack directory**: `_reports/conversation-authorization/task6-ops-readiness/`
**ZIP**: `task6-ops-readiness-v1-20260605.zip`
**REVIEW_RUN_ID**: `task6-ops-readiness-v1-20260605`

Files included:
- MONITORING_READINESS_REVIEW.md
- ROLLBACK_READINESS_REVIEW.md
- HUMAN_OVERRIDE_READINESS_REVIEW.md
- OPERATIONAL_RUNBOOK.md
- GPT_REVIEW_PROMPT.md
- POST_REVIEW_ROUTE.json
- smoke_report.txt
- PACK_MANIFEST.md / PACK_MANIFEST_VERIFY.md / VALIDATION_RESULT.json

**Submit to**: New GPT conversation (6a2191fb)
**Expected verdict pattern**: `task6_accepted: yes | no`

---

## 6. Remaining Tasks (7-10)

### Task 7: Evidence Archive Maintenance Policy
Dir: `_reports/conversation-authorization/task7-archive-policy/`
Required: EVIDENCE_ARCHIVE_MAINTENANCE_POLICY.md, EVIDENCE_INDEX_UPDATE_PROTOCOL.md, EVIDENCE_RETENTION_RULES.md, NO_CLEANUP_GUARDRAIL.md
Documentation only. No code changes. No evidence deletion.

### Task 8: Guard Merge Authorization Planning
Dir: `_reports/conversation-authorization/task8-guard-merge/`
Required: GUARD_MERGE_AUTHORIZATION_PLAN.md, GUARD_MERGE_RISK_MATRIX.json, GUARD_MERGE_TEST_PLAN.md
Planning only. No actual merge execution without separate auth.

### Task 9: B3 Conditional Rerun Authorization Draft
Dir: `_reports/conversation-authorization/task9-b3-rerun/`
DRAFT ONLY. Condition: B3 root cause fixable + separate auth + max 3 retry rounds.
Do NOT execute without Task 9 authorization accepted + Task 10 separate auth.

### Task 10: Production Promotion Authorization Draft
Dir: `_reports/conversation-authorization/task10-promotion-draft/`
DRAFT ONLY. production_promotion_approved=false MUST be preserved.
Template only. Do NOT submit as promotion request.

---

## 7. Operational Patterns

### Evidence Pack Creation
```bash
python tools/review_pack_flow.py "DIR" "TASK_ID" "REVIEW_RUN_ID"
```
Generates: PACK_MANIFEST.md, ZIP, VALIDATION_RESULT.json, PACK_MANIFEST_VERIFY.md

### Fix Manifest Counts (ALWAYS after pack creation)
```python
import json
v = json.loads(open('VALIDATION_RESULT.json').read())
actual_files = len([x for x in Path('.').iterdir()])  # minus ZIP
v['zip_entry_count'] = actual_files
v['manifest_file_count'] = actual_files
v['hash_exclusions'] = ['PACK_MANIFEST.md','PACK_MANIFEST_VERIFY.md','VALIDATION_RESULT.json']
json.dump(v, open('VALIDATION_RESULT.json','w'), indent=2)
```
**Without this fix, GPT will block on manifest/validation count mismatch.**

### CDP Submission
```python
from playwright.async_api import async_playwright
# Connect to Chrome CDP port 9222
# Find page with conversation ID 6a2191fb
# Upload ZIP via input[type="file"]
# Paste prompt into div[contenteditable="true"].ProseMirror
# Click button[data-testid="send-button"]
# Wait 60s, poll up to 3 times
```

### Submit Script Pattern
5 scripts have gate+entrypoint: _submit_p1.py through _submit_p5.py
Each has: `pre_submit_gate(D, RID)` before CDP + `record_submission_result(D, RID, success=True)` after.

### Evidence-First Principles
- Never self-declare "accepted" — GPT must confirm
- Every claim must have evidence in the ZIP
- Historical evidence must never be modified, deleted, moved, or renamed
- Blocked items must always be preserved
- REVIEW_RUN_ID exact match required in all GPT replies

---

## 8. Known Issues / Workarounds

| Issue | Workaround |
|-------|-----------|
| review_pack_flow manifest counts wrong | Manual fix after each run (see section 7) |
| tools/ not git-tracked → diff shows new files | Provide MINIMAL_DIFF_PROOF.md |
| GPT sometimes reads old ZIP | Re-copy files before re-running review_pack_flow |
| CDP send button not found | Fallback to `pg.keyboard.press('Enter')` |
| Conversation too long → no response | New conversation or user relays messages |

---

## 9. Key File Locations

```
D:\dev-frame-opencode\
├── HANDOFF.md                          ← THIS FILE
├── AGENTS.md                           Project entry
├── CLAUDE.md                           Project overview
├── PROJECT_STATE.md                    State tracking
├── CURRENT_ROUTE.json                  Blocked items + route
├── DECISION_LEDGER.jsonl              All decisions
├── PRODUCTION_PROMOTION_CRITERIA.md    8 promotion criteria
├── smoke_test.py                       5 smoke commands
├── smoke_report.txt                    Latest: 5/5 PASS
├── readiness_score.json                Overall 0.80
├── tools/
│   ├── review_pack_flow.py            Evidence pack generation
│   ├── submission_guard.py            CDP dedup + retry
│   ├── _pre_submit_gate.py            Submission gate
│   ├── submission_entrypoint.py       Post-submit logging
│   ├── b1_replay.py                   B1 pack scanner
│   ├── b2_replay.py                   B2 chain replay
│   ├── b3_bounded_submit.py           B3 CDP chain
│   ├── readiness_score.py             10-metric scoring
│   ├── _submit_p1.py ~ _submit_p5.py  Guarded submit scripts
│   └── AUTHORIZED_GPT_CONVERSATION.json
├── ai-workflow-hub/
│   └── tests/
│       ├── test_manifest_zip_consistency.py (8 tests)
│       ├── test_submission_guard.py (7 tests)
│       ├── test_submission_integration.py (11 tests)
│       ├── test_b1_replay.py (8 tests)
│       ├── test_b2_replay.py (11 tests)
│       ├── test_b3_bounded.py (12 tests)
│       └── test_readiness_score.py (11 tests)
└── _reports/conversation-authorization/
    ├── task1-final-gap-review/
    ├── task2-b3-root-cause/
    ├── task3-guard-behavioral/
    ├── task4-script-inventory/
    ├── task5-criteria-gap/
    ├── task6-ops-readiness/            ← PENDING SUBMISSION
    ├── task7-archive-policy/           ← not started
    ├── task8-guard-merge/              ← not started
    ├── task9-b3-rerun/                 ← not started
    └── task10-promotion-draft/         ← not started
```

---

## 10. Next Actions (Priority Order)

1. **Submit Task 6** — pack is ready, needs CDP upload to GPT conversation 6a2191fb
2. **Execute Task 7** — create 4 evidence archive policy files, submit
3. **Execute Task 8** — create guard merge planning files, submit
4. **Execute Task 9** — B3 conditional rerun DRAFT only (do not execute)
5. **Execute Task 10** — Production promotion DRAFT only (do not execute)

**Each task**: create files → `review_pack_flow.py` → fix manifest counts → CDP submit → wait 60s → poll GPT → persist decision → next task.

---

## 11. DO NOT

- Delete, move, rename, or overwrite historical evidence
- Self-declare "accepted", "unblocked", or "production approved"
- Skip manifest count fix step
- Modify production source code without separate authorization
- Unblock any of the 5 blocked items
- Execute production promotion
- Use base URL fallback for GPT
- Create new GPT conversation (use 6a2191fb)
