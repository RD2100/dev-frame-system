---
description: "The human /goal-complete slash command for hosts completing a goal through the verified completion admission, with stable rejections and durable completion receipts."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-command-goal-binding

English | [中文](README.zh.md)

## Summary

`dsh-experimental-command-goal-binding` gives the human a `/goal-complete` command that completes the current goal only through the verified completion admission: the source fingerprint must re-derive from the worktree, the registered required checks must have passed, and the authorized review must have passed. The command dispatches through the real command registry, reads the devframe projection this package registers, and records a durable completion receipt on success. Every expected refusal comes back as a stable, direct command error that names the failed stage without exposing goal identities, so adapters can render it as command output. This is an experimental wave package: it composes the admission seam for host command surfaces and ships no host surfaces of its own beyond the command.

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

Mount the plugin in compositions whose agents carry bounded goals, and give operators one human verb that completes a goal only when the admitted evidence chain holds.

### When to choose it

Choose it when a deployment wants completion to mean "the verified admission admitted it" — the source tree is exactly the bound snapshot, every required check ran and passed, and an authorized review passed — and wants that gate on a human command rather than on model discretion. Hosts that complete goals through model-facing goal tools alone do not need it. The package is experimental and registers a private composition service, so treat its surface as wave-scoped rather than public.

### Command reference

| Input | Result |
|---|---|
| `/goal-complete` | Completes the current goal at the configured worktree through the completion admission and records one completion receipt |
| `/goal-complete <worktreePath>` | Completes the current goal against the given worktree, overriding the configured root |

### Stable rejections

Expected refusals are direct command errors with fixed text: no current goal, no completion binding for the goal, no attributed verification evidence, a goal that is already complete, a latched projection replay failure, and a missing worktree path when neither the command line nor the config names one. A rejected admission names its stage — `source-fingerprint`, `required-checks`, or `review` — without exposing the goal id or revision. Structural errors (`GoalBindingError`, `SourceFingerprintError`, `RequiredChecksError`) are not caught: they fail dispatch so adapters report a command failure.

### Minimal configuration

The command injects the command registry, the goal service, and the session projection registry; a custom app mounts their owners plus this plugin:

```yaml
- id: commands
  name: '@deepseek-ai/dsh-commands'
- id: goal
  name: '@deepseek-ai/dsh-goal'
- id: session-projection
  name: '@deepseek-ai/dsh-session-projection'
- id: command-goal-binding
  name: '@deepseek-ai/dsh-experimental-command-goal-binding'
  config:
    workspaceId: ws-team-alpha
```

| Field | Default | Meaning |
|---|---|---|
| `workspaceId` | required | Workspace identity attributed to this composition's bindings and evidence |
| `workspaceRoot` | none | Worktree used when the command line omits a path |

An empty `workspaceId` or a relative `workspaceRoot` fails plugin activation loudly.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

This section explains how the command resolves evidence and dispatches the admission; the observable contract is covered in [Use this package](#use-this-package).

### Design

- **Reads the projection this package owns.** Activation registers the devframe projection unit, and the handler reads its state for the invoking session: the latest verification evidence attributed to the current goal, plus the latest review record. Review evidence is not pre-filtered by goal — its attribution is enforced structurally by the admission, which fails closed on a foreign review.
- **Fail closed before dispatch.** The handler refuses on a missing binding, missing evidence, or a latched projection replay failure before it reaches the admission, and resolves the worktree path explicitly so a missing root is a data error rather than a structural failure.
- **Receipts only after admission.** An admitted completion advances the native goal through the admission's compare-and-set and records one `completion-admission` evidence entry through the goal service; rejections leave the goal phase, binding, and admission state untouched.

### Source map

| File | Role |
|---|---|
| [`src/index.ts`](src/index.ts) | Plugin entry: name, injection list, config schema, apply |
| [`src/composition.ts`](src/composition.ts) | Composition service: binding start lane, admission reads, completion handler |
| [`src/command.ts`](src/command.ts) | Command grammar, rejection rendering, receipt evidence |
| [`src/config.ts`](src/config.ts) | Config schema and validation |
| — | No runtime invariant companion is published; admission semantics are owned and tested by the devframe package, and command behavior is covered by package tests. |

</details>

-----

<a id="further-exploration"></a>
## Further Exploration

The command is a thin host surface over the admission seam; read these pages for the contracts it composes.

- [DevFrame host-work session seam](../devframe/README.md) — the projection, fingerprints, required checks, and reviews this command reads and dispatches.
- [Commands service](../../interaction/commands/README.md) — the registry boundary the command registers into and dispatches through.
- [Goal service](../../goal/goal/README.md) — the native goal lifecycle the admission completes and receipts attach to.
- [Host command surface Agent Note](../../../.agents/notes/implemented/architecture/2026-09-06-command-goal-binding-host-command-surface.md) — the composition and attribution decisions.

-----

<a id="model-experience"></a>
## Model Experience

### Human `/goal-complete` control

#### What the model sees

The slash input, the admission dispatch, and the direct success/error output never enter model requests. An admitted completion records one `goal/change` receipt carrying the `completion-admission` evidence entry, and the projection this package registers exposes the completed binding and review state to host surfaces; a later continuation prompt observes the completed goal only through those owned channels.

#### Token effect

Dispatching the command, receiving its result, and recording the receipt add no model tokens. Later goal-round prompts see the completed phase only through the ordinary request history an enabled driver assembles.

#### KV Cache effect

Command discovery, admission verdicts, and receipt persistence do not affect the cache. Later continuation prompts follow the driver's ordinary request history.

## Known Limitations and Deferred Work

<a id="known-limitations-and-deferred-work"></a>


These limits define when the command is a poor fit or needs special care. They are current package constraints, not a task backlog.

- **Memory stores only** — bindings and the required-checks registration live in process memory; after a restart the checklist registration is gone and the command fails closed with a structural error instead of completing.
- **Start and resume lanes are test-visible only** — this wave ships the completion command; host surfaces for starting, disarming, and resuming bindings remain deferred.
- **Evidence producers are deferred** — a completion needs prior `devframe/verification` and `devframe/review` records; hosts that do not produce them always receive the stable no-evidence error.
- **Review attribution is structural** — the command takes the latest review record without a goal pre-filter; a foreign latest review surfaces as a structural `GoalBindingError`, which is the fail-closed direction.
- **Model completion paths bypass this seam** — model-facing goal tools that complete a goal directly do not run this admission; the command gates only the human completion verb.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

This package is the v14 host-command-surface experimental wave. Open, undecided: host surfaces for the start and resume lane, production evidence producers, and durable stores; the memory stores are composition defaults, not a persistence promise.

</details>
