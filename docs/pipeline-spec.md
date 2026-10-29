# Pipeline Specification

## Pipeline 定义结构

```yaml
pipeline_id: "unique_id"
version: 1
description: "Human readable"
global_invariants:
  guard_removal_approved: false
  evidence_cleanup_approved: false
stages:
  - id: "stage_id"
    type: authorization | execution_closure | audit | planning | bootstrap
    depends_on: "previous_stage_id"
    requires_gpt_acceptance: true | false
    evidence_spec:
      required_files: [...]
      required_assertions: [...]
recovery_policy:
  max_retries_per_stage: 3
  cooldown_seconds: 30
  on_exhausted: human_required | stop | skip
```

## 阶段类型

| 类型 | 说明 | 需要 GPT | 修改状态 |
|------|------|----------|----------|
| bootstrap | 项目初始化 | 否 | 否 |
| planning | 设计/规划 | 否 | 否 |
| authorization | 请求 GPT 授权 | 是 | 否 |
| execution_closure | 提交执行结果 | 是 | 可能 |
| audit | 只读检查 | 否 | 否 |

## 状态转换

```
initialized → planned → in_progress → completed
                                  ↘ blocked → (fix) → in_progress
                                  ↘ failed → human_required
```

## 不变式

- 所有阶段前后检查 CURRENT_STATE.yaml
- blocked items 转换必须经过 authorization + execution_closure
- 证据包必须通过 manifest-zip 一致性检查
- GPT 拒绝 → blocked，不超过 max_retries
- 任何阶段可因 CDP 不可用 → human_required
