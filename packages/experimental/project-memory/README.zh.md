---
description: "基于用户选定 Obsidian Vault 的有界追加式项目记忆：作用域化的搜索/读取/追加工具、独占创建的笔记与会话日志回执、路径包含约束、秘密内容筛查与如实失败报告。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-project-memory

[English](README.md) | 中文

## 概述

`dsh-experimental-project-memory` 实现了[详细设计第 3 部分](../../../docs/detailDesign-part3.zh.md)中的有界 Obsidian 记忆：Vault 只保存经过选择的事实、偏好、经验与未解决问题，不保存执行历史，也不授予任何权威。本包是私有实验库，核心是 `ProjectMemoryService`、三个有界工具（`memory_search`、`memory_read`、`memory_append`）以及由宿主基于 DSH 会话日志实现的回执接缝。它不是通用 Obsidian 同步：服务只管理追加式的 `<vault>/devframe-memory/` 专用子树，追加是独占创建且幂等的，记忆内容是不可信上下文，不能授予工具、权限或指令权威。

## 目录

- [使用本包](#use-this-package)
- [理解实现](#understand-the-implementation)
- [模型体验](#model-experience)
- [已知限制与未做工作](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

当宿主需要对用户选定的 Vault 根目录做作用域化召回与如实追加时使用本包：调用会话的工作区身份、同意开关（`writeEnabled`、`userScopeEnabled`）与回执存储由宿主提供；文件系统行为由服务负责。

### 先解析 spec，再调用工具

默认值在包边界显式解析；服务不做任何隐藏兜底。

```ts
import { createMemoryReceiptStore, ProjectMemoryService, resolveMemorySpec } from '@deepseek-ai/dsh-experimental-project-memory'

const spec = resolveMemorySpec({
  vaultRoot: 'D:/Obsidian/MyVault', // user-selected, must already exist
  writeEnabled: true,              // the user enabled appends
  userScopeEnabled: false,         // user memory not allowed for this caller
  workspaceId: workspaceId,        // host-derived native workspace identity
})
const memory = new ProjectMemoryService(spec, receiptStoreOverSessionLog)
const recall = await memory.search({ scope: 'project', query: 'deploy script' })
```

### 实现回执接缝

`MemoryReceiptStore` 只约定 `read` 与 `write`。宿主必须在追加返回 `created` 之前把每条回执（相对路径加完整文件摘要）持久化到会话日志，重启后据此回答 `already_exists`、`memory_changed` 或 `memory_missing`，而不是重建文件。测试与已经从恢复的回执列表组装接缝的工具使用 `createMemoryReceiptStore(entries)`。

### 预期显式失败

设计中的每种失败都以稳定错误码呈现在 `ProjectMemoryError` 上：未配置或缺失的 Vault 报 `MEMORY_UNAVAILABLE`，关闭写入报 `MEMORY_APPEND_DISABLED`，超大或含秘密的正文被拒绝并给出 `MEMORY_NOTE_TOO_LARGE` 或 `MEMORY_CONTENT_REJECTED`（原因只点名规则，绝不回显疑似秘密），不安全路径报 `MEMORY_PATH_REJECTED`。冲突或被外部改动的笔记是结果状态（`memory_conflict`、`memory_changed`、`memory_missing`、`incomplete_note`），绝不静默覆盖。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现内部细节——点击展开</summary>

本节解释功能背后的设计决策及其对应的代码；可观测行为已完整覆盖在[使用本包](#use-this-package)。

### 设计决策

- **推导身份，提交回执。** 笔记 ID 是 `sha256(namespace, sourceEventRef)`，同一追加的每次重试都落在同一文件；回执（相对路径加完整文件摘要）在 `created` 之前提交，是读取唯一信任的确认——编辑笔记自身元数据不能替代回执。
- **只创建的追加。** 文件以独占创建（`wx`）建立、刷盘，绝不截断或替换。冲突的候选报 `memory_conflict`；部分（被中断的）写入报 `incomplete_note` 并保留等待明确修复；权限错误与冲突不重试，瞬时失败遵循有界重试策略。
- **包含约束而非信任。** 工作区 ID 按单一安全路径段校验，笔记 ID 是 64 位十六进制摘要（穿越探测在形状检查即失败），逐组件检查非预期 symlink／reparse 点，解析后的目标必须停留在 Vault 根 realpath 之内。
- **有界、确定性的召回。** 各限制按 UTF-8 字节计数（默认每笔记 8 KiB、单次返回 16 KiB、10 条结果、200 个候选、2 KiB 查询），候选扫描是排序的确定性遍历，达到上限时如实报告 `coverageComplete: false` 而不是宣称不存在，摘录只在完整码点上截断。
- **信任标签只携带，不晋升。** 断言状态随每条命中与读取返回；`confirmed` 的用户偏好要求宿主提供 `humanConfirmation` 引用；替代只通过追加完成、限定同一命名空间，并保留被替代文件。

### 源码地图

| 文件 | 职责 |
|---|---|
| [`src/types.ts`](src/types.ts) | 命名空间、笔记元数据、工具请求/结果形态、限制、重试策略与回执接缝 |
| [`src/ids.ts`](src/ids.ts) | `NoteId` 品牌、来源引用校验与稳定 ID 推导 |
| [`src/notes.ts`](src/notes.ts) | 笔记序列化、严格解析、摘要与字节边界工具 |
| [`src/vault.ts`](src/vault.ts) | 命名空间布局、工作区段校验、symlink/reparse 拒绝与路径包含 |
| [`src/screen.ts`](src/screen.ts) | 秘密模式、环境转储与不安全内容筛查 |
| [`src/config.ts`](src/config.ts) | 按文档默认值做显式 spec 解析 |
| [`src/receipt.ts`](src/receipt.ts) | 供测试与重水化使用的内存回执存储 |
| [`src/memory.ts`](src/memory.ts) | 服务本体：真实文件系统上的搜索、读取与追加 |
| [`src/errors.ts`](src/errors.ts) | `ProjectMemoryError` 与稳定错误码枚举 |
| [`src/index.ts`](src/index.ts) | 包入口，统一再导出词汇 |

### Invariant

未发布运行时 invariant companion：服务不持有可跨进程观察的关系需要断言——其保证（独占创建、先回执后 `created`、路径包含）都在操作时由文件系统与回执接缝强制，并由绑定 `docs/testAndAcceptance.md` 中 `AT3-01…09` 的行为测试验证。

</details>

-----

<a id="model-experience"></a>
## 模型体验

### 契约词汇

#### 模型看到什么

目前什么都没有。本包以库形式提供三个工具；把它们接入 `ctx.tools`、在任务开始注入带标签的召回、并把注入记录到会话事件，属于宿主集成（[详细设计第 3 部分，失败处理与集成](../../../docs/detailDesign-part3.zh.md#failure)）。

#### Token 影响

每个请求零直接 token。

#### KV Cache 影响

与实时请求无关：本包不触碰请求前缀，不会使提供方缓存复用失效。

<a id="known-limitations-and-deferred-work"></a>
## 已知限制与未做工作

这些限制界定了记忆服务何时不适配或需要特别运维关注。它们是当前包约束，不是任务清单。

- **筛查是减少而非保证。** 规则列表固定；规则识别不了的内容仍会进入 Vault，形似模式的正常行文也会被拒绝——两者都是设计使然。
- **回执持久化是宿主职责。** 内存存储在释放后丢失回执；没有回执时确认退回追加重试的内容比对，且已确认文件消失后绝不重建。
- **召回是有界文本匹配。** 按设计不设后台索引、embedding 或向量存储，直到实测检索问题证明需要。
- **未知文件系统错误按瞬时处理。** 它们消耗配置上限内的重试次数，然后以 `MEMORY_WRITE_FAILED` 或 `MEMORY_UNAVAILABLE` 显式失败。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

无。

</details>
