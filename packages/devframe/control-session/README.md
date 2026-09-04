# `@deepseek-ai/dsh-devframe-control-session`

English | [中文](README.zh.md)

Host-owned controller Sessions for DevFrame. The package provides `ctx.devframeControlSessions`; it reuses DSH's Agent Registry, Session Store, persistence service, Goal Service, and Workspace Registry instead of creating another controller database or runtime.

## Service API

- `openGlobal({ profileId, signal? })` opens `devframe-global:<profileId>` with `$DSH_HOME/devframe-control` as its fixed non-project cwd.
- `openProject({ profileId, workspaceId, signal? })` resolves the native Workspace, opens `devframe-controller:<workspaceId>` with that Workspace path in the native Session header, and attaches the durable Session to the Workspace.
- `dispatchGlobalGoal({ profileId, objective, maxGoalRounds?, signal? })` runs one bounded native Goal Round through the Global Controller's AgentLoop and returns a pathless trace after `ctx.sessions.flush(session)` succeeds. `maxGoalRounds` is restricted to `1`; the composed Host must provide the configured default model, AgentLoop, Goal Service, and goal-round driver. The Global Controller's tool surface is empty, so this path cannot touch project files.
- `dispatchProjectGoal({ profileId, projectId, projectRoot, objective, maxGoalRounds?, signal? })` **fails closed in Slice 0 with `PROJECT_DISPATCH_DISABLED`**: a Project Controller mounts the shipped coding preset with project File/Shell tools, and the Slice 1A authority and Slice 1C policy gates that must precede project writes do not exist yet. The identity-only `openProject` path remains available; the full dispatch machinery is preserved for the gated Slice 1 slice.

Repeated same-ID opens with the same expected identity return the same service-owned live Agent inside one Host process; a conflicting expectation fails with `LIVE_COLLISION`. IDs accept only bounded ASCII identifier characters. Public failures use stable `ControlSessionError` codes and never echo profile IDs, workspace IDs, paths, persisted payloads, prompts, or credentials.

## Profile Host fence

The package also exports `acquireProfileHostFence()`. The CLI acquires it before mounting any configuration plugin whenever the composed tree contains the `devframe-control-session` row, provides its token-free owner projection as `ctx.profileHostFence`, disposes the complete plugin tree first, and releases the fence last. Profiles without that row retain native DSH concurrency.

The lease is deliberately scoped to the whole `$DSH_HOME`, at `$DSH_HOME/devframe/host-lease.json`, rather than to a profile id: DevFrame profiles under one Harness home share the same JSONL persistence authority and must not become independent writers. The strict version 1 record contains only `version`, a random ownership `token`, `pid`, normalized `hostname`, and `startedAt`; public errors never include those values or the absolute path.

Creation uses exclusive `wx`. An existing same-host owner is reclaimable only when `kill(pid, 0)` reports `ESRCH`; a live PID, `EPERM`, a foreign host, malformed data, or any uncertain process/filesystem result fails closed. Takeover and release are serialized by an exclusive transition record, verify the owner token, and atomically rename the lease to a unique tombstone before deleting only that tombstone. A process killed while holding the ordinary lease can therefore be recovered on its next same-host launch without allowing two writers.

## Identity and durability

Creation prepares an unpublished Session, appends exactly one version 1 `controller/identity` event at sequence 0, persists it, and only then resumes it into the live Agent and Session registries. The service validates the Agent/Session/header relationship and returns only after `ctx.sessions.flush(session)` succeeds. Resume requires the same role-specific cwd; a persisted artifact that cannot be resumed is treated as invalid identity, never as permission to create a replacement authority.

The event contains `schemaVersion`, `role`, `sessionId`, `profileId`, canonical `cwd`, and, for a Project Controller, `workspaceId`. This does not create a new path exposure: native DSH Session summaries already carry the same header cwd to the browser. The bounded identity card does not render cwd. A Global Controller therefore cannot inherit the Host process's launch project through `process.cwd()`; a Project Controller still uses only its registered Workspace path. This identity-only tracer does not claim an `agentPreset` because it does not mount one.

## Execution policy

Global Controller setup installs an empty tool allowlist and a guard that blocks project/tool execution. Project Controller setup keeps the existing DSH tool registry available for the identity-only open, but opens only after the requested project id and root match a registered Workspace. In Slice 0 the bounded dispatch path is Global-only: it creates one native Goal, admits its single Goal Round, waits for the AgentLoop turn to settle, flushes the Session, and returns only safe identifiers and route metadata. Project write dispatch is hard-disabled (`PROJECT_DISPATCH_DISABLED`) until the Slice 1A/1C gates exist; a subsequent explicit Global task closes a prior stopped Goal before creating its own, and an armed active Goal is never replaced concurrently. Worker dispatch, policy escalation, retries, and the later autonomous DevFrame orchestration loop remain outside this slice.

## Model Experience

### Identity-only opens and bounded Goal dispatch

#### What the model sees

An identity-only open adds no model-visible content. The first bounded dispatch adds the native `goal/change` event, Goal Round prompt, and the model's normal request/response events to the same DSH Session; it does not add a second task/run log or expose paths, prompts, or credentials in the returned trace.

#### Token effect

Identity-only opens consume zero model tokens. A bounded dispatch consumes the tokens required by the configured model request; token accounting and user-visible budget controls are not part of this tracer yet.

#### KV Cache effect

Identity-only opens do not create a model cache prefix. Dispatch cache behavior follows the configured provider; DevFrame does not claim a cache policy in this slice.

## Known Limitations and Deferred Work

- **Interrupted transition requires recovery** — a process killed while the short takeover/release transition record exists leaves startup blocked instead of guessing whether a writer was admitted. Readiness diagnostics must require explicit local recovery after the operator confirms no DevFrame Host is running.
- **No atomic materialize API** — identity creation currently uses the public persistence `create` and `append` operations before live publication. A failed first append remains private and can be retried by this service; an uncertain or incompatible artifact is blocked and is never reported as ready.
- **Explicit profile identity** — callers must provide a stable validated `profileId`; the package does not provision a profile UUID or derive one from cwd or telemetry identity.
- **Bounded dispatch only, Global-only in Slice 0** — Global dispatch admits one Goal Round and requires an already-composed goal-round driver; Project dispatch is disabled (`PROJECT_DISPATCH_DISABLED`) until the Slice 1A/1C gates exist. Worker dispatch, controller-to-controller messaging, policy, retries, budgets, and autonomous indefinite iteration remain outside this package.
- **Task reuse is explicit** — a new request can close a prior `blocked`, `paused`, or disarmed Goal after its Agent is idle; an active armed Goal returns `GOALS_UNAVAILABLE` instead of being overwritten.
