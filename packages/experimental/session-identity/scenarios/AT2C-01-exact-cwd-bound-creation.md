---
description: "AT2C-01 recorded-session 场景草案：精确 cwd 绑定创建——createBoundSession 一次调用写齐 header（逐字 cwd、parent、深度派生/显式）与 binding record，role/parent/深度/cwd 拒绝探针全部先于会话创建。"
kind: "acceptance-scenario-draft"
---

# AT2C-01 场景草案：精确 cwd 绑定创建

包已在 main（session-identity 合并提交 `c23e78a17a`；本分支基点 `4bc507e332` 验证），场景对其当前契约。

映射：[at2c-runner-checklist](../../../../.agents/devframe/accept/at2c-runner-checklist.md) `AT2C-01`；P22 验收矩阵 P01 责任面（[pluginized-round-registry.md](../../../../.agents/devframe/pluginized-round-registry.md) 6a 执行表"冷恢复与绑定测试"；`AT1-01`/`AT1-02` 的绑定注册表底座，[testAndAcceptance.md](../../../../docs/testAndAcceptance.md#part-1-acceptance)）。

## 覆盖契约要点

- `createBoundSession` 一次调用完成两件事：native Session 创建（header 携带逐字 `cwd`、`parentSession`、`delegationDepth`）与 binding record 的一次持久写——host Session id、parent、worktree 一次写齐，不 staging partial facts。
- 深度契约：缺省由 parent header 派生（`parent depth + 1`）；显式 `delegationDepth` 必须伴随 `parentSessionId`（`delegationDepth requires a parentSessionId`），且须为非负安全整数。
- 前置校验先于创建：未知 role（`"<role>" is not a hierarchy role`）、空 cwd（`cwd must be a non-empty absolute path`）、未知 parent（`SESSION_IDENTITY_PARENT_UNKNOWN`）都在 `sessions.create` 之前抛——拒绝路径零新会话、零 record。
- 非绝对 cwd 或重复 id 由 session store 拒绝，包装为 `SESSION_IDENTITY_INVALID_REQUEST`（`the session store rejected the creation metadata …`），仍在 record 写之前。

## 前提（宿主集成）

- 组合按 README 顺序挂载：storage → storage-json → storage-domain → `@deepseek-ai/dsh-session` → `@deepseek-ai/dsh-experimental-session-identity`。
- 模型可见桥由组合挂载波提供（工具桥，落地名草案：`identity_probe`），暴露 `createBoundSession` 的参数面（cwd/role/parentSessionId/delegationDepth/pluginId/taskId/worktree），结果携带返回 record 与 session header 元数据，或 `SessionIdentityError` 稳定码文本；桥形态未定前本条记 `blocked`，不降级为包内单测。
- 主会话（controller 父）预先存在于 session store，供 `parentSessionId` 引用。

## 计划录制布局

`snapshots/session/session-identity-exact-cwd-bound-creation/`：`snapshot.yml`（`profile: headless`、`recording: authored`、header pin 同 `text-turn`）；`session.jsonl` 单会话桥探针序列；`workspace.expected/` 固定 `session_identity` 域 `bindings` 表终态行数与字段面（`createdAt`/session id 的掩码方式见开放问题）。

## 剧本（replay 步骤）

1. 无父创建：`createBoundSession({ cwd: <工作区绝对路径>, role: 'controller' })` → record：`role: controller`、无 `parentSessionId`；header `cwd` 与请求逐字一致、无 `delegationDepth`。
2. 有父创建：`createBoundSession({ cwd, role: 'lead', parentSessionId: controller-1, pluginId: 'plugin-a', taskId: 't-1' })` → record 携带 `parentSessionId`/`pluginId`/`taskId`；header `delegationDepth` = parent depth + 1（缺省派生观察点）。
3. 显式深度：`createBoundSession({ cwd, role: 'worker', parentSessionId: lead-1, delegationDepth: 1 })` → header `delegationDepth: 1`（显式覆盖派生）。
4. 拒绝探针（每次先于创建失败）：未知 role → `"gatekeeper" is not a hierarchy role`；空 cwd → `cwd must be a non-empty absolute path`；未知 parent → `parent session "<id>" does not exist in the session store`；显式深度无父 → `delegationDepth requires a parentSessionId`；非绝对 cwd → store 拒绝的包装文本。全部 `SESSION_IDENTITY_INVALID_REQUEST` 或 `SESSION_IDENTITY_PARENT_UNKNOWN`。
5. 落盘：`bindings` 表恰 3 行，逐行与返回 record 一致（`agentId` = `sessionId`）。

## 可观察通过标准

- 步骤 1–3 的 header `cwd` 与请求逐字相等（"精确 cwd"契约本体）；record 字段与请求逐字对应。
- 每个成功调用对应恰一行落盘（一次持久写、无中间态行）。
- 步骤 4 的每个拒绝先于 `sessions.create`：会话文件数等于成功调用数，拒绝路径零 record。

## 环境与安全

合成 pluginId/taskId/worktree 值；cwd 指向录制专用临时工作区；无网络、无子进程。

## 开放问题

- 桥落地形态与 record/header 暴露字段面由组合挂载波定；JSONL envelope 以首录回填。
- `workspace.expected` 对 `createdAt` 与 host session id 的掩码方式（固定时钟 vs 正则锚）由 snapshots 属主定。
- `SESSION_IDENTITY_PERSISTENCE` 中段失败（session 已建、record 未写）需 fault 注入点，归包测试，不挤进首录。
