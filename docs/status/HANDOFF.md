# DevFrame Project Execution Root

Lifecycle state: **CANONICAL EXECUTION ROOT**

Current verdict: **READY TO CONTINUE** on the bounded milestone below. This is
not a release, deployment, or production verdict.

Last reconciled: 2026-07-18 against `main` at
`b996c74f754bf0c277930767f6d5efccee467ca6` with a clean primary worktree.

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
| Public repository | `main` and `origin/main` both resolve to `b996c74f`; primary worktree was clean at reconciliation |
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
| KERNEL-001 | active | P1 | One physical go run can appear as separate `go_run` and `team_events` projections with the same canonical `run_id`; the team projection may lose the project identity | 2026-07-17 read-only cluster probe produced duplicate records and `unknown-project` on the team side | One deterministic canonical read view per physical run, with merged provenance and fail-closed acceptance state |
| DOCS-001 | closed | P1 | 120 tracked status documents could be mistaken for competing current plans | Lifecycle demotion, authority tests, docs-drift checks, independent review, and a clean exported public-snapshot gate passed on 2026-07-18 | `HANDOFF.md` is the only scheduling authority; all other status documents are explicitly non-scheduling references |

`DOCS-001` is mitigated by this document slice. Physical archival or deletion
is a later cleanup operation and must first prove that no active validator,
rule, script, or public link depends on the affected file.

## Delivery Roadmap

Only one milestone may be active. Later milestones are ordered backlog, not
permission to start parallel implementation.

| Milestone | State | User-visible outcome | Exit evidence |
|---|---|---|---|
| M0. Authority consolidation | accepted | One document controls direction and next work | Documentation drift, public snapshot, link, diff, and independent review gates passed |
| M1. Canonical run truth | active | CLI and clients see one governance record for one physical run | Real-path duplicate-run RED becomes one deterministic canonical projection; no false `final_ready` |
| M2. Review closure | queued | A real run moves from report to review, gate, and FinalVerdict without manual state reinterpretation | Real execution remains `review_pending` before independent review and becomes `final_ready` only after valid evidence |
| M3. Tutti adapter | queued | Tutti opens the existing DevFrame dashboard as a local Workspace App | Local app load/reload, `/healthz`, `/state.json`, and a visible Tutti path pass without Tutti core changes |
| M4. Executor equivalence | queued | The same TaskSpec can use command or ACP execution without changing governance meaning | Normalized RunRecord parity test passes; provider-specific data stays in provenance |
| M5. Paper vertical | queued | Paper work reuses the same evidence, review, and gate authority | One bounded paper task completes through the canonical kernel without a parallel state machine |

## Current Milestone: M1 Canonical Run Truth

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
| 2026-07-18 | Use a Tutti Workspace App wrapper before modifying Tutti core | Existing local-app load/reload and dashboard endpoints already provide the required seam |
| 2026-07-18 | Defer paper expansion until run identity, review closure, and executor parity are proven | Domain growth must not hide an unstable kernel boundary |
| 2026-07-18 | Accept M0 and promote M1 to active | Authority tests, docs drift, clean exported snapshot, actual diff review, and independent review passed |

## Next Action

Add real-path RED coverage for the three independent-review findings: reviewer
identity colliding with the merged worker set, missing project identity, and
non-equivalent run or worker statuses. Then revise the existing M1 production
candidate until all negative paths fail closed and the valid FinalVerdict path
still reaches `final_ready`.
