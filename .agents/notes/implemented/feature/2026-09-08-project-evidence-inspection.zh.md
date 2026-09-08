# Agent Note: Lead 检查权威项目证据

Status: implemented

[English](2026-09-08-project-evidence-inspection.md) | 中文

## 问题

独立 Lead 在记录审查前需要已交付的源码版本和实际检查结果。任务状态与 Worker 完成消息不提供这些证据。要求模型发现私有投影缓存会使审查依赖存储布局，还会消耗请求，却无法确定记录是否属于当前分配与 Goal。发现项参数若隐藏数组和对象结构，模型也无法得知审查执行器要求的 JSON 字段。

## 决策

[交付消费方](../../../../packages/experimental/project-controller/README.zh.md#deliver-and-review-work)向任务的实际父级 Lead 提供 `project_evidence`。工具只接受 `taskId`；当前绑定、角色策略、Goal 准入和已注册 worktree 所有权决定访问权限。它读取控制器已有的 DevFrame 投影，并共享交付工具按任务串行执行的队列。它不创建第二套证据存储，也不写入交付、验证、审查或任务状态。

结果标识当前任务与 Goal、最新交付、实际检查结果和已有审查。缺失与陈旧证据都有明确结果。匹配的交付要求观察到清洁且未改变的 Worker 源码，随后重新验证权限与所选记录。源码不清洁或无法观察时拒绝检查。读取证据不授予审查或集成权限：后续每项操作都会检查自身的当前准入条件。

渲染后的完整内容（包括文本包装层和 JSON 转义）使用配置项 `checkMaxOutputBytes` 的 UTF-8 字节上限。结果超限时拒绝返回，避免将不完整证据呈现为足以审查的内容。`project_review` 工具 schema 将发现项声明为对象数组，要求标识符、严重程度与说明；执行器仍然拒绝 JSON 编码字符串。

## 考虑过的替代方案

**从模型代码读取私有投影缓存。** 发现缓存不能确立当前 Goal、分配、源码或策略权限。按任务查询的工具将这项验证保留在拥有证据的控制器内。

**将任务状态或 Worker 完成状态作为审查证据。** 两者都不标识经过检查的源码，也不报告实际检查结果。独立审查需要持久化交付与验证记录。

**接受 JSON 编码的发现项字符串。** 这会为同一输入提供两种表示方式，并使模型可见 schema 保持模糊。结构化 schema 描述执行器本就要求的数组。

## 影响

Lead 可以通过普通日志记录的工具结果检查持久化证据，包括在交付消费方重新加载后。检查会增加有上限的会话内容；检查集较大时可能需要宿主提高输出上限。它不替代独立源码审查、不重跑检查、不集成工作，也不完成 Goal。

[集成恢复决策](../architecture/2026-09-07-controller-git-integration-recovery.zh.md)、[Worker 提交决策](2026-09-08-project-commit-consumer.zh.md)和[调度结算决策](../architecture/2026-09-08-dispatch-settlement-wake.zh.md)分别保留准入与恢复、授权提交和父级通知职责。证据检索不取代这些决策。

## 验证

[Loader 测试](../../../../packages/experimental/project-controller/tests/task-consumer-loader.spec.ts)覆盖 Lead 权限、缺失与陈旧记录、检查失败、只读检查、消费方重新加载、完整输出字节上限和数组形式的审查发现项。测试断言脚本化 Lead 的日志结果包含确切的 `review_ready` 交付与检查记录，并通过使用真实 JSONL 和存储提供方的新 Loader 恢复相同证据。测试使用真实本地 Git 和注册表。

[录制会话场景](../../../../snapshots/session/project-evidence-authority/snapshot.yml)验证工具定义、具名权限拒绝、字符串发现项被拒绝，以及数组发现项通过 schema 验证后被权限拒绝。Windows 刷新与重放通过。POSIX 预期输出由机械投影生成，尚未重放。脚本化模型响应不能证明真实提供方完成了任务。
