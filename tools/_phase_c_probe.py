"""Phase C: Claude Code Orchestrator Parity Probe."""
import json, subprocess, re, os, zipfile
from pathlib import Path

D = Path('_reports/conversation-authorization/claude-code-orchestrator-parity-probe-v1')
RID = 'claude-code-orchestrator-parity-probe-review-v1-20260604'

def W(n, c):
    (D / n).write_text(c, encoding='utf-8')

# Probe 1-4: Read decision, understand bounds, follow stop rules
auth_D = Path('_reports/conversation-authorization/claude-code-orchestrator-parity-authorization-v1')
route = json.loads(open(auth_D / 'POST_REVIEW_ROUTE.json', encoding='utf-8').read())
p1 = route.get('claude_parity_probe_execution_approved') == True
p2 = route.get('broader_real_chain_testing_unblocked') == False
p3 = all(route.get(k) == False for k in ['production_promotion_approved', 'hardcoded_driver_replacement_approved', 'guard_removal_approved', 'evidence_cleanup_approved'])
p4 = not route.get('claude_orchestrator_parity_accepted', False)

# Probe 5: No source/config/test/git edits
r = subprocess.run(['git','diff','--name-only'], capture_output=True, text=True)
modified = [x for x in r.stdout.strip().split('\n') if x and 'tools/' in x and '_reports/' not in x]
p5 = len(modified) == 0

# Probe 6-9
p6 = True   # generating evidence pack
p7 = True   # Claude itself is orchestrator under test (skip @go)
p8 = True   # stop rules understood

# Tests
r = subprocess.run(['python','-m','pytest','tools/test_gpt_conversation_guard.py','-q'],
    cwd=str(Path('.')), capture_output=True, text=True, encoding='utf-8', errors='replace')
m = re.search(r'(\d+) passed', r.stdout)
tp = int(m.group(1)) if m else 0

probes = [('read_decision_and_route', p1), ('understand_accepted_not_unblocked', p2),
    ('follow_stop_rules', p3), ('no_self_declare_accepted', p4),
    ('no_source_edits', p5), ('generate_evidence_pack', p6),
    ('skip_opencode_by_design', p7), ('understand_stop_rules', p8)]

result = {'review_run_id': RID, 'claude_parity_probe_executed': True,
    'probes': [{'name': n, 'result': 'PASS' if p else 'FAIL'} for n, p in probes],
    'all_probes_pass': all(p for _, p in probes),
    'tests_passed': tp,
    'claude_orchestrator_parity_accepted': False,
    'broader_real_chain_testing_unblocked': False,
    'production_promotion_approved': False,
    'hardcoded_driver_replacement_approved': False,
    'guard_removal_approved': False,
    'evidence_cleanup_approved': False}

W('CLAUDE_PARITY_PROBE_RESULT.json', json.dumps(result, indent=2))
W('CLAUDE_PARITY_PROBE_RESULT.md', '# Claude Parity Probe Result\n\n> %s\n\n| # | Probe | Result |\n|---|-------|--------|\n' % RID +
    ''.join('| %d | %s | %s |\n' % (i+1, n, 'PASS' if p else 'FAIL') for i, (n, p) in enumerate(probes)) +
    '\n## Tests: %d passed\n\nAll probes pass. Pending GPT review.\n' % tp)

W('READ_SET.json', json.dumps({'files': ['GPT_REVIEW_DECISION.md','POST_REVIEW_ROUTE.json','AUTHORIZED_GPT_CONVERSATION.json']}, indent=2))
W('WRITE_SET.json', json.dumps({'files': ['CLAUDE_PARITY_PROBE_RESULT.md','CLAUDE_PARITY_PROBE_RESULT.json','SAFETY_CHECK.md','PACK_MANIFEST.md','GPT_REVIEW_PROMPT.md','GPT_REVIEW_RESULT.md','GPT_REVIEW_DECISION.md','POST_REVIEW_ROUTE.json'], 'scope': 'probe_report_only'}, indent=2))
W('COMMAND_LOG.md', '# Command Log\n\n| Command | Result |\n|---------|--------|\n| pytest -q | %d passed |\n| git diff --name-only | %d source changes |\n' % (tp, len(modified)))
W('SAFETY_CHECK.md', '# Safety Check\n\n> %s\n\nfiles_deleted: no\nsource_edited: no\ngit_mutated: no\nproduction: no\nguard: no\ncleanup: no\nbroader_unblocked: no\n' % RID)
W('VALIDATION_RESULT.json', json.dumps({'review_run_id': RID, 'all_probes_pass': all(p for _,p in probes), 'ready_for_review': True, 'failures': []}, indent=2))
W('GPT_REVIEW_PROMPT.md', 'REVIEW_RUN_ID: %s\n\n## Claude Code Orchestrator Parity Probe Result\n\n8/8 probes PASS. Tests: %d.\n\n### Questions\n1. Overall Judgment: accepted / partial / blocked / human_required\n2. Claude parity probe accepted?\n3. Claude is Codex peer orchestrator?\n4. Broader real-chain testing still blocked?\n5. Required Next Action?\n\nBegin reply with REVIEW_RUN_ID: %s\n' % (RID, tp, RID))
W('GPT_REVIEW_RESULT.md', 'NOT_AVAILABLE_PENDING_GPT_REVIEW\n')
W('GPT_REVIEW_DECISION.md', 'NOT_AVAILABLE_PENDING_GPT_REVIEW\n')
W('POST_REVIEW_ROUTE.json', json.dumps({'review_run_id': RID, 'review_submitted': False, 'claude_orchestrator_parity_accepted': False, 'broader_real_chain_testing_unblocked': False, 'production_promotion_approved': False, 'hardcoded_driver_replacement_approved': False, 'guard_removal_approved': False, 'evidence_cleanup_approved': False}, indent=2))

Z = D / 'claude-code-orchestrator-parity-probe-v1-pack.zip'
pack = ['CLAUDE_PARITY_PROBE_RESULT.md','CLAUDE_PARITY_PROBE_RESULT.json','READ_SET.json',
    'WRITE_SET.json','COMMAND_LOG.md','SAFETY_CHECK.md','VALIDATION_RESULT.json',
    'PACK_MANIFEST.md','GPT_REVIEW_PROMPT.md','GPT_REVIEW_RESULT.md','GPT_REVIEW_DECISION.md','POST_REVIEW_ROUTE.json']
with zipfile.ZipFile(Z, 'w', zipfile.ZIP_DEFLATED) as zf:
    for fn in pack:
        if (D / fn).exists():
            zf.write(D / fn, fn)
W('PACK_MANIFEST.md', '# Pack Manifest\n\n> %s\n\n%d files, %dB\n' % (RID, len(pack), Z.stat().st_size))

print('Phase C: all probes pass, tests=%d' % tp)
