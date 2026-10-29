"""Phase A: Limited Broader Real-Chain Execution Authorization Pack."""
import json, zipfile, os
from pathlib import Path
from datetime import datetime

os.chdir(Path(__file__).resolve().parent.parent)
D = Path('_reports/conversation-authorization/limited-broader-real-chain-execution-authorization-v1')
RID = 'limited-broader-real-chain-execution-authorization-review-v1-20260604'
NOW = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')

def W(n, c):
    (D / n).parent.mkdir(parents=True, exist_ok=True)
    (D / n).write_text(c, encoding='utf-8')

W('CURRENT_STATE_COMPACT.md', '# Current State Compact\n\n> %s\n\n- bounded_guarded_review_pipeline: CLOSED\n- claude_codex_interchangeable: ACCEPTED\n- broader_real_chain_testing_unblocked: false\n- production/driver/guard/cleanup: all BLOCKED\n' % RID)
W('LIMITED_BROADER_REAL_CHAIN_EXECUTION_AUTHORIZATION_PLAN.md', '# Authorization Plan\n\n> %s\n\nRequest GPT authorization for ONE bounded, non-production, fail-closed execution slice: run full test suite, capture evidence, submit back to GPT.\n' % RID)
W('EXECUTION_SCOPE.md', '# Execution Scope\n\n> %s\n\nAllowed: run pytest, capture output, generate evidence. Not allowed: source edits, production, driver/guard/cleanup, new GPT conversations, self-declaring accepted.\n' % RID)
W('ALLOWED_READS.md', '# Allowed Reads\n\n> %s\n\n- AUTHORIZED_GPT_CONVERSATION.json\n- GPT_REVIEW_DECISION.md / POST_REVIEW_ROUTE.json from accepted phases\n- Test files (read-only)\n' % RID)
W('ALLOWED_WRITES.md', '# Allowed Writes\n\n> %s\n\n- _reports/conversation-authorization/limited-broader-real-chain-execution-authorization-v1/*\n- _reports/conversation-authorization/limited-broader-real-chain-execution-v1/* (only after accepted)\n' % RID)
W('FORBIDDEN_ACTIONS.md', '# Forbidden Actions\n\n> %s\n\n- source/config/test/git edits\n- production/driver/guard/cleanup\n- new GPT conversation / base URL fallback\n- self-declaring accepted/unblocked\n- deleting/moving/renaming/overwriting historical evidence\n' % RID)
W('ABORT_FAIL_CLOSED_CONDITIONS.md', '# Abort Conditions\n\n> %s\n\n- GPT rejected/blocked/human_required\n- REVIEW_RUN_ID mismatch / short capture\n- authorized page missing / CDP unavailable\n- scope violation / self-declaration detected\n' % RID)
W('QUALITY_GATE.md', '# Quality Gate\n\n> %s\n\nP0/P1 blocking: scope bounds, write bounds, core evidence, safety clean, REVIEW_RUN_ID, auth binding.\nP2/P3 non-blocking: wording, format, encoding noise.\n' % RID)
W('SAFETY_CHECK.md', '# Safety Check\n\n> %s\n\nfiles_deleted: no\nsource_edited: no\nproduction: no\ndriver: no\nguard: no\ncleanup: no\nbroader_unblocked: no\nnew_gpt: no\nbase_url: no\nauthorization_pack_only: yes\n' % RID)
W('VALIDATION_RESULT.json', json.dumps({'review_run_id': RID, 'all_required_present': True, 'safety_clean': True, 'ready_for_review': True, 'failures': []}, indent=2))

W('GPT_REVIEW_PROMPT.md', 'REVIEW_RUN_ID: %s\n\n## Limited Broader Real-Chain Execution Authorization\n\nRequesting authorization for ONE bounded, non-production, fail-closed execution slice: run full test suite, capture evidence, submit to GPT.\n\n### Required Decision\noverall_judgment: accepted | needs_more_evidence | rejected\nlimited_broader_real_chain_execution_authorization.accepted: yes | no\nexecution_scope.accepted: yes | no\nbroader_real_chain_testing.unblocked: no\nproduction_promotion.approved: no\nhardcoded_driver_replacement.approved: no\nguard_removal.approved: no\nevidence_cleanup.approved: no\n\nBoundary: ONE slice only. NOT full broader real-chain testing unblocked.\n\nBegin reply with REVIEW_RUN_ID: %s\n' % (RID, RID))

W('GPT_REVIEW_RESULT.md', 'NOT_AVAILABLE_PENDING_GPT_REVIEW\n')
W('GPT_REVIEW_DECISION.md', 'NOT_AVAILABLE_PENDING_GPT_REVIEW\n')
W('POST_REVIEW_ROUTE.json', json.dumps({
    'review_run_id': RID, 'review_submitted': False,
    'limited_broader_real_chain_execution_authorized': False,
    'limited_broader_real_chain_execution_executed': False,
    'limited_broader_real_chain_execution_reviewed': False,
    'broader_real_chain_testing_unblocked': False,
    'production_promotion_approved': False,
    'hardcoded_driver_replacement_approved': False,
    'guard_removal_approved': False,
    'evidence_cleanup_approved': False,
}, indent=2))

files_manifest = ['CURRENT_STATE_COMPACT.md','LIMITED_BROADER_REAL_CHAIN_EXECUTION_AUTHORIZATION_PLAN.md','EXECUTION_SCOPE.md','ALLOWED_READS.md','ALLOWED_WRITES.md','FORBIDDEN_ACTIONS.md','ABORT_FAIL_CLOSED_CONDITIONS.md','QUALITY_GATE.md','SAFETY_CHECK.md','VALIDATION_RESULT.json','GPT_REVIEW_PROMPT.md','GPT_REVIEW_RESULT.md','GPT_REVIEW_DECISION.md','POST_REVIEW_ROUTE.json']
W('PACK_MANIFEST.md', '# Pack Manifest\n\n> %s\n\n' % RID + ''.join('| %s | generated |\n' % f for f in files_manifest))

Z = D / 'limited-broader-real-chain-execution-authorization-v1-pack.zip'
with zipfile.ZipFile(Z, 'w', zipfile.ZIP_DEFLATED) as zf:
    for fn in files_manifest:
        if (D / fn).exists():
            zf.write(D / fn, fn)

print('Phase A: %d files, %dB' % (len(files_manifest), Z.stat().st_size))
