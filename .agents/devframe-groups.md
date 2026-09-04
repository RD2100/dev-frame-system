# DevFrame 并行开发组注册表

夜间自主开发模式的组注册表。基线：`cbe08539d3`（main）。各组在独立 worktree 开发，只改自己的责任范围；合并条件见文末。控制会话：`session-714e9f00-099c-4b12-bddd-31185873b7fa`。

## G1 — SessionID 菜单与 Web UI 稳定性

| 项 | 值 |
| --- | --- |
| Group ID | G1 |
| Thread ID | d135afc3-9f0e-454b-b348-102136957643 |
| SessionID | session-714e9f00-099c-4b12-bddd-31185873b7fa（控制会话） |
| Worktree | D:\dsh-devframe-g1（分支 group1-session-ui） |
| 文件责任范围 | packages/client/ui-workspace/**（rows、locales、tests） |
| 验收标准 | 三个点菜单含“Session ID”；对话框显示完整 ID；点击 ID 或复制按钮均可复制；成功/失败均有明确反馈；重启、冷恢复后 ID 稳定；`pnpm run test:gui` 绿 |
| 测试命令 | `pnpm exec vitest run packages/client/ui-workspace` ；`pnpm run test:gui` |
| 状态 | **merged**（G1 submitted：b9edbb3924；main 合并提交 01eb0d288a；合并后 ui-workspace 155 tests 绿）。基线切片 45599c666c；实机验证全绿（2026-09-05 01:24，第二实例 :3081 + Playwright：行菜单 → Session ID → 完整 ID `session-714e9f00-…` 原样显示 → 复制按钮 → “已复制” → 剪贴板内容与完整 ID 一致，截图 apps/web/tmp-verify/sessionid-check.png）；该实例为全新启动进程，同一 SessionID 跨进程一致，即重启/冷恢复稳定性的直接证据 |
| 下一步动作 | 无（已合并）。遗留可选项：对话框上提为浏览器 owner 级需同步改 G1 钉住的两个测试（注释已互指） |

## G2 — Thread / Agent / Worktree 关联与状态

| 项 | 值 |
| --- | --- |
| Group ID | G2 |
| Thread ID | d9699759-fe06-492e-a29d-a92aec676399 |
| SessionID | session-714e9f00-099c-4b12-bddd-31185873b7fa |
| Worktree | D:\dsh-devframe-g2（分支 group2-thread-worktree） |
| 文件责任范围 | 新包 packages/workflow/worktree-registry（或 packages/workspace 下扩展现有服务）；Agent Note proposed/ |
| 验收标准 | WorktreeId 为 branded id 并持久化于 WorkspaceRecord 关联表；create/list/status/remove 服务齐备且有测试；不重复设计 SessionID（复用 dsh-brand、workspace 注册表）；README + 测试绿 |
| 测试命令 | `pnpm exec vitest run packages/workflow/worktree-registry`（或实际包路径）；`pnpm exec tsc -b tsconfig.client.json`（如涉及） |
| 状态 | 未启动 |
| 下一步动作 | 先写 proposed Agent Note（复用点：WorkspaceRecord、SessionHeader.cwd 归属、git worktree 命令面） |

## G3 — Project / Goal / Task / Evidence / 完成回执

| 项 | 值 |
| --- | --- |
| Group ID | G3 |
| Thread ID | 67e605ee-50da-43cf-bedd-7dd504e78114 |
| SessionID | session-714e9f00-099c-4b12-bddd-31185873b7fa |
| Worktree | D:\dsh-devframe-g3（分支 group3-goal-evidence） |
| 文件责任范围 | packages/goal/**、packages/experimental/devframe/**（goal-binding、projection） |
| 验收标准 | 完成回执以会话事件持久化（复用 goal/change 机制），Evidence 记录挂 GoalRef{id,revision}；不新造身份体系（复用 GoalId、TeamTaskId、WorkspaceId）；测试绿 |
| 测试命令 | `pnpm exec vitest run packages/goal packages/experimental/devframe` |
| 状态 | **merged**（G3 submitted：04e28977d5；main 合并提交 527269c5bf；合并后 packages/goal 143 tests 绿、test:docs 15/15 绿）。设计：`goal/change` union 新成员 receipt（GOAL_CHANGE_VERSION=1 不变，无格式 bump）；recordReceipt 带 CAS + complete 门；evidence 非空强制；fold 不改状态。deferred：devframe GoalBinding 回执引用、@Remote 暴露、模型可见呈现 |
| 下一步动作 | 无（已合并）。上游遗留：gen-cordis-catalog 在基线即红（ctx.profileIdentity partition violation，3bae3a9683 引入，非本夜改动），修复后重跑生成器闭合 goal.md 生成区 |

## G4 — 停止 / 恢复 / 超时 / 失败回滚可靠性

| 项 | 值 |
| --- | --- |
| Group ID | G4 |
| Thread ID | 3d2d84e9-d78a-4d45-a455-6dbcc55db82f |
| SessionID | session-714e9f00-099c-4b12-bddd-31185873b7fa |
| Worktree | D:\dsh-devframe-g4（分支 group4-reliability） |
| 文件责任范围 | packages/goal/goal-round-driver、packages/guard/**、packages/subagent/**（仅可靠性路径） |
| 验收标准 | 超时、停止、恢复、回滚路径各有行为测试；失败回滚不留半提交状态；不改动 goal/change 事件格式（避免与 G3 冲突） |
| 测试命令 | `pnpm exec vitest run packages/goal packages/guard packages/subagent` |
| 状态 | **merged**（G4 submitted：bb45d0ee29；main 合并提交 d28f2577bc；合并后 guard+goal 177 tests 绿、typecheck 绿）。加固：goal-round-driver teardown 撤回 latched queued round（latched-maintenance 窗口），2 个回归测试经 stash 对照验证无修复即失败。审计确认停止/恢复/超时/回滚既有覆盖密集 |
| 下一步动作 | 无（已合并）。未修复项（有理由）：retired-agent states Map 内部卫生、timeout 强制弃权（契约变更）、keepInbox 保留输入的 host 所有权边界——均已在 proposed Note Risks 记录 |

## G5 — 组合测试 / Web 回放 / 文档 / 快照 / 验收

| 项 | 值 |
| --- | --- |
| Group ID | G5 |
| Thread ID | 46bd891d-6c42-4ce3-8b9f-675f36ef69b9 |
| SessionID | session-714e9f00-099c-4b12-bddd-31185873b7fa |
| Worktree | D:\dsh-devframe-g5（分支 group5-qa-composition） |
| 文件责任范围 | snapshots/**、apps/web/tests/**（新增组合用例）、docs/**（文档同步） |
| 验收标准 | 产出组合测试计划与验收清单；为已合并功能补组合用例；快照只做针对性刷新（禁止无差别刷新）；`pnpm run test:docs` 绿 |
| 测试命令 | `pnpm run test:docs`；`pnpm run test:gui`；`pnpm run test:snapshot`（POSIX 项记录为 CI 信号） |
| 状态 | 未启动 |
| 下一步动作 | 先产出验收清单模板与本机已知环境限制清单 |

## 合并与验收规则

1. 只合并状态为 submitted 且附测试证据的组（证据 = 命令 + 结果摘要）。
2. 每合并一组跑该组测试命令；全部合并后跑类型检查、构建、test:gui、组合测试。
3. 快照差异只允许来自对应功能变更；禁止无差别刷新。
4. 本机已知限制（不阻塞）：无 npm/bash；`test:snapshot`、`test:web` 因 POSIX 夹具（bash 工具描述、JSON 转义）在 Windows 主机为既有红灯，属 CI 信号；提交用 `--no-verify` 并手工执行等价门禁（翻译配对、lint、notices、whitespace、零 vendor 暂存）。
5. 未经用户授权不推送、不发布、不删除数据、不重置用户改动；docs/env* 三文件永不提交。
