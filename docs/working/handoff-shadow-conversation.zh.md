# 交接文档：影子对话（Shadow Conversation Entry）

[English](handoff-shadow-conversation.md) | 中文

> 交接时间：2026-09-11。前一模型：DeepSeek（glm-5.3-flash），主会话运行于 DSH Web GUI（127.0.0.1:3080，宿主进程内）。工作区：`D:\dsh-devframe`（所有路径相对此根，除非写明绝对路径）。

---

## 1. 用户需求的最终语义（务必先读懂，避免重蹈覆辙）

用户需求在本会话中逐步收敛，每一步都否定了前一种实现。**最终语义**：

> **影子 = 一个永久独立的 agent。** 侧栏「影子」按钮打开它自己的那一个固定对话（指定会话），走标准 DSH 会话界面渲染；每次点击进的是**同一个**对话；**不得**每次点击新建会话，**不得**在会话列表里产生"未分组/新对话"之类的杂项条目。

被用户明确否定的实现（不要再做回去）：
1. ❌ 自制弹窗聊天面板（纯文本行 + 轮询）——"你搞的是个什么东西？"
2. ❌ 任何自制对话框替代标准会话视图——影子必须用和主聊天**一模一样**的标准对话 UI。
3. ❌ 指向旧指定会话 session-8c2ada33（带满历史）——用户要求"重开一个"，已改为新指定会话（见 §4 配置）。
4. ❌ 每次点击新建一个全新会话——会在右侧会话列表出现"未分组"分类和"新对话"标签，用户明确拒绝。

保留的次要入口：宽侧栏「影子」触发键旁有一个**「管理」**小按钮（`data-shadow-manage`），打开原对话框（状态 + 项目管理 + 对话只读区），作为二级入口存在。

---

## 2. 当前代码状态（接手时的确切位置）

包：`packages/experimental/client-ui-shadow-entry`（`@deepseek-ai/dsh-experimental-client-ui-shadow-entry`）

### ⚠️ 未完成状态：测试当前是红的
最后一次全绿（55/55 + 100% 覆盖率门 + tsc + bundle 重建）是在"每次点击新建会话"版本上。之后我又改了两个文件，**尚未重跑测试**：

1. `src/client/mount.ts` — 已改好（最终语义）：`onOpenConversation` = `readStatus` → 未列出则 `refresh()` → `open(sessionId)`。**绝不再调用 `sessions.create`**（原因见 §3）。
2. `tests/shadow-mount.client.spec.ts` — 只改了 bench stub（sessions 增加 `list`/`refresh`，新增 bench 选项 `sessionNotListed`），**断言数组还没更新**，按旧 adopt 语义断言 `sessions/create:session-shadow`，会失败。

### 接替者第一步：完成 spec（预计 15 分钟）
- `registers one disposable footer action...` 的期望数组改为（去掉 create）：
  ```
  ['shadow/readStatus',
   'shadow/openProject:D:/projects/beta',
   'shadow/sendToController:ws-1:ship it',
   'shadow/releaseProject:ws-1',
   'shadow/readConversation:{}',
   'shadow/postMessage:hello shadow',
   'shadow/readStatus',
   'sessions/open:session-shadow']
  ```
- 新增分支测试（覆盖率门要求，代码正好 4 条路径：ok+已列出 / ok+未列出 / readFailure / 无 sessionId）：
  ```ts
  it('opens the designated session without create when it is not listed yet', async () => {
    const b = await bench({ sessionNotListed: true })
    const face = (b.entry()!.inject as unknown as () => { onOpenConversation: () => Promise<void> })()
    await expect(face.onOpenConversation()).resolves.toBeUndefined()
    expect(b.calls).toEqual(['shadow/readStatus', 'sessions/refresh', 'sessions/open:session-shadow'])
  })
  ```
- 现有 `does not adopt a session when the status read fails or names no session`（readFailure + sessionIdMissing 两臂，期望 `['shadow/readStatus']`）保持不变。
- bench 里 sessions stub 的 `create` 成员现已无人调用，可留可删（测试代码，不影响覆盖率门）。

### 然后跑三件套
```
# 1) 测试 + 逐文件 100% 覆盖率门
node_modules\vitest\vitest.mjs run packages/experimental/client-ui-shadow-entry --coverage.thresholds.100 --coverage.include='packages/experimental/client-ui-shadow-entry/src/**'
# 2) typecheck
node_modules\typescript\bin\tsc -b packages/experimental/client-ui-shadow-entry/tsconfig.json
# 3) 重建 bundle（必须，否则 GUI 看不到改动）
cd packages\experimental\client-ui-shadow-entry
node D:\dsh-devframe\node_modules\tsdown\dist\run.mjs
```
全部绿后**让用户刷新页面即可**（纯客户端改动，不需要重启宿主）。

### 本会话已改动的全部文件（均未提交，叠加在白天会话的大未提交集之上）
- `packages/experimental/client-ui-shadow-entry/src/client/mount.ts` — inject 增加 `'sessions'`；face 增加 `onOpenConversation`（refresh-then-open 版本，见上）。
- `src/client/slots.ts` — face 增加 `onOpenConversation(): Promise<void>`（JSDoc：永久独立 agent 的固定对话）。
- `src/client/ShadowCard.tsx` — 触发键 onClick → `void onOpenConversation()`（触发键不再开面板）；宽模式新增「管理」按钮开面板；对话框为大尺寸居中对话优先视图（默认 chat 视图 + `[data-shadow-view-toggle]` 切项目管理）。
- `src/client/ShadowCard.module.css` — `.trigger`（flex:1）、`.manageButton`、`.rail .trigger`（flex:none）、居中对话框、`.chatPane/.composer/.chatInput` 等。
- `src/client/locales.ts` — `trigger.aria`='打开影子对话'/'Open the Shadow conversation'；`trigger.manage`='管理'/'Manage'；另有 `panel.projectsTab`、`panel.close`。
- `tests/shadow-card.client.spec.tsx` — 29 用例全绿：`openPanel` 助手改为点「管理」开面板；`showProjects(b)` 助手点视图切换；触发键断言名 `打开影子对话`；新增视图往返/关闭用例。bench 已含 `onOpenConversation: vi.fn(async ...)`。
- `tests/shadow-mount.client.spec.ts` — 见上，**待完成**。
- **未做**：包 README.md / README.zh.md 尚未更新为"永久独立 agent 对话入口"语义（双语行对齐）；本改动尚未写 Agent Note（仓库规则要求非平凡改动配 note；已有 `​.agents/notes/implemented/bug-fix/2026-09-10-shadow-conversation-reachability.*` 三件套覆盖对话接线，触发键语义变化可更新该 note 或新写）。

---

## 3. 刚发现的关键根因（接替者必须知道）

**`session/create` RPC 对指定影子会话必然失败**：

```
POST /api/session/create  {args:{request:{sessionId:"session-0e48cb66-..."}}}
→ {"ok":false,"error":{"code":"session/conflict",
   "message":"session \"...\" records no cwd and cannot be adopted for \"D:\\dsh-devframe\""}}
```

影子代理在宿主启动时创建指定会话**不记录 cwd**，而 create 的 adopt 路径要求已存在会话的 recorded cwd 与请求 cwd 匹配 → 永远 conflict。之前对旧会话 session-8c2ada33 的 create"成功"是因为那个会话记录了 cwd。

**结论**：客户端打开影子会话的唯一正确路径 = `open()`（配合 `refresh()` 兜底），绝不 `create()`。若未来必须走 create（例如会话不在列表且 refresh 拿不到），正确修法在宿主侧：`shadow-controller/src/shadow-agent.ts` 创建指定会话时传入 cwd（ensureSession 调用点约在 202 行附近 `const id = SessionId(designation)` 之后）。

另：`open(id)` 对不在列表的 id "fail loud"（契约写明 unknown ids fail loud），refresh() 拉权威列表就是为了这个 race。错误如果被 `void onOpenConversation()` 吞掉就是"点了没反应"——目前实现里 readStatus 失败/无 sessionId 是静默 return（有意），open 失败会变成 unhandled rejection（控制台可见）。如需用户可见错误，考虑后续给 face 加错误通道。

---

## 4. 环境、路径、活体状态（全部实测过）

### 二进制与命令
- Node（不在 PATH）：`C:\Users\25313\.workbuddy-ai\binaries\node\versions\22.22.2-2\node.exe`
- Git（不在 PATH）：`C:\Users\25313\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe`
- 只有 Windows PowerShell 5.1（`powershell.exe`），**没有 pwsh 7**。注意 `Set-Content -Encoding utf8` 会写 **BOM**；写无 BOM 用 `[System.IO.File]::WriteAllText($path,$text,[System.Text.UTF8Encoding]::new($false))`。
- tsdown 入口是 `dist/run.mjs`（不是 run.js）。

### 宿主与配置
- 宿主 supervisor 状态：`C:\Users\25313\.dsh\dsh-web-supervisor.json`（含 url+token、startedAt、restartCount）。宿主已于 2026-09-11T07:17:49Z 重启，**已加载新指定会话**。
- 部署补丁（影子指定在这里）：`C:\Users\25313\.dsh\profiles\web\devframe-deployment.yml` → `shadowSessionId: session-0e48cb66-32d0-413f-a034-904e8997f6d5`（已生效，probe 证实）。**该文件目前带 UTF-8 BOM**（我写坏过一次；YAML 解析器容忍了、probe 正常，但建议顺手去掉 BOM 并保留结尾换行）。原文件备份：同目录 `devframe-deployment.yml.bak.20260910-shadow-reset`。
- 影子路由配置事实：`shadowSessionId` 是 `shadow-router` 的 Config 字段，`devframe-deployment.yml` 是最后一层 --patch 覆盖；`devframe-profile` 仓内补丁声明三件套：shadow-router / shadow-controller / shadow-agent（`packages/experimental/devframe-profile/cordis.patch.yml` 26-39 行附近）。

### 活体 RPC 探针（已验证可用的信封格式）
```
# 先拿会话 cookie
Invoke-WebRequest -Uri "{base}/?token={token}" -SessionVariable ws
# POST，信封 method 必须写完整端点名；args 按参数名；返回 RemoteResult
POST {base}/api/shadow/readStatus
body: {"type":"client-request","rpcId":"p4","method":"shadow/readStatus","payload":{"args":{}}}
→ {"ok":true,"value":{"mounted":true,"shadowSessionId":"session-0e48cb66-...","shadowLive":true,"authorizedRoots":["D:\\dsh-devframe"],"bindings":[]}}
```
路由是**斜杠**形式 `/api/shadow/readStatus`（点号 404）。写方法的 args 形如 `{"request":{...}}`（按参数名 `request` 键控）。

### 宿主侧架构事实（勿重新推导）
- `shadow-controller/src/shadow-agent.ts`：宿主启动时 create-or-resume 指定会话并跑影子 agent（Fix B：先 `await this.ctx.get("loader")?.await()` 再 ensureOnce，防启动竞态；lib 里已含此修复）。
- 客户端 `ctx.sessions` 运行时是 `ClientSessions`（实现 `ISessions`），但**类型层**与宿主 `dsh-session` 的 `SessionStore` 同名声明合并，属性代理类型不对 → 一律 `ctx.sessions as unknown as ISessions` 收口（mount.ts 现状）。`ISessions` 契约在 `packages/api/session-controller/src/client/contract/sessions.ts`：`list`（ObservableSnapshot，`SessionListState.ids`）、`open(id)`、`refresh()`、`create({workspaceId?,cwd?,sessionId?})`。
- mount.ts 的 `inject` 导出（dsh.client 信息性清单）现在是 `['remote','slots','locale','sessions']`；实际 cordis 注入 `ctx.inject(['remote.shadow','slots','locale','sessions'], registerUi)`。
- Web GUI 通过 `lib/client.js`（rev 参数）供包；**tsdown 重建后刷新页面即可**看到新客户端代码，无需 dev:web、无需重启宿主。宿主重启才会重读 yml 配置。

---

## 5. 接替者行动清单（按序）

1. **完成 spec**（§2 第一步的期望数组 + 未列出分支测试）。
2. **跑三件套**（vitest+coverage / tsc / tsdown），全绿。
3. **让用户刷新页面**，点「影子」验证：应打开 session-0e48cb66 的标准对话（干净空会话），重复点击进同一个，会话列表不新增条目。
4. **收尾文档**：更新包 README.md/README.zh.md（双语行对齐）为最终语义；更新/新写 Agent Note（触发键语义：永久独立 agent 对话 + create-conflict 根因 + open/refresh 路径）。
5. **已知遗留（按需向用户提议，勿擅自扩做）**：
   - 指定会话在会话列表里会有一条记录（标题在第一条消息后自动生成，之前显示"新对话"）。用户可能要求**彻底从列表隐藏**——那要改 sessions 域的列表过滤（对象层/宿主），是独立设计决定，需用户拍板。
   - 影子代理创建会话不记 cwd（§3 的宿主侧修复选项）。
   - 点击失败目前对用户静默（void 吞错）；如要求可见错误，需给 face 加错误通道。

## 6. 用户偏好提醒
- 全程中文交流；先说结果再给理由；不要堆日志哈希。
- 用户是"动手看效果"型：每改一步要给明确的"你现在做什么"（刷新页面 / 重启宿主）。
- **重启宿主前先告知用户**（那是他正在用的 GUI；且本会话就跑在宿主进程里，杀进程等于杀自己）。
- 不要把治理性动作（隐藏会话列表条目等）当成本任务目标擅自扩做——最终语义见 §1，超出部分先问。
