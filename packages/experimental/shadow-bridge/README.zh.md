---
description: "宿主侧 function plugin：把 shadow router 中可转发的 received work 投递转为绑定 controller 会话的模型可见 follow-up，跨重启对每条投递恰好转发一次。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-shadow-bridge

[English](README.md) | 中文

## 概述

`dsh-experimental-shadow-bridge` 闭合插件化 Shadow 层级的投递环路。它轮询 `ctx.shadowRouter` 的公开读面，把每一条仍与其绑定的授权 open run 匹配的 `received` `work` 投递，转为绑定 controller 会话 live agent 上的一条 durable follow-up，让送达的输入最终到达模型，并以 `user/message` 会话事件进入 controller 的会话日志。每条已转发的 messageId 都记录在本包自己的 `shadow_bridge` 存储域中并在启动时恢复，因此重启不会重复转发。转发从不确定投递的完成：`completed` 始终是 controller 侧的事实，router 的行仍是"发送、接收、完成"的持久记录。本包不注册任何工具、提示词分段或会话事件，TypeScript 与 Python SDK 投影不受影响。

## 目录

- [使用本包](#use-this-package)
- [理解实现](#understand-the-implementation)
- [模型体验](#model-experience)
- [已知限制与延期工作](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

在已挂载 shadow router、存储栈与 agent registry 的组合中挂载本插件；它硬注入 `ctx.agents` 与 `ctx.storageDomain`，缺少任一项时加载失败。router 在每次轮询时通过 `ctx.get('shadowRouter')` 读取，因此两种挂载顺序都可行：router 较晚挂载的组合在就绪前轮询不到任何内容。

```yaml
- name: '@deepseek-ai/dsh-experimental-shadow-router'
  config:
    authorizedRoots: [dshHomePath('projects')]
    shadowSessionId: session-shadow
- name: '@deepseek-ai/dsh-experimental-shadow-bridge'
  config:
    intervalMs: 2000
    followupMaxChars: 8000
```

### 配置

| 字段 | 默认值 | 含义 |
|---|---|---|
| `intervalMs` | 必填 | 正安全整数：相邻两次投递轮询之间的毫秒数。 |
| `followupMaxChars` | 必填 | 正安全整数：单条转发文本（含头部）的字符上限。 |

两个字段均为必填、无默认值：缺失任一项的组合行加载失败。

### 到达 controller 的内容

一条可转发的投递变成 controller live agent 上的一条 follow-up：先是一个确定性的头部（标识该 Shadow 投递的 messageId 与 workspace），随后是逐字的投递原文；当总长超过 `followupMaxChars` 时从尾部截断。follow-up 进入 controller 的 inbox 并成为 `user/message` 会话事件，模型在下一个 turn 看到它，日志记录它。controller 没有 live agent 的投递留待之后的轮询——桥从不创建、恢复或处置 agent。仅当绑定的状态不是 `stopping` 或 `stopped`、绑定仍记录着授权 open run、且投递的 Goal 与验收关联等于该 run 时，投递才可转发；因此收到投递之后发生 Goal 切换，上一个 Goal 的消息也不会进入 controller 的当前 Goal。转发从不写 `completed`：已转发的行保持 `received`，直到 controller 侧结算它。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现内部——点击展开</summary>

本节解释特性背后的设计决策并指向实现它们的代码；可观察行为已在[使用本包](#use-this-package)中完整覆盖。

### 设计决策

- **router 的公开读面是唯一接缝。** 轮询只读 `listDeliveries()` 与 `findBinding()`——不注册事件、不写 router、不新增 router 侧契约。每次轮询重新解析 router，因此挂载顺序与重启都天然容忍。
- **详细设计的投递门禁在转发时再次执行。** router 在接收时已校验 Goal 归属；桥在每次转发前对照当前 run 复查，这正是把"属于上一个 Goal 的投递"挡在"open run 已前移的 controller"之外的原因。
- **先发送，后记录。** follow-up 先进入 controller 的 inbox，然后才写标记行。两步之间崩溃会让一条投递在重启后转发两次——带着相同头部的可见重复；相反的顺序则可能悄悄丢失输入。follow-up 或标记写入的每一次失败都按条包含，并在之后的轮询重试。
- **一张标记表，启动时重建。** `shadow_bridge` 域的 `forwarded` 表是桥唯一的持久状态；内存中的已转发集合是它的直写投影，在构造时恢复。

### 源码地图

| 文件 | 角色 |
|---|---|
| [`src/index.ts`](src/index.ts) | function-plugin 面：config、注入、域打开与轮询循环接线 |
| [`src/forwarder.ts`](src/forwarder.ts) | 投递门禁、live agent 解析、follow-up 发送与标记写入 |
| [`src/text.ts`](src/text.ts) | 确定性头部与受限的转发文本 |
| [`src/loop.ts`](src/loop.ts) | 自重排的轮询定时器：失败包含、退出时排空 |
| [`src/spec.ts`](src/spec.ts) | `shadow_bridge` 域 spec 与已转发记录 schema |

### 不变式

未发布运行时不变量伴生包：已转发集合是单张域表的 write-through 投影并在启动时由其重建，router 的投递索引是它自己的直写投影，因此不存在可能分叉的独立观察。

</details>

-----

<a id="model-experience"></a>
## 模型体验

### 转发到 controller 会话的投递

#### 模型看到什么

controller 会话为每条已转发投递收到一条身份化的 user-role 消息，来源为 `{ kind: 'plugin', plugin: 'shadow-bridge', form: 'relay' }`，内容是标注该 Shadow 投递 messageId 与 workspace 的方括号头部加逐字投递原文。这条消息成为一个普通 turn；除头部文字本身外，模型无法分辨传输方式。

#### Token 影响

每条已转发投递增加一个有界的 user turn——头部加原文，至多 `followupMaxChars` 字符——以及它的模型回复，二者在 controller 会话的余下生命周期中保留。没有转发任何内容的轮询不产生请求，也不产生 token。

#### KV Cache 影响

只追加：每条已转发投递延伸 controller 会话的请求前缀，而不使其之前的前缀失效，且头部对给定投递是确定性的。本包不添加任何工具 schema 与提示词分段，因此其自身从不重塑可复用前缀；provider 缓存的可用性与驱逐在本包契约之外。

## 已知限制与延期工作

<a id="known-limitations-and-deferred-work"></a>

这些限制定义了本桥何时适配不佳或需要特别的运维注意。它们是当前的包约束，不是任务清单。

- **仅限 live controller——不做冷恢复** —— 桥通过 live-agent registry 解析绑定的 controller 会话，从不创建、恢复或收养 agent；宿主从未使之 live 的 controller 永远收不到它的投递，投递保持 `received` 并在 router 中可见。
- **转发不确定投递的完成** —— `completed` 是 controller 侧的持久事实；本包从不调用 router 的完成接缝，已转发的投递保持 `received`，直到宿主或后续轮次通过 `completeDelivery` 结算。
- **follow-up 与标记之间的崩溃可能转发两次** —— 标记在 follow-up 进入 inbox 之后记录，因此被中断的进程会在下一次启动时把一条投递再转发一次；重复项携带相同的头部与 messageId。相比可能悄悄丢失输入的顺序，这里刻意选择了这一顺序。
- **`note` 投递不转发** —— 本轮只有 `work` 投递会调度 follow-up；note 保持 `received`。
- **投递延迟受轮询节奏限制** —— 输入至多晚 `intervalMs` 到达 controller，且一次轮询按 router 的稳定投递顺序串行转发。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者工作上下文——点击展开</summary>

下一轮的自然扩展：从 controller 侧的 goal 回执结算 `completed`、把 `note` 投递作为静默输入转发，以及一个在保留会话上拉起 controller agent 的宿主侧 provisioner——这三者本桥都刻意不拥有。

</details>
