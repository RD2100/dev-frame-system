---
description: DSH 原生 DevFrame 试点的紧凑里程碑记录。
---

# DevFrame 时间线

[English](timeline.md) | 中文

这是记录决策与验证结果的紧凑里程碑索引。详细行为放在设计与验收参考中；每个有意义的里程碑增加一条记录，不在这里复制每个运行时事件。

## 2026-09-02——权限与 Goal 启动顺序 spike

**状态：**作为无密钥集成证据 `passed`；这不是产品验收，也不是发布声明。

**基线：**DSH 提交 `4e84901e6471b79ec0338099867ebb4606d12bb5`；spike 在 `codex/dsh-permission-goal-spike` 分支运行，改动均为未提交的可丢弃内容。

**证据：**

- 真实组合同时启动了 AgentLoop、Goal、Goal Round Driver、Subagent、Team、Team 工具和 JSONL 持久化。
- 子会话 `toolFilter` 在冷恢复后仍然生效；继承的探针不可见，而作用域内的 `team_task_update` 仍可见，并在后置的 pre-execute 处理器允许时仍被审查者 guard 拒绝。
- Goal 创建后先停用续跑，再关联；关联事件刷盘后才显式恢复；恢复请求使用同一个 Goal 身份，未出现未关联的模型请求。
- 命令结果：8 个测试文件、199 项测试通过，其中包含 2 项聚焦 spike 断言，以及原生 Team、持久化、作用域、步骤拦截、Goal 和 Goal Round Driver 回归。

**决策：**原生接入点适合后续实现。探针证明需要保留窄范围的 Team 子会话组合参数透传；角色 profile、`/project` 流程、真实进程树停止／恢复、真实模型任务和效用试用仍未实现，也不作相应声明。

**记录卫生：**未使用凭据或模型费用，也没有提交、合并、推送或部署。完成本轮文档记录后，删除 spike 分支，只丢弃其可丢弃的探针与源码改动；保留用户原有文档和无关工作区文件。
