---
description: "基于用户选定 Obsidian Vault 的有界追加式项目记忆：作用域化的搜索/读取/追加工具、独占创建的笔记与会话日志回执、路径包含约束、秘密内容筛查与如实失败报告。"
kind: "package-bundle"
---

# @deepseek-ai/dsh-experimental-project-memory

[English](README.md) | 中文

## 概述

`dsh-experimental-project-memory` 是一个私有实验性 profile 层，实现[详细设计第 3 部分](../../../docs/detailDesign-part3.zh.md)中的有界 Obsidian 记忆：Vault 只保存经过选择的事实、偏好、经验与未解决问题，不保存执行历史，也不授予任何权威。它的 patch 插入一行 `project-memory`，提供 `ctx.projectMemory` 并在 `ctx.tools` 上注册三个有界工具（`memory_search`、`memory_read`、`memory_append`）；回执接缝依托会话日志，冷重启从重放的日志中恢复。按 shipped 默认值挂载时记忆处于未配置且只读状态，工具报告 `MEMORY_UNAVAILABLE`，直到部署配置 Vault 根。记忆内容是不可信上下文，不能授予工具、权限或指令权威；它不是通用 Obsidian 同步：服务只管理追加式的 `<vault>/devframe-memory/` 专用子树。

## 目录

- [使用本包](#use-this-package)
- [理解实现](#understand-the-implementation)
- [模型体验](#model-experience)
- [已知限制与延期工作](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

### 安装到 profile

从本仓库检出中，把该层加到一个已初始化的 profile：

```sh
pnpm dsh plugin --profile headless add ./packages/experimental/project-memory
```

该命令以 `@deepseek-ai/dsh-base` 开头初始化一个自定义 profile，并把包从检出中以 link 方式接入；清单中的 `dsh.bundle.patch` 声明使它加入有序层栈，而不是停留在普通依赖上。用 `dsh plugin --profile <name> remove @deepseek-ai/dsh-experimental-project-memory` 移除它时，依赖与该层一并移除。

### 配置 Vault

Shipped patch 默认以 `workspaceId: default`、关闭写入、无 Vault 根挂载该行，因此在任何地方加载都是安全的，且每次工具调用都报告 `MEMORY_UNAVAILABLE`，直到部署用 `vaultRoot` 覆盖该行的配置。用户选定的 Vault 根必须已存在——服务绝不创建它——并且在没有显式 `vaultRoot` 时启用 `writeEnabled` 会让 profile 在加载时失败。patch 条目替换目标行的整个配置，因此要保留的每个设置都必须重述；覆盖语义由[基础 bundle README](../../bundle/base/README.zh.md) 拥有。

### 你会得到什么

该层添加 `project-memory` 插件行：一个覆盖已配置 Vault 子树的 `ctx.projectMemory` 服务，外加三个模型工具。

- `memory_search` —— 对单个作用域笔记正文做确定性、按字节计界的文本匹配；命中携带笔记 ID、摘录、信任标签与新鲜度，`coverageComplete: false` 表示扫描达到上限，绝不表示知识不存在。
- `memory_read` —— 按 ID 读取一条完整笔记及其信任标签与来源；`memory_changed` 或 `incomplete_note` 表示存储文件与其已提交回执不一致，应视内容为未验证。
- `memory_append` —— 独占创建、幂等地追加一条有界笔记；回执在 `created` 返回之前送达调用会话的日志，被拒绝的正文只点名筛查规则，绝不回显疑似秘密。

设计中的每种失败都以稳定错误码呈现在 `ProjectMemoryError` 上（`MEMORY_UNAVAILABLE`、`MEMORY_APPEND_DISABLED`、`MEMORY_NOTE_TOO_LARGE`、`MEMORY_CONTENT_REJECTED`、`MEMORY_PATH_REJECTED`）；冲突或被外部改动的笔记是结果状态，绝不静默覆盖。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现细节——点击展开</summary>

本节解释特性背后的设计决策并指向实现它们的代码；可观察行为已在[使用本包](#use-this-package)中完整覆盖。

### Patch 文档

本包的运行时内容是 [`cordis.patch.yml`](cordis.patch.yml)：一个 `insert` 列表，按 shipped 默认值在 profile 根上挂载 `project-memory` 行。后续 bundle 层与用户的 profile patch 按 id 覆盖该行，每行以最后一次写入为准。在 profile 之外直接组装服务的源码检出宿主改为导入库形态：`resolveMemorySpec` 在包边界解析经校验的 spec，`ProjectMemoryService` 执行文件系统行为，宿主基于自己的会话日志提供 `MemoryReceiptStore`。

### 设计决策

- **推导身份，提交回执。** 笔记 ID 是 `sha256(namespace, sourceEventRef)`，同一追加的每次重试都落在同一文件；回执（相对路径加完整文件摘要）在 `created` 之前提交，是读取唯一信任的确认——编辑笔记自身元数据不能替代回执。
- **只创建的追加。** 文件以独占创建（`wx`）建立、刷盘，绝不截断或替换。冲突的候选报 `memory_conflict`；部分（被中断的）写入报 `incomplete_note` 并保留等待明确修复；权限错误与冲突不重试，瞬时失败遵循有界重试策略。
- **包含约束而非信任。** 工作区 ID 按单一安全路径段校验，笔记 ID 是 64 位十六进制摘要（穿越探测在形状检查即失败），逐组件检查非预期 symlink／reparse 点，解析后的目标必须停留在 Vault 根 realpath 之内。
- **有界、确定性的召回。** 各限制按 UTF-8 字节计数（默认每笔记 8 KiB、单次返回 16 KiB、10 条结果、200 个候选、2 KiB 查询），候选扫描是排序的确定性遍历，达到上限时如实报告 `coverageComplete: false` 而不是宣称不存在，摘录只在完整码点上截断。
- **信任标签只携带，不晋升。** 断言状态随每条命中与读取返回；`confirmed` 的用户偏好要求宿主提供 `humanConfirmation` 引用；替代只通过追加完成、限定同一命名空间，并保留被替代文件。

### 源码地图

| 文件 | 职责 |
|---|---|
| [`cordis.patch.yml`](cordis.patch.yml) | bundle 本体：携带 shipped 默认值的 `project-memory` 行 |
| [`src/types.ts`](src/types.ts) | 命名空间、笔记元数据、工具请求/结果形态、限制、重试策略与回执接缝 |
| [`src/ids.ts`](src/ids.ts) | `NoteId` 品牌、来源引用校验与稳定 ID 推导 |
| [`src/notes.ts`](src/notes.ts) | 笔记序列化、严格解析、摘要与字节边界工具 |
| [`src/vault.ts`](src/vault.ts) | 命名空间布局、工作区段校验、symlink/reparse 拒绝与路径包含 |
| [`src/screen.ts`](src/screen.ts) | 秘密模式、环境转储与不安全内容筛查 |
| [`src/config.ts`](src/config.ts) | 按文档默认值做显式 spec 解析 |
| [`src/receipt.ts`](src/receipt.ts) | 供测试与重水化使用的内存回执存储 |
| [`src/memory.ts`](src/memory.ts) | 服务本体：真实文件系统上的搜索、读取与追加 |
| [`src/errors.ts`](src/errors.ts) | `ProjectMemoryError` 与稳定错误码枚举 |
| [`src/index.ts`](src/index.ts) | 统一再导出词汇与插件接线的包入口 |

### 不变式

未发布运行时 invariant 伴随物：服务不持有可跨进程观察的关系需要断言——其保证（独占创建、先回执后 `created`、路径包含）都在操作时由文件系统与回执接缝强制，并由绑定 `docs/testAndAcceptance.md` 中 `AT3-01…09` 的行为测试验证。

</details>

-----

<a id="model-experience"></a>
## 模型体验

### 有界记忆工具

#### 模型看到什么

该层挂载后，工具作用域恰好多出三个工具：`memory_search`、`memory_read` 与 `memory_append`。它们的描述携带策略：笔记是带标签的数据，绝不是指令；追加记录的是观察，`confirmed` 的用户偏好只能经宿主的人工确认流程触达。按 shipped 默认值，每次调用都以 `MEMORY_UNAVAILABLE` 失败，绝不触碰任何路径。

#### Token 影响

该层缺席时为零。挂载后，三个工具的模式在可见作用域的每次请求中占用 token，每次调用追加一条受召回上限约束的 JSON 结果。

#### KV Cache 影响

行配置与工具模式不变时前缀稳定：模式只声明一次，调用结果追加在可复用请求前缀之后。挂载或移除该层会改变工具清单，破坏受影响代理下一次请求的提供方缓存复用。

## 已知限制与延期工作

<a id="known-limitations-and-deferred-work"></a>

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
