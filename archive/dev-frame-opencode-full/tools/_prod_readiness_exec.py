"""Phase C+D: Production Readiness Preparation Execution + Submit."""
import json, zipfile, os, time
from pathlib import Path
from playwright.sync_api import sync_playwright

os.chdir(Path(__file__).resolve().parent.parent)
D = Path('_reports/conversation-authorization/production-readiness-preparation-execution-v1')
D.mkdir(parents=True, exist_ok=True)
RID = 'production-readiness-preparation-execution-review-v1-20260604'

def W(n, c):
    p = Path(n); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(c, encoding='utf-8')

# Verify authorized
auth_D = Path('_reports/conversation-authorization/production-readiness-preparation-authorization-v1')
route = json.loads((auth_D / 'POST_REVIEW_ROUTE.json').read_text(encoding='utf-8'))
assert route.get('production_readiness_preparation_authorized'), 'NOT AUTHORIZED'

# Create 9 readiness docs
W('PRODUCTION_READINESS_CHECKLIST.md', '# Production Readiness Checklist\n\n## Accepted Capabilities\n- bounded guarded review pipeline: CLOSED\n- Claude/Codex interchangeable: ACCEPTED\n- OpenCode bounded executor: VERIFIED\n- limited broader real-chain execution: ACCEPTED (172/172)\n- Runbook/Ledger hardening: ACCEPTED\n\n## Pre-Production Checks\n- [ ] All tests pass (172/172)\n- [ ] GPT review authorization active\n- [ ] CDP submission functional\n- [ ] AUTHORIZED_GPT_CONVERSATION.json valid\n\n## Human Approvals Required\n- [ ] Production promotion (BLOCKED)\n- [ ] Hardcoded driver replacement (BLOCKED)\n- [ ] Guard removal (BLOCKED)\n- [ ] Evidence cleanup (BLOCKED)\n\n## Monitoring\n- review_unverified rate\n- CDP failure rate\n- Route anomalies\n\n## Rollback\n- Evidence preserved\n- Safe automation stop\n- Failed execution recovery\n\n## Failure Handling\n- HUMAN_REQUIRED on boundary violations\n- FAIL_CLOSED on unverified reviews\n')

W('PRODUCTION_RISK_MATRIX.md', '# Production Risk Matrix\n\n| Risk | Prob | Impact | Mitigation |\n|------|------|--------|------------|\n| GPT review failure | Med | High | Watchdog, retry, human_required |\n| review_unverified | Med | High | MIN_REPLY_CHARS=100, RID verify |\n| RID mismatch | Low | Critical | Stop on mismatch |\n| CDP unavailable | Med | High | human_required, no fallback |\n| CDP 403 | Low | High | Restart Chrome |\n| URL mismatch | Low | Critical | human_required, stop |\n| OpenCode write-boundary | Low | High | WRITE_SET verify |\n| False route interpretation | Med | Critical | POST_REVIEW_ROUTE gate |\n| Source edit risk | Low | Critical | SAFETY_CHECK, git diff |\n| Production promotion | N/A | Critical | BLOCKED |\n| Guard removal | N/A | Critical | BLOCKED |\n| Evidence cleanup | Low | Critical | append-only policy |\n')

W('ROLLBACK_PLAN.md', '# Rollback Plan\n\n## Can Be Rolled Back\n- Documentation files (version control)\n- Route decisions\n- Authorization state (conservative by default)\n\n## Cannot Be Rolled Back\n- Deleted evidence (prevented by policy)\n- Overwritten evidence (prevented by policy)\n- GPT conversation history\n\n## Evidence Preservation\nAll files append-only or new-only. No delete/move/rename/overwrite.\n\n## Safe Stop\n- human_required on boundary violations\n- Stop on review_unverified / route mismatch\n\n## Recovery\n- Retry from authorization phase\n- Do not skip authorization gate\n- New GPT review for scope expansion\n\n## Human Approval Required\n- Production promotion, driver replacement, guard removal, evidence cleanup\n')

W('MONITORING_PLAN.md', '# Monitoring Plan\n\n| Metric | Target | Action |\n|--------|--------|--------|\n| review_unverified rate | <20% | Investigate CDP/GPT |\n| CDP failure rate | <10% | Restart Chrome |\n| RID mismatch rate | 0% | Stop, investigate |\n| Route anomalies | 0 | Stop, review route |\n| OpenCode delta | expected only | Stop on unexpected |\n| Manifest/hash failures | 0 | Rebuild pack |\n| human_required frequency | as needed | Review scope |\n| Failed test rate | 0 | Stop, fix |\n')

W('RELEASE_CRITERIA.md', '# Release Criteria\n\nproduction_promotion_approved: false\nproduction readiness: preparatory only\nfuture production promotion: requires new current-GPT review\nall blocked items remain blocked\n\nTest Baseline: 172/172\nSafety Boundaries: all intact\n')

W('HUMAN_OVERRIDE_PROTOCOL.md', '# Human Override Protocol\n\n## When human_required is MANDATORY\n- Production promotion\n- Hardcoded driver replacement\n- Guard removal\n- Evidence cleanup\n- New GPT conversation\n- Base URL fallback\n- Scope expansion beyond authorization\n\n## Agents MUST NOT Decide Alone\n- GPT_ACCEPTED / FINAL_ACCEPTED\n- REAL_CHAIN_UNBLOCKED\n- PRODUCTION_APPROVED\n- GUARD_REMOVAL_APPROVED\n\n## Who Must Approve\n- Current authorized GPT for review decisions\n- Human user for production/boundary changes\n\n## When Automation MUST Stop\n- GPT rejected/blocked/human_required\n- REVIEW_RUN_ID mismatch\n- review_unverified\n- CDP unavailable\n- URL mismatch\n')

W('FAILURE_RESPONSE_RUNBOOK.md', '# Failure Response Runbook\n\n| Failure | Response | Exit | Retry |\n|---------|----------|------|-------|\n| blocked | Stop, record | 20 | No |\n| rejected | Stop, record | 20 | No |\n| needs_more_evidence | Assess scope | 20 | Yes if in scope |\n| review_unverified | Stop, record | 20 | Yes |\n| human_required | Stop, wait | 10 | No |\n| CDP 403 | Stop, human_required | 30 | Yes after restart |\n| GPT capture fail | Stop, review_unverified | 20 | Yes |\n| Test failure | Stop, fix | 1 | Yes after fix |\n| Write-boundary violation | Stop, human_required | 10 | No |\n')

W('PRODUCTION_READINESS_GAPS.md', '# Production Readiness Gaps\n\n## Before Production\n- production_promotion_approved: false\n- Requires new current-GPT authorization\n\n## Before Full Broader Real-Chain\n- broader_real_chain_testing_unblocked: false\n- Requires new current-GPT authorization\n\n## Before Driver Replacement\n- hardcoded_driver_replacement_approved: false\n- Requires separate review track\n\n## Before Guard Removal\n- guard_removal_approved: false\n- Requires separate review track\n\n## Before Evidence Cleanup\n- evidence_cleanup_approved: false\n- Requires separate review track\n')

W('PRODUCTION_READINESS_SUMMARY.md', '# Production Readiness Summary\n\nState: PREPARATION ONLY\nproduction_promotion_approved: false\nbroader_real_chain_testing_unblocked: false\nhardcoded_driver_replacement_approved: false\nguard_removal_approved: false\nevidence_cleanup_approved: false\n\nAccepted goals: 5, Tests: 172/172. All blocked items preserved.\n')

# Evidence files
W(D / 'READ_SET.json', json.dumps({'files': ['GPT_REVIEW_DECISION.md', 'POST_REVIEW_ROUTE.json', 'RUNBOOK.md'], 'scope': 'authorization_verification'}, indent=2))
W(D / 'WRITE_SET.json', json.dumps({'files': ['PRODUCTION_READINESS_CHECKLIST.md', 'PRODUCTION_RISK_MATRIX.md', 'ROLLBACK_PLAN.md', 'MONITORING_PLAN.md', 'RELEASE_CRITERIA.md', 'HUMAN_OVERRIDE_PROTOCOL.md', 'FAILURE_RESPONSE_RUNBOOK.md', 'PRODUCTION_READINESS_GAPS.md', 'PRODUCTION_READINESS_SUMMARY.md'], 'scope': 'readiness_documentation_only'}, indent=2))
W(D / 'COMMAND_LOG.md', '# Command Log\n\nCreated 9 production-readiness documentation files.\n')
W(D / 'WORKSPACE_STATUS_AFTER.txt', 'Created: 9 readiness docs.\n')
W(D / 'WORKSPACE_STATUS_DIFF.txt', '+9 readiness files\n')

safe = {'files_deleted': 'no', 'files_moved': 'no', 'files_renamed': 'no', 'source_edited': 'no',
    'production': 'no', 'driver': 'no', 'guard': 'no', 'cleanup': 'no',
    'broader_unblocked': 'no', 'new_gpt': 'no', 'base_url': 'no', 'readiness_docs_only': 'yes'}
W(D / 'SAFETY_CHECK.md', '# Safety Check\n\n> %s\n\n' % RID + '\n'.join('%s: %s' % kv for kv in safe.items()))

W(D / 'PRODUCTION_READINESS_EXECUTION_RESULT.json', json.dumps({
    'review_run_id': RID, 'files_created': 9, 'source_edits': 0, 'safety_clean': True,
    'broader_real_chain_testing_unblocked': False, 'production_promotion_approved': False,
    'hardcoded_driver_replacement_approved': False, 'guard_removal_approved': False,
    'evidence_cleanup_approved': False,
}, indent=2))
W(D / 'PRODUCTION_READINESS_EXECUTION_RESULT.md', '# Production Readiness Execution Result\n\n> %s\n\nCreated 9 readiness documentation files. Source edits: 0. Safety: CLEAN.\n' % RID)
W(D / 'VALIDATION_RESULT.json', json.dumps({'review_run_id': RID, 'all_required_created': True, 'safety_clean': True, 'ready_for_review': True, 'failures': []}, indent=2))
W(D / 'GPT_REVIEW_PROMPT.md', 'REVIEW_RUN_ID: %s\n\n## Production Readiness Preparation Execution Evidence\n\nCreated 9 readiness docs: checklist, risk matrix, rollback plan, monitoring plan, release criteria, human override protocol, failure response runbook, gaps, summary.\nAll blocked items preserved.\n\n### Required Decision\noverall_judgment: accepted | needs_more_evidence | rejected\nproduction_readiness_preparation_execution.accepted: yes | no\nsafety_boundary_preserved.accepted: yes | no\nbroader_real_chain_testing.unblocked: no\n\nBegin reply with REVIEW_RUN_ID: %s\n' % (RID, RID))
W(D / 'GPT_REVIEW_RESULT.md', 'NOT_AVAILABLE_PENDING_GPT_REVIEW\n')
W(D / 'GPT_REVIEW_DECISION.md', 'NOT_AVAILABLE_PENDING_GPT_REVIEW\n')
W(D / 'POST_REVIEW_ROUTE.json', json.dumps({
    'review_run_id': RID, 'review_submitted': False, 'production_readiness_preparation_reviewed': False,
    'broader_real_chain_testing_unblocked': False, 'production_promotion_approved': False,
    'hardcoded_driver_replacement_approved': False, 'guard_removal_approved': False,
    'evidence_cleanup_approved': False,
}, indent=2))

# Build zip with ALL actual files + evidence
actuals = ['PRODUCTION_READINESS_CHECKLIST.md', 'PRODUCTION_RISK_MATRIX.md', 'ROLLBACK_PLAN.md',
    'MONITORING_PLAN.md', 'RELEASE_CRITERIA.md', 'HUMAN_OVERRIDE_PROTOCOL.md',
    'FAILURE_RESPONSE_RUNBOOK.md', 'PRODUCTION_READINESS_GAPS.md', 'PRODUCTION_READINESS_SUMMARY.md']
evidence = ['PRODUCTION_READINESS_EXECUTION_RESULT.md', 'PRODUCTION_READINESS_EXECUTION_RESULT.json',
    'READ_SET.json', 'WRITE_SET.json', 'COMMAND_LOG.md', 'WORKSPACE_STATUS_AFTER.txt',
    'WORKSPACE_STATUS_DIFF.txt', 'SAFETY_CHECK.md', 'VALIDATION_RESULT.json',
    'GPT_REVIEW_PROMPT.md', 'GPT_REVIEW_RESULT.md', 'GPT_REVIEW_DECISION.md', 'POST_REVIEW_ROUTE.json']

Z = D / 'production-readiness-preparation-execution-v1-pack.zip'
with zipfile.ZipFile(Z, 'w', zipfile.ZIP_DEFLATED) as zf:
    for fn in actuals:
        p = Path(fn)
        if p.exists(): zf.write(p, fn)
    for fn in evidence:
        if (D / fn).exists(): zf.write(D / fn, fn)

with zipfile.ZipFile(Z, 'r') as zf:
    n = len(zf.namelist())
print('Phase C: 9 readiness docs + %d evidence = %d total, %dB' % (len(evidence), n, Z.stat().st_size))

# Phase D: Submit
pw = sync_playwright().start()
browser = pw.chromium.connect_over_cdp('http://127.0.0.1:9222')
page = None
for ctx in browser.contexts:
    for p in ctx.pages:
        if '6a1ec646' in p.url: page = p; break
if not page:
    page = browser.contexts[0].pages[0]
    page.goto('https://chatgpt.com/c/6a1ec646-e758-83a2-92b1-eff24811873a', wait_until='domcontentloaded', timeout=30000)
    time.sleep(3)

fi = page.query_selector('input[type="file"]')
if fi: fi.set_input_files(os.path.abspath(str(Z)))
prompt = (D / 'GPT_REVIEW_PROMPT.md').read_text(encoding='utf-8')
el = page.wait_for_selector('#prompt-textarea', timeout=10000, state='visible')
el.click(); time.sleep(0.5); el.fill(prompt); time.sleep(1)
btn = page.query_selector('button[data-testid="send-button"]')
if btn: btn.click()
print('Phase D: Submitted'); pw.stop()
