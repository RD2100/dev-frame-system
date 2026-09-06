---
description: Project controller v1.2 handoff final (2026-09-06, third edition): current-state entry, preserved AT4 in-flight chain, P05 full closure, and successor first actions.
---

# Project controller handoff — 2026-09-06 (final)

English | [中文](dsh-controller-v1.2-handoff-2026-09-06.zh.md)

## Handoff status: in-flight chain not closed; handover may proceed while the old chain keeps its receiving duty

The AT4 fault-injection worker is still running (zero file dependency on this document, preserved). After committing this document the outgoing controller **stops new dispatches and main-tree merges**; the duty to receive AT4's settlement stays with the outgoing controller until the handover moment. V1.3 is created externally and, once in control, must never rebuild, interrupt, or re-dispatch AT4. This document is the successor controller's **current-state entry point**; the historical ledger (`.agents/devframe/pluginized-round-registry.md`) is consulted on demand.

## Voided conclusions (latest user directives govern)

The old conclusions — concurrency caps (2/5), provider backoff/exclusivity assumptions, "routine rulings wait for authorization", and "round-setting adjustments" — are **all void**. Current rules: no fixed concurrency cap, scale by measured API throughput (two provider names do not imply two independent quotas); same-owner does not imply serial — judge by concrete file/interface conflict, and a lead may split several workers in parallel with dependent wiring landing serially last; rollback-able development/test/config/acceptance within the existing project scope is **already authorized** and executes by default; only an operation that needs a real credential (registry auth, DEEPSEEK_API_KEY) or the user's deployment root carries its own block marker, everything else continues; the 40-round inspection rule stays unchanged and the 8-minute cadence belongs to external automation.

## Main tree snapshot

| Item | Value |
| --- | --- |
| HEAD at writing | `c4ad144d81` (this document's commit follows immediately; the SHA is authoritative in git log) |
| User changes and stash protection | `AGENTS.md`, `docs/working/devframe-qa-2026-09-04.*`, `stash@{0}` stay untouched — never committed, reverted, pushed, or deleted; besides these the working tree has no uncommitted changes of mine |
| Authoritative gate baseline | build exit 0 (220 artifacts); experimental+extensions sweep 130 files 1256P+1S; agent-hierarchy 40/40; gen-cordis-catalog 0; test:docs 15/15; verify-cordis-config 133; verify-package-invariants 39 |

## P05 fingerprint chain (fully closed)

| Wave | Merge | Evidence |
| --- | --- | --- |
| Engine | `4f1df4348a` (`85f6e8cab7` src+`8321c3e0b4` test+`3671385046` docs) | devframe 53/53, new module 100% covered; build exit 0 |
| Verify face (Option B ruling applied) | `88668ea890` (`77a6371a7a` src+`bc85310b2c` test+`09b155c4a3` docs) | devframe **58/58** (+5 verify cases); build exit 0; zero diff to controller/events/schemas/journal |

Design record: `.agents/devframe/p22/fprecompute-design.md` (fingerprint composition, the 5-error family, untracked-invisible as the ruled boundary, Option A = a forward use of Option B left for later).

## In-flight chain (the only preserved one): AT4 fault injection

| Item | Value |
| --- | --- |
| Worker SessionID | `dc51bc32-92b6-4b51-9bc3-fedabedaad1f` (one-shot subagent) |
| Parent lead chain | Worker → L-Foundation `55979618-6bd7-4bc7-badc-8a3b13079158` → outgoing controller `session-724834c2-9ff4-49e5-9b0a-4ce5f68d2c2d` |
| Worktree / branch / cwd | `D:\dsh-devframe-p-at4` (created by the lead per the three-layer topology), branch `p/at4process`, base `526e773b23`; session creation cwd=`D:\dsh-devframe`, task workspace=p-at4 |
| Provider / model | Not yet recorded in JSON (first turn unfinished) — **re-check the session_projcache JSON at settlement**, never assume |
| Artifacts | No commits; worktree dirty=2 (read-only investigation / early writes); task = land AT4-02/03/06 real process-injection journeys in `agent-reliability/tests/` (zero model dependency) |
| Actual call | One-shot subagent running; recovery point = resume from the worktree file state, never redo what is on disk |
| Settlement receiving | The outgoing controller keeps the receiving duty until the handover moment (personally verify commits/vitest/tsc/build/evidence → merge right remains valid until stopped); after handover V1.3 continues the lead session via `send_message`, **never rebuilding, interrupting, or re-dispatching** |

## Shadow / Memory four states and concrete production gaps

| Plugin | Source | Install+enable (proven = isolated instances) | Runtime verification (proven = real probes) | Production ready (concrete gaps) |
| --- | --- | --- | --- | --- |
| Shadow (`packages/experimental/shadow-router`) | ✅ (incl. completeDelivery stopped guard) | ✅ integration profile six-plugin rows; bundle rows+manifest declarations | ✅ package-level 26P+1S; composition-level markShadow/delivery journey/stop contrast/crash-window (measured double-0 on `.dsh-integration` and a fresh temp root) | No host-composition markShadow production call site (the P23/S4 seam); production authorizedRoots needs real deployment config (that operation blocked by the real data root); UI state sets |
| Memory (`packages/experimental/project-memory`) | ✅ | ✅ same profile rows | ✅ three-tool face+receipt rehydration+cold recovery (same probe, measured) | writeEnabled not enabled on a production instance (config face; local instances may proceed); memory three tools not in the role allowlist (config face); real Vault root (blocked by the real data root) |

Cold-recovery rerun (measured): create a new empty temp directory as `DSH_HOME` → bootstrap with `pnpm dsh plugin --profile integration add @deepseek-ai/dsh-<pkg>` (the install step exits 1 for missing registry auth, but the config lands and the probe resolves plugins from source; record actual behavior on first run) → probe `--phase write`/`--phase verify` expecting double 0 → afterwards delete only that temp root. **Never whole-tree delete existing sessions/storages/vault in a shared home.** Evidence paths: `.agents/devframe/p22/shadow-delivery-flow-evidence.md`, `s6-evidence.md`, `memory-rehydration-evidence.md`, registry entries integration-3/4, shadowflow, shadowguard.

## Remaining tasks and the successor's first batch (checked against current state)

| Task | Lead | File domain | Proven dependency | Acceptance | Conflict handling |
| --- | --- | --- | --- | --- | --- |
| Windows B-family snapshot (the only 88F root) | L-Foundation (patch lines)+L-Verify (corpus expectations/delta) | `base/cordis.patch.yml` L252-254, minimal preset L36-38, snapshot corpus expectation face | platform-parameterization technical ruling (authorized): scenario-level platform expectation config fields | test:snapshot lib delta (A/C families stay 0)+dump | patch lines and corpus expectations sit with different leads in different file domains |
| Shadow/Memory local config integration | L-Integration | local (non-shared) profile instances+writeEnabled/role allowlist local instances | none (the integration file domain is idle) | dump-config+dual-phase probe (fresh temp root)+build | no file overlap with other tasks |
| AT4 process injection/recovery | L-Foundation | `agent-reliability/tests/` | **in flight, preserved (above)** | package vitest+tsc+build | await its settlement, never re-dispatch |
| Real three-level task offline scaffolding | L-Verify | three-level task briefs+acceptance scaffolding (parts not needing DEEPSEEK_API_KEY) | none; a missing key blocks only the real-run segment | scaffolding offline segments green | separate profile/e2e file domains from L-Integration's task, or serialize |
| P05 residual (required-checks model; wrong-reviewer ① and snapshotId⇄fingerprint ④ are closed) | L-Foundation | devframe config schema+evidence comparison face | fprecompute closed (this Option-B face); product config face design first | package vitest+tsc+build+jsdoc | different package from AT4, zero conflict; events/schemas wiring lands serially last |

Successor first actions: verify main HEAD / registry last entry / this document agree → confirm AT4 continuation with L-Foundation via `send_message` (no rebuild) → dispatch the Windows B-family parameterization design and Shadow/Memory local integration in parallel (different leads, zero file conflict) → schedule P05 required-checks design following the Option-A layering path in fprecompute-design.md.

## Handoff gate (executed through step 2)

1. ✅ The in-flight P05 chain settled, personally verified, and merged (engine `4f1df4348a`+verify face `88668ea890`).
2. ✅ AT4's current state persisted (this section+registry `c4ad144d81`)+this document committed.
3. ✅ The outgoing controller **stops new dispatches and main-tree merges** from this document's commit onward (through the registry's last entry) and pauses the automatic goal at handover.
4. ⏳ V1.3 is created by **external coordination**: an independent top-level Session+independent worktree; the outgoing controller never creates it as a child agent and never edits parent-child records.
5. ⏳ V1.3 takes control after checking: main HEAD, the registry's last entry, and this document agree; it never rebuilds or re-dispatches AT4.

## Preserved rules (mandatory for V1.3)

Three-layer topology (controller→lead→worker; a worker never creates agents); leads and the controller keep independent worktrees; the controller alone merges to main; no idle spinning; SessionID/Agent/Worktree/task/result persistence; lanes and providers labeled only from persisted JSON; no silent routing, no blind retries of uncertain calls; the user's uncommitted items and stash stay untouched throughout; no push, no PR, no publish, no deletion of user files.

## Dev Note

This document is the 2026-09-06 final snapshot, expiring scratch under docs/working; V1.3 updates the in-flight section after closing AT4 and starts its own versioned record. Provider fields not yet recorded must be re-checked against persisted JSON before use.
