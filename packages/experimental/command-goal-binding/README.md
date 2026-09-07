---
description: "The human /devframe-start, /devframe-resume, /devframe-stop, and /goal-complete slash commands: start a bound goal with real verification evidence, resume it after a stop or restart, stop the project tree through the reliability stop chain, and complete it only through the verified completion admission."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-command-goal-binding

English | [中文](README.zh.md)

## Summary

`dsh-experimental-command-goal-binding` gives the human the start, resume, stop, and completion verbs of the DevFrame goal-binding flow. `/devframe-start <objective>` binds a new goal to the configured worktree and produces real verification evidence: the host computes the worktree's source fingerprint, registers the approved required-checks checklist, starts the goal through the controller, and lands the role-policy, goal-binding, and verification records on the controller session log by executing every declared check as a real subprocess. `/devframe-resume` restores the current bound goal after a stop or restart, rebuilding the binding from the session log projection or the binding store. `/devframe-stop` ends the current goal through the real reliability stop chain: it closes admission, drains the project tree's jobs and captured processes, flushes every participating session, and releases the writer only after the chain confirms quiescence. `/goal-complete` completes the current goal only through the verified completion admission: the source fingerprint must re-derive from the worktree, the registered required checks must have passed, and the authorized review must have passed. Every expected refusal comes back as a stable, direct command error that names the failed stage without exposing goal identities, so adapters can render it as command output. This is an experimental wave package: it composes the admission seam for host command surfaces and ships no host surfaces of its own beyond the commands.

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

Mount the plugin in compositions whose agents carry bounded goals, and give operators the human verbs that start a goal with real evidence, resume it across a restart, and complete it only when the admitted evidence chain holds.

### When to choose it

Choose it when a deployment wants goal work to be host-audited end to end: the objective and required checks are approved through the deployment config, start executes them for real and records the honest results, and completion means "the verified admission admitted it" — the source tree is exactly the bound snapshot, every required check ran and passed, and an authorized review passed. Hosts that start and complete goals through model-facing goal tools alone do not need it. The package is experimental and registers a private composition service, so treat its surface as wave-scoped rather than public.

### Command reference

| Input | Result |
|---|---|
| `/devframe-start <objective>` | Starts a new bound goal against the configured worktree: lands the role-policy, goal-binding, and verification records on the controller session log, and reports the real executed check count and verification status |
| `/devframe-resume` | Restores and resumes the current bound goal after a stop or restart, rebuilding the binding from the session log projection or the binding store |
| `/devframe-stop` | Runs the stop chain when `stopChain` is enabled: closes admission across the project tree, drains owned jobs and captured descendant processes, flushes every participating session, and releases the writer only after the chain confirms quiescence; an interrupted stop flow converges on the repeat stop |
| `/goal-complete` | Completes the current goal at the configured worktree through the completion admission and records one completion receipt |
| `/goal-complete <worktreePath>` | Completes the current goal against the given worktree, overriding the configured root |

### Stable rejections

Expected refusals are direct command errors with fixed text. Start refusals: a missing objective, a missing `workspaceRoot` in the config (the start line cannot name a worktree alongside the objective), and a goal that is already current and not complete. Resume refusals: unexpected input after the command name, no current goal, a goal that is already complete, and no binding record in either the session log projection or the binding store. Stop refusals (with `stopChain` enabled): unexpected input after the command name, no current goal, no binding record, a second chain while one is already in flight, and a binding that is already stopped. An unconfirmed stop — an unresolved job or process, a missing live agent identity, an unwired release hook, an unverifiable project tree, or a missing jobs registry — returns the stable needs-attention error naming every remaining resource (for example `job:<id>: timeout` or `writer:release: operation_failed`), reports that the writer remains held, and appends the inventory note when the project tree could not be verified; the flow stays re-stoppable, and the repeat stop re-enters the drain or the release instead of being refused. Completion refusals: no current goal, no completion binding for the goal, no attributed verification evidence, a goal that is already complete, a latched projection replay failure, and a missing worktree path when neither the command line nor the config names one. A rejected admission names its stage — `source-fingerprint`, `required-checks`, or `review` — without exposing the goal id or revision. Structural errors (`GoalBindingError`, `SourceFingerprintError`, `RequiredChecksError`, `DevFramePersistenceError`) are not caught: they fail dispatch so adapters report a command failure.

Fail-graded task warnings also report repair admission. Repeating the same warning reuses its durable receipt, including after restart; negative project reviews consume the same Goal allowance. The default `repairLimit` is 2. Human-authorized resume does not reset this accounting, and all consumers of the Goal must agree on its limit. See the [DevFrame correction contract](../devframe/README.md#bound-correction-rounds).

### Minimal configuration

The plugin injects the command registry, the goal service, the session store, and the session projection registry; a custom app mounts their owners plus this plugin. The start lane reads the approved work parameters from the config. Create the ledger’s parent directory (`D:/dsh-state` in this example) before the first start; keep the ledger outside the source worktree and reuse its path after deployment restarts:

```yaml
- id: commands
  name: '@deepseek-ai/dsh-commands'
- id: goal
  name: '@deepseek-ai/dsh-goal'
- id: session
  name: '@deepseek-ai/dsh-session'
- id: session-projection
  name: '@deepseek-ai/dsh-session-projection'
- id: command-goal-binding
  name: '@deepseek-ai/dsh-experimental-command-goal-binding'
  config:
    workspaceId: ws-team-alpha
    workspaceRoot: D:/worktrees/team-alpha
    requiredChecksPath: D:/dsh-state/required-checks.json
    taskIds: [task-alpha]
    maxAttempts: 3
    checks:
      version: 1
      checks:
        - checkId: unit-tests
          executable: pnpm
          arguments: [exec, vitest, run, packages/a]
          cwd: D:/worktrees/team-alpha
```

| Field | Default | Meaning |
|---|---|---|
| `workspaceId` | required | Workspace identity attributed to this composition's bindings and evidence |
| `workspaceRoot` | none | Worktree `/devframe-start` binds, and the fallback `/goal-complete` uses when the command line omits a path |
| `requiredChecksPath` | required | Non-empty absolute path without surrounding whitespace of the persistent approved-checks ledger; its parent directory must exist |
| `checks` | required | The human-approved required-checks checklist `/devframe-start` registers and executes for real; every `cwd` must be absolute |
| `taskIds` | required | Non-empty unique native task ids every start binding carries |
| `maxAttempts` | required | Maximum charged attempts frozen into every start binding |
| `maxGoalRounds` | none | Optional continuation round cap frozen into every start binding |
| `repairLimit` | `2` | Positive integer shared Goal correction limit; must match the project delivery consumer |
| `stopChain` | `false` | Runs the real reliability stop chain behind `/devframe-stop`; `false` keeps the vocabulary-only face |
| `stopGraceMs` | `2000` | Positive finite grace the chain grants its drains, session flushes, and terminal bookkeeping |

An empty `workspaceId`, a relative `workspaceRoot`, an absent, empty, or relative `requiredChecksPath`, a relative check `cwd`, an empty or duplicated `taskIds`, a non-positive `maxAttempts`/`maxGoalRounds`, or a non-positive-finite `stopGraceMs` fails plugin activation loudly. `repairLimit` must be a positive safe integer.

The mounted plugin persists approved check configurations under their canonical digests. The first start can create an absent ledger file, but its parent directory must already exist. Completion after restart resolves the historical digest from that same ledger; a missing ledger, missing digest, or corrupt registration fails instead of substituting the current deployment’s checklist. Retain older registrations while their evidence remains in use.

Delivery and integration consumers can read this same ledger. The deployment must designate one writer and serialize saves: whole-file replacement does not provide concurrent-writer merging or cross-process locking. Keeping the ledger outside the fingerprinted worktree prevents registration writes from changing the source evidence.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

This section explains how the commands resolve evidence and dispatch the admission; the observable contract is covered in [Use this package](#use-this-package).

### Design

- **Reads the projection this package owns.** Activation registers the devframe projection unit, and the handlers read its state for the invoking session: the latest verification evidence attributed to the current goal, plus the latest review record. Review evidence is not pre-filtered by goal — its attribution is enforced structurally by the admission, which fails closed on a foreign review.
- **The host collects every start fact.** `/devframe-start` computes the worktree’s [actual source fingerprint](../devframe/README.md#fingerprint-source-contents), derives `snapshot-v2-<headCommit>-<stateHash>` with the complete state hash, and hashes the approved objective and checklist into the acceptance digest. The command adapter supplies human authorization; model input never writes evidence, and the honest four-state check results are recorded as-is.
- **One role authority, derived from the log.** The reviewer directory resolves a Session's role from the role-policy snapshot folded into its devframe projection — not from a host-memory side ledger — so the review gate's authority is the session log's own record, and an unassigned role is fail-closed.
- **Journal instances share Session durability.** The composition and evidence journals flush through `ctx.sessions.flush`. Every journal using the same live Session shares its append queue and failure latch; one uncertain flush blocks later writes from all of them.
- **Fail closed before dispatch.** The handlers refuse on missing goals, missing bindings, missing evidence, or a latched projection replay failure before they reach the admission, and resolve the worktree path explicitly so a missing root is a data error rather than a structural failure.
- **Receipts only after admission.** An admitted completion advances the native goal through the admission's compare-and-set and records one `completion-admission` evidence entry through the goal service; rejections leave the goal phase, binding, and admission state untouched.
- **The stop chain is opt-in and host-wired.** The project tree face, the captured descendant processes, and the writer release are injection points on the composition service — not config: the host captures and owner-verifies the project tree (the root plus every real descendant agent) and owns the release. The chain fails closed on a missing or empty tree inventory, a missing jobs registry, and an unwired release hook — absent is never quiet.
- **The writer releases only after the confirmed chain.** The confirmed-quiescence record is the durable pre-release prerequisite; the stopped terminal record, store entry, and checkpoint land only after the release actually succeeded, each landing bounded by the stop grace so a never-settling persistence face returns instead of hanging. A release failure folds `needs_attention` and never lands `stopped`.
- **Interrupted stop flows converge on the repeat stop.** A log left at `stop_requested` (a crash during the drain) re-enters the drain over the host's current inventory; a log left at `quiescence_confirmed` re-enters the release. Missing live identities surface as `needs_attention` with the writer held — never a silent bypass, and interrupted goal work is never restarted.

### Source map

| File | Role |
|---|---|
| [`src/index.ts`](src/index.ts) | Plugin entry: name, injection list, config schema, apply |
| [`src/composition.ts`](src/composition.ts) | Composition service: start/resume/stop lanes, binding start lane, admission reads, completion handler, stop-chain drain and recovery |
| [`src/command.ts`](src/command.ts) | Command grammar, data-error texts, rejection rendering, receipt evidence |
| [`src/host-evidence.ts`](src/host-evidence.ts) | Flush closure, projection-derived reviewer directory, role-policy/goal-binding landing helpers, acceptance digest |
| [`src/config.ts`](src/config.ts) | Config schema and validation |
| — | No runtime invariant companion is published; admission semantics are owned and tested by the devframe package, and command behavior is covered by package tests. |

</details>

-----

<a id="further-exploration"></a>
## Further Exploration

The commands are thin host surfaces over the admission seam; read these pages for the contracts they compose.

- [DevFrame host-work session seam](../devframe/README.md) — the projection, fingerprints, required checks, and reviews these commands read and dispatch.
- [Commands service](../../interaction/commands/README.md) — the registry boundary the commands register into and dispatch through.
- [Goal service](../../goal/goal/README.md) — the native goal lifecycle the admission completes and receipts attach to.
- [Host command surface Agent Note](../../../.agents/notes/implemented/architecture/2026-09-06-command-goal-binding-host-command-surface.md) — the composition and attribution decisions.
- [Stop chain composition Agent Note](../../../.agents/notes/implemented/architecture/2026-09-08-command-goal-binding-stop-chain-composition.md) — the tree fail-closed, release-after-confirmation, bounded bookkeeping, and recovery decisions.

-----

<a id="model-experience"></a>
## Model Experience

### Human start, resume, and completion control

#### What the model sees

The slash inputs, the host's evidence collection, and the direct success/error outputs never enter model requests. `/devframe-start` and `/devframe-resume` append `devframe/role-policy`, `devframe/goal-binding`, and `devframe/verification` records to the controller session log — a host-side durable record that never enters a model request. An admitted completion records one `goal/change` receipt carrying the `completion-admission` evidence entry, and the projection this package registers exposes the binding, evidence, and review state to host surfaces; a later continuation prompt observes goal phases only through those owned channels.

#### Token effect

Dispatching a command, collecting evidence, and recording receipts add no model tokens. Later goal-round prompts see goal phases only through the ordinary request history an enabled driver assembles.

#### KV Cache effect

Command discovery, evidence collection, admission verdicts, and receipt persistence do not affect the cache. Later continuation prompts follow the driver's ordinary request history.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>

These limits define when the commands are a poor fit or need special operational care. They are current package constraints, not a task backlog.

- **Review production is not in this wave** — `/devframe-start` lands verification evidence only and fabricates no review decision; after it, `/goal-complete` honestly reports the missing review record (the stable no-review error) instead of completing.
- **Start has a partial-failure window** — if a journal landing fails after the native goal and the store binding exist, `/devframe-start` throws fail-closed without rolling them back; `/devframe-resume` is the recovery path (a binding present in the store without a log record is re-landed on the log).
- **One live writer per Session** — shared journal queues coordinate one live Session inside one process; they do not provide cross-process compare-and-set or protect multiple independently restored writers.
- **Binding restoration uses the Session log** — the composition’s default binding store remains in memory; `/devframe-resume` rebuilds it from the projection. The mounted plugin uses the file-backed required-checks store at `requiredChecksPath`; programmatic compositions retain their explicit store injection points.
- **The role policy assigns the controller role only** — no reviewer is authorized, so any review submission is rejected fail-closed until a review production wave lands a reviewer assignment.
- **Review attribution is structural** — `/goal-complete` takes the latest review record without a goal pre-filter; a foreign latest review surfaces as a structural `GoalBindingError`, which is the fail-closed direction.
- **Model completion paths bypass this seam** — model-facing goal tools that complete a goal directly do not run this admission; the commands gate only the human verbs.
- **The stop chain drains, never restarts** — a recovery re-runs the drain over the host's current inventory and fails closed on missing live identities; it does not resume or restart the interrupted goal work, and the writer stays held until a run confirms the tree quiescent.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

Review production and binding-store selection remain host-composition responsibilities. The stop chain's tree capture and writer release stay host responsibilities too; the composition refuses the release when either is absent.

</details>
