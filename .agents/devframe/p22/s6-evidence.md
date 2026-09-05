# S6 Role Whitelist Evidence and Verification Record

- Task: S6 (independent verification), supervised by L-Shadow, under the DeepSeek Harness pluginization plan (P22 line).
- Worktree: `D:\dsh-devframe-p-s6`, branch `p/s6`, baseline `9dbf3911f0` (current main HEAD including the docfix-2 README rewrite).
- Scope: static evidence for the agent-hierarchy role allowlist mechanism as it exists at the baseline, plus the two S6 runtime verification specs. Nothing in `packages/experimental/shadow-router/src/` was modified; `.agents/devframe/p22/anchor-matrix.md` was read as a reference only.

## 1. The current agent-hierarchy allowlist mechanism (as read from source)

**Schema** — `packages/experimental/agent-hierarchy/src/config.ts`: the validated host config carries `roleToolPolicies`, a lookup table over exactly three roles — `controller`, `lead`, `worker` — each a `roleToolPolicySchema` object with two fields: `inheritedTools`, the required list of global tools the role keeps (an empty list denies every global tool for the role), and the optional `denyScopedTools`, host-selected additional scope-local tool names denied for the role. `reviewer` is deliberately absent from the table ("its semantics live in the lead and worker deny faces" — `config.ts` roleToolPolicies comment and the `policy.ts` module doc): `send_message` is deliberately kept available to workers because it is the authorized reporting route toward the lead, while the merged reviewer denials sit in the lead face. `roleToolPolicies` itself has no default: `parseAgentHierarchyConfig` parses an omitted config object as `{}` (`safeParse(input ?? {})`), and a deployment that then lacks `roleToolPolicies` fails loud at load with `HIERARCHY_INVALID_CONFIG`; within the config, `denyScopedTools` is optional (absent = no extras) and `leadPluginScopes` defaults to `{}` (unlisted leads are approved for nothing — fail closed).

**Enforcement** — two independent halves. The *allow face*: `AgentHierarchy` (`src/service.ts`) installs, for every agent bound to a hierarchy role, `agent.ctx.tools.restrict({ allow: [...policy.inheritedTools] })` on that agent's scope (`installRestriction`), triggered from the `agent/created` listener, lazily from the guard's `onRoleResolved` hook, and re-installed for restored bindings at service init (`reinstallForActiveSessions`, cold recovery). Per the tools registry contract (`packages/core/tools/src/index.ts`), a restriction filters what the scope *inherits* — the global layer and every ancestor layer — and never what the scope's own layer registers, so the allow list gates global tools only. The *deny face*: `src/policy.ts` `denyFaceFor(role, config)` builds the monotonic deny set (controller = host extras only; lead = package `teamToolNames` + extras; worker = `delegationToolNames` + `teamToolNames` + `otherCreationToolNames` + extras), and `src/guard.ts` `createHierarchyGuard` — registered once on the root registry via `ctx.tools.guard(...)` in `service.ts` — resolves the executing agent's role live from the binding registry at execution time and enforces, in order: exact live identity, fail-closed role presence for controlled tools, the role's deny face, the absolute delegation-depth budget, and the lead's approved plugin scopes. Guards can only narrow, never allow.

**Deployed wiring** — `.agents/devframe/integration/cordis.patch.yml`, the `agent-hierarchy` row's `roleToolPolicies` block: three roles with `inheritedTools` lists and **no `denyScopedTools` for any role**, plus `delegationToolNames: [subagent, subagent_fork]` and `leadPluginScopes: {}`. The full deployed lists (read in their entirety for this record, not from the block head):

- `controller.inheritedTools` (26 entries): `bash`, `create_goal`, `edit`, `exit_plan_mode`, `get_goal`, `glob`, `grep`, `interrupt_agent`, `job_kill`, `job_list`, `job_output`, `list_agents`, `ralph`, `read`, `read_image`, `send_message`, `skill`, `str_replace_editor`, `subagent`, `subagent_fork`, `todo_write`, `update_goal`, `web_fetch`, `web_search`, `workflow`, `write`.
- `lead.inheritedTools` (26 entries): identical to controller, entry for entry.
- `worker.inheritedTools` (19 entries): `bash`, `create_goal`, `edit`, `get_goal`, `glob`, `grep`, `job_kill`, `job_list`, `job_output`, `read`, `read_image`, `send_message`, `skill`, `str_replace_editor`, `todo_write`, `update_goal`, `web_fetch`, `web_search`, `write` — i.e. worker lacks exactly `exit_plan_mode`, `interrupt_agent`, `list_agents`, `ralph`, `subagent`, `subagent_fork`, `workflow` relative to controller/lead.

## 2. Evidence matrix

Registration facts behind the cells (both read from source):

- The four shadow project tools (`project_open`, `project_send`, `project_status`, `project_stop`) are **scope-local installs**: `packages/experimental/shadow-router/src/tools.ts` `installShadowTools` registers them through `agent.ctx.tools.register(...)` into the scope of the one agent the host designated as Shadow via `ShadowRouter.markShadow`. They never appear in any role's global `inheritedTools` list, and the deployed integration profile marks no Shadow agent, so they are installed in no role's scope at all. (The allow list could not filter them even if a role held them — restrictions never filter a scope's own layer — but that path never arises: the install itself is Shadow-only by construction.)
- The three memory tools (`memory_search`, `memory_read`, `memory_append`) are **global registrations**: `packages/experimental/project-memory/src/plugin.ts` `apply()` registers all three unconditionally through `ctx.tools.register(...)` on the mounting (root) context; the deployed profile's `writeEnabled: false` / `userScopeEnabled: false` change what the tools may *do*, not whether they are registered. Because they are global tools, each role's `inheritedTools` allow list governs them — and the names are absent from all three deployed lists, so the installed `tools.restrict({ allow })` face filters them out for every role.

| Tool | controller | lead | worker |
| --- | --- | --- | --- |
| `memory_search` | EXCLUDED — global registration; name absent from the controller's deployed `inheritedTools` list (full 26-entry list read; the name does not appear) | EXCLUDED — name absent from the lead's deployed `inheritedTools` list (full 26-entry list read) | EXCLUDED — name absent from the worker's deployed `inheritedTools` list (full 19-entry list read) |
| `memory_read` | EXCLUDED — same evidence as `memory_search` | EXCLUDED — same evidence as `memory_search` | EXCLUDED — same evidence as `memory_search` |
| `memory_append` | EXCLUDED — same evidence as `memory_search` | EXCLUDED — same evidence as `memory_search` | EXCLUDED — same evidence as `memory_search` |
| `project_open` | EXCLUDED — scope-local install into the host-designated Shadow scope only; unreachable through the role's global allow list because it is never installed in the controller's scope, and the name is absent from the controller's deployed `inheritedTools` list | EXCLUDED — same mechanism; name absent from the lead's list (full list read) | EXCLUDED — same mechanism; name absent from the worker's list (full list read) |
| `project_send` | EXCLUDED — same evidence as `project_open` | EXCLUDED — same evidence as `project_open` | EXCLUDED — same evidence as `project_open` |
| `project_status` | EXCLUDED — same evidence as `project_open` | EXCLUDED — same evidence as `project_open` | EXCLUDED — same evidence as `project_open` |
| `project_stop` | EXCLUDED — same evidence as `project_open` | EXCLUDED — same evidence as `project_open` | EXCLUDED — same evidence as `project_open` |

Notes on the matrix:

- No deployed role configures `denyScopedTools`, so none of the seven names is denied through that face either; the exclusion mechanism is the allow list for the (global) memory tools and the absence of any scope-local install for the shadow project tools.
- None of the seven names appears in the hierarchy package's own deny face either (`denyFaceFor` covers only the delegation/team/creation surfaces plus host extras) — consistent with the exclusions being allow-list- and install-scoping-driven, not guard-driven.
- This matches the P22 anchor matrix's leftover item #6 observation ("memory 三工具已全局注册但未纳入 hierarchy 角色允许表（部署选择）") — here confirmed against the deployed lists directly.

## 3. Static evidence only

No allowlist was implemented or changed in S6. This record documents the mechanism as it exists at baseline `9dbf3911f0`; the memory tools' presence in or absence from any role's allow list is a deployment decision, and any future change to this matrix (tool-face work, `/project` command surface, role-surface re-planning) is owned by the P23/S4 proposal, not by S6.

## 4. S6 verification results

New vitest specs (both in `packages/experimental/shadow-router/tests/`, names carry the literal `S6`):

- `s6-markshadow-scope.spec.ts` — scope-level `markShadow` installation: with the real scoped tools registry accessor (`ctx.tools.schemas(agent)` / `ctx.tools.get(name, agent)`), the marked scope's visible tool set is exactly `[...SHADOW_TOOL_NAMES]` (asserted equal to the literal four names `project_open`, `project_send`, `project_status`, `project_stop`), the unmarked runtime agent's scope contains none of the four (zero leakage), and the real dispatcher cross-check returns isError with `unknown tool "project_status"` for the unmarked agent and isError false for the marked agent. **1 test, passed.**
- `s6-cold-restore.spec.ts` — binding row-level cold recovery: two real projects opened through `router.openProject` (rows traverse reserving → provisioning → ready through real storage), one delivery per project after `setActiveGoal`, then `h.close()` (context disposed, root kept) and a fresh `harness(root, { authorizedRoots: [root] })`. Post-restart, for each workspace: `findBinding` state `ready`, `bindingRevision` / `canonicalPath` / `controllerSessionId` / `profileKey` identical (plus a whole-record equality check — the restored row is the same durable row, not a re-created one), the controller session is absent right after the restart and exists again with matching `header.cwd` after an explicit `ctx.sessions.create` on the same reserved id, and `listDeliveries` returns the same message ids with state `received` (persisted received ≠ completed survives restart). **1 test, passed.**

Gates as run (from the worktree root):

- `pnpm exec vitest run packages/experimental/shadow-router/tests` → **Test Files 10 passed (10); Tests 22 passed | 1 skipped (23)**. The 23 = the pre-existing 21 (of which 20 passed and 1 — `aliases.spec.ts` "a symlink alias resolves to the target workspace on POSIX" — is platform-skipped on Windows by its own POSIX gate) plus the 2 new S6 tests, both passed.
- `pnpm exec tsc -b packages/experimental/shadow-router` → **exit 0, zero errors** (run on the frozen `src`; the specs are not in the package tsc program).

Fail-loud findings: **none**. Both required seams existed (the scoped tools registry accessors, the real cold-restart path through JSON storage + JSONL persistence with lazy materialization), and no gate failed.

## 5. 中文摘要

本文档为 S6 静态+运行时验证记录。现状机制：agent-hierarchy 以 `roleToolPolicies`（controller/lead/worker 三角色，各含 `inheritedTools` 全局允许表 + 可选 `denyScopedTools`）驱动两半执行——service 对每个已绑定角色安装 `tools.restrict({ allow })`（只过滤全局层，不过滤本层注册），guard 在执行时活解析角色并先查 `denyFaceFor` 拒绝面；`reviewer` 刻意缺席（语义并入 lead/worker 拒绝面）。部署接线在 `.agents/devframe/integration/cordis.patch.yml` 的 `roleToolPolicies` 块（三角色各 26/26/19 项，无 `denyScopedTools`）。证据矩阵结论：七个工具（memory_search/read/append、project_open/send/status/stop）对三个角色**全部 EXCLUDED**——memory 三工具是全局注册但名字不在任何角色的 deployed 允许表内（已逐项读全表核实）；shadow 四工具是仅装入被标记 Shadow 会话的 scope-local 安装，从不进入任何角色的全局表。S6 未实现或更改任何允许表；未来矩阵变更归 P23/S4 提案。运行时验证：两个新 S6 用例全过（包内合计 22 过/1 平台跳过/10 文件），`tsc -b` 零错误，无 fail-loud 发现。
