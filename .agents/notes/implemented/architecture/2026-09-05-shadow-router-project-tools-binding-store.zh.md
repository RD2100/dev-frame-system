# Agent Note：Shadow 项目工具经由绑定存储授权目标，而非邮箱

Status: implemented

[English](2026-09-05-shadow-router-project-tools-binding-store.md) | 中文

## Problem

Shadow 层需要一个由宿主指定的会话，它既能打开独立的项目根，又能把工作路由进去。两个既有模式争夺这条缝：agent-team 邮箱按团队成员身份校验目标，而临时性的工具面允许模型直接选择目标会话 id。两者在这里都不对——团队成员身份说明不了哪个目录归哪个写入者所有，而模型自选的会话 id 会让一个项目的调用方伸进另一个项目的控制器。路由器需要一个目标权威：能扛住崩溃、只圈定一个代理、且无法从工具参数伪造。

## Decision

`packages/experimental/shadow-router` 把这条缝拆开：四个项目工具（`project_open`、`project_send`、`project_status`、`project_stop`）只安装进宿主用 `markShadow` 标记的代理作用域，而每次分发都通过以工作区 id 为键的持久绑定存储解析目标——绝不经过调用方提供的会话 id。绑定存储与工具同步演化：`project_open` 在控制器根会话存在之前先持久化 provisioning 状态机（`reserving → provisioning → ready`，带回滚的 `failed` 与停摆的 `needs_attention`）；`project_send` 只对绑定的当前 revision 及其宿主授权的 Goal/验收关联接受输入，把 `queued` 意图与 `received` 接受作为两个独立的持久行来保存；`project_stop` 只取消该绑定的 queued 行并停为 `stopping`，直到宿主确认。工具缝拒绝未知的参数键（共享参数模式是隐式开放的，所以白名单自己负责这项检查）——这正是伪造的 `target_session_id` 会响亮失败而不是被悄悄忽略的原因。

## Alternatives considered

**复用 agent-team 邮箱做跨根投递。** 否决：邮箱按成员身份授权，回答的是"这个发送方能否进入团队"，而不是"这个工作区的控制器是不是正确目标"；绑定存储已经持有路由所需的规范路径与 revision 事实，再引入一个成员身份权威只会与之漂移。

**让模型在每次调用时传入控制器会话 id。** 否决：模型无从得知控制器 id 的角色，一次泄露就把任意会话变成跨根写入者；目标必须从已授权绑定推导，open 的 schema 把这一点固定下来。

**接受之后再持久化投递。** 否决：那样一来，在模型可见的调度与控制器接受之间崩溃，就会在每次中断时恰好丢失一次意图；两次写入的顺序（先意图、后接受）才让重启收敛到一条可见的 received 行而不重复任务。

## Consequences

Shadow 的模型面恰是四个目标由宿主拥有的工具，且每条授权事实都在路由器自行重建的一张域表中扛过重启。代价：宿主组合必须自己标记 Shadow 并调用宿主专用缝（`setActiveGoal`、`completeDelivery`、`confirmProjectStopped`、`recoverDeliveries`）；投递在宿主转发之前对控制器不可见；同一存储根上的第二个存活路由会响亮失败，因为 JSON 后端拒绝第二个句柄——三者在此处都被接受，因为另一头是模型可以操纵的目标权威。
