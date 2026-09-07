# A2 agent-dispatch integration — status, corrections, and evidence

Branch `codex/v14-llmargs` (tip after this stack), tree
`D:\dsh-devframe-v14-llmargs-lead`. Replacement lead A2 took over the
uncommitted 6-file WIP package `packages/experimental/agent-dispatch/` intact,
synced `main` (fast-forward `3b9e834042` → `43b36c1774`, exit 0, includes the
external B1 engine commits `f10efcd426` + `e330aea19b` already in history), and
landed the corrected adapter in two commits:

- `72a0beeffb` — scope policy reuses the engine approved-set contract + real
  registry worktree proof (validation face).
- `45003ca67c` — real assembly and dispatch chain + real createChildAgent test
  suite (assembly face).

Zero model calls; no full-repo build; the B1 dedupe/review matrix was consumed
read-only from
`D:/dsh-devframe-codex-b1/.agents/devframe/codex-b1/creation-integration.json`
and is not reproduced here beyond the deferred-items section.

## ① Verdict on the received WIP

- `entry.ts` header claimed the engine "lets a controller create any role" —
  outdated against the merged engine: `creation.ts` allows controller→lead
  only, and `e330` rejects scope-less requests before any binding.
- The lead scope check used the narrow `request.pluginId !== creator.pluginId`
  comparison — a lead approved for several plugins could not dispatch inside
  any but its own binding scope, contradicting the engine contract.
- `service.ts` called `worktreeRegistry.status(id)` and discarded the return
  value: `directoryExists: false` returns normally, and a registered id alone
  proves nothing about the requested path/branch. Any registered id paired
  with arbitrary request paths would have passed.
- No assembly existed: optional `options.setup` passed through verbatim, no
  preset join, no worktree bind, no prompt delivery — while the header claimed
  the setup order was "structural". No tests existed.

## ② Corrections

- Scope policy: `evaluateDispatchEntry(creator, request, approvedScopes)` now
  restates the daily two-step chain (controller→lead, lead→worker, worker
  dispatches nothing, explicit scope required) and reads the lead's plugin
  scope from the engine's own contract
  `config.leadPluginScopes[creator.agentId]`, sourced by the service from
  `ctx.agentHierarchy.config`. No second policy table; engine denials still
  propagate unchanged.
- Registry proof before the engine call, in this order: the authoritative
  `list(workspaceId)` row proves registration and ownership (unknown row or
  workspace → `DISPATCH_WORKTREE_UNREGISTERED`), then `status()` supplies the
  live observation (missing directory, wrong live branch, failed live
  observation on a proven row → `DISPATCH_WORKTREE_MISMATCH`; classified
  `WorktreeGitOperationError` refusals rethrow unchanged), plus row-path and
  foreign single-writer-binding checks. `status` alone is treated as carrying
  only `directoryExists/branch/clean`, per the external API verification.
- Real assembly inside the engine factory setup window: the child joins its
  parent's preset composition (`agentPresets.composeFrom`, the subagent seam
  convention, opportunistic — a no-op on a rosterless deployment), then takes
  the registered worktree's single-writer bind with the child session id as
  holder, then the caller's setup runs, then the engine persists the prepared
  binding and publishes. A caller-setup failure releases the entry's own
  bind. The new `DispatchAgentOptions.prompt` is delivered via
  `Agent.followup` strictly after creation resolves, never before
  publication.
- Surface: `ctx.agentDispatch.createChildAgent(parent, request, options)` with
  `options.workspaceId` required (anchors the row proof) and `options.prompt`
  optional; engine fields (`sessionId`, `agentOptions`, `signal`, `setup`)
  pass key-explicit. Error codes: `DISPATCH_WORKTREE_UNREGISTERED`,
  `DISPATCH_WORKTREE_MISMATCH`, `DISPATCH_PARENT_UNBOUND`,
  `DISPATCH_HIERARCHY_DENIED`.

## ③ Verification (real exit codes)

- `tsc -b packages/experimental/agent-dispatch` — exit 0. Program: this src
  plus vendor/cosmokit, vendor/cordis, agent-hierarchy, project-contracts,
  session-identity, core/agent, core/session, llm/llm, preset/agent-presets,
  workspace/workspace, worktree-registry.
- `tsc -b tsconfig.host.json` — exit 0. The host aggregate include covers
  `packages/*/*/tests/**/*.ts` (this package's spec is in the program) and now
  references the agent-dispatch project.
- `pnpm exec vitest run packages/experimental/agent-dispatch/tests/agent-dispatch.spec.ts`
  — exit 0, 3/3 passed (~5.9 s), zero unhandled errors. Every spec boots the
  real composition (agent loop, storage, workspace registry, git worktree
  registry, binding registry, engine, dispatch entry) and real git worktrees.
  Covered: lead-then-worker happy path with the worker inside a second
  approved plugin scope (the retired narrow comparison would reject it),
  registry `lockedBy` equal to the child session, binding-record fields, and
  prompt inbox delivery after publication; classified rejections for
  unregistered id, foreign workspace, vanished directory, wrong path, wrong
  branch, git-broken worktree, foreign lock holder, unbound parent, worker
  dispatcher, and unapproved lead scope.
- Commits ran `--no-verify` (no bash on host) with
  `git diff --cached --check` receipt exit 0 recorded in each message.

## ④ Deferred and unverified items (per the B1 creation-integration matrix)

- Shipped-profile mounting and a real model-driven dispatch round (profile
  script with a real worker model call) — NOT verified here; the external B1
  profile combination script owns it. The preset join is verified only as the
  rosterless no-op; a real-roster join assertion is part of that script.
- Model-driven delegation, durable task/result acknowledgement, and retry
  deduplication through this entry — NOT verified. The matrix's dedupe
  finding applies unchanged: `Inbox.append` rejects only currently pending
  ids, so reusing a child or message id proves nothing about once-only task
  execution.
- Publication-failure reservation recovery (retained bindings after a vetoed
  publication, missing persisted session logs) — NOT addressed here; the
  engine's reserved-child semantics and the matrix failure rules stand. The
  entry releases only its own bind on caller-setup failure.
- Product review/admission gate, integrated snapshots, and user-facing
  acceptance including broader Shadow/Memory scope — NOT started.

## ⑤ Identity retry, engine recovery lane, and the concurrency gate
(merge main → `e881697302`, engine recovery `190271fd4f` in history)

- `findDispatchedChild(parent, taskId)` exposes the durable identity an
  earlier dispatch returned, keyed by the engine's own dedupe rule
  (`parentSessionId` + `taskId`), with a `live` flag. A blind same-task
  retry refuses with `DISPATCH_IDENTITY_EXISTS`, naming the returned agent
  id; a retry that passes the id back as `sessionId` runs the full registry
  proof and the engine's dedupe answers with the same child. Reuse never
  re-delivers a prompt. Engine errors — including the reserved-child
  recovery refusal — propagate unwrapped; no replacement child.
- `recoverChildAgent(parent, request, {sessionId, ...})` routes the engine's
  fixed recovery lane behind the same entry proof and reuses the SAME host
  assembly as creation: the composed setup re-joins the preset composition
  and re-takes the worktree single-writer binding on the recovered session,
  with the identical failure-cleanup face. The recovery type omits `prompt`
  structurally. Corruption/cancellation surface as the same unwrapped
  instances; only the typed missing-log result republishes under the
  reserved identity (engine-owned).
- Per-task gate: one parent task's full dispatch span — identity judgment,
  engine call, first delivery — serializes inside one boundary. Creation
  dedupe is not delivery dedupe: two concurrent same-task requests both
  observed an empty registry behind the engine's serial creation and each
  delivered a prompt to the one child. The gate makes the identity
  observation atomic with the delivery decision; cleanup rides the
  never-rejecting tail (a `finally` on the gated result derived an unhandled
  second rejection). Proven by a concurrent pair resolving one child with
  exactly one briefing.
- Commits `fd51399465` (identity query + retry face), `c049c8a33f`
  (recovery lane + gate + one-shot briefing ownership). Evidence:
  `tsc -b tsconfig.host.json` exit 0; vitest `agent-dispatch.spec.ts` exit 0
  (6 passed, cold-restart reservation and dropped-lock re-bind proofs);
  `git diff --cached --check` exit 0 per commit.

## ⑥ Formal consumer: the `agent_dispatch` tool (commit `d24ebb48e6`)

- The composition layer's formal caller: the model-facing tool over
  `ctx.agentDispatch`, mirroring the agent-worktree seam (service constructed
  on the plugin fiber, system-prompt guidance, stable tool name). Parameters:
  `role/taskId/pluginId/worktreeId` required, `prompt` (fresh briefing, never
  re-sent on retry), `retry` (reuse the returned identity), `childId`
  (deployment-configured preallocated identity — the `leadPluginScopes`
  approved sets are keyed by these ids, so a model-dispatched lead must name
  its configured id).
- Authorization door: the calling session's workspace resolves from the
  immutable session header, extended to the workspace's registered worktree
  directories (a lead working inside its dispatched tree dispatches workers
  onto sibling trees). The worker role policy hides the tool entirely
  (restrict makes it unknown before any policy runs).
- `AgentDispatch` now declares `agents` in its static inject: the loader
  guard refuses undeclared service access, and the durable-identity query is
  the first accessor of `ctx.agents`.
- core/system-prompt allocates `TOOL_AGENT_DISPATCH: 2850` (between
  `TOOL_SUBAGENT` and `TOOL_REPORT`); shipped profiles do not mount the
  plugin, so recorded snapshots are unaffected.
- Evidence: `tsc -b tsconfig.host.json` exit 0; vitest
  `dispatch-consumer.spec.ts` + `agent-dispatch.spec.ts` exit 0 (11 passed)
  — schema, lead dispatch with lock/record/post-publication briefing, blind
  refusal, retry reuse without re-briefing, controller→lead→worker chain
  with approved-set keying, worker invisibility, unknown-worktree and
  lead-cascade refusals; `git diff --cached --check` exit 0.

## ⑦ Rows awaiting the controller's single write (verified deltas)

- Resolver manifests: `@deepseek-ai/dsh-experimental-agent-dispatch` is in no
  manifest that would serve a composition row (apps/cli deps and every bundle
  union checked); `@deepseek-ai/dsh-experimental-agent-hierarchy` likewise;
  `@deepseek-ai/dsh-experimental-session-identity` is already an apps/cli
  dependency. The consumer plugin's inject names: tools, systemPrompt,
  workspaceRegistry, worktreeRegistry, agentHierarchy, agentBindings, agents
  — the yml row must sit after the hierarchy stack it requires.
- Role policy requirement observed by tests: `roleToolPolicies` for
  `controller` and `lead` must include `agent_dispatch` in `inheritedTools`,
  or the restrict() install makes the tool invisible to exactly the roles
  allowed to dispatch.
- New public types since the controller's catalog pass:
  `DispatchedIdentity`, `RecoverDispatchAgentOptions` (service.ts), plus the
  consumer exports (`name/inject/apply/TOOL_NAMES`, `DispatchCaller`,
  `resolveCaller`, `requireNonEmpty`) — catalog regen (gen-cordis-catalog +
  api-catalog) owed by the single-write pass. No new session event types;
  the persistence-catalog gate is unaffected.

## ⑧ Loader entry fix (commit `a5bbfa7490`, P1 close-out blocker)

- The package root default-exported the service alongside the consumer
  namespace; the Loader unwraps `exports.default` first, so a shipped
  composition mounted the bare service, `apply` never ran, and the
  `agent_dispatch` tool never registered. The default export is removed:
  the function-plugin namespace is the only unwrapped entry; the named
  `AgentDispatch` export stays for direct service consumers.
- New `tests/loader-composition.spec.ts` boots a real cordis.yml through the
  real Loader (full stack, hierarchy role policy naming `agent_dispatch`,
  jsonl persistence) and proves the face the direct-service suites could
  not: tool registered on the namespace face, executable on controller and
  lead faces (lead→worker through the configured approved set), unknown on
  the worker face. Red-proofed: restoring the default export fails the
  tool-registration assertion.
- Evidence: `tsc -b tsconfig.host.json` exit 0; vitest all three dispatch
  specs exit 0 (12 passed); `git diff --cached --check` exit 0.

## ⑨ Durable task acknowledgment (commit `3aa5d27de1`, B1 open item closed)

- The dispatch entry mints a deterministic briefing identity from the
  durable binding facts (parent session id + task id), and
  `ctx.agentDispatch.taskAck(parent, taskId)` re-derives the account from
  the child's OWN session log — delivery splice, claiming splice, claiming
  turn's `turn/end` — so the ack survives restarts and the recovery lane by
  construction. No parallel in-memory ledger exists to lose.
- Durability is never inferred: the ack reads a snapshot, drives the
  session store's flush barrier over it, and grants `durable: true` only
  when a durability listener participates. A barrier failure reports
  `durable: false` + `degraded: true` instead of hiding the dispatch
  outcome behind an exception.
- States: `briefed` / `claimed` (claiming turn open) / `terminal`
  (`completed` exactly when the reason is `completed`, other reasons
  carried verbatim) / `dropped` (canceled unrun) / `unbriefed` (cold
  recovery republished an empty log) / `unavailable` (child not live).
- Tool face: the `agent_dispatch` result carries the ack; reuse renders the
  task's standing (wait, recover, or dispatch a new task). `AgentDispatch`
  and the consumer declare the `sessions` service for the loader guard.
- Proven over real jsonl persistence with real turns (scripted adapter,
  zero model calls): briefed/claimed/terminal(completed/error); unbriefed
  after a typed missing-log recovery; the terminal account surviving a cold
  restart through the reloaded log; fold unit cases cover dropped and claim
  forensics; the stub-harness consumer suite pins `durable: false` when no
  backend participates.
- Evidence: `tsc -b tsconfig.host.json` exit 0; vitest all four dispatch
  suites exit 0 (21 passed, two consecutive runs); `git diff --cached
  --check` exit 0. Branch tip after main fast-forward merge
  (`4b3212719f` in history): `3aa5d27de1`.
