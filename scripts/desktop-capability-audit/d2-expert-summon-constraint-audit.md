# D2 专家召唤约束审查

## 1. expert-team 后端执行机制梳理

### 工具注册（plugin.ts → tools.ts）

插件在 `apply()` 中调用 `createExpertTeamTools(orchestrator)` 并通过 `ctx.tools.register()` 将四个工具注入全局工具注册表：

| 工具名 | 并发安全 | 职责 |
|---|---|---|
| `expert_team_list` | ✓ | 列出已挂载的团队/专家/阶段元数据 |
| `expert_team_run` | ✗ | 启动流水线运行或单专家咨询 |
| `expert_team_status` | ✓ | 读取运行快照 |
| `expert_team_approve` | ✗ | 记录人工审批决定并恢复流水线 |

`EXPERT_TEAM_TOOL_NAMES` 常量明确禁止专家 allowlist 引用这四个工具，防止专家自行触发编排器。

### 工具权限约束（runtime.ts）

`createExpertAgent()` 在 `setup` 窗口内执行三层约束：

```
agentCtx.tools.restrict({ allow: [...expert.tools] })   // 可见层：仅暴露 allowlist 内工具
agentCtx.tools.guard(exec => allow.has(exec.name) ? undefined : '...')  // 执行层：运行时阻断
agentCtx.tools.presentAs('native')                       // 显示层：强制 native 面板
```

allowlist 在运行启动前由 `requireMountedTools()` 预验证（每个专家的工具必须已挂载），工具不存在则抛出 `EXPERT_TEAM_TOOL_MISSING`，运行不会创建目录。

### 阶段流水线（orchestrate.ts）

`startRun()` → `advance()` 按 DAG 拓扑顺序逐阶段调用 `drivePhase()`：

```
startRun(teamId, input)
  └── advance(record)
        ├── drivePhase(record, index, phase)   // 委托给 ExpertRuntime.executePhase()
        │     ├── requireMountedTools(expert)
        │     ├── derivePhaseAgent()            // 派生受限子 Agent
        │     ├── agent.followup(briefing)
        │     └── agent.whenIdle()             // 等待模型完成
        └── parkRun(state, phase)              // gate-pending → waiting-approval
```

每个 park 点调用 `persist()` 将 `run-state.json` 原子写盘。并发 approve 通过 `withRunGate()`（Promise 串行化）防止状态竞争。

### 人工审批（orchestrate.ts approve()）

`approve(runId, decision, comment)` 检查是否有 `gate-pending` 阶段：
- **approved**：phase.status → done，发送 post-approval followup，继续 `advance()`
- **rejected**：re-drive 同一 session（保留对话上下文），以 reviewer comment 为修改指引，重新 park 在同一 gate

失败阶段只能 rejected（不能 approved），对应 `EXPERT_TEAM_GATE_PENDING` 错误。

---

## 2. 当前 UI 召唤流程

### 召唤链路（ExpertTeamCard.tsx → selection.ts）

```
用户点击「召唤」按钮（ExpertCard 或 ExpertDetail）
  └── onSummon(target, summonPrompt(target, t, suggestion?))
        └── ExpertTeamCard.onSummon → summon(target, draft)  [face.summon]
              └── ExpertSelectionController.summon(target, draft)
                    ├── store.set({ target, sessionId: undefined })
                    ├── ctx.uiWorkspace.startSession()        // 打开新 blank session
                    └── reconcile()
                          └── ctx.conversation.input.for(scope).setDraft(draft)
                                // draft = t('center.defaultPrompt', {...}) + suggestion
```

**关键发现**：`summon()` 只做了两件事：
1. 打开新的空白 Session
2. 把一段模板文本（`center.defaultPrompt`）预填到输入框 draft

整个流程止步于 UI 层，**没有向后端发送任何 RPC 调用**，没有调用 `expert_team_run`，没有触发任何流水线。

### ExpertSelectionChip（ExpertSelectionChip.tsx）

Chip 只在 blank session 显示选中专家的标签（头像+名字），点击可移除，**本身没有任何提交或执行逻辑**。

### Gateway（gateway.ts）

`ExpertTeamGateway` 只暴露了一个 `@Remote('view')` 方法，即只读地返回团队列表和运行历史，**没有暴露任何 start/approve 操作**给 Web UI。

---

## 3. 约束接入现状

| 能力 | 状态 | 说明 |
|---|---|---|
| 召唤按钮 → 触发 `expert_team_run` | **缺失** | 召唤仅预填 draft 文本，由用户手动发送；模型收到消息后才可能自行决定调用 `expert_team_run`，但无强制触发路径 |
| 单专家召唤 → 工具权限约束（allowlist） | **已实现（后端）** | `createExpertAgent()` 同时应用 `restrict` + `guard` 双重约束；UI 展示了 allowlist 但对召唤路径无影响 |
| 专家团召唤 → 阶段流水线（DAG pipeline） | **缺失（UI 侧）** | 后端 `startRun()` + `advance()` 实现完整，但 UI 没有触发流水线的入口；用户只能靠预填 prompt 诱导主模型调用工具 |
| 人工审批节点 → `expert_team_approve` UI 入口 | **缺失** | RunSection 仅显示运行状态（status + dot），无 Approve/Reject 按钮，等待审批的运行无法从 UI 推进 |
| 专家上下文 → 通过 expert-team 注入 system prompt | **部分实现** | 后端 `composePersonaSection()` + `agentCtx.systemPrompt.section()` 在子 Agent 内注入；UI 召唤路径（主 session）完全绕过此机制，draft 只是普通文本 |
| Gateway → 写操作 RPC 暴露 | **缺失** | `ExpertTeamGateway` 仅 `view()`，没有 `startRun` / `approve` Remote 方法 |

---

## 4. 缺口与补缺方案

### 缺口 A：召唤按钮不触发 `expert_team_run`（最高优先级）

**现状**：点击「召唤」→ `setDraft(prompt)` → 用户手动发送 → 主模型可能调用工具（不确定）。

**最小修复方案**：
1. 在 `ExpertTeamGateway` 增加两个 Remote 方法：
   - `startRun(teamId: string, input: string): Promise<RunSnapshot>` — 委托 `orchestrator.startRun()`
   - `consult(teamId: string, expertId: string, question: string): Promise<ConsultResult>` — 委托 `orchestrator.consult()`
2. 在 `ExpertTeamCardFace` 接口中增加 `startRun` / `consult` 方法，由 `mount.ts` 连接到 `ctx.remote.expertTeam.*`
3. 在 `ExpertDetail` 中区分「召唤专家（咨询模式）」和「启动流水线」两个按钮，直接调用上述 face 方法，绕过 draft 预填路径

### 缺口 B：等待审批的运行无 UI 推进入口（次高优先级）

**现状**：`RunSection` 展示 `waiting-approval` 状态但无操作，门控阶段的 `userQuestions` 也不展示。

**最小修复方案**：
1. 在 `ExpertTeamGateway` 增加 Remote 方法：`approve(runId, decision, comment?): Promise<RunSnapshot>`
2. 扩展 `ctx.remote.expertTeam.view()` 返回值（或新增 `getRunDetail(runId)`）以暴露每个运行的 `userQuestions`
3. 在 `RunRow` 组件中，当 `status === 'waiting-approval'` 时展开审批面板：
   - 显示 `userQuestions` 内容
   - 提供 Approve / Reject 按钮 + 可选 comment 输入框
   - 点击后调用 `face.approve(runId, decision, comment)`
   - 增加相应 locale key（approve/reject/comment）

### 缺口 C：主 Session 召唤路径绕过 persona 注入（中优先级）

**现状**：`summonPrompt()` 生成的是普通自然语言 prompt，主模型没有获得专家 persona 的 system section；persona 仅在 `expert_team_run` 触发后的子 Agent 内注入。

**最小修复方案**（两个选项，选其一）：

- **选项 1（推荐，轻量）**：修复缺口 A 后，召唤直接走 `startRun/consult` 路径，子 Agent 内 persona 注入自然生效，主 session 不需要额外注入。
- **选项 2（不建议）**：在主 session 的 system prompt 中注入专家 persona section。实现复杂且让主模型"伪装"成专家，与后端架构设计（专家运行在独立派生子 Agent 中）不符。

### 缺口 D：Gateway 缺少写操作 Remote（配合 A/B 实施）

**最小修复方案**：
在 `gateway.ts` 增加三个 `@Remote` 方法，对应 `orchestrator.startRun()`、`orchestrator.consult()`、`orchestrator.approve()`，输入参数与工具参数保持一致。这三个方法执行实际后端操作，Remote 层需确认来源合法（Gateway 已在 Host 进程侧，信道本身受 TypertRemote 保护）。

---

## 5. 工作量估算

| 缺口 | 修复范围 | 估算工作量 |
|---|---|---|
| A：召唤触发 `expert_team_run` | `gateway.ts`（+2 Remote）、`ExpertTeamCardFace`（+2 方法）、`ExpertTeamCard.tsx`（按钮区分逻辑）、`mount.ts`（face 连接） | ~1 天 |
| B：审批节点 UI | `gateway.ts`（+1 Remote + view 扩展）、`ExpertTeamCard.tsx`（RunRow 审批面板）、`locales.ts`（approve/reject 文案） | ~1 天 |
| C：persona 注入（选项 1，依赖 A） | A 完成后自动覆盖，无额外工作 | 0 |
| D：Gateway 写操作（配合 A/B） | `gateway.ts` 单文件 | ~0.5 天 |
| **合计** | | **~2.5 天** |

### 建议修复顺序

1. **D → A**：先扩展 Gateway（D），再实现召唤真正触发运行（A）——解决最核心的"假召唤"问题
2. **B**：再接入审批 UI——使 `waiting-approval` 运行可从界面推进
3. **C（选项 1）**：A 完成后自动覆盖，无需额外操作
