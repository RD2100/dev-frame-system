# Agent Note：停止链在 /devframe-stop 后组装项目树停止

Status: implemented

[English](2026-09-08-command-goal-binding-stop-chain-composition.md) | 中文

## 问题

`/devframe-stop` 只记录停止词汇，从未真正取消任何东西：不杀拥有的作业、不终止已捕获的进程、不刷新会话、也不释放 writer。已交付的 `stopProject` primitive 拥有 drain 协议，但它是仅调用面——组合层必须决定谁来枚举项目树、谁拥有 writer 释放，以及崩溃窗口把日志留在 `stop_requested`、`quiescence_confirmed` 与释放之间时流程如何收敛。

## 决策

组合层把真实链接到 `/devframe-stop` 之后，由 `stopChain` 配置门控；默认 `false` 对既有部署保持逐字节相同的仅词表面。三个面由宿主注入到组合服务上，而不是 Schema 配置：项目树面返回根加上每个真实后代 agent（宿主已完成 owner 与 worktree 身份验证）；进程面返回每个已捕获的后代进程；释放钩子执行 writer 释放且必须容忍重复调用。

链对每个缺失的面都 fail-closed。树 inventory 缺失或为空、作业注册表缺失、释放钩子未接线，都会拒绝释放——空列表绝不冒充已验证的完整树，缺失绝不等于安静。停止链只在宿主验证过的成员上运行，因此无关项目的作业与进程永远不会被排空。

确认静止的记录是持久的释放前前置。stopped 终态记录、存储条目与检查点只在该次释放真实成功之后落盘，每次落盘都通过 race 受停止宽限期约束，永不 settle 的持久化面会返回而不是挂起。释放失败折叠为 `needs_attention`，绝不落 `stopped`。

被中断的流程在重复停止时收敛。日志停在 `stop_requested`（链在 drain 中等待时崩溃——这是用户明确要求的停止的正常失败窗口）时，`resumeStopRequestedStop` 基于宿主当前 inventory 与活跃注册表身份重新进入 drain；日志停在 `quiescence_confirmed` 时，`finishConfirmedStop` 重新进入释放。缺失的活跃身份以 `needs_attention` 具名呈现且 writer 保持持有——绝不静默绕过，也绝不重启被中断的 goal 工作。

## 已考虑的替代方案

**在组合层内枚举后代。** 组合层将猜测项目成员关系，并复制宿主的 owner 与 worktree 验证。宿主本就拥有活跃注册表与已捕获句柄，经验证的 inventory 面让成员关系保持权威，并让组合层对无法验证的内容 fail-closed。

**在释放之前落 stopped 终态。** 释放回调可能抛错，进程也可能在预落 `stopped` 之后、释放之前死亡，这会误述一个"已停止但 writer 仍持有"的 goal 并拒绝重复停止。因此终态只在释放真实成功之后落盘，持久的释放前状态就是既有的 `quiescence_confirmed` 记录。

**围绕释放与记账建事务框架。** 释放无法回滚，通用事务只增加范围而不消除窗口；有界落盘加上重入路径，让每个失败状态都有具名、可重试的收敛。

## 后果

聚焦的真实面用例覆盖：有序子进程 drain、后代树（子拥有的作业、进程与会话刷新，加上不受扰的无关项目）、宽限期超时的 needs_attention 重跑、跨冷重启的预算、重复停止拒绝、进行中互斥、未接线释放的 fail-safe、缺失与空树、缺失作业注册表、释放失败收敛、冷确认态收敛、永不 settle 保存的有界返回、冷 `stop_requested` 续停、以及陈旧身份拒绝。

两个边界是刻意保留的。`finishConfirmedStop` 的终态记账调用点没有像新链那样逐一包失败处理——行为保持有界且不阻塞，但不对称在此记录。停止链只 drain 并收敛；它不恢复也不重启被中断的 goal 工作，writer 在某次运行确认树静止前保持持有。

## 相关

[准入截止调用原生项目停止](2026-09-08-admission-deadline-native-stop.zh.md)拥有 primitive 的截止面，[宿主命令面 note](2026-09-06-command-goal-binding-host-command-surface.zh.md)拥有命令组合与归属决策；两者都不覆盖本次组合接线。
