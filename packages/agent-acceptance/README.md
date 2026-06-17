# Agent Acceptance — 规范验收层

> **Agent 冷启动：请按顺序读取以下文件，不要跳过。**
>
> 1. `BOOT_CONTEXT.md` — 冷启动入口（3K 字符，60 秒可读完）
> 2. `memory/index.md` — 记忆索引（按需检索任务/知识）
> 3. `PROJECT_HISTORY.md` — 完整项目历史（需要时阅读）
> 4. `D:\devframe-control-plane\PROJECT_HISTORY.md` — 控制平面完整历史
>
> 读完 BOOT_CONTEXT 后按 CLAUDE.md 协议工作。不再使用 HANDOFF 文档，不再通过 CDP 做任务交接。

---

## 分层

| 层 | 目录 | 职责 |
|----|------|------|
| PowerShell Runner | `scripts/` | 单命令验收入口，exit code 语义 |
| Batch Runner | `scripts/` | 批量任务执行，每任务独立报告 |
| WorkQueue | `agent-workqueue/` | 队列化批量推进，Tier 分级，升级规则 |
| Parallel Group | `scripts/Run-QueueGroup.ps1` | 受控并行，冲突防护 |

## 快速开始

```powershell
# Smoke — 7 项基础检查
powershell -ExecutionPolicy Bypass -File scripts/Run-Smoke.ps1

# Batch — 10 项本地质量检查
powershell -ExecutionPolicy Bypass -File scripts/Run-Batch.ps1 `
  -TaskFile scripts/examples/batch-local-quality.json

# WorkQueue — 5 队列批量执行
powershell -ExecutionPolicy Bypass -File scripts/Run-AllQueues.ps1

# Parallel — 3 并行安全队列
powershell -ExecutionPolicy Bypass -File scripts/Run-QueueGroup.ps1 `
  -Parallel -MaxParallel 2 `
  -QueueFiles agent-workqueue/docs-quality.queue.json,...
```

## 核心约定

- Exit 0 = PASS, 1 = BLOCKED, 2 = FAILED
- Tier 0 自动执行，Tier 2 必须升级
- 禁止假绿：FAILED/BLOCKED 不伪装成 PASS
- 默认 dry-run，真实操作需要显式 flag

## 文档

- `docs/RECOVERY_PIPELINE_RUNBOOK.md` — OS kill 后如何恢复
- `docs/AGENT_WORKQUEUE_RULES.md` — 分级与升级规则
- `docs/ARTIFACT_RETENTION_POLICY.md` — 产物清理策略
- `docs/OPERATOR_RUNBOOK_INDEX.md` — 操作手册索引
- `docs/NEXT_AGENT_HANDOFF.md` — 下一智能体交接
