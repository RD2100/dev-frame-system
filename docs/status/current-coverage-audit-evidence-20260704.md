# Current Coverage Audit Evidence - 2026-07-04

Lifecycle state: Evidence record for current coverage audit

Reader: DevFrame maintainers and coding agents checking whether the current
coverage audit in `document-driven-transformation-master-plan.md` is grounded in
reproducible repository evidence.

Post-read action: use this as a bounded 2026-07-04 evidence snapshot. Current
progress is tracked in
[Review-Governance Kernel Completion Status](review-governance-kernel-completion-20260706.md);
historical Phase 1A gap rows are not current state. Do not treat this snapshot
as a clean release state.

Related docs: [Document-Driven Transformation Master Plan](document-driven-transformation-master-plan.md), [Review-First Governance Kernel Implementation Spec](review-first-governance-kernel-implementation-spec.md), [Review-Governance Kernel Completion Status](review-governance-kernel-completion-20260706.md), [Status Document Inventory](status-document-inventory.md), [Reviewer Index](reviewer-index.md)

## Scope

This evidence snapshot supports the `Current Coverage Audit` in the master plan.
It answers four narrow questions:

1. Is CodeGraph available enough to support structural repo inspection?
2. What repository state was inspected?
3. Are the planned Phase 1A review-governance kernel files present?
4. Does the known TestFrame import blocker still reproduce?

At capture time, it did not prove implementation readiness beyond Phase 1A
schema, fixture, and negative-test work.

## Repository State

Captured on 2026-07-04.

```text
branch: codex/public-mainline-batch-1
commit: 98d5202e509e27d85a77ec9e553bfe8ac773d82d
working_tree: dirty
```

The worktree includes many existing modified and untracked files. This evidence
record is therefore a current-worktree snapshot, not a clean committed release
claim.

## CodeGraph Status

CodeGraph was available and healthy enough for structural inspection.

```text
Files indexed: 312
Total nodes: 5574
Total edges: 11271
Database size: 16.61 MB
Backend: node:sqlite with WAL and FTS5
Journal mode: wal

Nodes by kind:
- class: 138
- constant: 25
- file: 288
- function: 2783
- import: 1395
- method: 274
- variable: 671

Languages:
- javascript: 7
- python: 281
- yaml: 24
```

## Phase 1A File-Existence Check

Command shape:

```powershell
$paths=@(
  'schemas/review_governance_kernel.schema.json',
  'schemas/examples/review-governance/success.json',
  'schemas/examples/review-governance/blocked.json',
  'schemas/examples/review-governance/insufficient-evidence.json',
  'schemas/examples/review-governance/missing-context.json',
  'schemas/examples/review-governance/goal-bound-continuation.json',
  'packages/control-plane/tests/test_review_governance_kernel.py',
  'packages/control-plane/control_plane/review_governance_kernel.py'
)
foreach($p in $paths){
  '{0} {1}' -f ($(if(Test-Path $p){'EXISTS'}else{'MISSING'})), $p
}
```

Observed output:

```text
MISSING schemas/review_governance_kernel.schema.json
MISSING schemas/examples/review-governance/success.json
MISSING schemas/examples/review-governance/blocked.json
MISSING schemas/examples/review-governance/insufficient-evidence.json
MISSING schemas/examples/review-governance/missing-context.json
MISSING schemas/examples/review-governance/goal-bound-continuation.json
MISSING packages/control-plane/tests/test_review_governance_kernel.py
MISSING packages/control-plane/control_plane/review_governance_kernel.py
```

Conclusion: in this 2026-07-04 snapshot, Phase 1A was still a planned
implementation target. The expected schema, fixtures, contract tests, and
optional helper did not exist in this worktree snapshot.

## TestFrame Import Probe

Command shape:

```powershell
@'
import sys
sys.path.insert(0, 'packages/test-frame')
try:
    import aggregator.report as r
    print('TESTFRAME_REPORT_IMPORT_OK_WITH_PATH')
except Exception as e:
    print(type(e).__name__ + ': ' + str(e))
'@ | python -
```

Observed output:

```text
ModuleNotFoundError: No module named 'schema'
```

Conclusion: this remains an evaluation-governance blocker. It is not a blocker
for Phase 1A review-governance kernel schema, fixtures, and negative tests.

## Focused Tests

Command:

```powershell
python -m pytest packages\control-plane\tests\test_external_review_bundle.py packages\control-plane\tests\test_web_ai_browser_launcher.py packages\control-plane\tests\test_custom_skills.py -q
```

Observed output:

```text
.......................                                                  [100%]
23 passed in 0.53s
```

Conclusion: the tested external-brain bundle, persistent browser launcher, and
custom skill management behaviors are real substrate, but they do not implement
the review-governance lifecycle by themselves.

## Public Snapshot Gate

Command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1
```

Observed output:

```text
[OK] Public snapshot required paths are present.
[OK] Governance rule references are present.
[OK] No submodules, local agent state, evidence archives, generated packages, or oversized files found.
[OK] JSON files parse as UTF-8.
```

Conclusion: the current public-snapshot checks passed for this worktree state.

## External-Brain Review

The v1 external-brain review returned `CONDITIONAL PASS`: the direction was
correct, but the master-plan coverage audit lacked raw repository evidence in
the review bundle.

After this evidence record and the matching master-plan edits were added, the
v2 external-brain review returned `PASS`:

```text
PASS; prior P0/P1 closed; GO for accepting the updated coverage audit; GO for
keeping Phase 1A as the next mainline; NO-GO for treating the coverage audit as
proof that Phase 1A is implemented.
```

The browser-hosted review artifacts are runtime evidence and remain outside the
public repository.

## Evidence Boundary

This evidence supports these historical 2026-07-04 claims:

- Phase 1A remained the next implementation target in the audited snapshot.
- Existing external-brain, browser-launch, and custom-skill code paths are
  tested substrate.
- TestFrame still has an importability gap that blocks later evaluation
  governance work.

This evidence does not support these claims:

- the post-2026-07-04 implementation status of Phase 1A; check the completion
  status record instead.
- TestFrame is ready as a general evaluation substrate.
- Graph projection, Paper KB iteration, or multi-browser transport should move
  ahead of the review-governance kernel.
