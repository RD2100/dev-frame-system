"""Global Final Audit Pack — evidence collection (read-only copy only)."""
import shutil, json, os, subprocess, re
from pathlib import Path
from datetime import datetime

ROOT = Path('.')
AUDIT = ROOT / '_global_final_audit_pack'
NOW = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
COMMIT = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()[:8]
BRANCH = subprocess.run(['git', 'branch', '--show-current'], capture_output=True, text=True).stdout.strip()

def cp(src_rel, dst_rel):
    """Copy file from src to audit dir, preserving relative path."""
    src = ROOT / src_rel
    dst = AUDIT / dst_rel
    if src.exists() and src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return 'copied'
    return 'missing'

def cp_multi(pattern_dir, file_list, dst_subdir):
    """Copy multiple files from a directory to audit subdirectory."""
    results = {}
    for fname in file_list:
        src = Path(pattern_dir) / fname if not isinstance(fname, tuple) else Path(fname[0]) / fname[1]
        rel_dst = Path(dst_subdir) / (fname if isinstance(fname, str) else fname[1])
        results[str(src)] = cp(str(src), str(rel_dst))
    return results

# ── A. CONTRACTS_AND_SCHEMAS ──
schema_dir = ROOT / 'D:/agent-acceptance/contracts'
if not schema_dir.exists():
    schema_dir = ROOT / '..' / '..' / 'agent-acceptance' / 'contracts'
for schema_glob in ['*.schema.json', '*_SCHEMA.json', '*_schema.json']:
    for f in ROOT.glob(schema_glob):
        cp(str(f.relative_to(ROOT)), f'CONTRACTS_AND_SCHEMAS/{f.name}')
# Copy from agent-acceptance if accessible
contracts_root = Path('D:/agent-acceptance/contracts')
if contracts_root.exists():
    for f in contracts_root.glob('*.json'):
        cp(str(f), f'CONTRACTS_AND_SCHEMAS/{f.name}')
    for f in (contracts_root.parent / 'policies').glob('*.md') if (contracts_root.parent / 'policies').exists() else []:
        cp(str(f), f'CONTRACTS_AND_SCHEMAS/policies_{f.name}')

# ── B. PHASE_REGISTRY ──
registry_files = ['PHASE_REGISTRY.yaml', 'phase_registry.py', 'test_gca_2a_v3.py']
for f in registry_files:
    cp(f'tools/{f}', f'PHASE_REGISTRY/{f}')
# Copy registry evidence
for sub in ['phase-registry-prototype', 'phase-registry-enforcement-prep',
            'phase-registry-guarded-enforcement', 'phase-registry-remediation']:
    src_dir = ROOT / '_reports' / 'gca-phase3' / sub
    if src_dir.exists():
        for f in src_dir.rglob('*.json'):
            rel = f.relative_to(ROOT)
            cp(str(rel), f'PHASE_REGISTRY/{sub}/{f.name}')
        for f in src_dir.rglob('*.md'):
            rel = f.relative_to(ROOT)
            cp(str(rel), f'PHASE_REGISTRY/{sub}/{f.name}')

# ── C. CONTROL_PLANE ──
cp('tools/run_until_terminal_controller.py', 'CONTROL_PLANE/run_until_terminal_controller.py')
cp('tools/test_run_until_terminal_controller.py', 'CONTROL_PLANE/test_run_until_terminal_controller.py')
cp('tools/gpt_review_decision_parser.py', 'CONTROL_PLANE/gpt_review_decision_parser.py')
cp('tools/post_review_router.py', 'CONTROL_PLANE/post_review_router.py')
for sub in ['control-plane-skeleton', 'control-plane-guarded-mode',
            'global-control-plane-diagnostic', 'phase-transition-hardening']:
    src_dir = ROOT / '_reports' / 'gca-phase3' / sub
    if src_dir.exists():
        for f in src_dir.rglob('*.json'):
            cp(str(f.relative_to(ROOT)), f'CONTROL_PLANE/{sub}/{f.name}')
        for f in src_dir.rglob('*.md'):
            cp(str(f.relative_to(ROOT)), f'CONTROL_PLANE/{sub}/{f.name}')

# ── D. RUNNER_AND_DISPATCH ──
runner_files = [
    'oracle_post_decision_driver.py', 'oracle_decision_dispatcher.py',
    'oracle_flow_runner.py', 'oracle_taskspec_runner.py',
    'oracle_flow_state.py', 'oracle_gpt_full_review_flow.py',
    'oracle_gpt_reply_monitor.py', 'oracle_chatgpt_cdp_handoff.py',
    'long_run_evidence_integrity_gate.py',
]
for f in runner_files:
    cp(f'tools/{f}', f'RUNNER_AND_DISPATCH/{f}')

# ── E. REVIEW_PACKS ──
key_run_ids = [
    's3-phase3', 'gca-phase1', 'gca-phase2a', 'gca-phase2b', 'gca-phase3',
    'control-plane-skeleton', 'phase-registry-guarded-enforcement',
    'full-registry-enforcement-consideration', 'full-registry-enforcement-readiness',
    'controlled-shadow-execution', 'controlled-full-enforcement-execution',
    'production-promotion-readiness', 'production-promotion-authorization',
    'production-promotion-execution', 'post-promotion-verification',
    'steady-state-monitoring', 'cdp-handoff-deprecation',
    'cdp-submission-timeout-recovery', 'cdp-unavailable-handling',
    'control-plane-responsibility-consolidation',
]
# Scan gca-phase3 subdirectories
gca3 = ROOT / '_reports' / 'gca-phase3'
if gca3.exists():
    for sub in gca3.iterdir():
        if sub.is_dir():
            sub_name = sub.name
            for key_file in ['GPT_REVIEW_RESULT.md', 'GPT_REVIEW_DECISION.md',
                             'FLOW_OUTCOME.json', 'DISPATCH_RESULT.json',
                             'TRANSITION_LOG.jsonl', 'TEST_OUTPUT.md',
                             'PACK_MANIFEST.md', 'EVIDENCE_INTEGRITY_RESULT.json']:
                src = sub / key_file
                if src.exists():
                    cp(str(src.relative_to(ROOT)), f'REVIEW_PACKS/{sub_name}/{key_file}')

# Also check root _reports directories
for report_dir in ['s3-frozen-taskspec', 's3-phase1', 's3-phase2', 's3-phase3',
                   'contract-freeze-review', 'contract-freeze-review-prep',
                   'long-run-test', 'gpt-reviews', 'oracle-flow-state']:
    src_dir = ROOT / '_reports' / report_dir
    if src_dir.exists():
        for f in src_dir.rglob('*.json'):
            if f.stat().st_size < 100000:  # Skip huge files
                cp(str(f.relative_to(ROOT)), f'REVIEW_PACKS/{report_dir}/{f.name}')
        for f in src_dir.rglob('*.md'):
            cp(str(f.relative_to(ROOT)), f'REVIEW_PACKS/{report_dir}/{f.name}')

# ── F. TEST_EVIDENCE ──
for f in ROOT.glob('tools/test_*.py'):
    cp(str(f.relative_to(ROOT)), f'TEST_EVIDENCE/{f.name}')

# Copy latest test output from skeleton dir
for d in ['control-plane-skeleton', 'phase-registry-guarded-enforcement']:
    src = gca3 / d / 'TEST_OUTPUT.md' if gca3.exists() else None
    if src and src.exists():
        cp(str(src.relative_to(ROOT)), f'TEST_EVIDENCE/{d}_TEST_OUTPUT.md')

# ── G. PRODUCTION_PROMOTION_EVIDENCE ──
for d in ['production-promotion-readiness', 'production-promotion-authorization',
          'production-promotion-execution', 'post-promotion-verification']:
    src_dir = gca3 / d if gca3.exists() else None
    if src_dir and src_dir.exists():
        for f in src_dir.rglob('*.md'):
            cp(str(f.relative_to(ROOT)), f'PRODUCTION_PROMOTION_EVIDENCE/{d}/{f.name}')
        for f in src_dir.rglob('*.json'):
            cp(str(f.relative_to(ROOT)), f'PRODUCTION_PROMOTION_EVIDENCE/{d}/{f.name}')

# ── H. STEADY_STATE_MONITORING ──
src_dir = gca3 / 'steady-state-monitoring' if gca3.exists() else None
if src_dir and src_dir.exists():
    for f in src_dir.rglob('*'):
        if f.is_file():
            cp(str(f.relative_to(ROOT)), f'STEADY_STATE_MONITORING/{f.name}')

# ── I. SOURCE_SNAPSHOTS ──
source_files = [
    'tools/phase_registry.py', 'tools/run_until_terminal_controller.py',
    'tools/oracle_post_decision_driver.py', 'tools/oracle_decision_dispatcher.py',
    'tools/oracle_flow_runner.py', 'tools/oracle_taskspec_runner.py',
    'tools/oracle_flow_state.py', 'tools/oracle_gpt_full_review_flow.py',
    'tools/long_run_evidence_integrity_gate.py', 'tools/gpt_review_decision_parser.py',
    'tools/post_review_router.py', 'tools/test_run_until_terminal_controller.py',
    'tools/test_gca_2a_v3.py', 'tools/test_control_plane_responsibility_consolidation.py',
    'tools/test_cdp_handoff_deprecation.py', 'tools/test_cdp_timeout_watchdog.py',
    'tools/_guarded_enforcement_pack.py', 'tools/_control_plane_skeleton_pack.py',
    'tools/_enforcement_readiness_pack.py', 'tools/_shadow_execution_pack.py',
    'tools/_skeleton_v23_pack.py', 'tools/_skeleton_v24_pack.py',
    'tools/PHASE_REGISTRY.yaml',
]
for f in source_files:
    cp(f, f'SOURCE_SNAPSHOTS/{Path(f).name}')

# Run test and capture output
r = subprocess.run(['python', '-m', 'pytest',
    'tools/test_run_until_terminal_controller.py',
    'tools/test_gca_2a_v3.py',
    'tools/test_control_plane_responsibility_consolidation.py',
    'tools/test_cdp_handoff_deprecation.py',
    'tools/test_cdp_timeout_watchdog.py',
    '-q'], cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8', errors='replace')
(AUDIT / 'TEST_EVIDENCE' / 'LATEST_TEST_OUTPUT.txt').write_text(r.stdout, encoding='utf-8')
m = re.search(r'(\d+) passed', r.stdout)
tp = int(m.group(1)) if m else 0
mf = re.search(r'(\d+) failed', r.stdout)
tf = int(mf.group(1)) if mf else 0
print(f'Tests: {tp}/{tp+tf} passed')

# Count copied files
total_copied = len(list(AUDIT.rglob('*')))
print(f'Files in audit pack: {total_copied}')
print(f'Git: {COMMIT}@{BRANCH}')
print(f'Done: {NOW}')
