# Autonomous Progress Policy

GPT 和 agent 可自主推进的操作范围策略。

## 策略概述

本策略定义：在 Oracle GPT Review 自动化框架中，哪些操作可以由 GPT/agent 自主推进，哪些操作必须人工确认。

## GPT 可自主推进

| 操作 | 前提条件 | 约束 |
|------|---------|------|
| 判断 accepted / blocked / human_required | 有完整 evidence pack | 不得仅凭 agent summary 判断 |
| 判断是否 allow_next_stage | 所有 4 个条件满足 | 即使 allow_next_stage=true 也不得自动执行 S3 |
| 判断 S3 是否 allowed | full review 完成 | S3 仍需 agent 在本地执行 |
| 判断框架是否 ready | 有 framework freeze context pack | 可为下一步提供方向 |
| 生成 Frozen TaskSpec | 判断框架 ready | TaskSpec 不得包含高风险操作 |
| 建议下一步（非破坏性） | 有完整 context | 只建议不执行 |

## Agent 可自主推进

| 操作 | 前提条件 | 约束 |
|------|---------|------|
| 生成 evidence pack | task 有执行产物 | 不得伪造证据 |
| Chrome CDP handoff | CDP 可用 | 不得使用系统默认 Chrome profile |
| 粘贴 prompt | prompt 文件存在 | 不得改写 prompt 内容 |
| 上传 zip | zip 通过安全检查 | 不得上传非指定文件 |
| 点击发送 | 用户确认 SEND | 非交互环境需降级 |
| 监控 GPT 回复 | CDP 连接正常 | 只抓取 assistant 消息 |
| 保存 GPT 回复 | 回复完整 | 保存原始内容 |
| 解析 decision | 回复可解析 | 不得美化/包装结果 |
| 生成 reconciliation pack | 有 blocked reasons | 只处理可自动处理的问题 |
| 多轮 loop | max_rounds 内 | human_required 时停止 |
| 创建/更新命令文档 | — | 仅文档操作 |
| 创建/更新技能文档 | — | 仅文档操作 |
| 创建/更新配置文件 | — | 仅配置操作 |
| 运行测试 | 测试文件存在 | 记录退出码和输出 |

## 必须人工确认

| 操作 | 原因 | 确认方式 |
|------|------|---------|
| 执行 S3 | 下一阶段 | GPT 明确 accepted + S3 allowed + 人工批准 |
| 修改 S2 核心逻辑 | 影响已有系统 | 人工审查变更内容 |
| 修改 ai-workflow-hub/src/ | 高风险文件 | 人工 diff review |
| 修改 tasks.yaml | 核心数据文件 | 人工确认变更是必需的 |
| 修改 smoke_report.txt | 健康报告 | 人工确认 |
| 删除文件 | 不可逆 | 人工确认每个文件 |
| 移动/重命名文件 | 可能破坏引用 | 人工确认 |
| 清理 worktree | 不可逆 | 人工确认 |
| 覆盖历史 evidence | 审计链断裂 | 人工确认 |
| 修改 .env / 敏感配置 | 安全风险 | 人工确认 |
| 伪造 pre-S2 baseline | 证据造假 | **永远禁止** |
| 伪造测试结果 | 证据造假 | **永远禁止** |
| 包装 blocked/human_required 为 accepted | 审查失效 | **永远禁止** |
| 绕过 SEND 确认自动提交（非交互环境除外） | 安全 gate | 非交互环境降级为 PARTIAL |

## 非破坏性操作判定

非破坏性操作满足全部条件：
1. 不修改已有源码文件
2. 不删除、移动、重命名文件
3. 不覆盖历史文件
4. 只创建新文件（文档、配置、报告）
5. 不影响已有测试结果
6. 不影响已有 evidence pack

GPT/agent 可自主推进非破坏性操作。
高风险操作（删除、移动、重命名、清理、覆盖、伪造）必须 human_required。
