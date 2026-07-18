# DevFrame Project Execution Root

Lifecycle state: **CANONICAL EXECUTION ROOT**

Current verdict: **READY TO CONTINUE** on the bounded milestone below. This is
not a release, deployment, or production verdict.

Last reconciled: 2026-07-18 against the clean `main` worktree at
`d6c03f7b384f16f5be7dce0fb8246c7e5737ec0a`, immediately before this
distribution-contraction slice.

## Authority

This file is the single authority for current project direction, milestone
order, active risk, and the next implementation slice.

Authority order for repository work is:

1. `AGENTS.md`, `rules/`, and tested runtime contracts define mandatory
   behavior and safety boundaries.
2. This file selects the current product objective and executable milestone.
3. Stable documentation under `docs/agent-runtime/` explains implemented
   behavior.
4. Every other file under `docs/status/` is supporting evidence, historical
   research, a scoped Recon Receipt, or a frozen release snapshot.

If another status document conflicts with this file, this file controls the
schedule. Code and tests still control claims about implemented behavior.

Do not create another master plan, current handoff, roadmap, launch plan, or
parallel backlog. Update this file in place.

## Product Decision

DevFrame is a governance kernel for development work. It owns the contracts
and authority needed to take work from intent to independently reviewable
outcome. It does not need to own every client, coding agent, compiler, or
domain UI.

The stable product boundary is:

| Layer | DevFrame responsibility | Replaceable implementations |
|---|---|---|
| Governance kernel | TaskSpec, run identity, evidence, review, gates, decisions, FinalVerdict | Not delegated to clients or workers |
| Client adapter | Read-only projection, requests, proposals, explicit execution requests | CLI, Tutti, RD-Code, Web AI |
| Executor adapter | Execute a bounded TaskSpec and return normalized evidence | command, ACP, Codex, OpenCode, Claude Code |
| Toolchain adapter | Run project-native build, test, lint, and compiler commands | Go, Gradle, pytest, npm, other compilers |
| Domain pack | Add domain contracts without creating a second authority system | code, test, paper |

`devframe code` remains the shortest primary product path. Tutti and RD-Code
are clients of the same governance state, not alternate kernels.

### Kernel Invariants

- Worker success is not acceptance.
- Report text is not authority by itself.
- Independent review, gate evidence, and a valid FinalVerdict are required for
  `final_ready`.
- Clients may display, request, propose, and explicitly invoke permitted
  actions; they may not manufacture decisions or completion.
- Provider and model identity are provenance, not governance semantics.
- Runtime state stays outside the public repository.
- Existing schemas and runtime records are extended only when a real vertical
  path proves a missing contract.

## Verified Baseline

The current public mainline includes these accepted capabilities:

| Area | Current proof |
|---|---|
| Public repository | `main` and `origin/main` both resolved to `d6c03f7b` immediately before this cleanup slice; the primary worktree was clean at reconciliation |
| Release history | GitHub Release `v0.1.0` exists; PyPI, deployment, and production rollout remain separate decisions |
| Governed coding | TaskSpec dispatch, execution reports, sealed context, review/gate evidence, and opt-in finalization exist |
| Acceptance safety | PR #29 requires canonical acceptance evidence instead of trusting worker status alone |
| Conversation intake | PR #30 adds durable conversation intake without making the client an authority |
| Session safety | PR #24 makes the ai-workflow-hub session gate fail closed |
| Client runtime | PR #25 hardens editor lifecycle; PR #28 adds RD-Code instance and portable tool resolution contracts |
| Distribution hygiene | PR #26 removed obsolete phase-1B submission scripts; PR #27 reconciled bootstrap mirrors |
| Research baseline | Read-only cluster probes passed 82 control-plane tests, 168 ai-workflow-hub tests, and targeted Tutti local-app Go tests |

Research probes are architecture evidence, not release or production evidence.

## Current Risk Register

There are no known open P0 risks in the verified public baseline. Current and
recently closed P1 risks are:

| ID | Status | Priority | Risk | Evidence | Closure condition |
|---|---|---|---|---|---|
| KERNEL-001 | closed | P1 | One physical go run could appear as separate `go_run` and `team_events` projections with the same canonical `run_id`; the team projection could lose the project identity | Canonical real-path RED→GREEN, 40 RunIndex tests, 87 related regressions, a clean public snapshot, and an independent read-only review passed on 2026-07-18 | One deterministic canonical read view per physical run, with merged provenance and fail-closed acceptance state |
| DOCS-001 | closed | P1 | 120 tracked status documents could be mistaken for competing current plans | Lifecycle demotion, authority tests, docs-drift checks, independent review, and a clean exported public-snapshot gate passed on 2026-07-18 | `HANDOFF.md` is the only scheduling authority; all other status documents are explicitly non-scheduling references |
| DIST-001 | closed | P1 | A 3,770-file Tutti snapshot and importer made a replaceable client look like part of the DevFrame kernel and inflated the public checkout | Real RED probe, exact Git untracking, ignored local-reference check, strict tracked-product probe, 1,564 control-plane tests passed, and no active importer references | `products/tutti/` is not tracked, the local reference is ignored, and the kernel distribution remains self-contained |
| DOCS-002 | closed | P2 | Two expired coordinator handoff prompts duplicated the current execution root and encouraged stale takeover instructions | Activity-reference audit, exact retirement, inventory update, docs-drift and current-entry tests passed | `HANDOFF.md` and stable runtime docs are the only live continuation path; retired prompts remain recoverable in Git history |

`DOCS-001` is mitigated by this document slice. Physical archival or deletion
is a later cleanup operation and must first prove that no active validator,
rule, script, or public link depends on the affected file.

## Delivery Roadmap

Only one milestone may be active. Later milestones are ordered backlog, not
permission to start parallel implementation.

| Milestone | State | User-visible outcome | Exit evidence |
|---|---|---|---|
| M0. Authority consolidation | accepted | One document controls direction and next work | Documentation drift, public snapshot, link, diff, and independent review gates passed |
| M1. Canonical run truth | accepted | CLI and clients see one governance record for one physical run | Real-path duplicate-run RED became one deterministic canonical projection; invalid authority paths fail closed |
| M2. Review closure | accepted | A real run moves from report to review, gate, and FinalVerdict without manual state reinterpretation | Real execution remains `review_pending` before independent review and becomes `final_ready` only after valid evidence |
| M3. Kernel distribution contraction | active | A fresh checkout contains the DevFrame kernel and replaceable adapters, not a vendored client product | Tracked Tutti snapshot and importer are gone, local reference remains ignored, public paths and core tests pass, and the dashboard is documented as optional diagnostics |
| M4. Executor equivalence | queued | The same TaskSpec can use command or ACP execution without changing governance meaning | Normalized RunRecord parity test passes; provider-specific data stays in provenance |
| M5. Paper vertical | queued | Paper work reuses the same evidence, review, and gate authority | One bounded paper task completes through the canonical kernel without a parallel state machine |

## Completed Milestone: M1 Canonical Run Truth

### Objective

Produce one deterministic, read-only canonical projection for a physical go
run while preserving all raw adapter entries for audit compatibility.

### Frozen Write Set

- `packages/control-plane/control_plane/run_index.py`
- `packages/control-plane/tests/test_run_index.py`
- this file, only to record the final verdict and next milestone after M1

Any additional production path requires a same-risk write-set amendment before
editing. Do not change storage, schemas, TeamRuntime event production, client
UI, Tutti, RD-Code, or ai-workflow-hub in M1.

### Required RED

A real-path fixture must reproduce all of the following:

- one `go-run.json` and matching TeamRuntime events describe the same run;
- legacy adapter entries share a canonical `run_id`;
- the team-only projection lacks or disagrees on project identity;
- the current read index cannot provide one unambiguous canonical view.

### Required GREEN

- Raw adapter entries remain available and unchanged for audit use.
- A deterministic canonical projection contains one record for the run.
- Project identity comes from a valid project-bearing source and cannot be
  silently replaced by `unknown-project`.
- Worker results, sealed context, evidence, review, gates, FinalVerdict, and
  provenance are reconciled without inventing missing facts.
- A passed worker with no valid independent review remains `review_pending`.
- Conflicting authoritative facts fail closed with a diagnostic instead of
  choosing whichever file was read last.

### Verification

```powershell
python -m pytest packages/control-plane/tests/test_run_index.py -q
python -m pytest packages/control-plane/tests/test_rdreview.py packages/control-plane/tests/test_client_governance_projection.py -q
powershell -ExecutionPolicy Bypass -File scripts/verify-public-snapshot.ps1
git diff --check
```

### Stop Lines

- No new kernel package, facade, database, policy engine, or protocol.
- No automatic independent-review synthesis.
- No generic default auto-finalization.
- No mutation of legacy runtime files during projection.
- No client or executor may acquire FinalVerdict authority.
- Do not start M2 until M1 has a real-path GREEN, independent review, actual
  diff reconciliation, and P0/P1 findings equal to zero for its slice.

### M1 Verdict

Accepted on 2026-07-18. Raw adapter entries remain audit-visible while
`canonical_runs` merges matching go and TeamRuntime projections. Project
identity, worker/reviewer identity, FinalVerdict artifact and event producer
identity, producer role, status conflicts, and journal snapshot drift all fail
closed. Evidence: `test_run_index.py` (40 passed), related regression tests
(87 passed), clean-worktree public snapshot (41 passed), `git diff --check`,
and independent read-only review with P0/P1 equal to zero. A large-run event
lookup index is a future P2 performance optimization, not an acceptance gap.

## Current Milestone: M2 Review Closure

### Objective

Prove the transition from a governed execution report to independent review,
gate evidence, and FinalVerdict without clients or workers reinterpreting the
state themselves.

### Recon And Initial Write Set

Start with read-only Recon of the existing TeamRuntime, `rdreview`, evidence
gate, and RunIndex paths. The initial write set is limited to
`packages/control-plane/tests/` for the first real-path RED. Freeze any
production write set only after that RED identifies the missing contract.

### First Required RED

Create one real TeamRuntime-backed run that has a passing worker report but no
valid independent review, gate, or FinalVerdict. The public read path must
remain `review_pending`; any path that reaches `final_ready` is a failure.

### Recon Result

The first M2 increment is already implemented in the committed runtime and is
therefore closed without a new production change. `tools/go_evidence.py`
records review and FinalVerdict references only after the evidence gate passes;
the TeamRuntime and RunIndex then project `final_ready`. The same real path
keeps self-review and invalid-review cases at `review_pending` without a
FinalVerdict. Evidence on 2026-07-18:

- `tests/test_go_evidence.py` selected M2 paths: 5 passed.
- `test_finalize_backfills_go_run_context_before_team_runtime_final_ready`
  proves the valid `go_evidence -> TeamRuntime -> RunIndex` transition.
- `test_finalize_records_only_evidence_refs_for_self_review_blocker` and the
  invalid-review variants prove the missing-review negative path.

The existing runtime-governance Recon Receipt covers this adapter boundary.
The frozen write set for a follow-up M2 code slice is empty: a new production
change requires a newly observed lifecycle gap and a new real-path RED.

### Independent M2 Review

The independent review on 2026-07-18 found no uncovered lifecycle transition.
The review followed the production-shaped path rather than accepting artifact
fields in isolation:

- `tools/go_evidence.py` evaluates the evidence gate, writes its governance
  artifacts, and records only references in TeamRuntime.
- `TeamRuntime` records the execution, review, and FinalVerdict journal events.
- `control_plane.run_index` validates independent reviewer identity, governance
  ownership, passing gate evidence, and sealed context before it projects
  `final_ready`.
- The valid lifecycle test reaches `final_ready`; self-review, malformed review,
  worker-role review, non-passing review, and missing sealed context remain
  non-final or blocked.

Reviewer Index:

| Item | Evidence |
|---|---|
| Changed files | None; this was a read-only review of committed behavior |
| Critical paths | `tools/go_evidence.py:record_team_runtime_finalization`; `packages/control-plane/control_plane/team_runtime.py`; `packages/control-plane/control_plane/run_index.py:_team_review_refs`, `_team_final_verdict_ref`, and `_axes` |
| Real-path tests | `python -m pytest tests/test_go_evidence.py -q` -> 36 passed; `python -m pytest packages/control-plane/tests/test_run_index.py -q` -> 40 passed |
| Generated artifacts | Per-test temporary evidence directories and TeamRuntime journals; pytest cleaned them after execution |
| Findings | P0=0, P1=0. P2: event lookup for unusually large journals remains a future performance optimization, not a correctness gap |
| Review focus | Keep FinalVerdict authority limited to governance producers and preserve the requirement for a passing independent review, passing gate, and sealed context |

### M2 Verdict

Accepted on 2026-07-18. No M2 production write set is open. Promote M3 only
as read-only Recon until a durable Recon Receipt and reuse decision authorize a
write-capable adapter slice.

## Current Milestone: M3 Kernel Distribution Contraction

### Objective

Reduce the public repository to the governance kernel and its necessary,
understandable adapters. Tutti remains an external reference checkout, not a
vendored product or a second implementation path. The dashboard remains
available as an optional diagnostic surface while its product value is assessed;
it is not the primary delivery target.

### Frozen Cleanup Scope

- Remove the tracked `products/tutti/` snapshot from the public distribution;
  keep any local checkout available only as an ignored external reference.
- Remove the one-off snapshot importer that exists only to recreate the
  vendored copy.
- Preserve the DevFrame CLI, governance kernel, schemas, tests, and necessary
  adapter contracts.
- Inventory dashboard references before any later decision to retire or shrink
  that code; this slice does not delete a live CLI surface.
- Keep all historical Tutti evidence as supporting records unless a later
  cleanup proves it is unreferenced and safe to remove.

### Stop Lines

- No Tutti core change, submodule, client runtime, provider binding, or
  dashboard rewrite.
- Do not delete the local external reference checkout in this slice.
- DevFrame keeps TaskSpec, run identity, evidence, review, gates, decisions,
  and FinalVerdict authority under `rules/open-source-reuse.md` RULE reuse-002.

### M3 Batch 1 Verification

The first contraction batch externalizes the local Tutti reference without
deleting its disk copy. The public repository no longer tracks the snapshot or
the one-off `scripts/import-tutti-snapshot.py` importer. The public snapshot
script now treats `products/` as an ignored external-reference root and its
strict mode rejects any future tracked product path.

Reviewer Index:

| Item | Evidence |
|---|---|
| Changed paths | `.gitignore`, `README.md`, `README.zh-CN.md`, `scripts/verify-public-snapshot.ps1`, `packages/control-plane/tests/test_public_snapshot.py`, `docs/status/HANDOFF.md`; exact deletion set is the tracked `products/tutti/` snapshot plus `scripts/import-tutti-snapshot.py` |
| Preserved paths | The local `products/tutti/` directory remains on disk and is ignored; no local reference files were physically deleted |
| Critical paths | Public snapshot traversal, strict tracked-product check, public distribution boundary, `devframe code` product positioning |
| Real-path tests | RED before cleanup: tracked Tutti paths reported by `git ls-files`; GREEN after cleanup: external-reference probe and strict tracked-product probe passed |
| Regression tests | `python -m pytest packages/control-plane/tests -q` -> 1,564 passed, 1 skipped; four public-snapshot tests remain blocked by pre-existing `.agents`, `.aiworkflow/reports`, `.claude`, `.codex`, and `.gsd` directories in the primary worktree |
| Static checks | `git diff --check` passed; `git ls-files products/tutti` -> 0; `git check-ignore products/tutti/README.md` -> ignored |
| Findings and focus | P0=0, P1=0 for this slice. Verify a clean checkout's public snapshot before release; do not treat the local ignored reference as a release artifact |

### M3 Batch 2 Verification

The reference audit retired two stale coordinator handoff prompts:
`continue-global-coordinator-conversation-mainline.md` and
`next-agent-global-coordinator-prompt.md`. Neither had an active code, test,
rule, or documentation entrypoint reference; both duplicated instructions now
represented by this file. The historical inventory was updated, and the files
remain recoverable from Git history.

Evidence:

- `rg` activity-reference audit returned no live references after retirement.
- `python -m pytest packages/control-plane/tests/test_docs_drift_validator.py -q`
  -> 23 passed.
- Current-entry and release snapshot checks -> 3 passed.
- `git diff --check` -> passed.

P0=0 and P1=0. Remaining status documents require individual classification;
do not bulk-delete Recon Receipts, release evidence, or files read by runtime
validators.

### Stop Lines

- No automatic review or FinalVerdict synthesis.
- No client, worker, or executor acceptance authority.
- No storage, schema, client, Tutti, RD-Code, or provider changes during Recon.

## Execution Protocol

Every milestone follows this loop:

1. Reconcile this file against current `HEAD`, worktree state, existing tests,
   and the relevant Recon Receipt.
2. Freeze one bounded TaskSpec with read set, write set, non-goals, RED,
   verification commands, and stop lines.
3. Produce a real-path RED before changing P0/P1 behavior.
4. Implement the smallest GREEN without adjacent refactoring.
5. Run targeted tests, relevant regression tests, the public snapshot gate,
   and `git diff --check`.
6. Reconcile the actual diff and generated artifacts against the frozen slice.
7. Perform independent review and record a Reviewer Index: changed files,
   critical paths, tests, artifacts, gaps, and review focus.
8. Only the root coordinator may accept the slice and perform exact-path Git
   staging and one logical commit. Push, PR, merge, release, and deployment
   follow the human gates in `AGENTS.md`.
9. Update this file with the milestone verdict and promote exactly one queued
   milestone to current.

Activity, worker count, document count, and report count are not outcomes.
Progress requires a product artifact, actual diff, test result, review verdict,
or accepted delivery.

## Documentation Policy

- Do not add a new status document for an ordinary milestone, batch, review,
  handoff, or progress update.
- Update the Current Milestone, Risk Register, Verified Baseline, and Decision
  Log in this file instead.
- Store local execution reports, temporary Recon artifacts, screenshots, and
  evidence packs outside the public repository.
- Keep a new public Recon Receipt only when `rules/recon.md` requires durable
  public evidence and no existing receipt covers the scope.
- Promote durable implemented behavior to `docs/agent-runtime/`; do not leave
  it as a target-state claim in `docs/status/`.
- Treat `LAUNCH_NOW.md`, `release-readiness.md`, `reviewer-index.md`, and
  `status-document-inventory.md` as supporting release, review, and historical
  lookup records. They do not choose the next task.
- Archive or delete old status files only in a dedicated, reviewed cleanup
  slice after reference and validator checks prove the operation safe.

## Human Gates

Explicit human approval remains required for release, deployment, production
data or credentials, paid services, legal or ethical decisions, destructive
cleanup of unknown content, force push, history rewrite, and protection-rule
bypass.

Ordinary bounded local edits and tests may proceed under this execution root.
Git mutations follow the current `AGENTS.md` authorization rules.

## Decision Log

| Date | Decision | Reason |
|---|---|---|
| 2026-07-18 | Keep `docs/status/HANDOFF.md` as the canonical path and expand it instead of creating another master plan | Reusing the established entrypoint reduces document sprawl |
| 2026-07-18 | Define DevFrame as a governance kernel, not a new monolithic runtime package | Existing contracts and authority paths are substantial; another facade would duplicate them |
| 2026-07-18 | Make canonical run reconciliation the first implementation milestone | A real cluster probe exposed duplicate identity before any new client or adapter work |
| 2026-07-18 | Keep Tutti as an external reference and defer Workspace App integration | Existing local-app load/reload and dashboard endpoints remain optional references; no required user flow currently justifies a public adapter |
| 2026-07-18 | Defer paper expansion until run identity, review closure, and executor parity are proven | Domain growth must not hide an unstable kernel boundary |
| 2026-07-18 | Accept M0 and promote M1 to active | Authority tests, docs drift, clean exported snapshot, actual diff review, and independent review passed |
| 2026-07-18 | Accept M1 and promote M2 to active | Canonical projection, authority-boundary probes, clean snapshot, actual diff review, and independent read-only review passed |
| 2026-07-18 | Close the first M2 review-closure increment as already satisfied | Existing go-evidence, TeamRuntime, and RunIndex paths provide the required valid and invalid lifecycle transitions |
| 2026-07-18 | Accept M2 and promote M3 to read-only Recon | Full production-shaped lifecycle tests and an independent source review found no uncovered review-closure transition |
| 2026-07-18 | Deprioritize Tutti dashboard integration and contract M3 as distribution contraction | The kernel is the product; a vendored 3,770-file client snapshot adds maintenance cost without proving a required user flow |

## Next Action

Continue the status-document and script audit with the next clearly redundant
historical batch. In parallel, inventory dashboard callers and tests; do not
delete dashboard code until a real user-flow probe proves it is unused and a
replacement CLI/API path is documented.
