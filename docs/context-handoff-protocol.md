# Context Handoff Protocol

## 是什么

Context Handoff Protocol 是 DevFrame Control Plane 的标准化上下文交接协议。当新 agent、新 GPT session、新 conversation 或长上下文切换发生时，它确保新参与者能够可靠理解项目状态、安全边界和下一步任务。

## 为什么需要

新 conversation / 新 agent 不能依赖旧聊天记忆：
- 对话上下文窗口有限（~200 条消息后递减回报）
- 旧对话可能已关闭或不可访问
- 新 agent 没有旧对话的隐式知识
- 安全边界必须在每次交接时显式传递

## 触发条件

以下任一情况必须触发 handoff：

| 触发条件 | 说明 |
|----------|------|
| 新 conversation | 旧对话过长或关闭，切换到新对话 |
| 新 agent | 不同执行智能体接管任务 |
| 阶段跨越 | G0→G1→G2...每阶段完成后可触发 |
| 用户显式请求 | 用户要求生成交接文档 |

## 标准流程

```
1. 生成 HANDOFF.md（使用 HANDOFF_TEMPLATE.md）
2. 验证交接文档完整性（context_handoff.schema.json）
3. 提交到新 conversation 或新 agent
4. 捕获 bootstrap reply
5. 解析新参与者是否理解上下文
6. handoff_verified=true → 允许进入下一阶段
7. handoff_verified=false → fail-closed
```

## Fail-Closed 规则

若新 conversation / 新 agent 出现以下任一情况，必须判定 `handoff_verified=false`，不得继续后续阶段：

- 未按 YAML schema 回复
- handoff_understood 不是 yes
- safety_boundaries_understood 不是 yes
- 混淆当前阶段与下一阶段
- 声称尚未执行的阶段已完成
- 要求真实用户数据、cookies、session、browser profile
- 建议跳过授权直接执行
- 未确认 ready_for_next_authorization=yes

## 适用范围

此协议同时适用于 `code_project` 和 `paper_iteration` 两种模板。
