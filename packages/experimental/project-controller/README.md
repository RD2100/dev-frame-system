---
description: "Configure project task admission and controller-only Git integration with persisted verification, lead review, and explicit recovery."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-project-controller

English | [中文](README.zh.md)

## Summary

Track a task from assignment through review, integration, and completion, with an explicit recovery plan whenever work blocks or fails. Bound concurrent development without confusing task slots with model-request capacity. A registered root controller can integrate reviewed Worker commits through `project_integrate`; the tool checks current evidence and worktree ownership before a fast-forward, and integrates a diverged reviewed branch as a real merge commit. Interrupted operations retain an intent so the controller can inspect what Git actually changed before deciding whether to retry.

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the implementation](#understand-the-implementation)
- [Further Exploration](#further-exploration)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

Use this package for a project with one integration controller, plugin leads, and assigned Workers on registered worktrees. The host owns project admission, approved checks, and writer allocation.

### Composition and configuration

Mount `@deepseek-ai/dsh-experimental-project-controller` once for `ctx.projectController`, alongside storage-domain and session-identity. Mount `/consumer` for `project_integrate`, `/task-consumer` for `project_task`, and `/delivery-consumer` for `project_deliver`, `project_evidence`, `project_review`, and `project_commit`, using the full package name before each subpath. Mount `/request-budget-consumer` to enforce model sending admission. These consumers use the existing service and export Loader function-plugin namespaces without default exports.

Integration also requires live sessions, the DevFrame session projection, workspace and worktree registries, and persisted verification and review evidence. The tool additionally requires the live Agent registry and tool runtime. The [real Loader test composition](tests/consumer-loader.spec.ts) supplies these prerequisites and exercises the two entries without making model requests.

| Entry | Field | Default | Meaning |
|---|---|---|---|
| Service | `maxActiveTasks` | `2` | Positive integer limit on tasks in `developing`. |
| Service | `requestBudget` | `1` | Positive integer cumulative model sending-attempt budget. |
| Request budget consumer | `controllerSessionId` | Required | Host-selected root Session for the exclusively scoped project model traffic. |
| Delivery consumer | `repairLimit` | `2` | Positive integer shared Goal correction limit; must match the command consumer. |
| Consumer | `requiredChecksPath` | Required | Absolute path of the existing approved-checks registration ledger. |
| Consumer | `gitExecutable` | Required | Deployment-selected Git executable. |
| Consumer | `gitTimeoutMs` | Required | Positive integer timeout in milliseconds per Git subprocess. |
| Consumer | `gitMaxOutputBytes` | Required | Positive integer output limit in bytes per Git subprocess. |

The consumer reads the configured ledger; it does not approve checks or create a replacement ledger. Missing registrations and corrupt contents fail admission. The host's controller tool policy must allow `project_integrate`; leads and Workers must not receive it.

### Bound model sending attempts

The request budget consumer requires the LLM service, live Agents, durable agent bindings, and the existing project controller in a scope dedicated to one project. Configure its root `controllerSessionId` on the host. Each actual initiating Agent must resolve to that root, its plugin Lead, or that Lead’s scoped Worker; unbound or foreign requests are refused. Use separate plugin scopes for unrelated model traffic.

The consumer reserves budget before delegating `llm/stream` to the adapter. Root, Lead, and Worker requests share the service budget, and each AgentLoop retry consumes another allowance. The last available allowance admits exactly one concurrent request. Cancellation or adapter failure after persistence does not refund a charge: a charge records a sending attempt, not supplier billing or proof that HTTP occurred. An uncertain storage write closes charging until service reload restores durable usage. Internal provider-SDK retries require adapter-specific verification.

### Plan and start tasks

Mounting the task consumer exposes only the `plan` and `start` actions. The host opens project admission with `startProject()`, prepares the current Goal binding, and allows `project_task` in the controller tool policy. Calls require the actual live root controller, the task in its current open Goal, and its registered worktree with the controller writer lock.

`plan` takes `taskId`, `title`, and `pluginId` and records a planned task. `start` takes `taskId` and an optional `briefing`; it derives exactly one live Worker from the task and plugin bindings. The Worker must belong to a matching plugin lead under that controller. Controller, lead, and Worker need independent registered worktrees in the Goal workspace, each with its own writer lock. The host supplies the existing Worker through the hierarchy/dispatch composition; this tool does not create it.

Start assigns a planned task, admits development within `maxActiveTasks`, and queues the optional briefing. Repeated starts reject after development admission and do not re-send the briefing. Ownership is checked again inside the serialized task-write queue and before briefing delivery.

A failed call may leave the task assigned or developing: task writes and briefing delivery are not atomic. Inspect the task board before recovery; an error is not proof that no state changed, and repeating start cannot recover a missing briefing for a developing task.

The [task Loader tests](tests/task-consumer-loader.spec.ts) exercise planning, authorization refusal, refusal after a durable stop request, three queued-write revocations, and two real Workers with overlapping model requests. The seven cases use real local registries, storage, dispatch, and worktrees; a scripted adapter supplies external model responses. They do not demonstrate an online model completing project work.

<a id="deliver-and-review-work"></a>
### Deliver and review work

The delivery consumer uses the same ledger and Git settings as the integration consumer. It additionally requires `requiredChecksByTask`, a host-owned task-to-approved-digest map, positive `checkTimeoutMs` and `checkMaxOutputBytes` limits per check subprocess, and the optional `commitPathsByTask` map registering the artifact paths each task may commit. Each registered check must run in the assigned Worker's actual worktree. Allow `project_deliver` and `project_commit` for Workers and `project_evidence` and `project_review` for their independent plugin leads. `checkMaxOutputBytes` also caps the complete rendered evidence result, including its text wrapper and UTF-8 encoding; an oversized result refuses and requires the host to raise the limit.

A Worker explicitly calls `project_deliver` with `taskId` from a clean, committed worktree. The host derives identities and source data, records a task delivery without changing the original Goal input binding, and runs the existing approved checks. Passing checks advance development to review only while the source still matches. Failed checks retain their results without advancing the task; failed or interrupted attempts require explicit `retryChecks: true` to rerun that approved checkset.

The actual parent lead calls `project_evidence` with `taskId` before reviewing. It reads the controller's recorded evidence for that task in the current open Goal and requires the current Lead assignment, role policy, and registered hierarchy worktrees with their writer locks. It reports the Goal and task state, approved checkset digest, latest delivery's commit, fingerprint and worktree, actual verification checks, and any recorded review. Missing records are `null`. The call does not run checks, record a review, or advance the task.

The result distinguishes `missing_delivery`, `stale_delivery`, `missing_verification`, `stale_verification`, and `checks_failed` from `review_ready` and `review_recorded`. A matching delivery is current only while its Worker source remains clean and unchanged; dirty or unobservable source refuses inspection. Authority or selected evidence changing during inspection also refuses. A `review_ready` result supplies evidence for the Lead's independent decision; `project_review` still checks current admission when called. The [evidence inspection decision](../../../.agents/notes/implemented/feature/2026-09-08-project-evidence-inspection.md) owns the retrieval rationale.

The actual parent lead calls `project_review` with `taskId`, `decision`, and `findings`. `findings` is a JSON array, with `[]` for no findings; JSON-encoded strings are rejected. Each finding requires non-empty `id` and `message` fields and a `severity` of `blocking`, `warning`, or `note`; `path` and a positive one-based `line` are optional. A pass requires passing verification for the latest delivery and submits that output. `changes_required` records the review, charges the shared Goal repair allowance, and returns the task to development within the active-task limit. Exhaustion retains the review without admitting correction. Identical retries reuse both the review and its durable repair receipt, including recovery from a failed task-state write. A conflicting decision requires a new delivery, and rejected source must change before another delivery. Idle Workers do not constitute delivery or approval.

A Worker producing task artifacts calls `project_commit` with `taskId`, explicit relative `paths`, and an optional single-line `message`. The host commits only paths registered for the task in `commitPathsByTask`; a task without a registered scope refuses. The commit refuses while the caller has a non-terminal background job, and rechecks after the single HEAD observation — a live job may still write the worktree, and that evidence is not an operating-system lock. The observation reads the registered branch ref from the owner workspace, never through the Worker checkout, and the worktree-registry commit Service re-verifies branch and expected HEAD inside its pinned gitdir. The Worker shell never runs `git commit`. Pending changes that remain after the commit are reported as unverified rather than classified; delivery still requires a fully clean worktree. Scope matching is exact and case-sensitive; on case-insensitive filesystems such as Windows this can only cause fail-closed refusals, never a bypass.

Evidence, repair admission, and task writes are separate durable operations. Journals using the same live controller Session share the append queue and persistence-failure latch across calls and consumers. Inspect retained evidence after an error; successful logging does not prove task advancement. Integration still requires the latest exact task delivery, verification, independent review, and unchanged source commit. The [DevFrame correction contract](../devframe/README.md#bound-correction-rounds) defines shared review/warning accounting and cold recovery.

### Task admission and integration

A fresh service starts `stopped`. The host calls `startProject()` before creating or advancing tasks through `planned → assigned → developing → reviewing → submitted`. A `blocked` or `failed` move requires a reason, next action, and wake condition; `resume` clears those fields and returns the task to `assigned`.

The integration tool accepts only `taskId` and `action`. It derives the caller from the actual live Agent, verifies the root-controller binding and session directory, and resolves source and target paths through the assigned Worker and controller worktree records. Model arguments cannot supply another caller, paths, check results, or merge markers.

Admission requires a submitted task, a current Goal binding, matching persisted verification and independent plugin-lead review, approved required checks, and no failing task warning. All three hierarchy worktrees must be independent and belong to the same workspace. The Worker and controller must hold their respective source and target writer locks. Source fingerprint, exact Git commits, clean worktrees, and the ancestry the selected mode needs are checked; evidence and ownership are rechecked before Git starts. A read-only relation probe selects the mode explicitly: a diverged reviewed source — the normal shape when two Workers branch from the same base — integrates as a real merge commit whose parents are the observed target head and the exact reviewed source, while every other relation keeps the fast-forward path.

| Action | Behavior |
|---|---|
| `integrate` | Prepare a fresh intent, execute one fast-forward or merge, and record `integrated` after observing the applied result. |
| `reconcile` | Observe a retained intent without repeating Git. An `applied` result can finish recording integration; `unchanged` does not advance the task; a `conflicted` merge left the conflict state for the operator; `ambiguous` requires investigation. |
| `retry` | Explicitly re-admit a prepared attempt only when its clean target still has the original HEAD. Current evidence and ownership must pass again. |

After interruption, reopen project admission and reconcile using the original controller identity and writer lock. An ordinary `integrate` call does not replace a retained intent. Neither a command error nor cancellation proves that Git left the target unchanged. An ignored local file that conflicts with incoming tracked content is preserved and causes the merge to fail.

A host consumer uses `requestMainTreeMerge(callerSessionId, taskId, request)`, then passes the returned marker directly to `integrate(taskId, marker)`. The request carries exact Git paths and commits, process limits, the approved-checks store, and optional `retryUnchanged` and cancellation signal. Markers are single-use object capabilities, not transferable JSON. The service's `reconcileMainTreeIntegration(callerSessionId, taskId, options)` reads the durable intent. Integration does not call `complete` automatically. Goal completion is its own gate: `selectGoalCompletionIntegration` builds the final-merge contract from the applied integration receipts plus the whole-Goal verification and review recorded for the Goal, and the completion admission then re-anchors its fingerprint stage at the merged tree — the initial start fingerprint is never rewritten into the final state. The production entry face is `selectGoalCompletionEvidence`: a Goal whose work never entered the controller tree keeps the plain completion lane, and once any integration receipt or whole-Goal record exists the gate is engaged and completion must carry the complete evidence, refusing an unfinished gate by name.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

The controller serializes task mutations and integration attempts. Task records, cumulative request charges, and Git intents persist through the `project_tasks` domain; lifecycle state and marker capabilities remain process-local. An applied Git observation is persisted before the task becomes integrated, so a failed task write can be reconciled after restart.

Evidence comes from the existing DevFrame projection and three-level binding registry. The package does not add a reviewer role or a second evidence database. A marker does not replace execution-time admission: a newer review, verification, warning, or ownership record invalidates the prepared evidence.

| File | Responsibility |
|---|---|
| [`src/controller.ts`](src/controller.ts) | Task lifecycle, serialized admission, durable intent, and recovery. |
| [`src/consumer.ts`](src/consumer.ts) | Integration tool entry, caller authorization, and host configuration. |
| [`src/task-consumer.ts`](src/task-consumer.ts) | Root-controller planning, registered Worker admission, and briefing delivery. |
| [`src/delivery-consumer.ts`](src/delivery-consumer.ts) | Explicit Worker delivery, approved checks, read-only evidence inspection, and independent lead review. |
| [`src/integration-evidence.ts`](src/integration-evidence.ts) | Exact task evidence and independent lead authority. |
| [`src/completion-contract.ts`](src/completion-contract.ts) | Final-merge completion contract from applied receipts and whole-Goal evidence. |
| [`src/git-integration.ts`](src/git-integration.ts) | Bounded Git inspection, fast-forward, exact-source merge, and outcome observation. |
| [`src/spec.ts`](src/spec.ts) | Versioned task, request-budget, and integration-intent storage. |

No runtime invariant companion is published: Git advancement and task persistence can differ after interruption, so reconciliation reports and resolves that recovery state rather than requiring continuous equality. The [controller recovery tests](tests/integration-controller.spec.ts) and [Loader tests](tests/consumer-loader.spec.ts) exercise these relationships; callers must reconcile uncertain outcomes.

</details>

-----

<a id="further-exploration"></a>
## Further Exploration

- [Architecture and profiles](../../../docs/architecture.md): supported launch and composition.
- [Agent hierarchy](../agent-hierarchy/README.md): controller, lead, and Worker authority.
- [DevFrame](../devframe/README.md): Goal binding, checks, and review evidence.
- [Worktree registry](../../workflow/worktree-registry/README.md): registered worktrees and writer locks.

-----

<a id="model-experience"></a>
## Model Experience

### Project task and integration tools

#### What the model sees

Mounting the consumer exposes `project_integrate` with `taskId` and `action` parameters. Successful results contain the task id, task state, and integration observation; failures report the refusal through the tool runtime. The ordinary tool call/result log carries these model-visible values. Mounting the service alone does not expose a tool. The task consumer separately exposes `project_task`: plan requires a title and plugin scope, while start accepts an optional briefing. Its result reports `taskId`, `state`, and `briefingQueued`; queued instructions do not prove Worker completion. The delivery consumer also exposes `project_deliver` (task and optional retry flag), `project_review` (task, explicit decision, and findings), and `project_commit` (task, explicit relative paths, and optional message); models cannot choose identities, source paths, check commands, or a commit scope beyond the host-registered one. The Lead's `project_evidence` takes only `taskId` and returns JSON with task and Goal identity, `status`, `reason`, and nullable delivery, verification, and review records. The ordinary tool call/result log preserves this evidence for subsequent model requests. The `project_review` schema exposes findings as an array of objects, including required fields and severity choices.

##### Delivery, review, and commit results

```markdown
Task <taskId>: <state>; <outcome>.
```

#### Token effect

The tool definition contributes request tokens when visible to the Agent, and each call adds its arguments and result to conversation history. This package has no measured fixed token cost. The request budget consumer adds no messages or tool definitions.

#### KV Cache effect

A stable tool definition can remain in a reusable request prefix. Changing tool visibility or configuration of the surrounding tool policy can change that prefix; calls and results extend conversation history. Provider cache reuse is not measured by the package tests.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>

These constraints matter when choosing the composition and handling interrupted work.

- The lifecycle starts stopped after restart. The host must reopen admission and reassess restored in-flight tasks; process-local markers cannot survive restart.
- The version 4 storage domain rejects older layouts. Do not activate it against an existing version 2 or 3 domain or reset that domain as an implicit upgrade.
- Integration supports clean, independent worktrees in one repository, with fast-forward updates and explicit merges of diverged reviewed sources. It does not reset files, resolve conflicts, or automatically repeat uncertain commands; a conflicted merge leaves the conflict state for the operator and every failure names what it observed.
- Writer locks require participating hosts to honor ownership. They do not fence unrelated filesystem writers or Git commands that bypass the registries.
- `maxActiveTasks` counts developing tasks, not live model requests. Request charges persist across restarts, but serialization belongs to one controller service instance; it is not a cross-process compare-and-set. Account and provider limits remain deployment concerns.
- Loader and real-Git tests verify local composition. They do not establish a shipped-profile rollout, production activation, or real-model completion quality.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
