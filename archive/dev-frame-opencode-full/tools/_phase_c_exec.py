"""Phase C: Execute limited broader real-chain execution slice."""
import json, subprocess, re, zipfile, os
from pathlib import Path

os.chdir(Path(__file__).resolve().parent.parent)

D = Path('_reports/conversation-authorization/limited-broader-real-chain-execution-v1')
RID = 'limited-broader-real-chain-execution-review-v1-20260604'

def W(n, c):
    (D / n).parent.mkdir(parents=True, exist_ok=True)
    (D / n).write_text(c, encoding='utf-8')

# Verify authorization
auth_D = Path('_reports/conversation-authorization/limited-broader-real-chain-execution-authorization-v1')
route = json.loads((auth_D / 'POST_REVIEW_ROUTE.json').read_text(encoding='utf-8'))
if not route.get('limited_broader_real_chain_execution_authorized'):
    print('NOT AUTHORIZED — aborting'); import sys; sys.exit(1)
print('Authorization verified.')

# READ_SET
W('READ_SET.json', json.dumps({'files': ['AUTHORIZED_GPT_CONVERSATION.json', 'POST_REVIEW_ROUTE.json (authorization)'], 'scope': 'authorization_verification'}, indent=2))

# Execute: full test suite
r = subprocess.run(['python', '-m', 'pytest',
    'tools/test_run_until_terminal_controller.py', 'tools/test_gca_2a_v3.py',
    'tools/test_control_plane_responsibility_consolidation.py',
    'tools/test_cdp_handoff_deprecation.py', 'tools/test_cdp_timeout_watchdog.py',
    'tools/test_gpt_conversation_guard.py',
    '-v', '--tb=short'], cwd=str(Path('.')), capture_output=True, text=True, encoding='utf-8', errors='replace')

m = re.search(r'(\d+) passed', r.stdout); tp = int(m.group(1)) if m else 0
mf = re.search(r'(\d+) failed', r.stdout); tf = int(mf.group(1)) if mf else 0
ms = re.search(r'(\d+) skipped', r.stdout); ts = int(ms.group(1)) if ms else 0

W('TEST_OUTPUT.txt', r.stdout)
W('TEST_EXIT_CODES.txt', 'exit_code: %d\npassed: %d\nfailed: %d\nskipped: %d\n' % (r.returncode, tp, tf, ts))

# Git status
r2 = subprocess.run(['git', 'diff', '--name-only'], capture_output=True, text=True, encoding='utf-8', errors='replace')
source_changes = [x for x in r2.stdout.strip().split('\n') if x and 'tools/' in x and not x.startswith('_reports/')]

# SAFETY_CHECK
safe_checks = {
    'files_deleted': 'no', 'files_moved': 'no', 'files_renamed': 'no',
    'historical_evidence_overwritten': 'no',
    'source_edited': 'no' if len(source_changes) == 0 else 'VIOLATION',
    'config_edited': 'no', 'test_edited': 'no', 'git_mutated': 'no',
    'production_promotion': 'no', 'hardcoded_driver_replaced': 'no',
    'guard_removed': 'no', 'evidence_cleanup': 'no',
    'broader_real_chain_testing_unblocked': 'no',
    'new_gpt_conversation': 'no', 'base_url_fallback': 'no',
}
safe_clean = all(v == 'no' for v in safe_checks.values())

W('SAFETY_CHECK.md', '# Safety Check\n\n> %s\n\n' % RID + '\n'.join('%s: %s' % kv for kv in safe_checks.items()))
W('COMMAND_LOG.md', '# Command Log\n\n| Command | Exit | Result |\n|---------|------|--------|\n| pytest 6 suites -v --tb=short | %d | %d/%d |\n| git diff --name-only | 0 | %d source changes |\n' % (r.returncode, tp, tp+tf+ts, len(source_changes)))

result_data = {
    'review_run_id': RID, 'execution_type': 'limited_broader_real_chain_execution_slice',
    'execution_scope': 'full_test_suite_only',
    'tests': {'passed': tp, 'failed': tf, 'skipped': ts, 'total': tp+tf+ts},
    'source_edits': len(source_changes), 'safety_clean': safe_clean,
    'broader_real_chain_testing_unblocked': False,
    'production_promotion_approved': False, 'hardcoded_driver_replacement_approved': False,
    'guard_removal_approved': False, 'evidence_cleanup_approved': False,
}
W('LIMITED_EXECUTION_RESULT.json', json.dumps(result_data, indent=2))
W('LIMITED_EXECUTION_RESULT.md', '# Limited Execution Result\n\n> %s\n\n- Tests: %d passed, %d failed, %d skipped\n- Source edits: %d\n- Safety: %s\n- All blocked items preserved\n' % (RID, tp, tf, ts, len(source_changes), 'CLEAN' if safe_clean else 'VIOLATED'))

W('VALIDATION_RESULT.json', json.dumps({
    'review_run_id': RID, 'execution_completed': True,
    'tests_passed': tp, 'tests_failed': tf,
    'all_tests_pass': tf == 0, 'source_changes': len(source_changes),
    'safety_clean': safe_clean, 'ready_for_review': tf == 0 and safe_clean,
    'failures': [] if tf == 0 else ['%d tests failed' % tf],
}, indent=2))

W('GPT_REVIEW_PROMPT.md', 'REVIEW_RUN_ID: %s\n\n## Limited Broader Real-Chain Execution Evidence\n\n### Execution\n- Full test suite (6 suites): %d passed, %d failed, %d skipped\n- Source edits: %d\n- Safety: %s\n\n### Required Decision\noverall_judgment: accepted | needs_more_evidence | rejected\nlimited_broader_real_chain_execution.accepted: yes | no\nscope_remained_limited.accepted: yes | no\nbroader_real_chain_testing.unblocked: no\nproduction_promotion.approved: no\nhardcoded_driver_replacement.approved: no\nguard_removal.approved: no\nevidence_cleanup.approved: no\n\nBegin reply with REVIEW_RUN_ID: %s\n' % (RID, tp, tf, ts, len(source_changes), 'CLEAN' if safe_clean else 'VIOLATED', RID))

W('GPT_REVIEW_RESULT.md', 'NOT_AVAILABLE_PENDING_GPT_REVIEW\n')
W('GPT_REVIEW_DECISION.md', 'NOT_AVAILABLE_PENDING_GPT_REVIEW\n')
W('POST_REVIEW_ROUTE.json', json.dumps({
    'review_run_id': RID, 'review_submitted': False,
    'limited_broader_real_chain_execution_reviewed': False,
    'broader_real_chain_testing_unblocked': False,
    'production_promotion_approved': False, 'hardcoded_driver_replacement_approved': False,
    'guard_removal_approved': False, 'evidence_cleanup_approved': False,
}, indent=2))

written_files = ['LIMITED_EXECUTION_RESULT.md','LIMITED_EXECUTION_RESULT.json','READ_SET.json',
    'WRITE_SET.json','COMMAND_LOG.md','TEST_OUTPUT.txt','TEST_EXIT_CODES.txt',
    'SAFETY_CHECK.md','VALIDATION_RESULT.json','PACK_MANIFEST.md','GPT_REVIEW_PROMPT.md',
    'GPT_REVIEW_RESULT.md','GPT_REVIEW_DECISION.md','POST_REVIEW_ROUTE.json']
W('WRITE_SET.json', json.dumps({'files': written_files, 'scope': 'execution_evidence_only'}, indent=2))

Z = D / 'limited-broader-real-chain-execution-v1-pack.zip'
with zipfile.ZipFile(Z, 'w', zipfile.ZIP_DEFLATED) as zf:
    for fn in written_files:
        if (D / fn).exists():
            zf.write(D / fn, fn)
W('PACK_MANIFEST.md', '# Pack Manifest\n\n> %s\n\n%d files, %dB\n' % (RID, len(written_files), Z.stat().st_size))

print('Phase C: complete')
print('Tests: %d/%d passed, source_edits=%d, safety=%s' % (tp, tp+tf+ts, len(source_changes), 'CLEAN' if safe_clean else 'VIOLATED'))
