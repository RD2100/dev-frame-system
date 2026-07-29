# DevFrame Project Execution Root

Lifecycle state: **CANONICAL EXECUTION ROOT**

Current verdict: **M11C ON-DEMAND CROSS-CLIENT MEMORY ROOT_ACCEPTED LOCALLY**.
The stdio adapter, client-native manifests, final installed-wheel probe, clean
release gate, and repeat independent `PASS` close the local source slice. The
already installed local memory plugin remains usable; this verdict did not
reinstall global client state and is not a remote release, deployment, or
publication verdict.

Last reconciled: 2026-07-29 against current local source, the M11C Recon
Receipt, installed-wheel stdio probe, clean release gate, and repeat
independent Luna Max review. Push, PR, global plugin installation, and remote
delivery remain separate human gates; this document does not predict remote
delivery evidence.

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
| Public repository | Local `main` contains the accepted M1-M9 kernel and adapter slices; M9's exact commit and ordinary remote-head verification form the next delivery boundary |
| Release history | GitHub Release `v0.1.0` exists; PyPI, deployment, and production rollout remain separate decisions |
| Governed coding | TaskSpec dispatch, execution reports, sealed context, review/gate evidence, and opt-in finalization exist |
| Workflow profiles | Trusted coding and paper entrypoints deterministically record ordered, permission-bounded, planned-only Skill stages; ambiguous work remains human-required |
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
| KERNEL-002 | closed | P1 | Toolchain inspection could combine same-ID metadata provenance from one byte snapshot with canonical review/acceptance state from another snapshot | A real CLI A/B replacement RED, exact handle-bound metadata SHA binding, 74 focused tests, 219 related regressions, installed-wheel status smoke, an isolated public snapshot, and independent review passed on 2026-07-19 | Inspection output and canonical governance state must share the exact same `go_run` source hash |
| DOCS-001 | closed | P1 | 120 tracked status documents could be mistaken for competing current plans | Lifecycle demotion, authority tests, docs-drift checks, independent review, and a clean exported public-snapshot gate passed on 2026-07-18 | `HANDOFF.md` is the only scheduling authority; all other status documents are explicitly non-scheduling references |
| DIST-001 | closed | P1 | A 3,770-file Tutti snapshot and importer made a replaceable client look like part of the DevFrame kernel and inflated the public checkout | Real RED probe, exact Git untracking, ignored local-reference check, strict tracked-product probe, 1,564 control-plane tests passed, and no active importer references | `products/tutti/` is not tracked, the local reference is ignored, and the kernel distribution remains self-contained |
| DOCS-002 | closed | P2 | Two expired coordinator handoff prompts duplicated the current execution root and encouraged stale takeover instructions | Activity-reference audit, exact retirement, inventory update, docs-drift and current-entry tests passed | `HANDOFF.md` and stable runtime docs are the only live continuation path; retired prompts remain recoverable in Git history |
| DIST-002 | closed | P2 | A desktop-shortcut helper promoted the deprecated T3/RD-Code visual-client path despite having no current product, test, or release entrypoint | Script-reference audit found only one historical roadmap mention; launcher tests and release gates do not depend on it | The shortcut helper is removed; the tested `launch-editor.ps1` advanced entry remains available |
| DOCS-003 | closed | P2 | A pre-release cutover checklist and superseded 90-day product roadmap remained visible after their decisions were absorbed into the current execution and release roots | Per-file audit found no live dependency; docs drift and current-entry gates passed; independent review passed with P0/P1/P2/P3 equal to zero | Current direction remains in `HANDOFF.md`; release history remains in `LAUNCH_NOW.md` and `release-readiness.md`; retired drafts remain recoverable in Git history |
| DIST-003 | closed | P2 | The primary `devframe code` command carried an optional dashboard-launch shortcut plus four dashboard-only server parameters, duplicating the explicit diagnostic command and widening the daily coding surface | Existing client Recon and reuse assessment, real CLI/bootstrap RED, minimal GREEN, 1,564 control-plane tests, installed-wheel smoke, and a second independent review with P0/P1/P2/P3 equal to zero | `devframe code` stays CLI-first while `devframe dashboard serve` preserves the full diagnostic/API surface |
| KERNEL-003 | closed | P2 | A malformed or unavailable project Skill policy can make Profile planning fall back to its built-in defaults without a diagnostic | M10B on 2026-07-26: missing, malformed, and unreadable `skills.json` policy all fail closed with zero side effects before any Profile stage is consumed; real-path regressions, a 42-check installed-CLI probe, and an independent non-author review passed | Before any Profile stage is consumed, policy-resolution failure must become human-required or conservatively read-only/no-network, with a real-path regression |
| MEMORY-001 | closed | P1 | The validated Obsidian candidate and its installed local read runtime could become a second lifecycle beside current `main` if a new plan feature were added without an explicit migration/cutover boundary | Candidate/main reconciliation, production-path RED -> GREEN, `1720 passed, 6 skipped` on a fresh verify tree, installed-wheel canary `3/0/0`, independent review PASS with P0/P1/P2/P3 all zero, and the 2026-07-20 live MCP + SessionStart canaries | Current `main` owns the only maintained Memory semantics and existing writeback owns all mutation; the current wheel is the sole active local runtime, while the old runtime is inactive and retained only for rollback |
| MEMORY-002 | closed | P1 | Reducing repeated memory authorization could accidentally turn safe capture into arbitrary overwrite, cross-project publication, raw-chat persistence, or broad client trust | M11B production RED -> GREEN; focused `130 passed, 4 skipped`; clean exported full suite `2083 passed, 9 skipped` with two isolated non-M11B failures; exact wheel/source binding; native SessionStart, actual compaction, PreCompact retry/concurrency, fresh MCP reconnect, cross-project rejection, kill-switch, and outage probes; P0/P1 review passed | Exact token-bound client trust; only read/create-only tools pre-approved; deterministic agent-owned paths, bounded high-signal PreCompact capture, read-only kill switch, human-gated plan/global publication, and project scope bound to Codex sandbox cwd |
| QUAL-001 | open | P2 | The QREM-B7/B8 dashboard handler-split results were lost before any commit, and `dashboard.py` complexity has regrown past the pre-remediation level (do_GET 88 / do_POST 158 decision points vs the B8 target of 64/140) | 2026-07-26 read-only audit: the implementation is absent from the worktree and from all Git history; specs, reports, and baselines remain under local `.aiworkflow/` | Either re-scope the remediation as a new governed slice from the retained specs, or the owner explicitly writes the debt off and archives the stale `.aiworkflow/session/current.json` |

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
| M3. Kernel distribution contraction | accepted | A fresh checkout contains the DevFrame kernel and replaceable adapters, not a vendored client product | Tracked Tutti snapshot and importer are gone, local reference remains ignored, public paths and core tests pass, and the dashboard is documented as optional diagnostics |
| M4. Executor equivalence | accepted | The same TaskSpec can use command or ACP execution without changing governance meaning | Normalized RunRecord parity test passes; provider-specific data stays in provenance |
| M5. Paper vertical | accepted | Paper work reuses the same evidence, review, and gate authority | One bounded synthetic paper task completes through the canonical kernel without a parallel state machine |
| M6. Adapter conformance entry | accepted | A third-party command-style executor can prove canonical governance parity offline | A bounded user CLI check reuses the accepted M4 parity path and fails closed on missing or divergent canonical records |
| M7. Toolchain adapter manifest | accepted | A compiler/test command set can be described and checked against the kernel without binding the kernel to one compiler | One offline manifest-driven preview and conformance contract, with execution still explicit and provider-neutral |
| M8. Governed toolchain run | accepted | One selected manifest action can enter the existing governed command path without creating a compiler-specific runtime | A real temporary project executes one manifest action only after explicit opt-in and produces canonical run, evidence, review-pending, and adapter-conformance projections |
| M9. Toolchain run inspection | accepted | A user can inspect one governed toolchain result without decoding generic go-run metadata or opening packet files | Installed CLI status binds structured toolchain provenance to the exact canonical source bytes and remains read-only/fail-closed |
| M10A. Governed workflow profiles | accepted | Structured coding or paper context deterministically selects and records an ordered, permission-bounded Skill profile without executing external capabilities | Real coding and paper missing-path REDs became schema-valid planned-only TaskSpecs; generic ambiguity remains human-required; installed-wheel and independent review gates passed |
| M10B. Governed coding canary | accepted | One offline coding entrypoint consumes the narrowly adopted pre/post stage plan through an explicit opt-in without changing correctness, safety, or acceptance authority | Policy-resolution failure fails closed before any stage is consumed; the fingerprint-bound offline canary passed real CLI paths, the full affected gates, installed-wheel smoke, a 42-check real-path probe, and an independent non-author review |
| M11A. Unified Obsidian working-plan MVP | accepted (live locally) | Codex, CLI, and later RD-Code can share one private working plan without moving formal project authority out of the repository or creating a second write lifecycle | Existing writeback stages and create-only publishes immutable project-plan versions; source drift, target races, project leakage, secret content, and absolute-path disclosure fail closed through real MCP/CLI paths; local cutover and fresh live canaries passed |
| M11B. Safe automatic Obsidian memory | accepted (live locally) | Exact trusted Codex clients can recall and create bounded project memory without repeated prompts, while destructive and global actions stay human-gated | Native PreCompact and MCP paths proved deterministic create-only checkpoints/lessons, exact-client reconnect, sandbox-cwd project isolation, kill switch, fail-open outage behavior, full related tests, and P0/P1 review |

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

## Completed Milestone: M2 Review Closure

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

## Completed Milestone: M3 Kernel Distribution Contraction

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

### M3 Batch 3 Verification

The script audit retained the three active release-verification scripts and the
tested `launch-editor.ps1` advanced client launcher. It retired only
`scripts/create-editor-shortcut.ps1`, whose sole reference was a historical
roadmap and whose only function was to create a desktop shortcut for the
deprioritized visual-client path.

Evidence:

- Activity-reference audit: one historical reference, no README, CLI, test,
  workflow, rule, or release-gate reference.
- `test_launch_editor_script.py` remains the contract for the retained launcher.
- Public-snapshot and docs-drift gates do not require the shortcut helper.

P0=0 and P1=0. Do not remove the retained scripts without a separate real-path
replacement or retirement contract.

### M3 Batch 4 Verification

Retire only `product-maturity-roadmap.md` and `launch-cutover-checklist.md`.
At the captured `HEAD` baseline, both were referenced only by the historical
status inventory. Their live decisions are already represented by this
execution root, the repository README files, `LAUNCH_NOW.md`, and
`release-readiness.md`.

Preserve `agent-cluster-unknowns-register.md` because it still records
unverified assumptions. Preserve `design-devframe-mcp-orchestrator-surface.md`
because it contains unique MCP permission, audit, network, and human-gate
boundaries not yet promoted to a stable runtime contract.

Evidence:

- `python -m pytest packages/control-plane/tests/test_docs_drift_validator.py -q`
  -> 23 passed.
- Eight selected public-snapshot tests covering links, the current execution
  root, release boundaries, and reviewer visibility passed.
- Activity-reference audit found only this retirement record after the
  inventory update; `git diff HEAD --check` passed.

Reviewer Index:

| Item | Evidence |
|---|---|
| Changed files | `HANDOFF.md`, `status-document-inventory.md`, and exact deletion of `product-maturity-roadmap.md` plus `launch-cutover-checklist.md` |
| Critical paths | Canonical execution root, historical status inventory, docs drift validator, current-entry links, and frozen release evidence |
| Tests and checks | Docs drift: 23 passed; selected current-entry/release checks: 8 passed; exact reference audit and `git diff HEAD --check` passed |
| Generated artifacts | None |
| Known gaps | The independent read-only reviewer could inspect test sources but its sandbox rejected launching pytest; root-side test runs supplied the execution evidence |
| Review focus | Preserve Recon Receipts, current release evidence, runtime contracts, and status documents with unique unresolved constraints |
| Verdict | PASS; P0=0, P1=0, P2=0, P3=0 |

### M3 Batch 5 Verification

The existing `recon-receipt-local-agent-client-mainline.md` and
`t3code-client-mainline-reuse-assessment.md` cover this client boundary. The
Recon audit found that the dashboard server itself is not redundant: it hosts
read-only state and session inspection, T3/RD-Code adapter endpoints, action
queues, controlled mutation routes, and explicit remote-bind protections. It
must remain independently runnable and release-tested.

The redundant layer was the `devframe code --dashboard` shortcut. It added
`--dashboard`, `--host`, `--port`, `--refresh-seconds`, and `--allow-remote` to
the primary coding command even though every prepared run already prints the
equivalent `devframe dashboard serve --runtime-dir <dir>` command. Batch 5
removes only that shortcut and its bootstrap `-Dashboard` alias. The standalone
dashboard command, server, endpoints, security checks, and client adapters are
unchanged.

Evidence:

- Real RED: three of four focused tests failed because code help still exposed
  `--dashboard`, the production parser still accepted it, and bootstrap still
  generated `-Dashboard`; the standalone remote-bind safety test passed.
- GREEN: the same four tests passed after the contraction.
- Dashboard and CLI regression: 178 passed.
- Control-plane suite: 1,564 passed, 1 skipped, 4 deselected. The deselected
  snapshot cases are blocked in the primary worktree by preserved `.agents`,
  `.aiworkflow/reports`, `.claude`, `.codex`, and `.gsd` local state.
- Installed control-plane wheel smoke passed, including CLI help, code prepare,
  the standalone dashboard, client/T3 endpoints, action queues, controlled
  execution, invalid filters, and rejected PATCH requests.
- The five retired `devframe code` arguments are covered through the production
  parser; the final focused CLI, standalone safety, and bootstrap gate passed 8
  tests.
- A fresh independent read-only review passed with P0=0, P1=0, P2=0, and P3=0.
  The dispatch API accepted the `gpt-5.6-sol` and `high` selectors; this is
  selector attestation, not an internal model self-attestation.

Review focus: verify that no primary-code dashboard launch path remains, the
bootstrap wrapper still supports preview/prepare/execute, standalone dashboard
security and API contracts are preserved, documentation points to the explicit
replacement command, and no historical status snapshot is rewritten as current
authority.

Reviewer Index:

| Item | Evidence |
|---|---|
| Changed files | `README.md`, `HANDOFF.md`, control-plane quickstart/README, `_coding.py`, `_usage.py`, bootstrap docs/templates/wrappers, focused CLI/public-snapshot tests, and wheel smoke assertions; 14 paths total |
| Critical paths | `devframe code` production parser and dispatch, bootstrap preview/prepare/execute, standalone dashboard loopback guard, dashboard/T3/client/action APIs |
| Tests and checks | Real RED; final focused gate 8 passed; dashboard/CLI regression 178 passed; control-plane 1,564 passed and 1 skipped; installed-wheel smoke passed; `git diff --check` passed |
| Generated artifacts | None retained in the public repository |
| Known gaps | Release, deployment, and production validation remain out of scope; strict clean-candidate snapshot remains the root pre-push delivery gate |
| Review focus | Ensure exact staged paths contain no standalone dashboard/API change and the ordinary push remains non-force |
| Verdict | PASS; P0=0, P1=0, P2=0, P3=0 |

### M3 Closure Verdict

Accepted on 2026-07-18. The closure audit confirmed that `products/tutti/`
has zero tracked files, its retained local checkout is ignored, and the retired
snapshot importer has no active execution path. The standalone dashboard and
its API/security contracts remain intact. The final root-help contraction
reduced the primary discovery screen from 48 to 35 lines while preserving all
commands and subcommand help; the complete CLI gate passed 129 tests. No M3
write set remains open.

## Completed Milestone: M4 Executor Equivalence

### Objective

Prove that command and ACP execution remain replaceable adapters: they may
retain different provenance, but they must project the same canonical
governance meaning for an equivalent TaskSpec.

### Verification

The production capability was already present, so this milestone did not
change production code. A durable production-shaped parity test now executes a
real command worker and a mock governed ACP session through
`run_go_dispatch`, persists TeamRuntime events, and reconciles each run through
`build_run_index` using both `go_run` and `team_events` sources.

Both drivers project the same canonical values for `domain`, `profile`,
`outcome`, `review_state`, `gate_state`, and `acceptance_state`. Driver identity
does not enter those governance fields; it remains in source-domain provenance.

Reviewer Index:

| Item | Evidence |
|---|---|
| Changed files | `packages/control-plane/tests/test_go_acp_driver.py`; this execution root records the accepted milestone |
| Critical paths | `run_go_dispatch`; command worker; governed ACP session; TeamRuntime event persistence; `build_run_index` canonical `go_run + team_events` reconciliation |
| Tests and checks | ACP, TeamRuntime, and RunIndex affected regression: 64 passed; docs-drift and Outcome-First policy checks: 32 passed; complete CLI gate: 129 passed; `git diff --check` passed |
| Generated artifacts | Test-only temporary Git repositories, execution reports, TeamRuntime journals, and run indexes; no generated artifact is retained in the public repository |
| Known gaps | Release, deployment, and production provider validation remain outside this milestone; provider/model identity is provenance rather than governance authority |
| Review focus | Preserve semantic parity when adding executors; provider-specific fields must stay in provenance and must not alter review, gate, or acceptance meaning |
| Verdict | Independent review PASS; P0=0, P1=0, P2=0, P3=0 |

### M4 Verdict

Accepted on 2026-07-18 as already implemented, with durable executor-parity
proof added. A future executor must satisfy the same canonical parity contract
before it can be treated as interchangeable.

## Current Milestone: M5 Paper Vertical

### Objective

Run one bounded, synthetic-only paper task through the shipped DevFrame CLI and
canonical governance projection. The executor must produce a review-pending
candidate; an explicit `devframe paper finalize` command may consume a separately
authored independent review and then reuse the existing gate, FinalVerdict, and
RunIndex authority. Do not add another workflow engine, client, provider, or paper
state authority.

### Recon Receipt And Real RED

This section is the durable Recon Receipt for the first M5 repair slice under
`rules/recon.md` RULES recon-001, recon-003, recon-009, and recon-010.

- Resource map: `control_plane.cli` owns `devframe init` and `devframe run`;
  `stage_executor.py` owns the synthetic paper stages; `submission_adapter.py`
  owns the dry-run submission boundary; paper schemas and contracts remain in
  `schemas/` and `packages/agent-acceptance/contracts/`; `run_index.py` owns the
  canonical read projection. Generated runs stay under `.devframe-runtime/`.
- Reuse decision: reuse PyYAML, JSON Schema, the existing pack manifest, paper
  Task IO contracts, submission adapter, FinalVerdict schema, and RunIndex.
  Do not restore the missing private validator scripts or copy the separate
  ai-workflow-hub paper state machine into the control plane.
- Integration risks: fail closed on malformed paper IO, unredacted/private
  content, bypass submission paths, incomplete evidence packs, failed tests,
  or invalid FinalVerdict. Keep synthetic-only and dry-run limitations visible.
- Build decision: add only an in-package paper pipeline gate and route the
  existing stage executor through it. The obsolete `live_handoff_transfer.py`
  is explicitly forbidden by `NO_BYPASS_SUBMISSION_CONTRACT`, has no runtime
  caller, and is superseded by `playwright_bridge.py`; remove it from the
  distribution and documentation rather than allowlisting it.

Production-path RED on 2026-07-18:

```text
devframe init paper_iteration <isolated-project>
devframe run --pipeline packages/control-plane/pipelines/reference_paper_review.yaml --project <isolated-project> --execute
Stages: 4/5 completed
blocking: bypass_check_failed,
paper_task_directory_paper_task_validator_not_found,
paper_task_evidence_pack_paper_task_validator_not_found,
workflow_closure_validator_not_found
```

The failure is in the clean public distribution: `stage_executor.py` and
`devframe pack validate` still call three `packages/agent-acceptance/scripts/`
files that are not shipped. It is not a provider, model, credential, network,
or paper-content failure.

After the shipped gates replaced those dependencies, the same production path
reached 6/7 stages and exposed the next same-slice failure: closure launched the
entire control-plane source test suite and timed out after 60 seconds. Installed
wheels do not ship that test tree, so source pytest is a development/CI gate,
not a valid per-run product dependency. M5 closure must use bounded artifact,
privacy, submission, and bypass checks instead; repository tests remain part of
the delivery verification outside the user run.

The bounded closure then completed 7/7 stages and projected a limited canonical
RunRecord, but the probe found no `TASKSPEC.json` or `execution-report.json`.
It also exposed the literal unrendered template identity `run-paper-paper_id`,
which would collide across newly initialized paper projects. The final M5 delta
is therefore a thin canonical artifact adapter plus deterministic paper-project
template rendering, not a second paper state machine.

The first implementation also exposed four P1 boundary failures in independent
review: the executor manufactured reviewer artifacts and FinalVerdict input,
the synthetic gate accepted authorized real excerpts, the browser bypass was a
whole-file allowlist, and pack validation ignored payload hashes. The repair
keeps execution at `review_pending`, requires exact synthetic/dry-run state,
uses AST reachability for the existing live bridge, validates safe unique ZIP
entries and SHA-256, and adds an explicit external-review finalizer. A second
real path proved `review_pending -> accepted_with_limitation` only after the
independent review JSON passed identity, schema, state, evidence, and pack-hash
checks.

### Frozen First-Slice Write Set

- `packages/control-plane/control_plane/paper_pipeline_gate.py`
- `packages/control-plane/control_plane/stage_executor.py`
- `packages/control-plane/control_plane/cli/_core.py`
- `packages/control-plane/control_plane/cli/app.py`
- `packages/control-plane/control_plane/cli/_usage.py`
- `packages/control-plane/control_plane/run_index.py`
- `packages/control-plane/control_plane/final-verdict.schema.json`
- `packages/control-plane/control_plane/gpt-review-result.schema.json`
- `packages/control-plane/control_plane/live_handoff_transfer.py` (exact deletion)
- `packages/control-plane/pipelines/reference_paper_review.yaml`
- `packages/control-plane/setup.py`
- `packages/control-plane/tests/test_stage_executor.py`
- `packages/control-plane/tests/test_cli.py`
- `packages/control-plane/tests/test_run_index.py`
- `scripts/verify-control-plane-wheel.ps1`
- `docs/README.md`
- this execution root at the milestone boundary

Stop lines: no real paper, browser, provider, network, credential, publication,
new workflow engine, ai-workflow-hub migration, executor-synthesized review, or
executor-synthesized FinalVerdict. The execution slice ends at `review_pending`;
only an explicit governance finalize with an external review may produce the
synthetic `accepted_with_limitation` result. Any path outside this write set
requires a new observed failure and an explicit scope amendment.

### Stop Lines

- No executor-controlled review or FinalVerdict synthesis; explicit finalization
  requires an external review artifact, distinct identity, current evidence
  hashes, and passing paper state/gates.
- No client, worker, or executor acceptance authority.
- No storage, schema, client, Tutti, RD-Code, or provider changes during Recon.

## Current Milestone: M6 Adapter Conformance Entry

### Recon Receipt And Real RED

The accepted M4 parity path is the reuse boundary for this slice:
`go_dispatch.run_go_dispatch` produces the execution and TeamRuntime facts,
`run_index.build_run_index` reconciles them into `canonical_runs`, and the
existing `test_go_acp_driver.py` proves command/ACP semantic equality. The new
surface must remain read-only and must not create another adapter or authority.

Production RED on 2026-07-18:

```text
devframe adapter verify --help
Unknown command: adapter
exit 1
```

The first M6 contract is therefore a bounded offline comparison of one
reference canonical go record and one candidate canonical go record. It fails
closed when either runtime has no unique paired `go_run` + `team_events`
projection, when the candidate lacks adapter provenance, or when canonical
governance fields differ.

### Frozen M6 Write Set And Stop Lines

- `packages/control-plane/control_plane/adapter_conformance.py`
- `packages/control-plane/control_plane/cli/_core.py`
- `packages/control-plane/control_plane/cli/_usage.py`
- `packages/control-plane/control_plane/cli/app.py`
- `packages/control-plane/tests/test_adapter_conformance.py`
- `packages/control-plane/tests/test_cli.py`
- `scripts/verify-control-plane-wheel.ps1`
- this execution root at the M6 milestone boundary

Stop lines: no changes to `go_dispatch.py`, `run_index.py`, ACP transport,
provider/browser integrations, client/dashboard UI, schemas, network, or
production data. The command reads existing runtime evidence and writes no
runtime state.

### M6 Closure Verdict

Accepted locally on 2026-07-18. The new read-only `devframe adapter verify`
command compares one reference and one candidate `canonical_runs` projection;
it requires paired `go_run` + `team_events`, `domain=code`, `profile=go`,
driver provenance, equal canonical governance fields, and an unambiguous run
selection. Missing or divergent evidence returns non-zero without writing
runtime state.

The production RED was the missing CLI route. The final focused suite passed
4 tests, the M4/CLI affected regression passed 140 tests, the installed wheel
constructed two local `execute=true` command runtimes and reported
`Adapter conformance: PASS`, and the complete wheel smoke ended with
`[OK] Control-plane wheel smoke passed`. Independent review reported
P0=0, P1=0, P2=0, and P3=0.

Reviewer Index:

| Item | Evidence |
|---|---|
| Changed files | This execution root; adapter conformance module; CLI core/usage/router; focused conformance and CLI tests; wheel verification; 8 paths total |
| Critical paths | `_select_canonical_go_record`; `verify_adapter_conformance`; canonical RunIndex projection; `devframe adapter verify`; installed-wheel local runtime fixtures |
| Tests and checks | Missing-route RED exit 1; focused GREEN 4 passed; affected regression 140 passed; installed-wheel real-path smoke passed; `git diff --check` passed |
| Generated artifacts | Temporary fixture runtimes and wheel outputs stayed under the smoke temp directory; no runtime state or artifact enters the public repository |
| Known gaps | Real compiler/provider/browser/network execution, release, deployment, push, and merge remain outside M6 |
| Review focus | Preserve paired canonical-source requirements, six-field semantic equality, driver provenance, ambiguity fail-closed behavior, read-only CLI operation, and packaged real-path smoke |
| Verdict | Independent review PASS; P0=0, P1=0, P2=0, P3=0 |

## Completed Milestone: M7 Toolchain Adapter Manifest

### Recon Receipt And Real RED

M7 reuses the installed PyYAML dependency, the existing structured pipeline
validation style, and the CLI's read-only preview pattern. A toolchain manifest
describes a compiler label plus build/test/lint command tokens; it is not an
execution request and must not read credentials or mutate a project. The
manifest validator is a boundary adapter, not a second TaskSpec or runtime
authority.

Production RED on 2026-07-18:

```text
devframe toolchain preview --manifest toolchain.yaml
Unknown command: toolchain
exit 1
```

### Frozen M7 Write Set And Stop Lines

- `packages/control-plane/control_plane/toolchain_manifest.py`
- `packages/control-plane/control_plane/cli/_core.py`
- `packages/control-plane/control_plane/cli/_usage.py`
- `packages/control-plane/control_plane/cli/app.py`
- `packages/control-plane/tests/test_toolchain_manifest.py`
- `packages/control-plane/tests/test_cli.py`
- `scripts/verify-control-plane-wheel.ps1`
- this execution root at the M7 milestone boundary

Stop lines: no command execution, shell/provider/browser integration, env or
credential reads, TaskSpec schema changes, new runtime state, client/dashboard
UI, compiler-specific adapter, or production data.

### M7 Closure Verdict

Accepted locally on 2026-07-18. `devframe toolchain preview --manifest`
validates a provider-neutral YAML manifest and returns a canonical
`domain=code`, `profile=toolchain` preview with `execution=explicit_only`.
The validator requires string IDs, project-relative working directories, and
tokenized build/test commands; it rejects unknown fields, mixed-type YAML keys,
absolute or escaping paths, empty tokens, and all C0/DEL control characters.
It does not execute commands, read environment variables or credentials, or
write runtime state.

The production RED was the missing public CLI route. The final affected suite
passed 145 tests. A newly built and installed wheel reported `toolchain preview
ok` and completed the full control-plane wheel smoke. A clean exported public
snapshot passed, `git diff --check` passed, and independent review reported
P0=0, P1=0, P2=0, and P3=0.

Reviewer Index:

| Item | Evidence |
|---|---|
| Changed files | This execution root; `toolchain_manifest.py`; CLI core/usage/router; focused manifest and CLI tests; wheel verification; 8 paths total |
| Critical paths | `app.main -> cmd_toolchain_preview -> validate_toolchain_manifest`; `yaml.safe_load`; typed unknown-key handling; ID, command-token, and working-directory boundaries; installed-wheel CLI entry |
| Tests and checks | Missing-route RED exit 1; affected regression 145 passed; independent control/path/type probe matrix passed; installed-wheel real-path smoke passed; clean exported public snapshot passed; `git diff --check` passed |
| Generated artifacts | Wheel, virtual environment, manifests, and adapter fixtures were temporary; the retained clean-snapshot clone under the system temp directory is not part of the repository |
| Known gaps | Real compiler execution, provider/browser/network integration, push, PR, merge, release, and deployment remain outside M7 |
| Review focus | Preserve validation before normalization, mixed-key type safety, lexical path containment, token-list-only commands, and the preview's no-execution/no-runtime-write boundary |
| Verdict | Independent review PASS; P0=0, P1=0, P2=0, P3=0 |

## Current Milestone: M8 Governed Toolchain Run

M8 will reuse the existing command executor, TaskSpec boundary, TeamRuntime,
RunIndex, and M6 adapter conformance path. It must not introduce a second
runtime, shell-string command path, compiler-specific plugin, dashboard, or
provider binding. The first batch is read-only Recon: locate the narrowest path
from one validated manifest action to the existing explicit command dispatch,
then freeze a finite write set and a real temporary-project RED before any
production edit.

### M8 Recon Receipt And Real RED

The existing `go_dispatch` path already provides the required packet creation,
explicit token-list `CommandWorker`, TeamRuntime task/result events, and
canonical RunIndex projection. It is the reuse path. The missing contract is a
provider-neutral wrapper that selects one already-validated manifest action,
rechecks the manifest bytes, and uses that command as one governed task.

Real RED on 2026-07-18, using a temporary project and manifest at
`.devframe-runtime/probes/m8-toolchain-run-1784367590004/`:

```text
devframe toolchain run --manifest <probe>\toolchain.yaml --action test \
  --project <probe> --execute
Usage: devframe toolchain preview --manifest <path> [--format text|json]
exit 1
```

### Frozen M8 Write Set And Stop Lines

- `packages/control-plane/control_plane/toolchain_manifest.py`
- `packages/control-plane/control_plane/toolchain_execution.py`
- `packages/control-plane/control_plane/go_dispatch.py`
- `packages/control-plane/control_plane/worker.py` (preserve a failed worker's
  specific rejection evidence while keeping the outer result fail-closed)
- `packages/control-plane/control_plane/cli/_core.py`
- `packages/control-plane/control_plane/cli/_usage.py`
- `packages/control-plane/control_plane/cli/app.py`
- `packages/control-plane/tests/test_toolchain_execution.py`
- `packages/control-plane/tests/test_cli.py`
- `scripts/verify-control-plane-wheel.ps1`
- this execution root at the M8 milestone boundary

Stop lines: no shell-string execution, implicit execution, model/provider
binding for toolchain actions, arbitrary environment or credential reads, new
runtime/storage authority, client/dashboard/Tutti/RD-Code changes, or public
runtime artifacts. Runtime evidence stays under ignored `.devframe-runtime`.

### M8 Closure Verdict

Accepted locally on 2026-07-18. `devframe toolchain run` defaults to a
no-write preview and executes one tokenized build/test/lint action only after
explicit `--execute`. The CLI-approved manifest bytes are bound by SHA-256 to
the worker's single read and parse; manifest replacement, runtime placement
inside the project, cwd escape, missing working directories, and implicit
`.cmd`/`.bat` shell adapters fail closed. The command runs in a dedicated
process group, timeout cleanup covers descendants, and a failed worker's
specific rejection report remains attached beneath the outer failed status.
Canonical projection stops at `review_pending` and does not invent a model or
provider identity.

The production RED was the missing public `toolchain run` route. A second
real-path RED proved that `CommandWorker` previously overwrote the worker's
manifest-drift rejection report. The final affected suite passed 235 tests
with one platform-specific skip. The full control-plane suite passed 1,607
tests with two skips in the clean candidate clone. A newly built and installed
wheel completed the full smoke, including preview, explicit execution, marker,
and canonical `review_pending` checks. The clean public-snapshot gate and
`git diff --check` passed. Independent review reported P0=0, P1=0, P2=0, and
P3=0.

Reviewer Index:

| Item | Evidence |
|---|---|
| Changed files | This execution root; `toolchain_manifest.py`; new `toolchain_execution.py`; `go_dispatch.py`; `worker.py`; CLI core/usage/router; new focused execution tests; wheel verification; 10 paths total |
| Critical paths | Default preview and explicit execute; immutable approved manifest bytes; project/runtime/cwd containment; batch-shell rejection; process-group timeout cleanup; fail-closed worker report preservation; TeamRuntime and canonical RunIndex `review_pending` projection |
| Tests and checks | Missing-route and overwritten-report REDs; affected regression `235 passed, 1 skipped`; clean-clone full suite `1607 passed, 2 skipped`; installed-wheel smoke `[OK]`; clean public snapshot `[OK]`; `git diff --check` passed with only an LF-to-CRLF notice |
| Generated artifacts | TaskSpec: `.devframe-runtime/probes/m8-toolchain-run-1784367590004/TASKSPEC.json`; clean candidate clone: `.devframe-runtime/isolated/m8-final-1784375115911`; wheel, venv, manifests, runtime, and fixture scripts were temporary and untracked |
| Known gaps | Windows cannot execute the POSIX-only process-group integration probe; a POSIX-only real test and an independent signal-sequence test cover the branch. Real provider/network execution, push, PR, merge, release, and deployment remain outside M8 |
| Review focus | Preserve first-read SHA binding, no-write preview, exact project/runtime/cwd boundaries, fail-closed outer status, descendant cleanup, empty provider provenance, and the prohibition on acceptance before independent review |
| Verdict | Independent `gpt-5.6-sol` high review PASS; P0=0, P1=0, P2=0, P3=0 |

## Completed Milestone: M9 Toolchain Run Inspection

M9 is a read-only product slice. It must let a user inspect one governed
toolchain run without decoding generic go metadata or opening packet files.
It reuses existing go-run metadata for project/worker/report provenance and the
canonical RunIndex for review/acceptance state. It does not execute, resume,
review, accept, finalize, or mutate a run.

### M9 Recon Receipt And Real RED

The durable Recon Receipt and TaskSpec are under ignored runtime state:

- `.devframe-runtime/probes/m9-toolchain-status-1784377692703/RECON-RECEIPT.md`
- `.devframe-runtime/probes/m9-toolchain-status-1784377692703/TASKSPEC.json`

The reuse decision is to adapt the existing `load_go_run_result()` and
`build_run_index()` paths. Generic code status already reads go metadata but
does not expose canonical review state. M8's action, approved manifest SHA-256,
and cwd currently exist only inside worker command/report text; M9 must not
parse those strings as a public contract. The smallest missing provenance is a
bounded `toolchain` object in the existing go-run metadata.

Installed-wheel RED on 2026-07-18, from committed `df5f67ec`:

```text
devframe toolchain status --runtime-dir <empty-runtime>
Usage: devframe toolchain preview --manifest <path> [--format text|json]
exit 1
```

### Frozen M9 Write Set And Stop Lines

- `packages/control-plane/control_plane/go_dispatch.py`
- `packages/control-plane/control_plane/toolchain_inspection.py`
- `packages/control-plane/control_plane/run_index.py`
- `packages/control-plane/control_plane/cli/_core.py`
- `packages/control-plane/control_plane/cli/_usage.py`
- `packages/control-plane/control_plane/cli/app.py`
- `packages/control-plane/tests/test_toolchain_inspection.py`
- `packages/control-plane/tests/test_run_index.py`
- `packages/control-plane/tests/test_cli.py`
- `scripts/verify-control-plane-wheel.ps1`
- this execution root at the M9 milestone boundary

Stop lines: no command execution or resume behavior, no review/acceptance or
finalization mutation, no second runtime/store/index, no command-string report
parsing, no dashboard/client/provider/network/credential behavior, and no
public runtime artifacts. Missing, corrupt, non-toolchain, or non-canonical
runs must fail closed.

### M9 Closure Verdict

Accepted locally on 2026-07-19. `devframe toolchain status` now projects the
action, approved manifest digest, working directory, worker/report provenance,
and canonical review/acceptance state through one read-only CLI path. The exact
metadata bytes parsed by inspection are read from one contained handle and
hashed; the canonical `go_run` source must carry the same run ID and source
hash. A same-ID A/B metadata replacement therefore fails closed instead of
combining provenance with another snapshot's governance state.

The production-path RED returned success while exposing replacement project
and action data with the original canonical state. The repaired path exits 1
with no JSON stdout. Toolchain inspection passed 26 tests; RunIndex plus
inspection passed 74 tests with one platform skip; the related manifest,
execution, inspection, index, and CLI set passed 219 tests with two platform
skips. A newly built and installed wheel completed `devframe toolchain status`,
the exact 11-path isolated candidate passed the public-snapshot gate, and
`git diff --check` passed. Independent review reported P0=0, P1=0, P2=1, and
P3=0. The P2 is explicit fail-closed behavior on non-Darwin BSD variants; it
does not permit mixed state or authority escalation.

Reviewer Index:

| Item | Evidence |
|---|---|
| Changed files | This execution root; `go_dispatch.py`; new `toolchain_inspection.py`; `run_index.py`; CLI core/usage/router; new focused inspection tests; RunIndex and CLI tests; wheel verification; 11 paths total |
| Critical paths | Structured toolchain provenance; explicit/latest selection; handle-bound metadata/journal reads; exact metadata-to-canonical source hash binding; report containment; CLI text/JSON and installed-wheel routing |
| Tests and checks | Same-ID A/B RED then GREEN; inspection `26 passed`; RunIndex plus inspection `74 passed, 1 skipped`; related regression `219 passed, 2 skipped`; installed-wheel smoke `[OK]`; isolated public snapshot `[OK]`; focused Ruff and `git diff --check` passed |
| Generated artifacts | Recon, TaskSpec, repair report, and independent reviews remain under ignored `.devframe-runtime/probes/m9-toolchain-status-1784377692703/`; the hash-matched candidate remains under ignored `.devframe-runtime/isolated/m9-final-1784379702491/` |
| Known gaps | Darwin `F_GETPATH` has deterministic contract tests but no macOS-host run; FreeBSD and other unproven BSD variants fail closed; protected concurrent methodology/humanize/ai-check paths remain outside M9 |
| Review focus | Preserve exact metadata/canonical source-hash equality, one-handle containment and bytes, read-only status behavior, generic-run isolation, and the prohibition on acceptance mutation |
| Verdict | Independent `gpt-5.6-sol` high review PASS; P0=0, P1=0, P2=1, P3=0 |

## Completed Milestone: M10A Governed Workflow Profiles

Accepted locally on 2026-07-19. Trusted coding and paper entrypoints now select
deterministic, versioned Profile plans and record them through the existing
TaskSpec, rdgoal packet, go metadata, RunIndex, and paper pipeline paths. The
contract records ordered stages, per-stage permissions, human gates, artifact
and evidence requirements, Skill availability, source fingerprint, selection
source, and Profile fingerprint. It remains `planned_only`: no production path
iterates or executes its stages, selection creates no `skill_usage`, and it
cannot produce review, FinalVerdict, or acceptance.

The ignored Recon Receipt, TaskSpec, and production-path RED are under
`.devframe-runtime/probes/m10a-workflow-profile-1784393403104/`. Coding and
paper TaskSpecs originally lacked an auditable Profile (`2 failed`); the final
contract and real paths pass 11 focused tests. Unknown or free-text-like work
types normalize to `generic`, require a human decision, and carry no stages.
TaskSpec validation requires the outer and inner work types to match and
requires Profile fields to appear as one coherent pair.

The affected production and compatibility set passed 539 tests with one
platform skip. A freshly built and installed wheel exercised coding, paper,
toolchain, rdgoal, RunIndex, client, and dashboard smoke paths and exited 0.
The exact candidate passed the isolated public-snapshot gate, focused Ruff and
`git diff --check`. Independent `gpt-5.6-sol` high review closed one schema P1
and returned P0=0, P1=0, P2=1, P3=0 after repair. The retained P2 is policy
resolver failure falling back to default planning constraints; M10A has no
execution consumer, but M10B must fail closed before consuming any stage.

Reviewer Index:

| Item | Evidence |
|---|---|
| Changed files | This execution root; seven existing control-plane modules; canonical and test-frame TaskSpec schemas; one focused Profile test; wheel verification; 12 accepted paths total |
| Critical paths | Structured work type to deterministic resolver; resolver to TaskSpec/packet; go metadata to RunIndex projection; paper pipeline to planned-only TaskSpec; schema coherence and restrictive project/P0 policy overlay |
| Tests and checks | Missing-path RED `2 failed`; focused Profile/schema `11 passed`; affected real-path set `539 passed, 1 skipped`; installed-wheel smoke `[OK]`; isolated public snapshot `[OK]`; Ruff, AST, schema-mirror, and `git diff --check` passed |
| Generated artifacts | Recon, TaskSpec, and RED remain under ignored `.devframe-runtime/probes/m10a-workflow-profile-1784393403104/`; exact snapshot remains under ignored `.devframe-runtime/isolated/m10a-final-1784419752090/` |
| Known gaps | Policy-resolution exceptions must fail closed before M10B execution; fingerprint/adoption remains descriptive until M10B adds an execution-time rejection; Agent Reach, Humanize, and ai-check execution remain deferred |
| Review focus | Preserve planned-only behavior, outer/inner schema coherence, generic human-required fail-closed behavior, exact Skill/Profile fingerprints, and the ban on selection self-certifying usage or acceptance |
| Verdict | Independent review PASS; P0=0, P1=0, P2=1, P3=0 |

## Completed Milestone: M10B Governed Coding Canary

### Objective

Let one offline coding entrypoint consume the narrowly adopted M10A
`governed-coding-v1` pre/post stage plan through an explicit opt-in, close
KERNEL-003 by making policy-resolution failure fail closed before any Profile
stage is consumed, and register the externally sourced methodology skills
without granting them any authority.

### Delivered Behavior

`devframe code` gains an explicit `--workflow-canary` opt-in that accepts only
the structured `"@go read <goal>"` coding form. The canary consumes exactly
two frozen offline stages (`pre:intent` intent-framing-gate and
`post:evidence` evidence-driven-acceptance), constructs no worker, subprocess,
ACP session, provider, network, or credential access, and produces only a
`Review Status: draft` ExecutionReport that enters the ordinary review-pending
channel. Project `skills.json` policy bytes, the resolved Profile, and every
bound skill source are bound by double-read SHA-256 fingerprints under one
`binding_fingerprint`; resume re-runs the full preparation from current disk
state. Missing, malformed, or unreadable policy fails closed with zero side
effects; authority injection (`final_ready`, `root_accepted`, `FinalVerdict`,
forged or downgraded envelope markers) is rejected over a closed key set.

The slice also registers the pinned third-party `@humanize` and `@ai-check`
methodology skills with documented use boundaries in
`docs/agent-runtime/methodology-skills.md`, adds the `rdpaper` cluster mention
target with a focused roster test, and documents the contract in
`docs/agent-runtime/coding-workflow-canary.md`.

### Verification

- Focused suites: workflow profiles plus full CLI `181 passed`; cluster
  control `37 passed`; docs drift `23 passed`; stage executor `14 passed`.
- Full control-plane suite: `1752 passed, 8 skipped`, 7 environment-blocked
  failures — 4 pre-existing public-snapshot cases short-circuited by preserved
  local root directories, and 3 MCP cases blocked by the ambient user-scope
  `DEVFRAME_MCP_TOKEN` from the M11A live cutover (all 3 pass with the
  variable cleared; the slice touches no MCP or dashboard path).
- Installed-wheel smoke: 62 stages, `[OK] Control-plane wheel smoke passed`.
- Real-path probe: 42 checks GREEN through the installed `devframe` entry —
  the prepare/execute happy path stays `review_pending` with no acceptance
  artifact; policy drift, authority injection, and non-coding activation all
  fail closed with byte-identical metadata and zero runtime writes.
- Static: no new Ruff findings, `compileall` 6/6, clean `git diff --check`,
  and both intake LICENSE files verified as complete MIT texts.
- Independent non-author review: PASS with P0=0, P1=0, P2=0, P3=4
  (documentation precision, one redundant read-only CLI resolve, pre-existing
  Ruff F401s, and this execution-root record — all non-blocking).

Reviewer Index:

| Item | Evidence |
|---|---|
| Changed files | `methodology_dispatch.py`; `go_dispatch.py`; `stage_executor.py`; CLI `_coding.py` and `_usage.py`; `cluster_control.py`; workflow-profile, CLI, and cluster-control tests; `docs/agent-runtime/methodology-skills.md`; new `docs/agent-runtime/coding-workflow-canary.md`; `tools/skills/humanize/` and `tools/skills/ai-check/`; this execution root; 16 paths total |
| Critical paths | Fail-closed policy read before Profile resolution; double-read SHA-256 policy/profile/skill binding under one `binding_fingerprint`; resume full re-preparation; normalized authority-key rejection over a closed envelope; worker-free stage consumption; draft-only reporting through the guarded ingest path |
| Tests and checks | Focused 181+37+23+14 passed; full suite `1752 passed, 8 skipped` with the 7 environment-blocked failures explained above; wheel smoke `[OK]`; 42-check real-path probe GREEN; adversarial probes (forged acceptance, fabricated stage results, path traversal, case-variant authority keys, reordered bindings, pre-seeded `FINAL_VERDICT.json`) all fail closed |
| Generated artifacts | Probe fixtures and gate logs remain under the session scratchpad; no runtime artifact enters the public repository |
| Known gaps | The upstream `harshaneel/humanize` pin is recorded but not network-verified; the ambient `DEVFRAME_MCP_TOKEN` leaks into three MCP tests (test-isolation follow-up); a Windows `os.replace` flake in `test_start_cluster_run_records_and_lists` (retry follow-up); one redundant read-only canary resolve in the CLI preview path |
| Review focus | Preserve fail-closed policy resolution order, immutable binding fingerprints, closed envelope key sets, authority-field rejection, and the draft-only evidence boundary |
| Verdict | Independent non-author review PASS; P0=0, P1=0, P2=0, P3=4 non-blocking |

### M10B Verdict

Accepted locally on 2026-07-26. KERNEL-003 is closed: policy-resolution
failure now fails closed with zero side effects before any Profile stage is
consumed. The canary remains the only Profile execution consumer, remains
opt-in and offline, and cannot produce review, FinalVerdict, or acceptance.
Push, PR, merge, and release remain separate human gates.

## Completed Milestone: M11A Unified Obsidian Working-Plan MVP

### Objective

Make current `main` the only maintained Obsidian Memory implementation for the
first useful product slice. `HANDOFF.md` remains the formal execution root;
Obsidian stores one bounded private working plan per project. The Memory module
owns schema, scope, source binding, and safe recall. Existing `writeback.py`
remains the only proposal, human approval, mutation, and audit owner. CLI and
MCP remain stateless adapters.

### Recon, Contract, And RED

The ignored Recon Receipt and TaskSpec are under `.devframe-runtime/recon/` and
`.devframe-runtime/contracts/`. They reconcile the fixed candidate at
`0b60c1d9d771` against current main and explicitly reject wholesale merge, the
2,871-line activation controller, parallel stores, Link as an MVP dependency,
automatic memory, global configuration changes, and real private-Vault writes.

The real production RED was the missing `control_plane.obsidian_memory` import
from the new MCP/CLI contract test. GREEN requires MCP proposal -> existing
human approval -> bounded recall plus CLI propose -> exact request-ID approval,
with source-byte binding and atomic create-only target publication.

### Frozen Write Set

- `packages/control-plane/control_plane/obsidian_memory.py`
- `packages/control-plane/control_plane/writeback.py`
- `packages/control-plane/control_plane/mcp_server.py`
- `packages/control-plane/control_plane/cli/_memory.py`
- `packages/control-plane/control_plane/cli/app.py`
- `packages/control-plane/control_plane/cli/_usage.py`
- `packages/control-plane/control_plane/dashboard.py`
- `packages/control-plane/tests/test_obsidian_project_plan.py`
- `docs/agent-runtime/obsidian-memory.md`
- this execution root

Existing writeback/MCP tests may receive focused assertions only if a real
regression requires them. The protected methodology, Humanize, and ai-check
candidate paths remain outside this slice.

### Acceptance And Stop Lines

- Focused real paths and affected writeback/MCP regressions pass.
- Installed-wheel CLI and isolated public-snapshot gates pass.
- Actual diff contains no activation controller, parallel store, private Vault,
  runtime state, global config, Link dependency, automatic apply, or deletion.
- Independent review reported P0=0, P1=0, P2=0, and P3=0 before root acceptance.
- The human-authorized live Vault/MCP Hook switch is configured against the
  current wheel; fresh MCP, CLI, and project-scoped SessionStart canaries plus
  independent live-state review pass before root acceptance. Push, PR, merge,
  and release remain separate human gates.

### M11A Accepted Local Slice

The bounded implementation was accepted locally as the only maintained project
working-plan path on current `main`. It derives immutable, create-only Obsidian
notes from the current repository `HANDOFF.md`; routes proposal, explicit
approval, mutation, and audit through existing writeback; and exposes stateless
CLI and MCP adapters. No live private Vault, activation controller, parallel
store, Link dependency, automatic apply, or global configuration change enters
the slice.

Production-path RED -> GREEN and review repairs bind approval to the exact
previewed project-plan action, proposal-time Vault and source physical
identities, and the current source SHA-256 before and around publication.
Create-only recovery requires a matching audit, Dashboard approval uses the
plan-specific validator, malformed UTF-8 fails with a controlled error, secret
patterns include GitHub OAuth and encrypted private keys, and recall returns no
absolute project, Vault, runtime, or target path.

The affected regression passed 121 tests with four platform skips. A fresh
verification worktree passed all 1,720 control-plane tests with six platform
skips, focused Ruff on the M11A-attributable files, compileall, `git diff
--check`, and the public-snapshot gate. The installed-wheel gate passed with
wheel SHA-256
`45cca1e516b7c37018cc19f0276e055fcd913c6d98a314db1ddd085448798ca2`.
Its installed CLI canary (PowerShell 7.6) returned propose/approve/recall exits
`3/0/0`, created one managed note, recalled `current`, and exposed zero
absolute roots. The local implementation acceptance gate is closed; the live
cutover is active locally under its separate evidence gate, and remote delivery
remains human-gated.

### Live Cutover Accepted Locally

The human-authorized local cutover replaces the stale `memory serve` MCP entry
and old upstream recall hook with the current mainline wheel. The active server
is loopback-only at `/mcp` and requires the existing DevFrame bearer token.
The Codex MCP registration permits only `recall_project_plan` and
`propose_project_plan`; the latter only stages a proposal, so Vault publication
still requires exact human approval through canonical writeback.

The isolated runtime uses wheel SHA-256
`45cca1e516b7c37018cc19f0276e055fcd913c6d98a314db1ddd085448798ca2`.
Its Memory and MCP module hashes match the accepted M11A files. SessionStart
uses a bounded, project-scoped, read-only wrapper over `memory plan recall`;
the Codex global instructions name the same current tools. The old isolated
runtime is no longer referenced by MCP or the hook, has no listener, and
remains intact only for rollback.

The first real live proposal wrote no Vault file before exact request-ID
approval, then create-only publication produced one managed note. Fresh CLI
and MCP probes recalled `current` with zero absolute-path leaks. SessionStart
allows only a fully qualified repository root or child path; foreign projects,
similar prefixes, rooted-relative paths, missing or malformed input, and an
oversized payload fail closed before service startup without plan content or
path disclosure. The real at-logon task cold-started to `Ready`, enabled, last
result zero, one loopback listener, and the expected runtime process chain;
warm Hook probes completed below the configured timeout with stable PIDs.

The managed MCP block was reconciled without replacing unrelated Codex
provider or MCP settings, and the installed runtime module hashes still match
the accepted source. Independent phase-1 live review closed P0/P1/P3 and
authorized final source binding. One P2 environment advisory remains: shell
test wrappers may keep tracking a detached service after it has bound, while
the actual scheduled task and warm Hook lifecycle complete normally. Exact
final note/source binding and one last independent read-only reconciliation
must pass before this closeout is committed.

Reviewer Index:

| Item | Evidence |
|---|---|
| Changed files | Accepted implementation: `docs/status/HANDOFF.md`; `docs/agent-runtime/obsidian-memory.md`; `control_plane/obsidian_memory.py`; `control_plane/writeback.py`; `control_plane/mcp_server.py`; `control_plane/dashboard.py`; CLI `_memory.py`, `app.py`, and `_usage.py`; `tests/test_obsidian_project_plan.py`; 10 paths total. Live closeout: `docs/status/HANDOFF.md` only |
| Critical paths | Project/source validation and immutable note derivation; proposal preview and action binding; exact request-ID approval; handle-bound source/root revalidation; atomic create-only publication and audit recovery; bounded recall; CLI, MCP, and Dashboard adapters |
| Tests and checks | Production RED -> GREEN; focused Obsidian `68 passed, 3 skipped`; writeback/MCP `58 passed, 1 skipped`; Dashboard/MCP `17 passed`; repair probes `7 passed`; affected `121 passed, 4 skipped`; fresh live affected `143 passed, 4 skipped` with the live token deliberately removed only from the isolated test process; fresh full control-plane `1720 passed, 6 skipped`; Ruff on M11A-attributable files, compileall, and `git diff --check` passed; public snapshot passed; latest wheel verification passed with SHA-256 `45cca1e516b7c37018cc19f0276e055fcd913c6d98a314db1ddd085448798ca2`; isolated canary `3/0/0`, one note, `current`, zero root leaks; live MCP initialize/list/pre-consent/`allow_once`/recall; 12 reject and 3 allow SessionStart scope probes; actual scheduled-task cold start; final note/source binding canaries |
| Generated artifacts | Recon: `.devframe-runtime/recon/recon-obsidian-memory-unification-20260719.md`; TaskSpec: `.devframe-runtime/contracts/m11a-unified-obsidian-plan-mvp.md`; canary: `.devframe-runtime/probes/m11a-installed-memory-canary.ps1`; fresh verification tree: `.devframe-runtime/verify/m11a-final-601b2b9788f941e1af0d1f441dcd6ae3`; retained wheel is identified by the SHA-256 above (its local temp path stays out of public docs) |
| Known gaps | A shell/ProcessStartInfo observer can continue tracking the detached service after successful bind; the real scheduled task returns `Ready`/zero and warm Hooks pass, so this remains a non-blocking P2 environment advisory. A newly started Codex task must instantiate the restored MCP registration and complete its normal connection-consent gate; push, PR, merge, release, and deployment remain human-gated and unexecuted |
| Review focus | Preserve proposal-time physical identity and current source-byte binding; pre/post-publish rechecks; preview/action coherence; create-only audit-backed recovery; secret rejection; bounded path-free responses; no second write authority |
| Verdict | M11A live cutover accepted locally after exact final binding and independent read-only reconciliation; P0=0, P1=0, P2=1 non-blocking environment advisory, P3=0 |

## Execution Protocol

Use the risk profiles in
`packages/agent-acceptance/policies/OUTCOME_FIRST_DELIVERY_POLICY.md` and the
operating lanes in `docs/agent-runtime/verification-gates.md`.

1. **Select**: inspect committed `HEAD`, the current failure, and this file;
   freeze one coherent outcome, write set, non-goals, and risk profile. Reuse an
   existing Recon Receipt, and open Recon only when `rules/recon.md` triggers.
2. **Implement**: make the smallest reversible batch. Require a real RED for a
   P0/P1 failure or changed production behavior when the path can be exercised;
   do not manufacture RED cases for wording-only work.
3. **Verify**: run focused evidence for the selected profile. Add affected
   integration/build checks for medium work, and reserve broad/full suites plus
   mandatory independent review for the milestone, PR, or high/critical gate.
4. **Accept and deliver**: reconcile the actual diff once. Follow the selected
   review profile, then use root-only exact staging and one logical commit.
   Push, PR, merge, release, and deployment retain the human gates in
   `AGENTS.md`.
5. **Record at the natural milestone boundary**: update this file once with
   the outcome, decisive evidence, residual risk, and next finite candidate.
   Do not create status-only batches or count Goal updates, polling, and report
   repetition as delivery.

For ordinary low- and medium-risk delivery, governance effort should remain
near or below the policy's coarse 20 percent budget. When it does not, remove
duplicate suites, reports, polling, and reviewer retries before changing a hard
safety gate.

One finding batch gets one bounded repair batch, one affected regression, and
one re-review. Do not turn unchanged polling, repeated plans, or intermediate
status narration into additional delivery stages.

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
| 2026-07-18 | Keep the dashboard as optional diagnostics but remove its shortcut from `devframe code` | The server has real client/API and safety duties; automatic launch parameters make the primary coding loop wider without adding unique capability |
| 2026-07-18 | Accept M3 Batch 5 after the focused finding was repaired and independently re-reviewed | Five retired arguments now have production-parser coverage; standalone dashboard and API boundaries are unchanged; P0/P1/P2/P3 are zero |
| 2026-07-18 | Replace the fixed nine-step milestone ritual with the existing Outcome-First risk profiles | The old verification guide contradicted the normative policy and imposed release-shaped work on low-risk batches; L0-L3 operating lanes now preserve hard gates while selecting proportionate evidence |
| 2026-07-18 | Accept M3 after the distribution closure audit and root-help contraction | Tutti is external and ignored, the importer is retired, the dashboard remains an explicit optional diagnostic, and root discovery is concise without removing capability |
| 2026-07-18 | Accept M4 as already implemented and retain a durable command/ACP parity test | Both executors traverse the production dispatch, TeamRuntime, and canonical RunIndex path with identical governance semantics; driver identity remains provenance |
| 2026-07-18 | Accept M5 after explicit external-review finalization was made fail-closed | The executor stops at review pending; current bytes, live bypass state, manifested hashes, attested reviewer identity, and duplicate verdict paths are revalidated before limited acceptance |
| 2026-07-18 | Accept M6 after adding the offline adapter conformance entry | A third-party command-style runtime can be compared against canonical code/go governance semantics without a new runtime, provider, or write authority |
| 2026-07-18 | Accept M7 and promote M8 to read-only Recon | Toolchain manifests now fail closed through the installed CLI without executing commands; the next product gap is explicit reuse of the existing governed command path |
| 2026-07-18 | Accept M8 and promote M9 to read-only Recon | One manifest action now traverses the governed command, evidence, team, and canonical review-pending path; the next user-facing gap is concise inspection of that result without exposing a second runtime authority |
| 2026-07-19 | Accept M9 and promote M10A to read-only Recon after exact delivery | Toolchain status now binds the exact parsed metadata bytes to canonical governance provenance; automatic workflow work must begin with a deterministic contract and missing-path RED, not external Skill execution or free-text guessing |
| 2026-07-19 | Accept M10A and queue one offline coding canary | Structured entrypoints now produce auditable planned-only Profiles without executing Skills; the next slice must first close policy-resolution failure and then prove one adopted, fingerprint-bound coding rule without hooks or external capabilities |
| 2026-07-19 | Promote unified Obsidian working plans before new client features | Shared private context is on the single external-brain product spine; current main must absorb only the bounded candidate behavior and reuse canonical writeback before RD-Code, Web AI, or automatic memory expands the surface |
| 2026-07-20 | Accept M11A locally and close MEMORY-001 | The fresh full suite, latest installed wheel canary, public-snapshot gate, exact diff checks, and independent read-only review all passed; live Vault/MCP Hook cutover and remote Git delivery remain explicit human gates |
| 2026-07-22 | Accept and activate M11A live locally under the existing human gate | The current accepted wheel now owns the loopback MCP and project-scoped SessionStart path; create-only publication, current recalls, startup task, token boundary, input isolation, path-redaction probes, and independent review pass while the old runtime remains rollback-only |
| 2026-07-26 | Repair the staged all-NUL `docs/status/HANDOFF.md` index blob by restaging the intact working-tree bytes | A crash-zeroed file was staged at 13:22; forensic search across editor histories, dangling blobs, and agent logs found no recoverable variant, and committing the unrepaired index would have destroyed the execution root |
| 2026-07-26 | Accept M10B with the methodology-skills intake and the rdpaper mention target, and close KERNEL-003 | Full affected gates, installed-wheel smoke, a 42-check real-path canary probe, and an independent non-author review (P0/P1/P2 = 0) passed; policy-resolution failure is fail-closed before any stage consumption |
| 2026-07-26 | Register the lost QREM-B7/B8 remediation as open debt QUAL-001 instead of silently dropping it | The remediation code was never committed and is gone from disk; renewal or write-off is an explicit owner decision backed by the retained `.aiworkflow/` specs |
| 2026-07-27 | Accept M11B live locally and close MEMORY-002 without widening destructive authority | Exact-client safe tools, sandbox-cwd project binding, immutable/idempotent checkpoint and lesson capture, native lifecycle and installed MCP probes, clean related gates, and P0/P1 review passed; plan/global publication, overwrite/delete, Git history, and remote delivery remain separate human gates |

## Next Action

M11B has no remaining repository implementation action in this slice. Review
the exact local Reviewer Index, then use a separate human gate for any local
acceptance commit, push, PR, merge, or release. No remote Git effect has been
performed. Vault Git history, OS-process attestation, and any broader automatic
publication are new scoped decisions, not implicit continuation work.

## Session Handoff — 2026-07-26 — Universal Governance Pilot

This is the latest continuation authority. It supersedes the older `Next
Action` above for scheduling, but does not grant acceptance to any candidate.
Current source, Git, tests, and independent review outrank remembered status.

### User intent

Build a provider-neutral governance layer that Codex, RD-Code/T3 Code, Claude
Code, and OpenCode can share. Git, the lifecycle ledger, evidence, review, and
integration remain authoritative; chat memory and executor reports do not.

Communication preference: concise, direct Chinese. Lead with completed,
blocked, and next action.

### Live repository boundary at handoff capture

- Canonical checkout: `<canonical-local-checkout>`.
- Branch: `codex/rdcode-secret-containment`.
- HEAD: `77b594f8342a9d840bc660050e6319859a551468`.
- The checkout was already dirty. Recheck it before every decision and
  preserve all existing changes. Known modified paths:
  - `docs/agent-runtime/methodology-skills.md`
  - `docs/status/HANDOFF.md`
  - `packages/control-plane/control_plane/cli/_coding.py`
  - `packages/control-plane/control_plane/cli/_usage.py`
  - `packages/control-plane/control_plane/cluster_control.py`
  - `packages/control-plane/control_plane/go_dispatch.py`
  - `packages/control-plane/control_plane/methodology_dispatch.py`
  - `packages/control-plane/control_plane/stage_executor.py`
  - `packages/control-plane/tests/test_cli.py`
  - `packages/control-plane/tests/test_workflow_profiles.py`
- Known untracked user-owned paths:
  - `tools/skills/ai-check/`
  - `tools/skills/humanize/`
- Never reset, clean, stash, restore, rebase, or broadly stage these paths.

### Earlier RD-CODE evidence boundary

The earlier takeover work established that RD-CODE was not ready for user
delivery. Three candidates were kept isolated and unstaged:

- R1F launch/install candidate: independently reviewed after a real product
  rework; preserve its frozen evidence rather than treating it as an implicit
  integration.
- Paper composed candidate: current raw bytes had drifted from the frozen
  digest and therefore remained `REWORK`.
- Project re-entry/identity candidate: source review passed, but review PASS
  alone was not root acceptance or permission to commit.

Evidence-custodian rule: when `REWORK` is only stale byte evidence and the
original author is unavailable, a takeover custodian may refreeze the same
exact paths only after focused tests and safe real-path probes pass. The
custodian may not modify implementation, expand scope, stage, commit, push, or
review their own evidence. A distinct non-author reviewer must still issue the
only `PASS` or `REWORK` verdict.

### Trusted Core v1 local candidate

- Worktree: `<trusted-core-local-worktree>`.
- Branch: `codex/trusted-core-v1`.
- Local commit: `403046bfa2dd0d875d8cba93504307438b5c43f8`
  (`fix(control-plane): harden trusted execution core`).
- Status at capture: clean, local only; not pushed, merged, or deployed.
- Delivered candidate behavior:
  - verified linked-worktree execution for live writes;
  - runtime-inside-repository fail-closed behavior;
  - signed execution receipts and a controller-signed full run roster;
  - authenticated v2 path leases, heartbeat, and fencing;
  - strict toolchain snapshot/roster validation;
  - minimized stdout/stderr persistence.
- Honest evidence boundary: affected expansion `383 passed, 1 skipped`, public
  snapshot passed, and focused non-author review passed. Do not claim the full
  repository suite passed; an earlier full-suite attempt exceeded five minutes.
- Residual P2: an adversarial process running as the same OS user is not
  isolated by filesystem HMAC. True isolation needs a separately approved
  sandbox, service account, or privileged controller.
- Do not copy or cherry-pick this candidate into the dirty canonical checkout.
  Reconcile it only from a fresh clean baseline with independent review.

### RD Paper universal-governance pilot

- Controller thread: `019f8871-28a2-70f0-9b67-cc3ae83a8aff`.
- Controller model request: `gpt-5.6-sol` / `medium`.
- Coding executor request: OpenCode `huoshan/glm-5-2`.
- Model identities are `REQUESTED_UNVERIFIED` unless the runtime provides
  attestation.
- Synthetic local T1--T12 governance pilot: `12 PASS / 0 PARTIAL / 0 BLOCKED`.
- Final governance validation:
  - narrow E2E: `29 passed`;
  - full suite: `306 passed`, `7` Windows symlink-capability skips;
  - Ruff clean;
  - non-author verdict: `PASS`, P0/P1=0.
- Pilot commits:
  - T1: `5fe86234766d424d19ec2f13860e4d55e3a7d1fe`;
  - E2E: `356225d3a622713090e934544be0c5638ff7a073`.
- Evidence: 10/10 records, SHA-256
  `15830C45B292FDB8EB835847E3EA255F3A55C741A8E93F05F1DA5417476F8B2E`.
- No push, merge, or destructive worktree retirement was performed.
- RD Paper canonical facts last reported:
  - branch `feat/g1-offline-runner-freeze-foundation`;
  - HEAD `28498c1264ca35e04c87a926eca0aa0e9e5b4f45`;
  - existing dirty count `16`, staged count `0`;
  - the pilot did not absorb or clean those paths.
- Open-source decisions:
  - native Git worktree: `ADOPT`;
  - `git-worktree-runner`: `ADAPT`, accounting for Git Bash/WSL on Windows;
  - `mergetrain`: `ADAPT` concepts only;
  - `claude-worktree-hub`: `ADAPT` lifecycle schema only;
  - AgentFS and LangGraph: reference only.

T1--T12 are complete and must not be rerun. The active Goal remains open only
for the cross-tool RD-Code/T3 Code proof.

### Current active cross-tool proof

At the latest observation, RD-Code was identified as the DevFrame T3 Code
desktop client/instance path rather than a separate standalone executable. The
official T3 checkout was recognized with frozen SHA prefix `5719e8a`.

One resumed OpenCode session was active:

- session: `ses_06523774cffeSEL7FlLvW56BHj`;
- requested executor/model: `huoshan/glm-5-2`;
- one OpenCode process and one child Node process were healthy at capture;
- dependency installation was partial: `node_modules` existed, Electron runtime
  was still missing;
- work was isolated to an exact ten-path DevFrame bridge slice;
- `package.json` and `pnpm-lock` matched upstream before resume.

Do not start a duplicate writer or installer. First check the process tree,
session/log output, isolated worktree status, exact ten paths, package/lock
bytes, and installation completeness. If the original process is still healthy,
wait for it. If it stopped, resume the same session only when its state is
recoverable; otherwise freeze the exact environment blocker.

Completion requires exact scope, no unexplained package/lock drift, focused
bridge/runtime verification, a Reviewer Index, and a separate non-author
`PASS` or `REWORK`.

### Open-source reuse gate

Before implementing another governance mechanism, record a dated Recon Receipt
with source/ref, license, maintenance signal, Windows suitability, security
boundary, integration cost, rollback, and `ADOPT` / `ADAPT` / `REJECT`.
Research alone is not delivery: the selected behavior must become a bounded
executable gate or regression. Do not install every researched project.

### Concrete next action

1. Read `AGENTS.md`, this section, and live Git/worktree state.
2. Read the latest RD Paper controller turn. Do not rerun T1--T12.
3. Check the existing OpenCode/T3 process and exact isolated worktree facts.
   Do not create a duplicate writer or dependency installer.
4. On worker completion, require exact paths, package/lock stability, focused
   product-path tests, and a non-author review.
5. Keep the DevFrame root coordination-only. Accept only material state
   transitions, not repeated status prose.
6. After the cross-tool verdict, select only the proven reusable mechanisms
   for a fresh clean DevFrame integration slice.
7. Keep Trusted Core commit `403046b` separate until clean-baseline provenance
   reconciliation and independent review are complete.

### Hard stops

- No push, merge, deployment, provider call, credential read, paper upload, or
  destructive cleanup without a current explicit human gate.
- No broad staging. Workers never stage or commit.
- No claim that worker success, chat memory, a branch name, or a test count is
  acceptance.
- No claim that same-OS-user malicious-process isolation is solved.
- No second master plan or handoff document.

### Root reconciliation addendum — 2026-07-26 evening

- The staged `docs/status/HANDOFF.md` index entry had been crash-zeroed to
  113,960 NUL bytes at 13:22 and was restaged from the intact working tree;
  forensics across editor histories, dangling blobs, and agent logs found no
  recoverable richer version, so this 89,836-byte lineage plus the records
  added below it is authoritative.
- M10B was accepted under its milestone record above and delivered as three
  logical commits: methodology-skills intake, rdpaper mention target, and the
  canary slice including this record.
- Test environment: a stale pip-orphaned `control_plane` copy in the global
  Python 3.10 `site-packages` shadowed subprocess imports; it was renamed to
  `control_plane.stale-20260726.bak` and the repository package is now
  installed editable (rollback: uninstall `devframe-control-plane` and restore
  the renamed directory).
- Cross-tool proof line: the OpenCode session `ses_06523774cffeSEL7FlLvW56BHj`
  and its clean ten-path worktree were verified recoverable; the dependency
  install was restarted with the pinned `pnpm@11.10.0` via `npx` after a
  corepack shim version mismatch was identified as the failed-restart cause.
- The ambient user-scope `DEVFRAME_MCP_TOKEN` from the M11A live cutover makes
  three MCP tests fail under an inherited user environment; all three pass
  with the variable cleared. Test isolation is a queued follow-up.

### Copy/paste prompt for the next DevFrame controller

```text
You are the new DevFrame root controller. Work from the canonical local checkout.
Read AGENTS.md and the final section “Session Handoff — 2026-07-26 —
Universal Governance Pilot” in docs/status/HANDOFF.md. Recheck live HEAD, Git
status, upstream divergence, worktrees, active processes, and exact ownership.
Preserve every pre-existing dirty/untracked path. Never reset, clean, stash,
restore, rebase, or broadly stage.

Your role is coordination and evidence review, not implementation. Continue the
RD Paper controller task 019f8871-28a2-70f0-9b67-cc3ae83a8aff. Its controller
requested gpt-5.6-sol / medium and its coding executor requested OpenCode
huoshan/glm-5.2; record these as REQUESTED_UNVERIFIED unless runtime attestation
exists.

The synthetic T1--T12 governance pilot is already complete: 12/12 PASS, narrow
29 passed, full 306 passed with 7 Windows capability skips, non-author PASS, and
10/10 evidence records. Do not rerun it. The Goal remains active only for the
RD-Code/T3 Code cross-tool proof.

Read the RD Paper task's latest turn first. At last capture, resumed OpenCode
session ses_06523774cffeSEL7FlLvW56BHj was working in one isolated exact
ten-path T3 bridge slice after a partial dependency installation. Do not start a
duplicate writer or installer. Check process/log/worktree/package-lock facts;
then wait, resume that same recoverable session, or freeze an exact blocker.
Require exact scope, unchanged package/lock bytes unless explicitly justified,
focused bridge/runtime verification, Reviewer Index, and a separate non-author
PASS/REWORK verdict.

Trusted Core v1 remains a separate clean local candidate at its isolated local
worktree, commit
403046bfa2dd0d875d8cba93504307438b5c43f8. It passed the affected 383/1
boundary, public snapshot, and focused non-author review, but it is not pushed,
merged, or deployed; full-suite completion is not claimed. Do not copy it into
the dirty canonical checkout. Integrate only from a fresh clean baseline after
provenance reconciliation and independent review.

Return first: live facts, RD Paper/RD-Code verdict, Goal, real active tasks,
RED/GREEN evidence, blockers, and the single next action. Use concise direct
Chinese. Do not push, merge, deploy, read credentials, call a real provider,
upload paper content, or perform destructive cleanup without a current explicit
human gate.
```

## Session Handoff — 2026-07-27 — M11B Safe Automatic Obsidian Memory

This is the latest scheduling authority. The user explicitly authorized a
bounded global-local activation that minimizes repeated approval without
weakening data safety. It does not authorize Git staging, commit, push, remote
sync, arbitrary note edits, deletion, command execution, or automatic global
playbook publication.

### Frozen governance

- Recon:
  `.devframe-runtime/recon/recon-obsidian-memory-safe-automation-20260727.md`
- TaskSpec:
  `.devframe-runtime/contracts/obsidian-memory-safe-automation-20260727.md`
- Existing RuntimeStore, writeback, MCP consent/audit, and Hook frameworks
  remain authoritative; no second memory database, proposal store, or audit
  store is permitted.
- Basic Memory is AGPL architecture reference only. Obsidian Local REST API,
  cyanheads/obsidian-mcp-server, and Obsidian Git are contract/recovery
  references only; no external source or dependency is copied.

### Required behavior

- Working Plan remains HANDOFF-bound and stale on source drift.
- Project Lessons and Session Checkpoints are immutable, project-scoped,
  bounded, secret-scanned, and independent of HANDOFF hash.
- Global candidates remain project lessons; promotion is a distinct
  create-only human-gated proposal.
- Only recall/search/list and deterministic safe-create tools may be
  client-pre-approved. Plan/promotion, overwrite, edit, move, delete, arbitrary
  path write, and command execution remain gated or unavailable.
- Durable v3 `allow_always` binds the stable native client name to the
  configured loopback token. Complete native clientInfo is required when the
  grant is created; title and version remain audit fields rather than trust-key
  inputs, so an ordinary Codex upgrade can reconnect without another prompt.
  Name-only or tokenless clients cannot persist trust, and legacy v2 grants are
  not silently promoted.
- Native SessionStart stays read-only for startup/resume/clear/compact.
  Native PreCompact captures only goal, decisions, failed attempts,
  verification, blockers, and next action; raw chat is not stored.
- `DEVFRAME_OBSIDIAN_MEMORY_READ_ONLY=true` hides and rejects all memory writes.
- Every automatic path fails open on unavailable runtime/Vault/service and
  never returns an absolute Vault path or secret.

### Current evidence boundary

- Production RED failed on missing safe-memory APIs and missing PreCompact
  template as expected. A later P0 RED exposed dot-segment sandbox-cwd
  normalization as a possible cross-project bypass; canonical local `file://`
  parsing now rejects dot segments, backslashes, and remote authorities before
  any Vault access.
- On HEAD `dea13159414dec059bf982763ff5b46623be23b5`, the exact activated
  source produced wheel SHA-256
  `48F61AF38AF0AB2416907FE789C1C8184E16AC8E20657B3718DA8FAA9488DFBE`.
  The installed hashes for all seven critical modules and both Hook templates
  match source. The Windows logon task is `Ready`, reports result `0`, and owns
  one loopback listener.
- Native SessionStart `startup`, `resume`, `clear`, and `compact` passed for
  both the Git project and a second project on another drive. Nested cwd,
  non-Git roots, same-name isolation, missing plans, stale plans, and service or
  Vault failure all remained bounded and fail-open.
- A fresh registered PreCompact Hook probe against the current native Codex
  transcript created one immutable checkpoint; the exact event retry created
  no second record and both Hook deliveries returned the bounded fail-open
  continuation envelope.
- Fresh installed native Codex MCP calls automatically reinitialized after a
  service restart, recalled the exact project without
  `authorization_pending`, created one immutable checkpoint, and returned
  `duplicate` on the same event retry. A direct Streamable HTTP restart probe
  returned `404` for the stale session, then `200` for initialize and the
  family-granted tool call under a changed client version. A second-drive
  project returned its own `missing` result, while the current Codex connection
  rejected cross-project and forged ids.
- Project Lesson recall survived a HANDOFF hash change while Working Plan
  retained `stale` semantics. A global candidate remained a project lesson;
  no Global Playbook was published.
- Fresh focused M11B domain/MCP/consent/Hook regression:
  `134 passed, 4 skipped`. This includes unavailable-Vault fail-open,
  create-only conflict/concurrency, secret, traversal, reparse/junction,
  sandbox-scope, read-only kill-switch, and literal PowerShell-metacharacter
  path coverage. The final clean release gate passed `2089 passed, 9 skipped`,
  public snapshot, installed-wheel smoke, and `git diff --check`. `compileall`
  also passed. Whole-file Ruff reported seven pre-existing dashboard findings
  outside the M11B change lines, so lint is recorded transparently rather than
  claimed green.
- The first independent release review returned `REWORK`: rendered Hook path
  placeholders were embedded in PowerShell-interpolated strings. Both public
  and packaged SessionStart/PreCompact templates now accept only Base64-encoded
  UTF-8 configuration values and decode them at runtime. A Windows
  production-path regression using a literal `$()` directory passed without
  creating the injected marker; the affected Hook/mirror suite passed
  `30 passed, 1 skipped`. The repeat independent review found no P0/P1 and
  returned `PASS`.
- Fresh installed SessionStart `startup`, `resume`, `clear`, and `compact`
  each returned exit `0`. With the service stopped, SessionStart returned in
  about 2.1 seconds and restored the single listener asynchronously.
  PreCompact created one checkpoint and the exact retry created zero. After a
  service restart, native MCP recall reinitialized automatically without
  `authorization_pending`; a bounded root checkpoint was created once and the
  exact retry returned `duplicate`.
- M11B changed the explicitly authorized local Hook/MCP/runtime configuration
  and created only immutable test checkpoint/lesson records. Exact rollback
  backups exist. It did not stage, commit, push, publish a global playbook,
  enable Vault Git, or change remote state.

### Next action

The root coordinator may now stage the exact 21 accepted M11B paths, verify the
cached path set and content, and create one local logical commit. After that,
resume the isolated T3/RD-Code real-path closure before integrating the
separately reviewed Trusted Core slices. Do not push, publish Global Playbooks,
enable Vault Git history, or broaden client/path trust. OS-process attestation
beyond the exact token-bound Codex fingerprint and optional local Vault history
each require a new scoped Recon.

## Completed Milestone: M11C On-Demand Cross-Client Memory

The 2026-07-29 user direction replaces the fragile resident HTTP/config path
for memory access with a narrower client-spawned stdio adapter. The candidate
reuses the accepted M11A/M11B project registry, Vault safety, create-only
operations, secret scan, human-gated promotion, and read-only kill switch.

- Recon:
  `.devframe-runtime/recon/recon-obsidian-memory-stdio-plugins-20260729.md`
- Command: `devframe memory mcp-stdio`
- Scope: current-project memory tools only; project identity comes from the
  process startup directory, not caller-provided Codex metadata.
- Distribution: one Codex plugin package and one standard `.mcp.json` template
  used by Claude Code or any stdio MCP client.
- Explicit non-goals: no daemon, HTTP proxy, second index, external memory
  authority, user config mutation, arbitrary Vault path, or global install.
- Acceptance evidence: real subprocess initialize/list/recall, read-only and
  cross-project negatives, installed-command probe, Codex plugin validation,
  and Claude Code project-manifest discovery.

### M11C Accepted Local Slice

The root coordinator sets this bounded 11-path slice to `root_accepted` under
`agent-discipline-001`, `agent-discipline-004`, `agent-discipline-005`,
`agent-discipline-006`, and `agent-discipline-010`:

- The server derives one project identity from its startup directory, exposes
  only the seven accepted project-memory tools, rejects an explicit mismatched
  project id, and reuses the M11A/M11B Vault and writeback safety.
- Every id-less JSON-RPC object is ignored before envelope validation or tool
  dispatch. The real subprocess regression proves malformed notifications and
  an id-less write tool produce neither a response nor a Vault note.
- The Codex plugin uses the official direct server-map shape. The two Claude
  Code bootstrap manifests retain their client-native `mcpServers` wrapper and
  are covered by the canonical runtime-bootstrap mirror test.
- Fresh affected regression passed `135 passed, 4 skipped`; scoped Ruff,
  `compileall`, and diff checks passed. The clean candidate release gate passed
  `2096 passed, 9 skipped`, public snapshot verification, control-plane wheel
  smoke, and whitespace verification.
- The exact final wheel SHA256 is
  `461B7895BB4674D90EDAC0AF68ABD725483756941E9EE7B32DC5C2016E146965`.
  Its installed `devframe.exe memory mcp-stdio` completed initialize, exposed
  exactly seven memory tools, and recalled `dev-frame-system` fail-open as
  `stale` without an MCP error.
- The first independent review returned `REWORK` for notification framing,
  Codex/Claude manifest conflation, missing installed-command evidence, and
  mirror coverage. The repairs and real-path evidence closed all findings; the
  final Luna Max actual-diff review returned `PASS` with P0/P1/P2/P3 all
  `None`.

The two pre-existing dirty SessionStart template files remain outside this
slice and protected. The root coordinator may now stage only these 11 accepted
paths, verify the cached path set and content, and create one local logical
commit. Do not push, create a PR, merge, reinstall global plugins, or release
without the explicit human gate.
