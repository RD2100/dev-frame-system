---
description: Requirement-linked test procedures and acceptance criteria for the proposed DSH-native DevFrame features.
---

# DevFrame on DSH: Tests and Acceptance

English | [中文](testAndAcceptance.zh.md)

## Summary

This reference defines observable acceptance for the [general design](generalDesign.md) and its four detailed parts. All `AT*` cases below are specifications for proposed DevFrame functionality and are not marked as implemented or passed. Existing native-Team test evidence is recorded separately and proves only its stated scope. Documentation validation does not constitute product acceptance. The evidence-anchor column in each acceptance matrix names existing test, scenario, or integration-probe artifacts; the [P22 anchor matrix](../.agents/devframe/p22/anchor-matrix.md) owns per-row coverage status, evidence still being produced on its own branch appears as a pending-link placeholder, and no anchor changes a `not_run` result.

## Table of Contents

- [Test environment and result rules](#rules)
- [Existing baseline evidence](#baseline)
- [Part 1 acceptance](#part1)
- [Part 2 acceptance](#part2)
- [Part 3 acceptance](#part3)
- [Part 4 acceptance](#part4)
- [Usefulness trial](#usefulness)
- [Delivery and evidence](#delivery)

<a id="rules"></a>

## Test environment and result rules

Use the pinned source baseline from the general design, disposable projects, temporary runtime storage, and a temporary Vault subtree. Exercise the selected Windows filesystem/subprocess providers for Windows claims. Do not run destructive fault injection against a real user Vault, unrelated processes, production systems, or a shared working tree.

Run four complementary levels: focused unit checks for deterministic policy, keyless integration through real session/tool/storage paths, a user-approved live-model demonstration, and fault-injection/restart checks. Mock model responses are suitable for deterministic tool tests, but do not prove live provider availability or useful autonomous task execution.

Each acceptance ID must be bound to an actual test file/test name or a reproducible manual procedure during implementation. A proposed ID, an invented command, or a screenshot without execution context is not evidence. Real-provider tests require explicit credentials/spend authorization; missing prerequisites remain `blocked`, not `passed`.

| Result | Meaning |
| --- | --- |
| `passed` | The specified path ran and all stated assertions have recorded evidence. |
| `failed` | The path ran and at least one assertion failed, including a false success claim. |
| `blocked` | A required capability, environment, authority, or prerequisite is unavailable. |
| `not_run` | The case has not been executed; this is the current state of all proposed `AT*` cases. |

For every permission, false-completion, data-loss, or cancellation fix, include a real-path negative case that would have exposed the original problem. A helper-only unit test is insufficient when the production tool/process path can be exercised safely.

<a id="baseline"></a>

## Existing baseline evidence

During source analysis on 2026-09-02, the following command ran successfully against the pinned checkout: 3 test files and 63 tests passed. These tests use mock model behavior and exercise native Team/session behavior, including persistence cases; they do not implement or accept the new DevFrame layer.

Run from the DSH repository root in PowerShell:

```powershell
pnpm.cmd exec vitest run packages/experimental/agent-team/tests/team.spec.ts packages/experimental/agent-team/tests/persistence.spec.ts packages/experimental/tool-agent-team/tests/tool-team.spec.ts
```

The source tests are [Team behavior](../packages/experimental/agent-team/tests/team.spec.ts), [persistence](../packages/experimental/agent-team/tests/persistence.spec.ts), and [Team tools](../packages/experimental/tool-agent-team/tests/tool-team.spec.ts). Rerun them when implementation changes their paths; do not reuse the historical result as fresh verification of later code.

During this design correction on 2026-09-02, the following native scope suite was executed: 1 file, 27 tests passed. It confirms the inherited/local distinction of `restrict()` and the native monotonic guard behavior, not the unimplemented DevFrame role integration.

```powershell
pnpm.cmd exec vitest run packages/core/tools/tests/scoped.spec.ts
```

The existing quick documentation command checks links, pairing, prose structure, and other repository documentation rules. It neither builds DevFrame nor runs the proposed acceptance cases:

```powershell
pnpm.cmd run test:docs
```

<a id="part1"></a>

## Part 1 acceptance

These cases verify [single-project development](detailDesign-part1.md). Use fresh disposable state except where a case explicitly requires consecutive Goals or recovery. Capture the complete Goal/task/acceptance/source binding, not just a source snapshot. `AT1-11` is defined in the separate usefulness section.

| ID / requirement | Setup and action | Observable pass criteria | Evidence anchors |
| --- | --- | --- | --- |
| `AT1-01` / `R1.1` | Through the real dispatcher, probe forbidden file/shell/workflow/Goal calls and a scope-local `team_task_update` with otherwise valid member/task arguments; force pre-execute to allow. | The role guard still rejects the local Team mutation before its body; inherited tool restrictions and omitted plugins also hold. Permitted reads work. A `restrict()`-only implementation must fail this case. | [agent-hierarchy guard.spec.ts](../packages/experimental/agent-hierarchy/tests/guard.spec.ts), [devframe permissions.spec.ts](../packages/experimental/devframe/tests/permissions.spec.ts), [devframe hierarchy-roles.spec.ts](../packages/experimental/devframe/tests/hierarchy-roles.spec.ts), [core scoped.spec.ts](../packages/core/tools/tests/scoped.spec.ts); composite online role-denial evidence: branch `p/hier2` (in flight, pending link) |
| `AT1-02` / `R1.1` | Persist roles, dispose the runtime, cold-resume, and repeat inherited and scope-local probes before and after role restoration; attempt dispatch with no role record. | New guards install before execution, missing roles deny, worker tools remain available, reviewer mutation remains denied, and disposed registrations leave no stale guards. | [agent-hierarchy cold-recovery.spec.ts](../packages/experimental/agent-hierarchy/tests/cold-recovery.spec.ts); [probe §2](../.agents/devframe/integration/e2e-evidence.md#2-双进程冷恢复探针重启恢复exit-0--2) |
| `AT1-03` / `R1.2` | Give the team a small fixture bug with a test that genuinely fails before the change; implement through the normal worker path. | The same real check fails before and passes after; a host-captured command/exit/log record exists, and unrelated dirty files remain unchanged. | [agent-evidence ledger.spec.ts](../packages/experimental/agent-evidence/tests/ledger.spec.ts) |
| `AT1-04` / `R1.2` | While a worker-owned mutating job remains active, attempt another writer and review/completion. | No second writer is admitted and completion is blocked; ownership is retained until the real job settles. | [worktree-registry agent-lock.spec.ts](../packages/workflow/worktree-registry/tests/agent-lock.spec.ts), [project-controller controller.spec.ts](../packages/experimental/project-controller/tests/controller.spec.ts) |
| `AT1-05` / `R1.3` | Supply fabricated success, failed/skipped checks, the wrong reviewer identity, and a review for a different snapshot; mutate a relevant untracked file after review and try removing a required check through project config. | Each variant is rejected with its actual blocking reason; `HEAD` equality does not hide the untracked change, and required checks cannot be silently weakened. | [agent-evidence ledger.spec.ts](../packages/experimental/agent-evidence/tests/ledger.spec.ts) |
| `AT1-06` / `R1.3` | Finish required tasks, checks, and independent review for one unchanged snapshot; request completion twice. | Native goal completes once; the repeated request is harmless. Evidence references resolve, and no separate acceptance database is required. | [devframe goal-binding.spec.ts](../packages/experimental/devframe/tests/goal-binding.spec.ts), [project-controller controller.spec.ts](../packages/experimental/project-controller/tests/controller.spec.ts), [devframe events.spec.ts](../packages/experimental/devframe/tests/events.spec.ts) |
| `AT1-07` / `R1.4` | Start the assembled profile; send a quiet message, then a work follow-up. Exercise failed provisioning and the native member cap. | No tool-name collision; quiet delivery does not wake, follow-up does; failed members count toward the cap, and recursive spawning is unavailable. | [agent-team team.spec.ts](../packages/experimental/agent-team/tests/team.spec.ts), [agent-team persistence.spec.ts](../packages/experimental/agent-team/tests/persistence.spec.ts), [composition-smoke workspace-composition.client.spec.tsx](../packages/test-support/composition-smoke/tests/workspace-composition.client.spec.tsx), [agent-team-profile profile.spec.ts](../packages/experimental/agent-team-profile/tests/profile.spec.ts), [probe §1](../.agents/devframe/integration/e2e-evidence.md#1-装配验证dump-configexit-0), [probe §3](../.agents/devframe/integration/e2e-evidence.md#3-recorded-session-无钥匙回放真实启动--真实工具调用exit-0); built-bin smoke evidence: [builtbin-smoke-evidence.md](../.agents/devframe/p22/builtbin-smoke-evidence.md) (`7569b2f98e`, merged in main) — fail-loud record: the build ran red, built-bin startup was not executed |
| `AT1-08` / `R1.4` | Make the reviewer repeatedly request changes with the repair limit set to two. | At most two correction/retest/review cycles follow the initial review; remaining issues require human input, without replacement-member or new-run bypass. | `status: missing` — [anchor matrix AT1-08](../.agents/devframe/p22/anchor-matrix.md#1-at1-单项目责任p02--p05--p04--profile--w4) |
| `AT1-09` / `R1.5` | Complete A, then start B in the same controller/team with an unrelated pending board item. Keep source unchanged but change B's requirements; consume budget, stop/restart, resume, and deliver a late A result. | A/B have distinct Goal/task/evidence bindings; old review cannot accept B; unrelated tasks do not block it. B retains consumption across revision/restart, and late A output cannot satisfy or charge B. Complete B using its own evidence. | [devframe goal-binding.spec.ts](../packages/experimental/devframe/tests/goal-binding.spec.ts), [devframe events.spec.ts](../packages/experimental/devframe/tests/events.spec.ts), [project-controller controller.spec.ts](../packages/experimental/project-controller/tests/controller.spec.ts) |
| `AT1-10` / `R1.6` | Exercise the proposed human command journey: configure/confirm/start, reject a stale preview, stop, change checks, resume, view result, and abandon a stopped unfinished Goal. Interrupt start between native Goal creation and binding persistence; attempt approval from a model call. | No execution before binding and authorization; changed checks invalidate evidence without resetting usage; uncertainty blocks resume; result links resolve; abandonment is not completion, and model text cannot grant approval. | `status: missing` — [anchor matrix AT1-10](../.agents/devframe/p22/anchor-matrix.md#1-at1-单项目责任p02--p05--p04--profile--w4); anchored rejection seam: [devframe goal-binding.spec.ts](../packages/experimental/devframe/tests/goal-binding.spec.ts); design proposal: [s4-toolface-plan.md](../.agents/devframe/integration/s4-toolface-plan.md) |

<a id="part2"></a>

## Part 2 acceptance

These cases verify [Shadow routing](detailDesign-part2.md). Use two disjoint temporary projects A and B with distinguishable tasks and output files.

| ID / requirement | Setup and action | Observable pass criteria | Evidence anchors |
| --- | --- | --- | --- |
| `AT2-01` / `R2.1` | Open A and B from Shadow and send different work to each. | Two independent controller roots exist; their workers are direct children of the correct root; no Team is nested and outputs stay in the intended project. | [shadow-router lifecycle.spec.ts](../packages/experimental/shadow-router/tests/lifecycle.spec.ts), [AT2-01 scenario](../packages/experimental/shadow-router/scenarios/AT2-01-open-route-two-projects.md) |
| `AT2-02` / `R2.1` | Use a worker to call project tools; probe Shadow's forbidden shell/raw-session tools; submit an arbitrary target session ID, unauthorized workspace, and obsolete binding revision. | All forbidden requests fail before target mutation; no secret/project content is returned as part of the rejection. | [shadow-router whitelist.spec.ts](../packages/experimental/shadow-router/tests/whitelist.spec.ts), [AT2-02 scenario](../packages/experimental/shadow-router/scenarios/AT2-02-forbidden-probes.md); S6 markShadow caller fail-closed evidence: [s6-evidence.md](../.agents/devframe/p22/s6-evidence.md) (`efd88d2e6c`, merged in main) |
| `AT2-03` / `R2.2` | Issue concurrent repeated opens, then interrupt between binding reservation and root readiness and recover. | The same authorized workspace resolves to one reserved/current controller, with no duplicate writer or silently replaced root. | [shadow-router provisioning.spec.ts](../packages/experimental/shadow-router/tests/provisioning.spec.ts), [AT2-03 scenario](../packages/experimental/shadow-router/scenarios/AT2-03-open-dedup-recovery.md); S6 markShadow binding cold-restore evidence: [s6-evidence.md](../.agents/devframe/p22/s6-evidence.md) (`efd88d2e6c`, merged in main) |
| `AT2-04` / `R2.2` | On the supported filesystem, open case/junction aliases and physically overlapping roots. | Aliases resolve consistently; overlapping simultaneous writers are rejected. Unsupported alias semantics are reported, not claimed as tested. | [shadow-router aliases.spec.ts](../packages/experimental/shadow-router/tests/aliases.spec.ts), [AT2-04 scenario](../packages/experimental/shadow-router/scenarios/AT2-04-alias-overlap.md) |
| `AT2-05` / `R2.3` | Interrupt delivery before target acceptance, after target flush, and before sender receipt; reopen the real storage. | The same message ID converges to one accepted input; receipt recovery does not duplicate a model-visible task. Run against both supported storage backends before claiming both. | [shadow-router delivery-recovery.spec.ts](../packages/experimental/shadow-router/tests/delivery-recovery.spec.ts), [AT2-05 scenario](../packages/experimental/shadow-router/scenarios/AT2-05-delivery-interruption.md) |
| `AT2-06` / `R2.3` | Retry identical/different payloads, exceed message/queue limits, and deliver a previous Goal's message after the controller starts another Goal. | Stable retries deduplicate; conflicting or oversized input rejects; an old Goal/acceptance binding never becomes input to the new Goal or resets retry limits. | [shadow-router delivery-limits.spec.ts](../packages/experimental/shadow-router/tests/delivery-limits.spec.ts), [AT2-06 scenario](../packages/experimental/shadow-router/scenarios/AT2-06-retry-limits-stale-goal.md) |
| `AT2-07` / `R2.4` | Run real owned jobs in A and B; stop A twice. | A stops idempotently after draining; B's job, queue, and controller continue unaffected. | [shadow-router stop-isolation.spec.ts](../packages/experimental/shadow-router/tests/stop-isolation.spec.ts), [AT2-07 scenario](../packages/experimental/shadow-router/scenarios/AT2-07-stop-isolation.md) |
| `AT2-08` / `R2.4` | Read status repeatedly for idle, queued, received, blocked, and completed runs, including a stale observation. | Status is bounded and read-only, includes observation time, never wakes a model, and never equates receipt or idle with accepted completion. | [shadow-router status.spec.ts](../packages/experimental/shadow-router/tests/status.spec.ts), [AT2-08 scenario](../packages/experimental/shadow-router/scenarios/AT2-08-status-readonly.md) |

<a id="part3"></a>

## Part 3 acceptance

These cases verify [Obsidian memory](detailDesign-part3.md) against an actual temporary filesystem. Use synthetic content and credentials-shaped test strings, never real secrets.

| ID / requirement | Setup and action | Observable pass criteria | Evidence anchors |
| --- | --- | --- | --- |
| `AT3-01` / `R3.1` | Append an authorized project observation and a human-confirmed preference; start a fresh project session with no prior conversation context. | Recall finds the allowed facts with provenance; another project's private note is absent. Native logs record what context reached the model. | [project-memory recall.spec.ts](../packages/experimental/project-memory/tests/recall.spec.ts), [project-memory receipt-log.spec.ts](../packages/experimental/project-memory/tests/receipt-log.spec.ts), [project-memory plugin.spec.ts](../packages/experimental/project-memory/tests/plugin.spec.ts), [AT3-01 scenario](../packages/experimental/project-memory/scenarios/AT3-01-workspace-isolation.md), [probe §2](../.agents/devframe/integration/e2e-evidence.md#2-双进程冷恢复探针重启恢复exit-0--2); agent-side rehydration evidence: [memory-rehydration-evidence.md](../.agents/devframe/p22/memory-rehydration-evidence.md) (`dd60bbc489`, merged in main) |
| `AT3-02` / `R3.1` | Search/read Chinese and mixed UTF-8 notes exceeding byte, result, and candidate limits. | Output stays within configured bytes/counts without broken characters; partial search and truncation are explicit. | [project-memory recall.spec.ts](../packages/experimental/project-memory/tests/recall.spec.ts), [project-memory notes.spec.ts](../packages/experimental/project-memory/tests/notes.spec.ts), [AT3-02 scenario](../packages/experimental/project-memory/scenarios/AT3-02-byte-limit-truncation.md) |
| `AT3-03` / `R3.2` | Concurrently append the same source event; retry matching and conflicting content, then simulate interruption during write. | At most one complete note is created; matching retry is idempotent, conflict never overwrites, and incomplete notes are excluded and reported. | [project-memory append.spec.ts](../packages/experimental/project-memory/tests/append.spec.ts), [AT3-03 scenario](../packages/experimental/project-memory/scenarios/AT3-03-concurrent-append-idempotency.md) |
| `AT3-04` / `R3.2` | Probe traversal, unauthorized namespace IDs, and symlink/reparse escapes through the real adapter. | No outside read or write occurs; unsupported safe-create behavior disables append rather than using a shell fallback. | [project-memory path-safety.spec.ts](../packages/experimental/project-memory/tests/path-safety.spec.ts), [AT3-04 scenario](../packages/experimental/project-memory/scenarios/AT3-04-path-containment-rejection.md) |
| `AT3-05` / `R3.3` | Store a note instructing the model to change permissions or write another project; attempt the requested tool calls. | The note remains labelled data; actual runtime policy is unchanged and unauthorized operations are rejected. | [project-memory trust.spec.ts](../packages/experimental/project-memory/tests/trust.spec.ts), [AT3-05 scenario](../packages/experimental/project-memory/scenarios/AT3-05-trust-label-carry.md) |
| `AT3-06` / `R3.3` | Supply inferred preferences, contradictory notes, and an observation for an old source snapshot. | No inferred preference becomes confirmed automatically; conflict/staleness is visible; explicit authorized supersession preserves the old note. | [project-memory trust.spec.ts](../packages/experimental/project-memory/tests/trust.spec.ts), [AT3-06 scenario](../packages/experimental/project-memory/scenarios/AT3-06-trust-promotion-contradiction.md) |
| `AT3-07` / `R3.4` | Disable the Vault, make it read-only, and remove it during access; test both a coding task and a memory-only task. | Coding can finish with a memory warning; a failed save is never reported as saved, and the memory-only task remains failed/blocked. | [project-memory failure.spec.ts](../packages/experimental/project-memory/tests/failure.spec.ts), [project-memory cold-restore.spec.ts](../packages/experimental/project-memory/tests/cold-restore.spec.ts), [AT3-07 scenario](../packages/experimental/project-memory/scenarios/AT3-07-vault-unavailable-degradation.md) |
| `AT3-08` / `R3.4` | Submit malformed notes and known secret-pattern fixtures; exhaust transient-failure retries. | Invalid/sensitive content is rejected without raw-secret logging, retries stop at the configured bound, and a stable recoverable candidate reference remains. | [project-memory failure.spec.ts](../packages/experimental/project-memory/tests/failure.spec.ts), [AT3-08 scenario](../packages/experimental/project-memory/scenarios/AT3-08-secret-screening-rejection.md) |
| `AT3-09` / `R3.2` | Edit a confirmed note's body/metadata, move/rename/delete it, retry its original append, and explicitly submit a correction. | Changed/missing files are reported and preserved, not auto-imported, overwritten, or recreated. An edited inline digest does not replace the session receipt. Only explicit confirmed correction creates a new sourced note. | [project-memory append.spec.ts](../packages/experimental/project-memory/tests/append.spec.ts), [project-memory cold-restore.spec.ts](../packages/experimental/project-memory/tests/cold-restore.spec.ts), [AT3-09 scenario](../packages/experimental/project-memory/scenarios/AT3-09-external-change-honest-reporting.md) |

<a id="part4"></a>

## Part 4 acceptance

These cases verify [reliability](detailDesign-part4.md). Fault injection must use process-owned resources and explicit timeouts; record the exact interruption point and verify the recovered source/storage state, not only an in-memory flag.

| ID / requirement | Setup and action | Observable pass criteria | Evidence anchors |
| --- | --- | --- | --- |
| `AT4-01` / `R4.1` | Restart with queued controller/child work; separately force a pre-step rejection before any model/tool step and a continuation pre-step rejection after a tool step has executed, then explicitly resume the same Goal for each case. | No unauthorized model/tool work occurs. Only input proven not started remains recoverable by its original operation reference and is explicitly reissued once; work with an executed step remains interrupted and work with uncertain execution remains `ambiguous`. Neither case is replayed as not started. Identity and limits remain intact. | [agent-reliability service.spec.ts](../packages/experimental/agent-reliability/tests/service.spec.ts), [devframe goal-binding.spec.ts](../packages/experimental/devframe/tests/goal-binding.spec.ts) |
| `AT4-02` / `R4.1` | A test command writes a marker, then the harness dies before its result is recorded; reopen the run. | Execution is reconciled or marked ambiguous; the command is not automatically repeated and the marker is not duplicated. | [agent-reliability service.spec.ts](../packages/experimental/agent-reliability/tests/service.spec.ts) |
| `AT4-03` / `R4.2` | Start a real long-running child with a grandchild that writes a heartbeat; stop the owning project. | The owned process tree ends, output stops, callbacks settle, and writer ownership is released only afterward. | [agent-reliability service.spec.ts](../packages/experimental/agent-reliability/tests/service.spec.ts) |
| `AT4-04` / `R4.2` | Simulate cancellation refusal/unknown process identity and plugin disposal during work; attempt a replacement writer. | The project remains unavailable for writing with a diagnostic; no false `stopped`, no replacement writer, and no unrelated process is killed. | `status: missing` — [anchor matrix AT4-04](../.agents/devframe/p22/anchor-matrix.md#4-at4-可靠性责任p06--l-foundationat4-08-未绑定) |
| `AT4-05` / `R4.3` | Set a project request budget to one and race controller/child attempts; include provider retry and restart. | At most the permitted charged attempts dispatch; no sibling race or retry/restart resets usage. Unknown token usage is not reported as zero. | `status: missing` — [anchor matrix AT4-05](../.agents/devframe/p22/anchor-matrix.md#4-at4-可靠性责任p06--l-foundationat4-08-未绑定) |
| `AT4-06` / `R4.3` | Exceed active-project/concurrent-request/queue limits and expire a short deadline while work is running. | Excess work is rejected or remains visibly unstarted; expiry closes admission and begins bounded cancellation without fresh continuation. | [agent-reliability service.spec.ts](../packages/experimental/agent-reliability/tests/service.spec.ts), [project-controller controller.spec.ts](../packages/experimental/project-controller/tests/controller.spec.ts) |
| `AT4-07` / `R4.4` | Inject real-storage write/flush failures at input acceptance and completion; inspect logs and displayed state. | No unpersisted success is announced, further mutations stop, and sanitized diagnostics identify project/operation without disclosing content or credentials. | [agent-reliability service.spec.ts](../packages/experimental/agent-reliability/tests/service.spec.ts), [devframe events.spec.ts](../packages/experimental/devframe/tests/events.spec.ts) |
| `AT4-08` / `R4.4` | Open recorded feature sessions with a missing required decoder or incompatible profile, then use the retained compatible reader. | Incompatible use fails clearly without modifying logs; the compatible path can inspect/export them. Rollback does not erase evidence or leave a writer alive. | `status: missing` — [anchor matrix AT4-08](../.agents/devframe/p22/anchor-matrix.md#4-at4-可靠性责任p06--l-foundationat4-08-未绑定); core repair/version seams: [core repair.spec.ts](../packages/core/session/tests/repair.spec.ts), [core session.spec.ts](../packages/core/session/tests/session.spec.ts) |

<a id="usefulness"></a>

## Usefulness trial

After the controlled single-project checks pass, select 3–5 small real user tasks, not only predetermined fixture bugs. Keep the team controller/members across the tasks and include a stop/resume. Run direct DSH single-agent comparisons from matching initial snapshots and acceptance requirements; record model/provider configuration and material differences. Alternate order or use comparable independent tasks to limit learning effects. This is a small observational trial, not a statistically proven speedup claim.

| ID / requirement | Setup and action | Observable pass criteria | Evidence anchors |
| --- | --- | --- | --- |
| `AT1-11` / `R1.7` | Complete the paired real-task trial and review its record with the user. | Record actual task outcomes, interventions, time, requests/usage, and valid/invalid review findings for both modes; retain failures. The user records `helpful`, `inconclusive`, or `not_helpful` and chooses continue, simplify/retry, or stop. No efficiency percentage is presupposed. | `status: missing` — [anchor matrix AT1-11](../.agents/devframe/p22/anchor-matrix.md#1-at1-单项目责任p02--p05--p04--profile--w4) |

Separate one-time setup cost from per-task operation. Count required confirmations as well as clarification, direction correction, and manual rescue; record human active time and total elapsed time separately. Count a review finding as useful only when its concrete issue is validated, not merely because a reviewer produced text. Unknown token/cost values remain unknown.

One compact comparison table in the existing trial report is enough. A completed assessment can show no benefit; passing the assessment does not mean the product is helpful. Expanding beyond the pilot requires an explicit user decision based on these facts. `inconclusive` or `not_helpful` favors simplifying roles or stopping expansion, not adding infrastructure to justify the workflow.

<a id="delivery"></a>

## Delivery and evidence

Select a delivery scope before execution. The document part number does not determine when a safety check runs; the early single-project subset below is required before ordinary user work. Multi-project, memory, and full version-recovery matrices remain attached to the features the user actually selects.

| Delivery | Required evidence | Not claimed |
| --- | --- | --- |
| Focused integration experiment | Native scope regression plus `AT1-01`, `AT1-02`, and the startup-order portion of `AT1-10` through actual Team composition. | A usable or released coding workflow. |
| Controlled single-project pilot | `AT1-01` through `AT1-10`; single-project `AT4-01` through `AT4-05`, the deadline portion of `AT4-06`, and admission/completion-flush failures in `AT4-07`; one approved live-model task. | Multi-project operation, memory, or the entire reliability matrix. |
| Value decision | `AT1-11` with the user's recorded choice after 3–5 real tasks. | Automatic approval to implement every remaining part. |
| Candidate multi-project extension | A separate user decision, the pilot baseline, `AT2-*`, and remaining applicable concurrency/queue portions of `AT4-06`. | Optional memory or hostile-user isolation. |
| Optional memory extension | `AT3-*` and an authorized temporary Vault trial when memory is selected. | Bidirectional Obsidian synchronization or guaranteed note semantics. |
| Daily-use release of selected features | All applicable cases for those features, full relevant `AT4-*` including compatible-data rollback, and independent review. | Unselected features, multi-tenancy, or automatic production publication. |

When only part of an `AT4-*` case runs, record the exact subcase as passed and leave the whole case incomplete; do not convert a partial check into a full pass. Request/time limits apply from the first pilot. Disabled memory is not a blocker to a coding-only release.

A required case that is failed, blocked, skipped, or not run prevents that delivery claim. Permission escape, wrong-project mutation, false completion, lost/overwritten user data, and a surviving uncontrolled writer are hard stop conditions. Lower-impact limitations must be named and accepted explicitly; a pass percentage cannot waive a failed required case.

Each run report contains the source commit plus dirty-input snapshot, profile/policy versions, platform and storage provider, model identity evidence or its absence, acceptance IDs, exact command/manual steps, exit codes, artifact paths, reviewer, result, and known gaps. Use native runtime storage and one compact report; do not create a new approval hierarchy or duplicate every runtime event in Markdown.

For a delegated code delivery, include a compact Reviewer Index in that same report: exact changed files, critical code paths, tests executed, generated artifacts, known gaps, and suggested review focus. Preserve unrelated changes and do not stage, commit, push, or deploy as a side effect of acceptance tests.

## Dev Note

The immediate implementation experiment is the native-Team permission hookup and Goal-binding startup order, followed by one user-selected real task. A disposable keyless composition probe passed two focused assertions on 2026-09-02 within an eight-file, 199-test command; it supports the focused experiment but does not mark any proposed `AT*` case as fully passed. These documents do not select a task or authorize model spending. Broader implementation depends on the observed pilot result; see the [timeline](timeline.md) for the compact evidence record.
