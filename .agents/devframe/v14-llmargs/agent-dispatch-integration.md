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
