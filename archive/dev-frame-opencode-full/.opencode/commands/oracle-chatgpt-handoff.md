# oracle-chatgpt-handoff

通过 Chrome CDP 将 evidence pack 上传至 ChatGPT 并提交 GPT 复审 prompt。

```bash
python tools/oracle_gpt_full_review_flow.py --task-id s2
```

## 功能
1. 启动或连接 Chrome CDP runtime（端口 9222）
2. 打开目标 ChatGPT 会话（`TARGET_CHATGPT_URL.txt`）
3. 自动粘贴 `GPT_REVIEW_PROMPT.md`
4. 自动上传 evidence pack zip
5. 记录 pre-submit baseline（assistant 消息数量）
6. 等待用户输入 `SEND` 确认
7. 点击发送按钮
8. 监控新 GPT 回复（assistant 消息增加）
9. 等待回复完成（stop 按钮消失 + 内容稳定）
10. 只保存 SEND 之后的新回复
11. 解析 GPT decision（accepted/blocked/human_required）
12. 生成全流程报告

## 依赖
- Playwright
- Chrome（`C:/Program Files/Google/Chrome/Application/chrome.exe`）
- 独立 Chrome profile（`.chrome-cdp-profile/`）

## 安全
- 不使用 Claude Code computer-use 控制浏览器
- 不使用系统默认 Chrome profile
- 不读取 cookies
- 不绕过登录
- 不自动提交（需用户输入 SEND）
- 不删除/覆盖历史 evidence

## Framework Freeze Status
**正式能力** — 已验证可用。
