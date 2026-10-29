# 工作流概念

## 核心循环

```
授权 → 执行 → 证据 → CDP 提交 → GPT 审查 → 闭合 → 下一阶段
```

## 阶段类型

| 类型 | 说明 | 需要 GPT 审查 |
|------|------|--------------|
| authorization | 请求 GPT 授权执行某项操作 | 是 |
| execution_closure | 提交执行结果给 GPT 审查 | 是 |
| audit | 只读检查，不修改状态 | 否 |
| planning | 设计/规划，不执行代码变更 | 否 |

## 状态转换

```
planned → authorization_submitted → authorized → 
  executed → closure_submitted → accepted → completed
```

任一阶段 GPT 返回 blocked → 修复后重新提交（有限重试）。

## 双循环模型

```
┌─ 授权循环 ─┐          ┌─ 执行循环 ─┐
│            │          │            │
│ 授权包     │  accepted │ 执行代码   │
│   ↓       │ ───────→ │   ↓       │
│ CDP 提交  │          │ 证据包     │
│   ↓       │          │   ↓       │
│ GPT 审查  │          │ CDP 提交   │
│   ↓       │ ←─────── │   ↓       │
│ accepted? │ blocked  │ GPT 审查   │
│            │          │   ↓       │
└────────────┘          │ accepted? │
                        └───────────┘
```

## 自动链式

GPT accepted 后自动进入下一阶段。失败时 fail-closed 停止。

## 重试策略

- 每阶段最多 3 次重试
- 30s 冷却间隔
- 连续 blocked 超过限制 → human_required
