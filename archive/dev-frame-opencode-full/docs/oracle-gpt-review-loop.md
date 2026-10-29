# Oracle GPT Review Loop

多轮 GPT-Agent 自动复审闭环架构与使用文档。

## 架构

```
GPT blocked result
    ↓
agent 读取 blocked reasons
    ↓
agent 生成 reconciliation evidence pack
    ↓
agent 通过 Chrome CDP 上传至 ChatGPT
    ↓
GPT 复审
    ↓
agent 抓取新 GPT 回复
    ↓
agent 解析 decision
    ↓
根据 stop rules 继续下一轮或停止
```

## 模式

| 模式 | 命令 | 说明 |
|------|------|------|
| dry-run | `python tools/oracle_gpt_review_loop.py --task-id s2 --dry-run true` | 读取历史结果，评估停止规则，不提交 GPT |
| live | `python tools/oracle_gpt_review_loop.py --task-id s2 --max-rounds 3` | 正式多轮 loop |
| 单轮 | `python tools/oracle_gpt_review_loop_once.py --task-id s2 --round 1` | 单轮闭环 |
| 中文 | `python tools/oracle_gpt_review_loop.py --task-id s2 --mode auto-non-human --language zh` | 中文自动非人工模式 |

## Stop 规则

| 规则 | 触发条件 | 行为 |
|------|---------|------|
| accepted + S3 allowed | GPT 明确 accepted 且 S3 allowed=yes | 停止，allow_next_stage=true |
| human_required | GPT 返回 human_required | 立即停止 |
| max_rounds | current_round >= max_rounds | 停止 |
| unknown | GPT decision 无法解析 | 停止 |
| repeated_block | 连续 2 轮同原因 blocked | 停止 |

## allow_next_stage 策略

只有同时满足以下条件才为 true：
- GPT overall_judgment: accepted
- GPT S3 allowed: yes
- new_reply_verified: true
- completion_status: complete
- 没有 human_required
- 没有 scope violation

即使 allow_next_stage=true，loop 不自动执行 S3。需要人工确认后由 agent 独立执行。

## 安全规则

- 不自动执行 S3
- 不修改 S2 核心逻辑
- 不修改原始 evidence pack
- 不伪造 baseline 或测试结果
- 不把 blocked/human_required 包装为 accepted
- human_required 时立即停止
- 中文 loop 只能处理无争议问题

## 配置文件

- `_reports/gpt-review-loop/s2/LOOP_CONFIG.yaml` — loop 配置
- `_reports/gpt-review-loop/s2/LOOP_STATE.json` — loop 状态

## Framework Freeze Status

**正式能力** — 已验证（dry-run + live + 中文），human_required stop 规则验证通过。
