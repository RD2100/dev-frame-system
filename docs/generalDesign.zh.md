---
description: 基于 DSH 原生能力的多 agent 开发方案与交付范围。
---

# 基于 DSH 的 DevFrame：总体设计

[English](generalDesign.md) | 中文

## 概述

本文是拟议架构与行为基线，不是冻结的实施计划，也不代表 DevFrame 产品已经实现。近期范围是在 DSH 上验证可用的单项目流程，包括安全停止／恢复与用户操作负担；多项目协调和记忆仍是候选扩展。部署场景是单个可信用户的本地进程，不是多租户服务或恶意代码沙箱。这些文档不授权部署、外部写入或修改旧治理内核。

## 目录

- [范围与基线](#scope)
- [系统组成](#composition)
- [文档与交付划分](#delivery)
- [功能复用](#reuse)
- [开发流程](#workflow)
- [约束与待确认事项](#constraints)

<a id="scope"></a>

## 范围与基线

源码基线是新 `dsh-devframe` 工作目录中的 DSH `dsh-v0.1.2-alpha.4`，提交为 `4e84901e6471b79ec0338099867ebb4606d12bb5`。本地源码、[架构说明](architecture.zh.md)和 [Agent Teams 参考](subsystems/agent-team.zh.md)优先于所提供提示词中的假设。旧 `dev-frame-system` 工作目录仅作为功能示例的只读参考，不作为实现底座。

| 产品需求 | 包含的结果 | 本方案不包含 |
| --- | --- | --- |
| 有人监督的开发 | 控制器分派实现工作，获得真实测试结果，并请求独立审查。 | 自动生产部署、推送、合并或凭据修改。 |
| 多项目协作 | Shadow 选择项目，将工作路由到该项目自己的控制器会话。 | 嵌套 Team、任意递归委派或分布式调度。 |
| 上下文连续性 | 原生会话恢复，加上有界且可选的 Obsidian 记忆。 | 第二套完整会话记录库、自动知识认证或强制向量检索。 |
| 可控运行 | 明确权限、取消机制、有限重试和可观察的失败。 | 替代性的 DEV 治理内核或通用 agent（智能体）管理平台。 |

产品复用 DSH 的 Web／终端交互与原生模型提供方配置。首期不新建桌面应用、HTTP 网关、模型计费系统或绑定某个提供方的 agent loop（智能体循环）。

<a id="composition"></a>

## 系统组成

先使用一个功能插件和一个组合包／profile。路由、角色策略和记忆先作为该插件内部模块；只有确实需要独立生命周期时才拆包。[实验性 Team profile](../packages/experimental/agent-team-profile/cordis.patch.yml)仅作为组合参考，不代表官方发布产物已经包含 Teams。

```text
User
  |
Shadow session (independent root; routing only)
  +---- Project A controller (independent root / native Team Lead)
  |       +---- Worker A   (direct child)
  |       +---- Reviewer A (direct child)
  +---- Project B controller (independent root / native Team Lead)
          +---- Worker B   (direct child)
          +---- Reviewer B (direct child)

All sessions -> DSH session persistence
Project bindings -> DSH workspace/domain persistence
Selected knowledge -> optional Obsidian Markdown notes
```

图示描述候选扩展产品。首轮验证由用户直接操作一个项目控制器，不需要 Shadow 或记忆。跨根路由不是原生 Team 成员关系：每个项目拥有扁平 Team，Shadow 不编辑项目文件，也不领导包含其他 Team Lead 的 Team。

| 职责 | 复用内容 | DevFrame 新增内容 |
| --- | --- | --- |
| 执行与模型调用 | [DSH 插件与 agent 生命周期](architecture.zh.md)。 | 角色组合与请求限制，不分叉核心循环。 |
| 项目团队 | 原生成员表、持久化邮箱、任务板和 Team UI。 | 控制器／开发者／审查者策略，以及受校验的项目完成入口。 |
| 多项目 | 工作区身份、根会话与原生存储。 | 一份工作区到控制器的关联，以及持久化跨根投递。 |
| 知识 | 原生运行日志继续保存执行历史。 | 用小型 Markdown 检索、读取和追加操作保存可复用知识。 |

一个插件包只是打包选择，不代表实现工作量小。估算阶段工作量前，应区分以下工作；权限接入由[第 1 部分](detailDesign-part1.zh.md#integration)负责。

| 工作 | 复用分类 |
| --- | --- |
| 原生会话、Team 成员表／任务板、presets 与可用 UI | 配置／组合复用，并验证组合后的行为。 |
| 角色 guard 与人工项目命令 | 包装 `tools.guard()`、作用域命令注册表与 Goal 服务；仍需新增角色／接收逻辑。 |
| Team 创建时传递子角色选项 | 确需修改实验性 Team 源码，不计划分叉核心循环。 |
| 源码指纹、检查执行／证据、写入所有权、预算与恢复 | 使用原生存储、工具与生命周期原语实现的新功能，不是只靠配置就能解决。 |
| 跨根投递与受管理 Vault 笔记 | 独立候选功能工作，在首轮验证作出决定后再考虑。 |

<a id="delivery"></a>

## 文档与交付划分

文档编号标识主题，不代表强制实施顺序。工作先经过单项目闭环、单项目安全停止／重启和[实际效用试用](testAndAcceptance.zh.md#usefulness)，之后才由用户决定是否继续多项目与可选记忆。后续章节可以调整或删除。

| 设计领域 | 归属文件 | 需求编号 | 应用时机 |
| --- | --- | --- | --- |
| 单项目团队与操作 | [第 1 部分](detailDesign-part1.zh.md) | `R1.1`–`R1.7` | 首轮验证：真实改动、明确归属的证据、连续任务和可用人工入口。 |
| 安全停止与恢复 | [第 4 部分](detailDesign-part4.zh.md) | 选定 `R4.*` 路径 | 首轮验证处理普通用户工作之前；提前验证的确切子集见验收表。 |
| Shadow 与多项目 | [第 2 部分](detailDesign-part2.zh.md) | `R2.1`–`R2.4` | 单项目价值判断之后的候选扩展。 |
| Obsidian 记忆 | [第 3 部分](detailDesign-part3.zh.md) | `R3.1`–`R3.4` | 可选扩展；缺少记忆不阻挡开发验收。 |
| 验证与产品价值 | [测试与验收](testAndAcceptance.zh.md) | `AT1-*`–`AT4-*` | 区分集成证明、安全运行，以及用户是否真的减少干预。 |

[单项目使用流程](detailDesign-part1.zh.md#user-flow)负责登记、配置批准、启动、停止、恢复与结果查看。不增加单独 UI 设计文档或新的计划数据库。

<a id="reuse"></a>

## 功能复用

先确认旧项目中的示例是否真正实现，再把它作为行为和测试参考。按 DSH 约定移植最小的有效功能，不整体导入旧控制器、审批层级或持久化状态机。

| 旧参考，相对于旧工作目录 | 有用部分 | 排除或暂缓内容 |
| --- | --- | --- |
| `packages/control-plane/control_plane/obsidian_memory.py` 及其项目计划测试 | 有界读取、项目命名空间、只创建写入和冲突处理。 | 治理依赖、发布流程和第二套运行存储。 |
| `packages/control-plane/control_plane/codegraph_fresh_context.py` | 返回有界上下文前检查索引身份与新鲜度。 | 把 CodeGraph 设为基础开发任务的必需服务。 |
| `packages/ai-workflow-hub/src/ai_workflow_hub/context_layer/adapters/paper_pdf_fulltext_segments.py` | 在任务需要论文时复用带页码的 PDF 提取与内容指纹。 | 在开发流程可用之前搭建研究平台。 |

这些旧工作目录路径只用于查找参考，不是新仓库的依赖或必备文件。仅面向 fixture（测试前置数据）的适配器不能作为生产集成已经可用的证据。浏览器／云端协调、常驻辩论团队和独立仲裁者不属于首期交付。

<a id="workflow"></a>

## 开发流程

采用小型软件开发闭环：定义用户可观察的结果，选择一个阶段，实现功能，验证真实路径，审查同一份源码快照，然后在需要时取得人工验收。对可能虚报成功或丢失数据的行为，先写验收用例，再实现。

- 目标与非目标放在本文；工具字段与失败处理放在对应详细设计。
- 每项必要行为使用一个 `R*` 编号，并关联至少一个 `AT*` 用例；不另建需求数据库。
- 实现改变设计决策时，同步修改相关设计和验收用例；不增加平行状态报告。
- 执行证据保存在源码工作目录之外的现有运行／产物位置；交付报告只保留路径和简短结论。
- 有实质影响的取舍记录在[方案说明](../.agents/notes/proposed/feature/2026-09-02-devframe-dsh-native-development.zh.md)中；不为每个日常选择单独建文档。

代码工作结束、项目验收和发布是三种不同决定。开发者和审查者都不暂存、提交、推送、部署、修改全局配置或自行增加权限。后续如需发布流程，必须获得用户的明确授权。

<a id="constraints"></a>

## 约束与待确认事项

首期选择是 DSH 原生工作流，同时明确需要实现角色限制、任务／证据归属和安全生命周期处理。模型负责规划与审查，代码检查身份、权限、限制和完成前提。LLM（大语言模型）的陈述不是测试结果或授权，参与角色更多也不能证明更有用。

[Windows ACL 提供方](../packages/sandbox/sandbox-windows-acl/README.zh.md)提供的是写入限制，不是完整的读取／网络隔离。进程内可信插件也共享进程。首个版本必须如实说明这些限制；恶意仓库、强跨项目秘密隔离或多个互不信任的用户，必须在引入经过单独验证的执行环境后才能接入。

在真实模型演示之前，用户需要选择模型／提供方、凭据、可丢弃的测试项目和开销上限。在记忆写入之前，用户需要选择允许的 Vault 根目录并启用追加。在日常使用之前，可靠性验收用例必须在实际 Windows 执行路径上通过。粘贴的提示词不能代替这些选择。

## 开发备注

本方案有意不选择向量数据库、分布式队列、外部网关或更多模型角色。只有在记录了实际限制及失败的验收示例，并评估了更小的替代方案之后，才重新考虑引入其中一项。
