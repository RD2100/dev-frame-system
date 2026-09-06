# Agent Note：文件后备的 Goal 绑定存储

Status: implemented

[English](2026-09-06-goal-binding-file-store.md) | 中文

## 问题

[文件后备的必需检查存储](2026-09-06-required-checks-file-store.zh.md) 已让 checks 谓词跨重启安全，但组合持有的 `GoalBindingStore` 仍是进程内存：重启即丢全部 goal 绑定，宿主重启后无法对着既有绑定派发 `/goal-complete`，只能手工重绑。绑定存储是完成准入证据链上最后一个重启脆弱输入。

## 决策

`FileGoalBindingStore` 在 `Config` 提供的 JSON 账本路径上实现既有四方法 `GoalBindingStore` 接口，整本对照 required-checks 文件存储契约：严格版本化信封、每次读取整体重校验、完整性失败走既有 `GOAL_BINDING_PERSISTENCE` 错误族（零新码）、同目录 temp+rename 发布、重复保存幂等、拒修损坏账本。继承裁定原样延续——无 fsync、无多写者锁、无目录创建、无 prune、单写者 last-write-wins——重启基准即实例重建测试矩阵：写入、进程内重建 store 实例、读回等值。该存储作为可注入替代实现交付，接口零变更；由组合注入点选择实现，四方法面与全部消费点零语义变更。

## 落选替代

**为绑定另起一套 durability 契约。** 偏离 required-checks 先例会在同一包内制造两种账本方言；镜像契约让完整性词汇保持一套。

**现在就把 durable 存储设为组合默认。** 注入点接受实现；设为 profile 默认与 checks 存储一样属属主波的部署决策。

**修复或迁移旧账本形态。** Pre-release 立场拒绝兼容垫片；外来或损坏信封 fail-loud，不做静默升级。

## 后果

- 配置绑定账本路径的宿主跨重启保留 goal 绑定；准入的绑定输入不再绑定内存。
- 包内全部账本存储共享同一信封、校验与错误族，运维只需理解一次。
- 并发、fsync 与 prune 仍是已登记的继承裁定，而非被默认的性质。
