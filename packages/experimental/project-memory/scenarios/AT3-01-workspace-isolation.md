---
description: "AT3-01 recorded-session 场景草案：双工作区内存隔离（memory_search / memory_read / memory_append）。"
kind: "acceptance-scenario-draft"
---

# AT3-01 场景草案：双工作区隔离

包已在 main 4bc507e332，场景对其当前契约。

映射：`docs/testAndAcceptance.md` Part 3 `AT3-01` / `R3.1`（Obsidian memory，授权追加 + 新会话召回 + 跨项目不可见）。

## 目标

在一个用户选定的共享 Vault 上，两个工作区身份各自持有独立的 `projects/<workspaceId>` 命名空间；验证授权事实能以 provenance 召回，另一项目的私有 note 不可达，且回执与召回上下文都留在原生日志里。

## 前提（宿主集成）

包当前只作为库交付三工具（README Model Experience：宿主才负责接入 `ctx.tools`、任务起点注入召回、并把注入记入会话事件）。录制前需要宿主侧最小装配：

- profile 以 `resolveMemorySpec` 派生每个会话的 `MemorySpec`（`vaultRoot`、`writeEnabled`、`userScopeEnabled`、`workspaceId` 由宿主提供，服务不做隐藏回退）。
- `MemoryReceiptStore` 落在会话日志上：回执事件先于 `created` 返回持久化。
- 模型可见的召回注入按 "Model-visible ⟺ logged" 走会话事件。

本文件是草案，不是可执行录制；下列 turn 以行为层描述，最终以宿主装配后的实际工具事件为准。

## 计划录制布局

`snapshots/session/memory-workspace-isolation/`：

- `snapshot.yml`：`profile: headless`，`composition`/`header.class` 按装配后实际值；`recording: live`；workspace facts 记录两个 `workspaceId`（`ws-alpha`、`ws-beta`）与临时 Vault 根的相对事实。
- `session.jsonl`：packed rows，含 `memory_append`/`memory_search`/`memory_read` 工具事件、宿主回执持久化事件（顺序在 `created` 之前）、召回注入事件。
- `workspace.expected/`：只覆盖项目工作区；Vault 树属于用户选定目录，不落在 `workspace.expected/` 内（见开放问题）。

## Vault 与工作区夹具

一个临时 Vault（授权的临时目录，非仓库内）。服务实例绑定：A = `workspaceId: ws-alpha`，`userScopeEnabled: true`；B = `workspaceId: ws-beta`，`userScopeEnabled: false`；两者 `writeEnabled: true`，共享同一 `vaultRoot`。

## 剧本（replay 步骤）

1. A 追加项目观察：`scope: 'project'`、`kind: 'fact'`、`assertionStatus: 'observed'`、稳定 `sourceRef`、`body` 含可检索短语（如 `deploy script`）。预期 `created` + `relativePath` `devframe-memory/projects/ws-alpha/<64-hex>.md`；回执事件先于该结果出现。
2. A 追加人类确认的偏好：`scope: 'user'`、`kind: 'preference'`、`assertionStatus: 'confirmed'`、`humanConfirmation` 指向确认事件。预期 `created`。随后负例：同一偏好缺 `humanConfirmation` → `MEMORY_INVALID_REQUEST`（`append` 在派生 id 之前拒绝）。
3. 全新项目会话（无先前对话上下文）以 A 身份 `memory_search`（`scope: 'project'`，query 命中步骤 1 短语）：命中事实 note，hit 携带 `noteId`/`excerpt`/`createdAt`/`kind`/`status`/`snapshot`/`freshness`/`source` 全套 provenance；再以 `scope: 'user'` 搜到偏好。
4. B 会话同一 Vault：`memory_search`（同 query）不含 A 的任何 note；以 A 的 `noteId` 调 `memory_read`（`scope: 'project'`）→ `memory_missing`（read 不跨命名空间追索，目标路径按 B 自己的命名空间解析）。B 请求 `scope: 'user'` → `MEMORY_SCOPE_FORBIDDEN`，且该检查先于任何 note 内容读取。

## 可观察通过标准（对应 AT3-01）

- 允许的事实以 provenance 召回：每条 hit 与 read 结果都带状态与来源字段，无一个字段靠模型转述。
- 另一项目的私有 note 缺席：B 的搜索与读取都不可达，而 A 的文件仍完整存在于 `devframe-memory/projects/ws-alpha/`（目录级隔离由 `deriveNoteId(namespace, sourceRef)` 与命名空间解析共同保证）。
- 原生日志记录了到达模型的上下文：回执持久化事件与召回注入事件可在 `session.jsonl` 中按序找到。

## 环境与安全

只用合成内容；Vault 用临时目录并在用后清理；不写入任何真实凭据。

## 开放问题

- Vault 夹具归属：`snapshot.yml` 的 workspace facts 与 `workspace.expected/` 都只管工作区；Vault 期望树需要宿主装配面提供（扩展比较或独立断言），录制属主定案。
- 两个 `workspaceId` 在一次录制里如何派生（同一 profile 两次启动 vs 一次会话内两个服务实例）取决于宿主装配面，尚未存在。
