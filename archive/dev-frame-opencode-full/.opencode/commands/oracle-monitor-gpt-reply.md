# oracle-monitor-gpt-reply

连接已有 CDP 会话，抓取 GPT 最新 assistant 回复并解析 decision。

```bash
python tools/oracle_gpt_reply_monitor.py --task-id s2
```

## 功能
1. 连接 Chrome CDP（端口 9222-9225）
2. 打开或复用目标 ChatGPT 页面
3. 等待 GPT 回复完成（stop 按钮消失 + 内容稳定 3 轮）
4. 区分用户 prompt 和 assistant 回复（内容评分制）
5. 只抓取 assistant 消息
6. 保存完整 GPT 回复
7. 解析 decision（accepted/blocked/human_required/S3 allowed）
8. 生成 monitor log

## 输出
- `_reports/gpt-reviews/s2-gpt-review-result.md`
- `_reports/gpt-reviews/s2-gpt-review-decision.md`
- `_reports/gpt-reviews/s2-gpt-review-monitor-log.md`

## 安全
- 不自动接受 GPT 输出
- 不执行下一阶段
- allow_next_stage 只有 GPT 明确 accepted + S3 allowed 时才 true
- 不得仅凭 natural language "pass" 判断 accepted

## Framework Freeze Status
**正式能力** — 已验证可用。
