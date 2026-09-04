---
description: Shadow 在独立项目会话之间的路由与持久化消息投递设计。
---

# 详细设计第 2 部分：Shadow 与多项目

[English](detailDesign-part2.md) | 中文

## 概述

本文是在[单项目操作](detailDesign-part1.zh.md#user-flow)、其前置停止／恢复检查和实际效用试用之后考虑的候选扩展。Shadow 在独立项目根会话之间路由用户意图，不拥有嵌套 Team、第二套任务板或不受限制的执行能力。跨根投递是新增实现工作，不是现有 Team 内邮箱。首轮验证不依赖本部分实现。

## 目录

- [需求与所有权](#requirements)
- [项目工具](#tools)
- [打开项目与路由](#routing)
- [投递与重试行为](#delivery)
- [状态、停止与展示](#status)

<a id="requirements"></a>

## 需求与所有权

使用[原生工作区注册表](../packages/workspace/workspace/src/index.ts)确定规范化项目身份，并参考[根会话控制器](../packages/api/session-controller/src/agent.ts)的创建／恢复行为。原生会话、Team 任务与事件日志继续各自管理自身状态。

| 编号 | 必要行为 | 验收位置 |
| --- | --- | --- |
| `R2.1` | 一个获授权工作区对应一个当前控制器，并防止跨项目错投。 | [AT2-01、AT2-02](testAndAcceptance.zh.md#part2) |
| `R2.2` | 对重复打开请求去重，并拒绝不安全的路径别名或根目录冲突。 | [AT2-03、AT2-04](testAndAcceptance.zh.md#part2) |
| `R2.3` | 持久化跨根投递，并区分工作已收到和工作已完成。 | [AT2-05、AT2-06](testAndAcceptance.zh.md#part2) |
| `R2.4` | 停止和检查一个项目时，不影响其他项目执行。 | [AT2-07、AT2-08](testAndAcceptance.zh.md#part2) |

唯一新增的项目索引是通过 DSH 原生领域持久化保存的关联：`workspaceId`、预留的 `controllerSessionId`、`profileKey`、`bindingRevision`、打开操作的 `requestId` 和创建状态。角色 profile 由宿主选择。这份关联不重复保存项目路径、原生任务行、会话全文或单独的完成状态。

控制器被有意替换时，关联版本号用于拒绝旧请求。首个单进程部署可以使用进程内互斥来串行处理操作，但持久化关联和操作 ID 必须能够跨重启保留。本方案不支持多个进程同时写入同一运行存储。

<a id="tools"></a>

## 项目工具

向 Shadow 暴露四个拟新增工具。项目开发者和审查者不获得这些工具。解析会话之前，先校验工具 JSON、实际调用者和工作区授权。

Shadow 面向模型的允许列表仅包含这些路由工具和明确启用的用户记忆访问。它不获得任意文件系统／shell 执行、原始会话控制工具、插件自我修改或无限制 MCP 访问。宿主创建项目时使用单独校验的用户授权，不从 Shadow 提示词继承无限制权力。

| 工具 | 输入 | 结果与错误行为 |
| --- | --- | --- |
| `project_open` | 已有且获授权的 `path`、稳定的 `requestId`。 | 返回 `workspaceId`、控制器身份、版本和就绪情况。拒绝缺失目录、未授权根目录或 profile／cwd 冲突，不悄悄创建目录。 |
| `project_send` | `workspaceId`、`bindingRevision`、`goalId`、`acceptanceHash`、稳定的 `requestId`、`mode`（`work` 或 `note`）和有界文本。 | 返回投递 ID 与回执状态；拒绝陈旧关联／工作身份、接收已关闭或队列已满的请求。回执不代表执行成功。 |
| `project_status` | 一个获授权的 `workspaceId`，或一页有数量限制的获授权项目。 | 根据原生会话／任务、投递状态和活动后台任务计算状态，并包含观察时间与阻断原因。 |
| `project_stop` | `workspaceId`、预期版本和稳定的 `requestId`。 | 只停止所选项目接收和执行工作；其所属工作停稳前返回 `stopping`。重复同一停止操作是安全的。 |

调用者不能提供任意目标会话 ID；宿主从已授权关联中解析它。相同 `requestId` 配合相同规范化输入时返回先前结果；配合不同输入时返回 `request_conflict`。UI／宿主在重试间保留请求 ID，不要求模型每次发明新 ID。

<a id="routing"></a>

## 打开项目与路由

按原生工作区规则及实际文件系统规范化已有根目录，包括 Windows 大小写和 junction 别名。拒绝物理范围重叠且准备同时写入的根目录；仅靠字符串前缀检查不够。独立 worktree 只有在工作目录互不重叠、且开发者无法执行共享 Git 修改操作时，才可以视为不同项目。

1. 校验请求路径与项目授权，解析或创建原生工作区身份。
2. 在每工作区的创建互斥范围内读取已有关联；如果有效就返回它。
3. 如果关联不存在，先预留一个控制器会话 ID，并在创建会话前持久化创建中的关联。
4. 使用项目获准的 cwd 和 preset 创建独立根会话，不把 Shadow 设为其 subagent 父会话。
5. 只有会话创建和必需角色设置已经持久化后，才保存就绪状态并向 Shadow 返回结果。

预留之后崩溃时，围绕同一个会话 ID 进行核对。如果身份、cwd 或策略不匹配，将项目保留为 `needs_attention`；不通过另建写入者来兜底。会话重启必须遵守原生目标的[明确恢复策略](detailDesign-part4.zh.md#recovery)。

<a id="delivery"></a>

## 投递与重试行为

跨根投递在原生会话持久化中使用小型发送意图和目标回执。遵循[原生 Team 邮箱](../packages/experimental/agent-team/src/mailbox.ts)的持久化顺序，但不能假装无关根会话是队友，直接调用检查成员身份的方法。只有现有辅助功能确实支持所需身份时，才复用它。

拟议消息字段为 `messageId`、`requestId`、源会话、工作区 ID、关联版本、目标会话、`goalId`、`acceptanceHash`、模式、有界内容／引用和创建时间。ID 与工作归属在首次持久化前固定，重试不改变。前一个 Goal 的消息不能被转给控制器的当前 Goal。

```text
Sender: persist intent + flush
  -> Target: validate identity/revision + deduplicate messageId
  -> Target: persist accepted input + flush
  -> Sender: persist received receipt + flush

received != started != completed
```

`work` 消息仅在其 Goal 与验收关联匹配已授权开放运行时安排跟进；`note` 是具有相同归属检查的安静输入。发送消息不创建或替换 Goal。启动或恢复使用与[第 1 部分](detailDesign-part1.zh.md#user-flow)相同的经校验人工授权路径，Shadow 不能自造授权。重试崩溃前的投递不授权旧工作重启。

目标去重覆盖持久化收件输入，不覆盖任意外部副作用。如果命令可能在崩溃前已经启动，但结果未知，将执行标为 `ambiguous`，并检查原生后台任务／进程证据。不能仅因发送端没有回执就重复不可逆工作。

投递重试次数有界，并复用同一个 ID；次数耗尽后保留可见的待投递／失败操作，由人工决定。新输入被接受之前就应用队列和消息大小限制。拟议默认值由[第 4 部分](detailDesign-part4.zh.md#limits)统一定义。

<a id="status"></a>

## 状态、停止与展示

将 `idle`、`running`、`waiting`、`stopping`、`stopped`、`completed` 和 `needs_attention` 作为计算得到的 UI 状态，不作为竞争性的持久化任务状态机。`completed` 必须依据第 1 部分的完成结果；队列为空或模型空闲都不够。陈旧观察结果要显示时间，且不能据此授权写入。

停止时只关闭所选项目的队列、停用其目标驱动器、取消其控制器与子会话，并等待所属进程停稳。已接受消息保留为取消或待人工处理，不悄悄丢弃，也不自动转给替代控制器。[第 4 部分](detailDesign-part4.zh.md#stopping)定义超时行为。

在既有[单项目流程](detailDesign-part1.zh.md#user-flow)上增加项目选择和四个 Shadow 工具，不另造批准或恢复流程。现有会话导航与工具卡片展示项目／控制器、当前 Goal／任务、投递状态、最近活动和阻断原因。只读状态刷新不唤醒 agent（智能体），也不包含其他项目的内容和秘密。

## 开发备注

本阶段不引入独立 HTTP 网关或分布式消息代理。只有实际需要多个进程或多台机器时，才重新考虑外部传输，并将这里的投递 ID、授权检查和不确定状态处理方式延续到后续设计。
