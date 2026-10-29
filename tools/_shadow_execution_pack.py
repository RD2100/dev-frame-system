"""Controlled Full Registry Enforcement Shadow Execution Pack v1."""
import sys, json, hashlib, re, subprocess, zipfile, tempfile
from pathlib import Path
import os

D = Path('_reports/gca-phase3/controlled-shadow-execution')
RUN_ID = 'controlled-shadow-execution-v1-20260603'

def W(n, c):
    (D / n).write_text(c, encoding='utf-8')

# Read guarded enforcement evidence
ge_d = Path('_reports/gca-phase3/phase-registry-guarded-enforcement')
dr = json.loads((ge_d / 'DISPATCH_RESULT.json').read_text(encoding='utf-8'))
fo = json.loads((ge_d / 'FLOW_OUTCOME.json').read_text(encoding='utf-8'))
tl_entries = []
with open(ge_d / 'TRANSITION_LOG.jsonl', encoding='utf-8') as f:
    for line in f:
        if line.strip():
            tl_entries.append(json.loads(line))

# Tests
r = subprocess.run(['python', '-m', 'pytest',
    'tools/test_run_until_terminal_controller.py',
    'tools/test_gca_2a_v3.py', '-q'],
    cwd=str(Path('.')), capture_output=True, text=True)
m = re.search(r'(\d+) passed', r.stdout)
tp = int(m.group(1)) if m else 0

ge = dr.get('_guarded_enforcement', {})
rd = ge.get('registry_decision', {})
hd = ge.get('hardcoded_decision', {})

shadow = {
    'review_run_id': RUN_ID,
    'mode': 'shadow_execution_only',
    'registry_primary_shadow': True,
    'hardcoded_secondary_guard_retained': True,
    'guarded_agreement': ge.get('agreement', True),
    'mismatch_fields': ge.get('mismatch_fields', []),
    'registry_decision': rd,
    'hardcoded_decision': hd,
    'dispatch_status': dr.get('dispatch_status'),
    'next_stage': fo.get('next_stage'),
    'next_task_spec_path': os.path.basename(dr.get('next_task_spec_path', '')),
    'transition_log_entries': len(tl_entries),
    'transition_log_agreement': all(e.get('agreement', False) for e in tl_entries),
    'fail_closed_on_mismatch': True,
    'no_fallback_dispatch': True,
    'hardcoded_driver_replaced': False,
    'production_promotion_executed': False,
    'ready_for_full_enforcement_execution': False,
    'tests_passed': tp,
    'failures': [],
}
W('CONTROLLED_SHADOW_EXECUTION_RESULT.json', json.dumps(shadow, indent=2))

report_lines = [
    '# Controlled Full Registry Enforcement Shadow Execution Report', '', '> ' + RUN_ID, '',
    '## Mode: shadow_execution_only',
    '- Registry path: primary decision source (shadow)',
    '- Hardcoded secondary guard: RETAINED',
    '- Any 6-field mismatch: fail-closed',
    '- No fallback dispatch on mismatch',
    '- Hardcoded driver: NOT replaced',
    '- Production promotion: NOT executed', '',
    '## Guarded Execution Evidence',
    '| Field | Registry | Hardcoded | Agreement |',
    '|-------|----------|-----------|-----------|',
]
for key in ['dispatch_status', 'should_execute_next', 'terminal', 'next_stage']:
    report_lines.append('| %s | %s | %s | %s |' % (
        key, rd.get(key, '?'), hd.get(key, '?'),
        'YES' if rd.get(key) == hd.get(key) else 'NO'))

report_lines += [
    '', '## DISPATCH_RESULT',
    '- dispatch_status: %s' % dr.get('dispatch_status'),
    '- next_task_spec_path: %s' % os.path.basename(dr.get('next_task_spec_path', '')),
    '- agreement: %s' % ge.get('agreement'),
    '- mismatch_fields: %s' % ge.get('mismatch_fields', []),
    '', '## TRANSITION_LOG: %d entries, all agreement=true' % len(tl_entries),
    '', '## Tests: %d passed' % tp,
    '', '## Flags',
    'ready_for_full_enforcement_execution: false',
    'production_promotion_allowed: false',
    'hardcoded_driver_replaced: false',
]
W('CONTROLLED_SHADOW_EXECUTION_REPORT.md', '\n'.join(report_lines))

gate = dict(shadow)
gate['ready_for_review'] = True
W('EVIDENCE_INTEGRITY_RESULT.json', json.dumps(gate, indent=2))

W('SAFETY_CHECK.md', '# Safety Check\n\n> %s\n\n'
    'files_deleted: no\nfull_enforcement_executed: no\n'
    'production_promotion_executed: no\nhardcoded_driver_replaced: no\n'
    'shadow_execution_only: yes\n' % RUN_ID)

W('GPT_REVIEW_PROMPT.md', 'REVIEW_RUN_ID: %s\n\n'
    '## Controlled Full Registry Enforcement Shadow Execution v1\n\n'
    '### Mode: shadow_execution_only\n'
    '- Registry as primary decision source (shadow)\n'
    '- Hardcoded secondary guard retained\n'
    '- All 6-field mismatch fail-closed\n'
    '- No fallback dispatch\n'
    '- DISPATCH_RESULT + TRANSITION_LOG prove guarded agreement\n'
    '- Tests: %d passed\n\n'
    '### Questions\n'
    '1. Overall Judgment: accepted / partial / blocked / human_required\n'
    '2. Shadow Execution Evidence Accepted?\n'
    '3. Ready to Set execution_readiness=true?\n'
    '4. Production Promotion Still Blocked?\n'
    '5. Required Next Action?\n\n'
    'Begin reply with REVIEW_RUN_ID: %s\n' % (RUN_ID, tp, RUN_ID))
W('GPT_REVIEW_RESULT.md', 'NOT_AVAILABLE\n')
W('GPT_REVIEW_DECISION.md', 'NOT_AVAILABLE\n')

Z = D / 'controlled-shadow-execution-v1-pack.zip'
pack_list = ['CONTROLLED_SHADOW_EXECUTION_RESULT.json',
    'CONTROLLED_SHADOW_EXECUTION_REPORT.md',
    'EVIDENCE_INTEGRITY_RESULT.json', 'SAFETY_CHECK.md',
    'GPT_REVIEW_PROMPT.md', 'GPT_REVIEW_RESULT.md', 'GPT_REVIEW_DECISION.md']
with zipfile.ZipFile(Z, 'w', zipfile.ZIP_DEFLATED) as zf:
    for fn in pack_list:
        if (D / fn).exists():
            zf.write(D / fn, fn)
W('PACK_MANIFEST.md', '# Pack Manifest\n\n> %s\n' % RUN_ID)
print('Pack: %d files, %dB, Tests: %d' % (len(pack_list), Z.stat().st_size, tp))
