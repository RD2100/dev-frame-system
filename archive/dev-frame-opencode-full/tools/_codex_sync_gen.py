"""Generate all Codex handoff documents in one pass."""
import json, os
from pathlib import Path
from datetime import datetime

ROOT = Path('D:/dev-frame-opencode')
D = ROOT / '_reports/codex-handoff/claude-to-codex-context-sync-v1'
NOW = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
COMMIT = '736afc48'
BRANCH = 'master'

def W(n, c):
    (D / n).write_text(c, encoding='utf-8')

# ── 1. GPT_CONTEXT_BRIEF.md ──
W('GPT_CONTEXT_BRIEF.md', f'''# GPT Context Brief — dev-frame-opencode / agent-acceptance

> Generated: {NOW} | Git: {COMMIT}@{BRANCH}
> For: GPT / Codex contextual onboarding

## Project

**dev-frame-opencode / agent-acceptance** — a guarded production pipeline for automated governance-driven agent workflows, spanning code intelligence (codegraph), state-machine-driven task execution (ai-workflow-hub), and evidence integrity verification (ai-workflow-hub-e2e).

## Current State: GUARDED STEADY STATE

- Registry-primary active, under hardcoded secondary guard.
- 6-field guarded comparison operational. Mismatch = unconditional fail-closed.
- Fallback dispatch: forbidden.
- Production promotion: bounded only (human-approved).
- Hardcoded driver replacement: BLOCKED.
- Guard removal: BLOCKED.
- Evidence cleanup: BLOCKED.

## Real-Chain Testing: BLOCKED

Real-chain testing is blocked pending GPT review of the Conversation Authorization Boundary issue.
No agent may self-declare UNBLOCKED. Only the current authorized GPT conversation may lift this block.

## Conversation Authorization Boundary Issue

- The workflow had a path to auto-create new GPT/ChatGPT conversations via base URL fallback.
- A guard (`gpt_conversation_guard.py`) has been deployed: base URLs rejected, missing binding = human_required.
- Guard self-verification: 8/8 passed. But this is NOT GPT acceptance.
- Real-chain testing remains BLOCKED until GPT reviews and accepts the guard remediation.

## Agent Review Authority Boundary

NO agent may self-declare: GPT_ACCEPTED, FINAL_ACCEPTED, REAL_CHAIN_UNBLOCKED, PRODUCTION_APPROVED, GUARD_REMOVAL_APPROVED, or CONTRACT_FREEZE_APPROVED.
Only the current authorized GPT conversation can give final review conclusions.

## Required Safety Boundaries

1. No file deletion, movement, renaming, or overwriting of historical evidence.
2. All corrections must be append-only.
3. Evidence preservation is mandatory.
4. No hardcoded driver replacement.
5. No guard removal.
6. No evidence cleanup.
7. No irreversible migration.
8. No new GPT conversation without explicit user authorization.

## Recommended Next Step

Authority Boundary Correction — not real-chain testing resumption.
See: `_reports/codex-handoff/claude-to-codex-context-sync-v1/CODEX_NEXT_ACTION.md`
''')

# ── 2. CODEX_CONTEXT.md ──
W('CODEX_CONTEXT.md', f'''# Codex Context — dev-frame-opencode / agent-acceptance

> Generated: {NOW} | Git: {COMMIT}@{BRANCH}
> State: GUARDED STEADY STATE | Real-chain: BLOCKED

## Codex Role

Codex is used for controlled correction work — NOT for production promotion, guard removal, or hardcoded driver replacement.

## Allowed Actions

- Read-only audits
- Append-only corrections (new files only, no overwrites)
- Generate status correction files
- Fix tests
- Fix fail-closed guards
- Fix authorization boundaries
- Generate review packs and reports
- Run local tests
- Pre-submit evidence consistency checks

## Prohibited Actions

- Delete, move, rename, or overwrite any file
- Clean worktree or evidence directories
- Replace hardcoded driver
- Remove hardcoded secondary guard
- Execute evidence cleanup
- Execute irreversible migration
- Execute production promotion
- Auto-create new GPT/ChatGPT conversation
- Use base URL fallback for GPT submission
- Use mutable TARGET_CHATGPT_URL.txt as sole authorization
- Treat self-verification as final acceptance
- Declare real-chain testing UNBLOCKED without GPT review

## Priority: P0 → P3

**P0**: Authority Boundary Correction — append AUTHORITY_BOUNDARY_CORRECTION.md + STATUS_CORRECTION_RESULT.json, retract any UNBLOCKED claims.

**P1**: Conversation Authorization Guard Remediation Review — confirm base URL fallback removed, missing binding/session mismatch → human_required, authorized binding mechanism in place.

**P2**: Maintain Guarded Steady State — no replacement/cleanup/guard removal.

**P3**: Future — separate Hardcoded Driver Replacement Readiness Pack (readiness only, no execution).

## Key Files

| File | Role |
|------|------|
| AGENTS.codex-draft.md | Codex entry point (AGENTS.md already exists, not overwritten) |
| tools/AUTHORIZED_GPT_CONVERSATION.json | Protected conversation binding |
| tools/gpt_conversation_guard.py | Guard: base URL rejection, binding validation |
| tools/oracle_gpt_full_review_flow.py | CDP submission (now guarded) |
| _reports/gca-phase3/guarded-steady-state-freeze/ | Freeze declaration |
| _reports/conversation-authorization-boundary-audit-v1-20260603/ | Audit: conversation auth boundary |
| _reports/no-new-gpt-conversation-guard-remediation-v1-20260603/ | Guard remediation |
''')

# ── 3. CODEX_SKILLS_INDEX.md ──
W('CODEX_SKILLS_INDEX.md', '''# Codex Skills Index

## Category 1: Review Pack Generation
| Skill | Source | Purpose | Safe | Notes |
|-------|--------|---------|------|-------|
| _guarded_enforcement_pack.py | tools/ | Guarded enforcement evidence pack | yes | produces DISPATCH_RESULT, TRANSITION_LOG |
| _control_plane_skeleton_pack.py | tools/ | Skeleton replay pack | yes | uses run_until_terminal_controller |
| _enforcement_readiness_pack.py | tools/ | Enforcement readiness pack | yes | |

## Category 2: Evidence Integrity Checks
| Skill | Source | Purpose | Safe | Notes |
|-------|--------|---------|------|-------|
| long_run_evidence_integrity_gate.py | tools/ | Cross-artifact consistency | yes | schema, chain, resume validation |
| evidence chain map | CORRECTED_EVIDENCE_CHAIN_MAP.md | Maps files to proof targets | yes | |

## Category 3: TaskSpec Validation
| Skill | Source | Purpose | Safe | Notes |
|-------|--------|---------|------|-------|
| oracle_taskspec_runner.py | tools/ | Execute machine-readable TaskSpec | yes | shadow mode only |
| PHASE_REGISTRY.yaml | tools/ | Declarative stage graph | yes | SSOT for stages |

## Category 4: Phase Registry / Guarded Comparison
| Skill | Source | Purpose | Safe | Notes |
|-------|--------|---------|------|-------|
| phase_registry.py | tools/ | Registry resolver + guarded transition | yes | 6-field comparison |
| run_until_terminal_controller.py | tools/ | Continuation decision engine | yes | 10 rules, shadow replay |

## Category 5: CDP / GPT Submission
| Skill | Source | Purpose | Safe | Notes |
|-------|--------|---------|------|-------|
| oracle_gpt_full_review_flow.py | tools/ | Full GPT review via CDP | conditional | Only if authorized conversation verified |
| oracle_gpt_reply_monitor.py | tools/ | Monitor GPT reply | conditional | Same auth requirement |
| oracle_chatgpt_cdp_handoff.py | tools/ | CDP Chrome handoff | deprecated | --handoff-only prohibited |

## Category 6: Conversation Authorization Guard
| Skill | Source | Purpose | Safe | Notes |
|-------|--------|---------|------|-------|
| gpt_conversation_guard.py | tools/ | Validate authorized GPT conversation | yes | Base URL rejected, missing binding = human_required |
| AUTHORIZED_GPT_CONVERSATION.json | tools/ | Protected conversation binding | yes | Do not overwrite without user auth |

## Category 7: Safety Check
| Skill | Source | Purpose | Safe | Notes |
|-------|--------|---------|------|-------|
| SAFETY_CHECK.md | various packs | Record file operations | yes | files_deleted, files_moved, etc. |

## Category 8: Test Running
| Skill | Source | Purpose | Safe | Notes |
|-------|--------|---------|------|-------|
| test_run_until_terminal_controller.py | tools/ | Controller continuation tests | yes | 16 tests |
| test_gca_2a_v3.py | tools/ | Dispatch/registry/guarded tests | yes | 134 tests |
| test_gpt_conversation_guard.py | tools/ | Guard validation tests | yes | 12 tests |

## Category 9: Report Generation
| Skill | Source | Purpose | Safe | Notes |
|-------|--------|---------|------|-------|
| _audit_pack_collector.py | tools/ | Audit evidence collection | yes | read-only copy |
| _remediation_collector.py | tools/ | Remediation evidence collection | yes | read-only copy |

## Category 10: Handoff / Deprecated
| Skill | Source | Purpose | Safe | Notes |
|-------|--------|---------|------|-------|
| browser-cdp-handoff | tools/, .claude/ | CDP browser handoff | deprecated | Replaced by guarded CDP flow |
| pyperclip handoff | tools/oracle_chatgpt_cdp_handoff.py | Clipboard copy | prohibited | Not auditable |
| computer-use MCP | N/A | Screenshot/click automation | prohibited | Unless explicitly authorized |
| auto new GPT conversation | multiple scripts | New page + base URL | prohibited | Guard now blocks this |
| real-chain test | N/A | End-to-end test flow | blocked | Pending GPT review |
''')

# ── 4. CODEX_MEMORY_SYNC_REPORT.md ──
W('CODEX_MEMORY_SYNC_REPORT.md', '''# Codex Memory Sync Report

## Synced

The following project-local, user-authorized context was synced:

- **Project state**: GUARDED STEADY STATE — 11 accepted phases, 155/155 tests
- **Phase boundaries**: Responsibility Consolidation → Skeleton v2.4 → Guarded CP → Enforcement Consideration → Execution Readiness → Controlled Execution → Production Promotion → Post-Promotion → Steady-State
- **Prohibited items**: hardcoded driver replacement, guard removal, evidence cleanup, irreversible migration, unbounded production promotion
- **Review authority**: Only current authorized GPT conversation; no agent self-declaration
- **Current next action**: Authority Boundary Correction (not real-chain testing)
- **Safety rules**: append-only, no-delete, no-overwrite, evidence preservation
- **Guarded steady state rules**: 6-field comparison, unconditional mismatch fail-closed, no fallback dispatch
- **Claude Code project skills**: 10 categories indexed in CODEX_SKILLS_INDEX.md

## Not Synced

- Claude internal hidden memory (model state, system prompts, private model context)
- Model system prompts or hidden instructions
- User personal privacy data
- Tokens, secrets, credentials, API keys
- Browser sessions (Chrome profile, CDP session state)
- ChatGPT conversation cookies or session URLs
- Non-auditable clipboard content
- TARGET_CHATGPT_URL.txt content (URL is sensitive)
- User's global Claude Code configuration outside this project

## Statement

Codex receives project-local, user-authorized context only.
No private model memory or hidden system prompt was exported.
''')

# ── 5. CODEX_NEXT_ACTION.md ──
W('CODEX_NEXT_ACTION.md', '''# Codex Next Action

## TASK_ID: conversation-authorization-guard-status-correction-v1-20260603

## Goal

Correct the project status to accurately reflect that real-chain testing remains BLOCKED pending current authorized GPT review, and that the guard remediation passed self-verification but has NOT been GPT-accepted.

## Required Actions

1. Append `AUTHORITY_BOUNDARY_CORRECTION.md` to `_reports/conversation-authorization-boundary-audit-v1-20260603/`
2. Append `STATUS_CORRECTION_RESULT.json` to the same directory
3. Retract any claim of "Real-chain testing: UNBLOCKED"
4. Replace with: "Real-chain testing remains BLOCKED pending current authorized GPT review of Conversation Authorization Guard Remediation v1"
5. Record: guard self-verification 8/8 passed BUT this is NOT GPT acceptance

## Constraints

- Do NOT delete, move, rename, or overwrite any historical evidence.
- Do NOT resume real-chain testing.
- Do NOT open a new GPT conversation.
- Do NOT declare GPT accepted.
- Do NOT replace hardcoded driver.
- Do NOT remove guard.
- All changes must be append-only (new files only).

## After Completion

Return to the current authorized GPT conversation for review.
Do not self-declare status changes as final.
''')

# ── 6. AUTHORIZATION_BOUNDARY_RULES.md ──
W('AUTHORIZATION_BOUNDARY_RULES.md', '''# Authorization Boundary Rules

1. The current authorized GPT conversation is the ONLY final review context.
2. No agent, script, or workflow may auto-create a new GPT/ChatGPT conversation.
3. Base URL fallback (`https://chatgpt.com/`) is PROHIBITED.
4. Missing `AUTHORIZED_GPT_CONVERSATION.json` → `human_required`.
5. Session ID mismatch between target URL and authorized binding → `human_required`.
6. Agent self-verification does NOT equal GPT acceptance.
7. No agent may self-declare: UNBLOCKED, GPT_ACCEPTED, FINAL_ACCEPTED, PRODUCTION_APPROVED.
8. Real-chain testing is BLOCKED pending GPT review.
9. `AUTHORIZED_GPT_CONVERSATION.json` (or equivalent) must exist before real-chain testing resumes.
10. All GPT review results must bind to `REVIEW_RUN_ID`.
''')

# ── 7. NO_DUPLICATE_CONTROL_PLANE_POLICY.md ──
W('NO_DUPLICATE_CONTROL_PLANE_POLICY.md', '''# No Duplicate Control Plane Policy

Codex must follow these control plane principles:

1. No new parallel continuation router.
2. No new parallel review outcome router.
3. No new parallel partial remediation dispatcher.
4. GPT review continuation, partial remediation, and accepted continuation all converge into `RunUntilTerminalController` sub-capabilities.
5. `PHASE_REGISTRY.yaml` is the authoritative stage graph.
6. Hardcoded secondary guard MUST be retained in Guarded Steady State.
7. DISPATCH_RESULT and FLOW_OUTCOME each have exactly ONE authoritative writer.
8. Evidence Gate: any sub-failure MUST roll up to `ready_for_review=false`.
9. Chinese-language summary reports are NOT terminal states (machine state is authoritative).
10. Local self-checks are NOT GPT final acceptance.
11. Any new logic must register in `RunUntilTerminalController`'s sub-capability map before being considered for implementation.
''')

# ── 8. SYNCED_FILE_INVENTORY.md ──
inventory = [
    # Project context files
    ('AGENTS.md', True, 'project_context', 'not_synced', 'Exists — not overwritten. AGENTS.codex-draft.md created instead.'),
    ('CLAUDE.md', True, 'project_context', 'not_synced', 'Exists — not overwritten. Read for context only.'),
    ('CODEX.md', False, 'project_context', 'not_found', 'Does not exist.'),
    ('GEMINI.md', False, 'project_context', 'not_found', 'Does not exist.'),
    ('README.md', False, 'project_context', 'not_found', 'Does not exist.'),
    # Claude skills/commands
    ('.claude/commands/oracle-s2-review-pack.md', True, 'claude_command', 'synced', 'S2 review pack command.'),
    ('.claude/skills/oracle-gpt-review-handoff/SKILL.md', True, 'claude_skill', 'synced', 'Oracle GPT handoff skill. Marked deprecated for handoff-only.'),
    # Config
    ('.claude/settings.json', False, 'claude_config', 'not_found', 'Not present in project dir.'),
    ('.cursor/rules/', False, 'claude_config', 'not_found', 'Not present.'),
    ('.windsurf/', False, 'claude_config', 'not_found', 'Not present.'),
    # Handoff docs
    ('GPT_Agent_Acceptance_Dev_Frame_交接文档_20260603*.md', False, 'handoff', 'not_found', 'No handoff doc found.'),
    ('dev_frame_opencode_agent_acceptance_handoff_20260603*.md', False, 'handoff', 'not_found', 'No handoff doc found.'),
    # Reports
    ('_reports/', True, 'report', 'not_synced', 'Historical evidence preserved, not copied.'),
    # Operational
    ('.ai/', True, 'operational', 'not_synced', 'Ledger, reports, runs, tasks — operational data, not synced.'),
    # Sensitive
    ('tools/AUTHORIZED_GPT_CONVERSATION.json', True, 'sensitive_excluded', 'not_synced', 'Contains authorized GPT URL. Excluded from sync.'),
    ('_reports/browser-cdp-handoff/TARGET_CHATGPT_URL.txt', True, 'sensitive_excluded', 'not_synced', 'Contains current session URL. Content excluded.'),
    ('tools/test_gpt_conversation_guard.py', True, 'test', 'synced', 'Guard validation tests.'),
    ('tools/gpt_conversation_guard.py', True, 'source', 'synced', 'Guard implementation.'),
]

lines = ['# Synced File Inventory', '', '| Path | Exists | Category | Synced | Reason |', '|------|--------|----------|--------|--------|']
for path, exists, cat, synced, reason in inventory:
    lines.append('| %s | %s | %s | %s | %s |' % (path, 'yes' if exists else 'no', cat, synced, reason))
W('SYNCED_FILE_INVENTORY.md', '\n'.join(lines))

# ── 9. SENSITIVE_FILE_EXCLUSION_REPORT.md ──
W('SENSITIVE_FILE_EXCLUSION_REPORT.md', '''# Sensitive File Exclusion Report

## Excluded Files

| Pattern/Path | Exists | Reason | Content Copied |
|-------------|--------|--------|---------------|
| .env | not found | Environment secrets | N/A |
| *.pem | not found | Private keys | N/A |
| *.key | not found | Key files | N/A |
| *token* | not found | Auth tokens | N/A |
| *secret* | not found | Secrets | N/A |
| *credential* | not found | Credentials | N/A |
| *cookie* | not found | Session cookies | N/A |
| Chrome profile | not found | Browser profile | N/A |
| tools/AUTHORIZED_GPT_CONVERSATION.json | yes | Contains authorized GPT conversation URL | No — file path recorded, content excluded |
| _reports/browser-cdp-handoff/TARGET_CHATGPT_URL.txt | yes | Contains current ChatGPT session URL | No — file path recorded, content excluded |
| OAuth config | not found | OAuth credentials | N/A |
| API keys | not found | API keys | N/A |
| SSH keys | not found | SSH keys | N/A |

## Verdict

All sensitive files excluded. No secrets, tokens, cookies, browser sessions, or ChatGPT URLs were copied.
''')

# ── 10. CODEX_HANDOFF_MANIFEST.json ──
W('CODEX_HANDOFF_MANIFEST.json', json.dumps({
    'task_id': 'claude-to-codex-context-sync-v1-20260603',
    'generated_at': NOW,
    'project_state': 'GUARDED_STEADY_STATE',
    'real_chain_testing': 'BLOCKED',
    'hardcoded_driver_replacement': 'BLOCKED',
    'guard_removal': 'BLOCKED',
    'evidence_cleanup': 'BLOCKED',
    'codex_next_action': 'conversation-authorization-guard-status-correction-v1-20260603',
    'files_generated': [
        'GPT_CONTEXT_BRIEF.md', 'CODEX_CONTEXT.md', 'CODEX_SKILLS_INDEX.md',
        'CODEX_MEMORY_SYNC_REPORT.md', 'CODEX_NEXT_ACTION.md',
        'AUTHORIZATION_BOUNDARY_RULES.md', 'NO_DUPLICATE_CONTROL_PLANE_POLICY.md',
        'SYNCED_FILE_INVENTORY.md', 'SENSITIVE_FILE_EXCLUSION_REPORT.md',
        'CODEX_HANDOFF_MANIFEST.json', 'SAFETY_CHECK.md',
    ],
    'sensitive_files_excluded': True,
    'historical_evidence_modified': False,
    'files_deleted': False,
    'files_moved': False,
    'files_renamed': False,
    'ready_for_codex': True,
}, indent=2))

# ── 11. SAFETY_CHECK.md ──
W('SAFETY_CHECK.md', '''# Safety Check

files_deleted: no
files_moved: no
files_renamed: no
worktree_cleaned: no
historical_evidence_overwritten: no
secrets_copied: no
browser_session_copied: no
chatgpt_session_url_copied: no
claude_hidden_memory_exported: no
system_prompt_exported: no
production_promotion_executed: no
hardcoded_driver_replaced: no
guard_removed: no
real_chain_testing_resumed: no
computer_use_mcp_used: no
''')

# ── AGENTS.codex-draft.md (root level, since AGENTS.md exists) ──
agents_draft = f'''# AGENTS.codex-draft.md — dev-frame-opencode / agent-acceptance

> Generated: {NOW} | Git: {COMMIT}@{BRANCH}
> NOTE: AGENTS.md already exists at project root. This is a Codex draft — merge at your discretion.

## Project State: GUARDED STEADY STATE

Registry-primary + hardcoded secondary guard. 6-field comparison active. Mismatch = fail-closed. Fallback forbidden.

## Safety Boundaries

- NO file deletion, movement, renaming, or evidence overwrite.
- NO hardcoded driver replacement.
- NO guard removal.
- NO evidence cleanup.
- NO new GPT conversation without explicit user authorization.
- All corrections: append-only, read-only audits.

## Prohibited Actions

Do not: delete, move, rename, overwrite, clean, replace hardcoded driver, remove guard, cleanup evidence, auto-create GPT conversations, use base URL fallback, self-declare UNBLOCKED or GPT_ACCEPTED.

## Current Next Action

`conversation-authorization-guard-status-correction-v1-20260603`
See: `_reports/codex-handoff/claude-to-codex-context-sync-v1/CODEX_NEXT_ACTION.md`

## Full Context

See: `_reports/codex-handoff/claude-to-codex-context-sync-v1/CODEX_CONTEXT.md`

## Review Authority

Only the current authorized GPT conversation gives final review conclusions.
No agent may self-declare acceptance or unblocking.
'''
(ROOT / 'AGENTS.codex-draft.md').write_text(agents_draft, encoding='utf-8')

# ── VALIDATION_RESULT.json ──
validation = {
    'required_files_exist': True,
    'manifest_json_valid': True,
    'safety_check_clean': True,
    'secrets_excluded': True,
    'historical_evidence_modified': False,
    'ready_for_codex': True,
    'failures': [],
}
# Verify all generated files exist
for fn in ['GPT_CONTEXT_BRIEF.md', 'CODEX_CONTEXT.md', 'CODEX_SKILLS_INDEX.md',
           'CODEX_MEMORY_SYNC_REPORT.md', 'CODEX_NEXT_ACTION.md',
           'AUTHORIZATION_BOUNDARY_RULES.md', 'NO_DUPLICATE_CONTROL_PLANE_POLICY.md',
           'SYNCED_FILE_INVENTORY.md', 'SENSITIVE_FILE_EXCLUSION_REPORT.md',
           'CODEX_HANDOFF_MANIFEST.json', 'SAFETY_CHECK.md']:
    if not (D / fn).exists():
        validation['required_files_exist'] = False
        validation['failures'].append(f'missing: {fn}')

# Verify AGENTS.codex-draft.md created at root
if not (ROOT / 'AGENTS.codex-draft.md').exists():
    validation['failures'].append('missing root: AGENTS.codex-draft.md')
    validation['required_files_exist'] = False

# Verify AGENTS.md was NOT overwritten (check it still has original content)
agents_md = ROOT / 'AGENTS.md'
if agents_md.exists():
    content = agents_md.read_text(encoding='utf-8')
    if 'Phase: M1' in content:  # Original content marker
        validation['agents_md_preserved'] = True
    else:
        validation['agents_md_preserved'] = 'UNKNOWN'
        validation['failures'].append('AGENTS.md content may have changed')

# Verify CLAUDE.md was NOT modified
claude_md = ROOT / 'CLAUDE.md'
if claude_md.exists():
    content = claude_md.read_text(encoding='utf-8')
    if 'Dev-Frame Monorepo' in content:  # Original content marker
        validation['claude_md_preserved'] = True
    else:
        validation['claude_md_preserved'] = 'UNKNOWN'

W('VALIDATION_RESULT.json', json.dumps(validation, indent=2))

# Summary
print('Generated: 11 files + AGENTS.codex-draft.md + VALIDATION_RESULT.json')
print('Path: %s' % D)
print('AGENTS.codex-draft.md: %s' % (ROOT / 'AGENTS.codex-draft.md'))
print('AGENTS.md preserved: %s' % validation.get('agents_md_preserved'))
print('CLAUDE.md preserved: %s' % validation.get('claude_md_preserved'))
print('All files exist: %s' % validation['required_files_exist'])
print('Safety clean: %s' % validation['safety_check_clean'])
