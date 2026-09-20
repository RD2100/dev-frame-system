# Agent Note：expert-team 插件的 M4 加固与发布准备

Status: implemented

[English](2026-09-15-expert-team-m4.md) | 中文

## Problem

M1 交付了带流水线编排的核心插件，M2 增加了第 5—8 阶段与 project-memory 记录，M3 增加了带层级绑定的层级模式。M4 的范围是加固与发布准备：多 pack 组合证据、实测 token/KV 影响、跨进程恢复决策、运行历史可观测性，以及面向用户的指南投影。

## Decision

**多 pack 组合**由两条新的 loader 组合测试证明：一条同时挂载已交付的论文 pack 与开发 pack，并断言两个团队都能正确列出完整阶段链、层级角色与关口声明；另一条在已挂载论文 pack 的同时执行层级开发团运行，证明两个 pack 可以互不干扰地共存。测试用的层级 pack 也与流水线 fixture pack 在同一组合中挂载。

**跨进程恢复**被明确否决。运行状态以内存为权威；`run-state.json` 是镜像，不是恢复点。该决定记录在专门的 Agent Note（[expert-team-no-cross-process-resume](../feature/2026-09-15-expert-team-no-cross-process-resume.zh.md)）中，理由是当前没有消费者需要它，内存 + 文件镜像 + project-memory 持久化已经足够，而恢复语义需要新增且复杂的存储接缝。

**运行历史可观测性**已实现为内存中的运行索引，并在每个持久化点镜像到 `<artifactsDir>/run-index.json`。索引为每次运行保存轻量元数据（runId、teamId、mode、status、createdAt、completedAt），并通过 `TeamOrchestrator.listRuns()` 暴露。这让部署可以在不引入数据库或外部存储的情况下查询运行历史。索引启动时不会加载（运行不会恢复）；它在进程生命周期内累积，并在每次更新时覆盖写入。

**token/KV 影响测量**延期。测量需要带 token 计数的真实模型后端；现有 mock adapter 测试基础设施无法给出有意义的结果。等有可录制场景（snapshot 层）后再处理。

**面向用户的指南投影**延期。网站投影遵循仓库现有的 VitePress 流程；expert-team 内容应进入网站内容树，不属于当前包的发布准备范围。

## Alternatives considered

**实现跨进程恢复。** 否决：没有部署请求该能力；其复杂度（存储接缝、会话恢复、关口重放、一致性校验）与当前需求不匹配。

**把 run-state.json 作为恢复点。** 否决：它是镜像而非检查点；升级为恢复点需要记录更多运行时状态，与“内存是权威”这一设计相矛盾。

**用合成基准测量 token/KV 影响。** 否决：合成基准不能反映真实模型行为；测量需要带真实 provider key 的录制场景。

## Consequences

收益：通过真实 Loader 证明了多 pack 组合——论文 pack 与开发 pack 可以一起挂载并独立执行；运行历史可通过 `listRuns()` 查询，索引文件持久化在产物根目录；跨进程恢复的决定已记录并写入文档。代价：token/KV 测量与面向用户的指南投影延期到有录制场景之后；进程重启会丢失进行中的运行（已记录为 README 已知限制）。

## Testing

- 多 pack 组合：两条新的 loader 组合测试证明论文 pack 与开发 pack 可以一起挂载，并且层级开发团运行能与论文 pack 共存执行。
- 运行索引：现有 orchestrate 测试隐式验证索引已写入（artifactsDir 现在会在运行目录旁包含 `run-index.json`）。
- 跨进程恢复：决定已记录在 Agent Note 中，运行时未实现恢复支持。
