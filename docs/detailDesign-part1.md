---
description: Proposed single-project roles, execution, and guarded completion on native DSH Teams.
---

# Detailed Design Part 1: Single-Project Development

English | [中文](detailDesign-part1.zh.md)

## Summary

This reference specifies the first implementation slice of the [general design](generalDesign.md). A project controller owns a native flat Team with one worker and one read-only reviewer. DSH owns execution and team state; DevFrame adds role restrictions and a small completion check. All DevFrame tool names and data additions below are proposed, not existing public APIs.

## Table of Contents

- [Requirements and inputs](#requirements)
- [Work identity and consecutive tasks](#work-identity)
- [Roles and permission enforcement](#roles)
- [Execution and verification](#execution)
- [Completion and failure behavior](#completion)
- [DSH integration](#integration)
- [User operation example](#user-flow)

<a id="requirements"></a>

## Requirements and inputs

The controller receives a user-approved project root, a concrete task, allowed change scope, and required checks. The user or an existing trusted project configuration supplies check commands; an untrusted document cannot silently register a new executable check.

Resolve and freeze the required check IDs, command definitions, and snapshot exclusions at run admission. A worker cannot lower those requirements by editing project configuration; changing the accepted check list requires a new explicit user decision and invalidates affected evidence. Review must also inspect changes to test code or scripts for weakened coverage.

| ID | Required behavior | Acceptance owner |
| --- | --- | --- |
| `R1.1` | Enforce each role's tool access at creation, execution, and cold resume. | [AT1-01, AT1-02](testAndAcceptance.md#part1) |
| `R1.2` | Implement one task with one active writer and capture real check results. | [AT1-03, AT1-04](testAndAcceptance.md#part1) |
| `R1.3` | Accept only the tested and reviewed source snapshot; reject bypasses. | [AT1-05, AT1-06](testAndAcceptance.md#part1) |
| `R1.4` | Reuse native composition, member lifecycle, and bounded continuation. | [AT1-07, AT1-08](testAndAcceptance.md#part1) |
| `R1.5` | Keep task, evidence, and budget ownership correct across consecutive goals and recovery. | [AT1-09](testAndAcceptance.md#part1) |
| `R1.6` | Let a human configure, start, stop, resume, and inspect one project without model-mediated approval. | [AT1-10](testAndAcceptance.md#part1) |
| `R1.7` | Measure whether repeated real tasks reduce the user's operating burden compared with direct single-agent use. | [AT1-11](testAndAcceptance.md#usefulness) |

Missing acceptance scope produces `needs_input`, not an invented product requirement. A small read-only analysis task can explicitly declare code checks inapplicable, but a code-change task cannot silently replace execution with a narrative summary.

<a id="work-identity"></a>

## Work identity and consecutive tasks

For an explicitly started team-development task, one project run means one native Goal owned by the controller session. The stable run key is `(controllerSessionId, goalId)`; it is not a new Run record or database. Ordinary single-agent work can remain in a normal DSH session without entering this workflow or creating a Goal.

| Field | Source and binding rule |
| --- | --- |
| `controllerSessionId`, `goalId` | Native session header and Goal identity; capture at dispatch, never infer from whichever Goal is current when a result arrives. |
| `taskIds` | Native Team task IDs included in this Goal, associated by host-owned session events; native task rows still own task status. |
| `acceptanceHash` | Fingerprint of the approved objective, allowed paths, required check definitions, and snapshot exclusions; persist that configuration with the hash. |
| `snapshotId` | Input-content fingerprint captured by verification; not a task or Goal identity. |

Verification and review bind the complete tuple `(controllerSessionId, goalId, taskIds, acceptanceHash, snapshotId)` plus role-policy version. Task-set changes invalidate evidence for the previous set. Old unfinished board items block a new Goal only if explicitly included as its required dependencies; do not inspect every historical task as a completion prerequisite.

Native [Goal identity and revision](../packages/goal/goal/src/types.ts) have different jobs: the ID identifies the run, while `{ id, revision }` protects each mutation with compare-and-set. Pause/resume changes revision, not run identity. Resume retains consumed budget and may retain evidence only after checking the same tuple and unchanged source; changing acceptance requirements invalidates evidence even if source bytes are identical.

After Goal A is accepted, an explicit new start creates Goal B with fresh task bindings and budget; reuse the controller and members. An unfinished Goal is resumed or explicitly abandoned after draining, never silently replaced. Abandonment clears the current native Goal while preserving history and is not acceptance. Late A results remain attributed to A and cannot satisfy or charge B.

<a id="roles"></a>

## Roles and permission enforcement

Role names are host-owned enum values, not arbitrary personas selected by a model. Each project begins with the following roles; optional researchers and additional workers are deferred.

| Role | Allowed | Denied |
| --- | --- | --- |
| Controller / Team Lead | Read project context, manage native tasks, dispatch follow-ups, inspect evidence, request project completion. | Direct project-file mutation, arbitrary shell execution, unrestricted spawning, self-modification, and permission escalation. |
| Worker | Read and edit within the approved project scope, run allowed development commands, execute configured checks. | Changing another project, publishing changes, changing role policy, or declaring project acceptance. |
| Reviewer | Read source, diff, requirements, and captured check output; submit findings for a named snapshot. | Writes, shell, formatters, generators, jobs, delegated execution, and accepting its own fixes. |

Native `tools.restrict()` filters inherited tools, not tools registered in the current scope; the [scope tests](../packages/core/tools/tests/scoped.spec.ts) pin this behavior. [Team tools](../packages/experimental/tool-agent-team/src/index.ts) register in `agent.ctx`, so forwarding a child `toolFilter` alone does not enforce the role.

| Mechanism | Selected use in the pilot |
| --- | --- |
| Profile composition | Use native tool presentation; omit unused workflow, plugin self-modification, external-executor, and arbitrary MCP plugins. Do not expose raw model-facing Goal mutations. |
| `tools.restrict()` | Limit inherited file/shell tools per role; it is not the control for scope-local Team tools. |
| `tools.guard()` | Register a monotonic deny check in the managed profile, using the actual live caller and host-restored role; apply it to all dispatched tools, including scope-local tools. |

The reviewer may use project reads, `list_agents`, `team_task_list`, `team_task_get`, and `project_review`; deny Team spawning, task mutation, interruption, and work dispatch. The guard also rejects unknown identities, missing policy, and attempts to use model-supplied roles. A later pre-execute allow cannot override a guard denial. If disallowed local Team schemas remain visible, they remain execution-denied; hiding them requires changing their registration, not another `restrict()` call.

The project root retains only the user-granted project execution scope so that its worker can inherit that scope. The controller's model-facing tool restriction is separate from this delegated grant. Do not make the parent sandbox read-only and then try to escalate the worker; a reviewer receives narrower access, and no child may widen its inherited authorization.

A project has one host-enforced writer owner. The owner covers file tools, shell-launched processes, formatters, test processes, and background jobs until they actually finish. Native task `writeScopes` is descriptive metadata, not a lock; lock transfer and cancellation follow [Part 4](detailDesign-part4.md#stopping).

Read-only review is a restriction on agent tools and supported execution adapters, not proof that Windows prevents every hostile same-user process from writing. The deployment limits in the [general design](generalDesign.md#constraints) still apply.

<a id="execution"></a>

## Execution and verification

The controller keeps task dependencies and task status in the native Team board. A task becomes `completed` when its assigned work finishes; that does not complete the project's native goal or satisfy acceptance.

1. Read the project context and the relevant files; capture the pre-existing dirty baseline without resetting or stashing it.
2. Create the smallest useful native task and send the worker a bounded work request with scope and required check IDs.
3. Use Team `followup_task` for work that must start. Team `send_message` is quiet delivery and must not be treated as a wake-up.
4. After editing, the worker calls `project_verify`; the host runs the configured checks and captures their real exit status and output.
5. Quiesce the writer and send the reviewer the exact source snapshot, acceptance scope, diff, and check references.
6. If review requests changes, resume the same worker, invalidate the earlier evidence, and repeat checks and review within the repair limit.
7. Ask `project_complete` to validate completion; return its actual result to the user.

The proposed tools are session-scoped. Each takes `goalId` and `acceptanceHash`; the host validates the caller's dispatch binding and captures its `taskIds` before asynchronous work. Responses carry those bindings with bounded summaries and evidence references. Stale work returns `stale_work`; it never becomes evidence for a newer Goal.

| Tool | Additional input beyond `goalId` and `acceptanceHash` | Host-owned output and rejection |
| --- | --- | --- |
| `project_verify` | `checkIds`; the caller must be the active worker. | A `verificationId`, `snapshotId`, per-check exit status, duration, and output references. Reject unknown checks, the wrong project, or missing writer ownership. |
| `project_review` | `snapshotId`, `decision` (`pass` or `changes_required`), and bounded findings; reviewer only. | A review reference bound to reviewer identity, policy version, and snapshot. Reject unknown snapshots or a worker impersonating a reviewer. |
| `project_complete` | `snapshotId`; controller only. | After validation, obtain the current native `GoalRef` for the same Goal and complete with compare-and-set; reject a changed Goal instead of silently retrying on another one. |

A source snapshot fingerprints the relevant tracked and untracked input bytes, including tests, dependency locks, and configuration; `HEAD` alone is insufficient. The project configuration declares output/cache exclusions. Any change outside those exclusions invalidates the snapshot, including human edits made during a run.

The host checks the snapshot before and after verification and again before completion. Check records include the actual executable, arguments, working directory, exit code, and bounded log reference. A model-written success statement, a test count without a process result, or a cancelled command cannot produce passing evidence.

<a id="completion"></a>

## Completion and failure behavior

Completion succeeds only when this Goal's required `taskIds` are finished, every required check and independent review passes the same current work tuple, no blocking finding remains, and no writer-owned process is active. The validation and native-goal transition execute under the same project mutation exclusion. Native phase `complete` without matching evidence is `needs_attention`, not project acceptance.

The feature stores role/policy identity, the Goal-to-task binding and approved configuration, usage events, verification, and review references in native session persistence. These are proposed plugin-owned event records, not existing DSH fields; they must be replayable before admission. Source snapshots and logs use existing artifact storage. Native Goals and Team tasks retain their states; no separate Run or acceptance database is introduced.

| Condition | Required response |
| --- | --- |
| Check fails, is skipped, or times out | Keep the goal unfinished; show the failing check and available output. |
| Review requests changes | Return to the worker within the configured repair limit; each new snapshot needs new evidence. |
| Repair/member/request limit reached | Stop automatic continuation and request a human decision; do not spawn around the limit. |
| Persistence fails | Do not announce accepted completion; block further mutations until state is readable again. |
| User changes acceptance scope | Record the new user instruction and invalidate affected evidence; do not reinterpret an older failure as a pass. |

<a id="integration"></a>

## DSH integration

The [native child composition](../packages/subagent/subagent/src/child-agent.ts) supports persona/tool restrictions and persisted delegation policy, while the [Team roster](../packages/experimental/agent-team/src/roster.ts) does not forward all of those options. Forwarding native child options through the experimental Team API is a required source change; DevFrame roles and policy stay outside the generic core loop.

Install the profile-level `tools.guard()` before session restoration. Restore role/policy data into a synchronous lookup used by the guard; absence denies execution. The creation/setup path applies persona and inherited-tool restrictions to each exact agent scope before its first step. Cold resume repeats that setup; do not serialize a disposer or assume a prior process's guards survived. Dispose guards only after owned work has drained.

Model-step admission is separate from tool permission: use `agent/pre-step` to reject a closed or mismatched work binding, preserving downstream rejection when calling `next()`. [Part 4](detailDesign-part4.md#recovery) owns rejected-input recovery. Scope-local guard denial, cold restoration, and pre-step admission must each be demonstrated by the focused acceptance cases before claiming the integration works.

Prefer fresh continuable teammates to full-history forks for the first slice; the controller supplies concise task context. Only direct children are admitted, and generic recursive spawning is disabled. Reuse members rather than respawning per task: native `maxMembers` is a lifetime roster cap that also includes failed provisioning, not merely an active-concurrency limit.

Use [native presets](../packages/preset/agent-presets/README.md), scoped Cordis effects, and the documented `dsh --profile` launch path. The exact new profile/package name is chosen during implementation and is not an executable command promised by this design. The required user presentation shows task, role, check/review status, and blocking reason in the existing DSH UI.

<a id="user-flow"></a>

## User operation example

Use the existing DSH Web session/directory selector and its scoped command registry. Add one human-only `/project` command adapter in the managed profile; it is proposed and not available in the current checkout. Reuse native Goal services behind it, but omit raw `/goal` mutation commands in that profile so they cannot bypass project admission. Ordinary DSH profiles keep their own commands.

| Human action | Entry and required result |
| --- | --- |
| Open a project | Existing directory/session selection opens a controller with admission closed; show the canonical root and role profile before any mutation. No Shadow is needed. |
| Approve scope and checks | Proposed `/project configure <JSON>` previews `allowedPaths`, `checks` (`id`, `command`), `snapshotExcludes`, and effective limits; `/project confirm <previewId>` approves that exact current preview. |
| Start task A | Proposed `/project start <objective>` creates and binds one native Goal using the approved configuration, then opens admission. Duplicate start cannot replace an unfinished Goal. |
| Stop or recover | Proposed `/project stop` closes admission and drains work; `/project resume` verifies identity, retained budget, source, and process cleanup before resuming the same Goal. |
| Change checks or resolve attention | Stop first, submit a new configure/confirm pair, and invalidate affected evidence without resetting this Goal's budget. Identity/process ambiguity blocks resume; `/project result` shows the unresolved work. |
| Inspect and continue | Proposed `/project result` shows the current diff, work identity, real check output, review findings, and next allowed action; a later explicit start creates task B after A is accepted. |
| Abandon unfinished work | Proposed `/project abandon` requires quiescence, records the human decision, and clears the native Goal without deleting history or claiming completion. Starting another task remains a separate action. |

The configure parser accepts only documented fields, uses deterministic defaults for omitted exclusions/limits, and displays resolved values for confirmation. A stale preview is rejected. Generated check suggestions are not trusted commands until confirmed. Applying configuration requires quiescence; model tool calls or text resembling a slash command do not supply human confirmation.

Native `Goal.create()` arms continuation immediately. The start handler must close admission first, create and synchronously disarm the Goal, persist its approved work binding and budget before admitting input, then explicitly resume it under the same human start authorization. An interrupted setup stays closed for reconciliation. The complete user journey, including changed checks and recovery, is exercised by `AT1-10`; no modal UI or new desktop app is assumed.

## Dev Note

Use the [delivery table](testAndAcceptance.md#delivery) to select the required cases for an integration experiment, controlled pilot, or later release; exercise the feature's real tool path. Native Team regression tests are prerequisites, not proof that the new permissions or completion policy exist.

On 2026-09-02, a disposable keyless composition probe exercised child tool-filter restoration, scope-local Team denial, and Goal-binding startup ordering successfully. The result is recorded in the [timeline](timeline.md); it is supporting evidence for the focused experiment, not a claim that the role profile or `/project` workflow is implemented.
