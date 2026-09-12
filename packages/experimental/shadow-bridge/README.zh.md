---
description: "宿主侧 function plugin：把 shadow router 中可转发的 received work 投递转为绑定 controller 会话的模型可见 follow-up，跨重启对每条投递恰好转发一次。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-shadow-bridge

[English](README.md) | 中文

## 概述

`dsh-experimental-shadow-bridge` 闭合插件化 Shadow 层级的投递环路。它订阅 shadow router 只观察的 `shadow/delivery-received` 事件，把每一条仍与其绑定的授权 open run 匹配的 `received` `work` 投递，转为绑定 controller 会话 live agent 上的一条 durable follow-up，让送达的输入最终到达模型，并以 `user/message` 会话事件进入 controller 的会话日志。挂载时与 loader 结束后各一次全量对账轮询，外加低频安全网定时器，覆盖在监听器窗口之外进入 `received` 的投递——挂载之前、上一个进程、或组合尚未结算完成时。每条已转发的 messageId 都记录在本包自己的 `shadow_bridge` 存储域中并在启动时恢复，因此重启不会重复转发。转发从不确定投递的完成：`completed` 始终是 controller 侧的事实，router 的行仍是"发送、接收、完成"的持久记录。本包不注册任何工具、提示词分段或会话事件，TypeScript 与 Python SDK 投影不受影响。

## 目录

- [使用本包](#use-this-package)
- [理解实现](#understand-the-implementation)
- [模型体验](#model-experience)
- [已知限制与延期工作](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

在已挂载 shadow router、存储栈与 agent registry 的组合中挂载本插件；它硬注入 `ctx.agents` 与 `ctx.storageDomain`，缺少任一项时加载失败。桥在挂载时订阅 `shadow/delivery-received`，每个转发单元都通过 `ctx.get('shadowRouter')` 重新解析 router，因此两种挂载顺序都可行：router 较晚挂载的组合在对账轮询与安全网看到它之前转不到任何内容。

```yaml
- name: '@deepseek-ai/dsh-experimental-shadow-router'
  config:
    authorizedRoots: [dshHomePath('projects')]
    shadowSessionId: session-shadow
- name: '@deepseek-ai/dsh-experimental-shadow-bridge'
  config:
    intervalMs: 60000
    followupMaxChars: 8000
```

### 配置

| 字段 | 默认值 | 含义 |
|---|---|---|
| `intervalMs` | 必填 | 正安全整数：相邻两次安全网对账轮询之间的毫秒数。`shadow/delivery-received` 事件承载实时转换，因此它只限定事件路径错过的投递至多等待多久。 |
| `followupMaxChars` | 必填 | 正安全整数：单条转发文本（含头部）的字符上限。 |

两个字段均为必填、无默认值：缺失任一项的组合行加载失败。

### 到达 controller 的内容

一条可转发的投递变成 controller live agent 上的一条 follow-up：先是一个确定性的头部（标识该 Shadow 投递的 messageId 与 workspace），随后是逐字的投递原文；当总长超过 `followupMaxChars` 时从尾部截断。follow-up 进入 controller 的 inbox 并成为 `user/message` 会话事件，模型在下一个 turn 看到它，日志记录它。controller 没有 live agent 的投递留给安全网——桥从不创建、恢复或处置 agent。仅当绑定的状态不是 `stopping` 或 `stopped`、绑定仍记录着授权 open run、且投递的 Goal 与验收关联等于该 run 时，投递才可转发；因此收到投递之后发生 Goal 切换，上一个 Goal 的消息也不会进入 controller 的当前 Goal。转发从不写 `completed`：已转发的行保持 `received`，直到 controller 侧结算它。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现内部——点击展开</summary>

本节解释特性背后的设计决策并指向实现它们的代码；可观察行为已在[使用本包](#use-this-package)中完整覆盖。

### 设计决策

- **只观察的事件是主通道；读面是对账接缝。** router 对每一次真实的 `queued` → `received` 转换恰好发出一次 `shadow/delivery-received`——发送路径与恢复收敛同权——携带冻结的投递快照，不暴露任何变更动词。桥从该事件转发，并在每个单元里重读 router 的公开读面（`listDeliveries()`/`findBinding()`），因此不写 router 也天然容忍挂载顺序与重启。
- **一条串行化转发链。** 事件单元与轮询单元在同一条 promise 链上运行，事件与对账轮询不可能在同一条投递上交错；内存中的已转发集合加上标记表，使此进程内或重启后的每个后续单元都跳过已转发的投递。
- **详细设计的投递门禁在转发时再次执行。** router 在接收时已校验 Goal 归属；桥在每次转发前对照当前 run 复查，这正是把"属于上一个 Goal 的投递"挡在"open run 已前移的 controller"之外的原因。
- **先发送，后记录。** follow-up 先进入 controller 的 inbox，然后才写标记行。两步之间崩溃会让一条投递在重启后转发两次——带着相同头部的可见重复；相反的顺序则可能悄悄丢失输入。follow-up 或标记写入的每一次失败都按单元包含，并由之后的单元重试。
- **一张标记表，启动时重建。** `shadow_bridge` 域的 `forwarded` 表是桥唯一的持久状态；内存中的已转发集合是它的直写投影，在构造时恢复。

### 源码地图

| 文件 | 角色 |
|---|---|
| [`src/index.ts`](src/index.ts) | function-plugin 面：config、注入、域打开、事件订阅、启动对账与安全网循环接线 |
| [`src/forwarder.ts`](src/forwarder.ts) | 串行化转发链、投递门禁、live agent 解析、follow-up 发送与标记写入 |
| [`src/text.ts`](src/text.ts) | 确定性头部与受限的转发文本 |
| [`src/loop.ts`](src/loop.ts) | 低频安全网定时器：失败包含、退出时排空 |
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

每条已转发投递增加一个有界的 user turn——头部加原文，至多 `followupMaxChars` 字符——以及它的模型回复，二者在 controller 会话的余下生命周期中保留。没有转发任何内容的单元不产生请求，也不产生 token。

#### KV Cache 影响

只追加：每条已转发投递延伸 controller 会话的请求前缀，而不使其之前的前缀失效，且头部对给定投递是确定性的。本包不添加任何工具 schema 与提示词分段，因此其自身从不重塑可复用前缀；provider 缓存的可用性与驱逐在本包契约之外。

## 已知限制与延期工作

<a id="known-limitations-and-deferred-work"></a>

这些限制定义了本桥何时适配不佳或需要特别的运维注意。它们是当前的包约束，不是任务清单。

- **仅限 live controller——不做冷恢复** —— 桥通过 live-agent registry 解析绑定的 controller 会话，从不创建、恢复或收养 agent；宿主从未使之 live 的 controller 永远收不到它的投递，投递保持 `received` 并在 router 中可见。
- **转发不确定投递的完成** —— `completed` 是 controller 侧的持久事实；本包从不调用 router 的完成接缝，已转发的投递保持 `received`，直到宿主或后续轮次通过 `completeDelivery` 结算。
- **follow-up 与标记之间的崩溃可能转发两次** —— 标记在 follow-up 进入 inbox 之后记录，因此被中断的进程会在下一次启动时把一条投递再转发一次；重复项携带相同的头部与 messageId。相比可能悄悄丢失输入的顺序，这里刻意选择了这一顺序。
- **`note` 投递不转发** —— 本轮只有 `work` 投递会调度 follow-up；note 保持 `received`。
- **错过事件的工作等待安全网** —— 实时转换经由事件立即转发，但转换发生在监听器窗口之外的投递、以及 controller 后来才上线的投递，至多等待 `intervalMs` 到下一次安全网轮询；一次轮询按 router 的稳定投递顺序串行转发。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者工作上下文——点击展开</summary>

下一轮的自然扩展：从 controller 侧的 goal 回执结算 `completed`、把 `note` 投递作为静默输入转发，以及一个在保留会话上拉起 controller agent 的宿主侧 provisioner——这三者本桥都刻意不拥有。

</details>
