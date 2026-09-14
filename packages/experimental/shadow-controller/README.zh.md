---
description: "Shadow 路由器聚合状态、面板写入面与持久 Shadow 对话宿主的 Remote 拥有者。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-shadow-controller

[English](README.md) | 中文

## 概述

`dsh-experimental-shadow-controller` 是[影子路由器](../shadow-router/README.zh.md)聚合状态、面板写入面与人类对话式影子的 Remote 拥有者。它以一个诚实的读取 `readStatus()`——是否挂载了影子路由器、宿主组合指定了哪个控制者会话、该会话是否在线、授权根目录，以及打开项目的行——、三个项目写入（`openProject(path)`、`sendToController(workspaceId, text)`、`releaseProject(workspaceId)`，委托给路由器的宿主桥）、以及由持久对话宿主服务的两个对话面（`postMessage(text)`、`readConversation(cursor)`）支撑生成的 `ctx.remote.shadow` 命名空间。每个项目写入都把校验、调用者门禁（以指定 Shadow 的授权运行）、重放与投递通道留在路由器内；控制器只为每次操作铸造一个新的请求 id。正式发布排除本包，只能从源码 checkout 使用。

## 目录

- [使用本包](#use-this-package)
- [理解实现](#understand-the-implementation)
- [延伸阅读](#further-exploration)
- [模型体验](#model-experience)
- [已知限制与推迟事项](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

### 从浏览器界面读取状态

把本服务挂载在[影子路由器](../shadow-router/README.zh.md)提供者旁边（[DevFrame profile 层](../devframe-profile/README.zh.md)已这样做），然后调用生成的命名空间：

```ts
const result = await ctx.remote.shadow.readStatus()
if (!result.ok) return
// result.value: { mounted, shadowSessionId?, shadowLive, authorizedRoots, bindings }
```

`mounted: false` 表示此部署没有组合影子路由器；`mounted: true` 而 `shadowSessionId` 缺失表示路由器存在但宿主尚未指定控制者。两者都是诚实的未启用回答，绝不伪装在线。

### 驱动面板写入

```ts
await ctx.remote.shadow.openProject({ path: 'D:/projects/alpha' }) // ProjectOpenResult
await ctx.remote.shadow.sendToController({ workspaceId, text: 'ship the release' }) // ProjectSendResult
await ctx.remote.shadow.releaseProject({ workspaceId }) // ProjectStopResult, status 'stopped'
```

失败以 `{ ok: false, error: { code, message } }` 解析，并逐字携带路由器自己的拒绝理由——未授权根、路径不存在、项目已关闭——因此界面显示服务的原因而不是编造一个。没有挂载路由器时，读取保持诚实（`mounted: false`），每个写入都大声失败。落到 `ready` 的 open 还会在路由器中记录该项目的授权运行——人类发起的 open 即授权动作——因此第一次 `sendToController` 无需额外的宿主设置。

### 与影子对话

挂载对话宿主行（DevFrame profile 层已插入），然后向指定会话投递消息并读回对话面：

```ts
await ctx.remote.shadow.postMessage({ text: 'Open D:/projects/alpha and fix the failing tests.' })
const page = await ctx.remote.shadow.readConversation({})
// page: { messages: [{ seq, role: 'user' | 'shadow', text, at }], cursor }
```

`postMessage` 接受消息并立即返回；会话的代理循环认领它并运行该轮——模型可以调用四个对话工具——回复落在持久化的对话面上。`readConversation` 把该面折叠成有界、按游标寻址的行，聊天界面用返回的 `cursor` 轮询。对话经会话持久化跨重启保留；部署未声明 Shadow 会话时宿主保持惰性（每个动作大声失败）。

### 你会得到什么

- `ctx.shadowController` 服务与诚实的 `readStatus()` 方法、三个写入面、两个对话面。
- `ctx.shadowAgent` 对话宿主（`./shadow-agent` 入口）：指定会话的创建/恢复、四个对话工具、人设段落、设计工具 allowlist 强制、部署挂载记忆工具时的记忆使用指引、面向无 cwd persona 模板的 scoped 诚实 cwd 变量，以及有界对话读取。
- 生成的 `@deepseek-ai/dsh-experimental-shadow-controller/remote` Client 产物，以及携带状态、写入与对话词汇的 `./types` 子路径。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现细节——点击展开</summary>

`ShadowController` 以服务键 `shadowController`、Remote 命名空间 `shadow` 继承 `TypertRemoteService`；`ShadowAgent`（同包 `./shadow-agent` 入口）是键为 `shadowAgent` 的普通 Service，注入 agents 注册表。每个 `@Remote` 方法都由装饰器注册；typert 生成器在 `lib/` 下产出宿主 face 与 Client contribution。项目写入调用 `ctx.get('shadowRouter')` 与路由器的宿主桥，并以每次操作铸造的 `randomUUID()` 请求 id。`ShadowAgent.ensure()` 从路由器快照解析指定会话 id，按原样复用存活会话（绝不拥有另一行的生命周期），等待完整应用就绪，然后经 `ctx.agents` 恢复持久会话或创建它；工厂 setup 组合作用域世界——四个对话工具（`installShadowConversationTools`）、人设段落、会话模型面上的设计工具 allowlist（原生呈现钉死、继承工具收敛到显式启用的 memory 访问、以及单调执行守卫）、部署挂载完整记忆三件套时的记忆指引段落（对先前上下文的引用先搜索一次、只追加人类要求保留的内容、失败逐字上报）、面向无 cwd persona 模板的 scoped 诚实 cwd 变量，以及全新会话上的宿主默认模型选择。只有本宿主创建或恢复的会话才随它释放。

| 文件 | 职责 |
|---|---|
| [`src/index.ts`](src/index.ts) | `ShadowController` 服务：读取、三个写入面与两个对话面 |
| [`src/shadow-agent.ts`](src/shadow-agent.ts) | `ShadowAgent` 对话宿主：创建/恢复、投递、有界对话读取 |
| [`src/shadow-tools.ts`](src/shadow-tools.ts) | 覆盖路由器宿主桥的四个对话工具 |
| [`src/shadow-prompt.ts`](src/shadow-prompt.ts) | Shadow 人设段落与条件性的记忆指引段落 |
| [`src/types.ts`](src/types.ts) | Client 安全的状态、写入与对话词汇（仅类型） |
| [`lib/typert.host.js`](lib/typert.host.js) | 生成的宿主 FaceModel 与严格结果编解码器 |
| [`lib/typert.remote-client.js`](lib/typert.remote-client.js) | 生成的 Client contribution，挂载 `ctx.remote.shadow` |
| — | 不发布运行时 invariant 伴生；对话宿主由真实组合套件覆盖（循环、存储、持久化、路由器、mock 模型）。 |

</details>

-----

<a id="further-exploration"></a>
## 延伸阅读

- [影子路由器](../shadow-router/README.zh.md)——本控制器暴露的指定控制者域、投递通道与宿主写入桥。
- [Shadow Web 入口](../client-ui-shadow-entry/README.zh.md)——读写此命名空间的常驻侧栏面板。
- [实验包](../README.zh.md)——孵化状态与发布排除。

-----

<a id="model-experience"></a>
## 模型体验

### Shadow 对话宿主

#### 模型看到什么

对话宿主给指定的 Shadow 会话一个模型可见面：一个作用域人设段落（`experimental:shadow`——人类的全局代理、人类 → 影子 → 项目总控 → worker 的层级，以及诚实规则）与四个工具——`shadow_open_project`、`shadow_message_controller`、`shadow_release_project` 与 `shadow_status`——其 schema 只携带任务概念，其执行运行路由器的宿主桥。deployment persona 的 `{{cwd}}` 引用仅在本作用域内解析为宿主的诚实 cwd 变量（"not fixed — you are the Shadow: you route work across authorized projects and never do project work yourself"）。当部署挂载完整记忆三件套时，再增加一个作用域段落（`experimental:shadow-memory`）教其使用：对先前上下文的引用先搜索一次、只追加人类要求保留的内容且以人为来源、每次记忆失败逐字上报。其他任何代理作用域都看不到这些段落与工具。宿主还跨组合出的会话模型面强制设计 allowlist：呈现钉死为原生，除显式启用的用户 memory（`memory_search`、`memory_read`、`memory_append`）外，每个继承的部署工具都从面上隐藏，并由单调守卫拒绝该作用域携带的任何其他执行——包括路由器同层的 `project_*` 白名单，其 schema 作为已记录的残余保持可见。Remote 面本身保持宿主面，绝不回答模型。

#### Token 影响

指定会话的每次请求都携带一次人设段落与四个工具 schema，叠加在对话自身历史之上；挂载记忆三件套时，记忆指引段落与三个记忆工具 schema 一并进入同一前缀。每次对话或记忆工具调用追加一轮结果。

#### KV Cache 影响

人设段落与四个工具 schema 进入指定会话的提示词；由于会话持久化，它们在该对话的整个生命周期占据该前缀（挂载记忆时还包括记忆段落与 schema）。其他会话不受影响。

## 已知限制与推迟事项

<a id="known-limitations-and-deferred-work"></a>

- **写入以指定 Shadow 的授权运行**——写入桥运行与模型面工具相同的受门禁流程，因此指定会话缺失或不在线的部署会以诚实消息拒绝所有写入，而不是绕过门禁。
- **路由器的 `project_*` schema 在指定作用域保持可见**——对话宿主在其组合的会话上强制设计 allowlist（呈现钉死为原生、除显式启用的 memory 访问外隐藏所有继承的部署工具、并由单调守卫拒绝其他一切执行），但路由器自己的 `markShadow` 会把它的 `project_*` 工具装进同一作用域层，而工具注册表有意豁免作用域自有注册不受限制约束——因此四个 schema 保持可见，而其执行被拒绝。消除可见性残余需要路由器侧的契约变更（每个指定会话一套工具面），而非宿主侧过滤。
- **不要在循环配置里声明该会话**——部署若经 `agent-loop` 的 `agents` 配置创建指定会话，对话宿主将无法组合人设、工具与 allowlist 强制（会话按原样使用）；让本宿主创建它。
- **解除是停止语义**——被解除的项目落在 `stopped` 并随行保持可见；重新打开会被路由器拒绝（`SHADOW_PROJECT_STOPPED`），因为重启遵循宿主恢复策略。
- **仅限源码 checkout**——正式 CLI、Web、npm 与 Python 发布负载排除此私有包。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

无。

</details>
