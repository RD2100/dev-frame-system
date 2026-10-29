# G8 Context Handoff Example

## 为什么 G8 前必须先进行上下文交接

当前对话（6a223019）已超过 220 条消息。GPT 审查效率随对话长度递减。G8 是第一次真实 GPT review pilot，需要新干净对话。

上下文交接确保新对话理解：
- G0-G7 已完成
- G7 只是 mechanical CDP pilot（发送按钮未点击）
- G8 是第一次真实的 bounded GPT review pilot
- 安全边界不变

## 流程

1. 使用 `templates/context_handoff/HANDOFF_TEMPLATE.md` 生成 `HANDOFF_G0_G7_TO_G8.md`
2. 用 `BOOTSTRAP_PROMPT.md` 模板包裹交接文档
3. 在新对话中发送 bootstrap prompt
4. 等待新对话按 YAML schema 回复
5. 验证 `handoff_understood=yes`
6. 只有 `handoff_verified=true` 才进入 G8 授权

## 文件

- `HANDOFF_G0_G7_TO_G8.example.md` — 示例交接文档
- `BOOTSTRAP_REPLY.example.yaml` — 合法 bootstrap 回复示例
