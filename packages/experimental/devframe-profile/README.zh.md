---
description: "叠加在 Web profile 之上的私有 DevFrame profile 层，供源码 checkout 用户使用层级栈：会话身份、影子路由、项目记忆、目标绑定与派发。"
kind: "package-bundle"
---

# @deepseek-ai/dsh-experimental-devframe-profile

[English](README.md) | 中文

## 概述

`dsh-experimental-devframe-profile` 是把 DevFrame 栈挂载到 Web profile（`dsh-base` + `dsh-web-app`）之上的私有 profile 层。它的 patch 插入 session-identity、shadow-router、project-memory、command-goal-binding 四行，外加三角色 agent-hierarchy 策略与 agent-dispatch 消费面。必须把本包显式加入已初始化的源码 checkout profile；正式发布排除本包。

## 目录

- [使用本包](#use-this-package)
- [理解实现](#understand-the-implementation)
- [延伸阅读](#further-exploration)
- [模型体验](#model-experience)
- [已知限制与延期工作](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

### 安装到 profile

在本仓库 checkout 中，把本层作为又一个 `--patch` overlay 应用到 Web profile，然后运行一个要求 controller 派发 lead 的任务：

```sh
pnpm dsh --profile web --patch ./packages/experimental/devframe-profile/cordis.patch.yml --no-open
```

profile 必须已包含 Web bundle 层；本层不动其 webserver 行。部署通过后续 `--patch` overlay 收窄安全的机器中立默认值（authorizedRoots、vaultRoot、shadowSessionId、workspace 身份），而不是编辑本文件。

本层的 patch 以 insert 方式加入六行，不指向既有行。不要同时通过这些行自带的包层挂载同一行（例如 `dsh plugin --profile <name> add @deepseek-ai/dsh-experimental-project-memory`）：两个 patch 列表重复插入同一行 id 会让启动以重复行 id 错误失败。收窄某行的默认值时，改用后续按 id 指向的 `--patch` 条目（`- id: project-memory, config: …`）——patch 条目替换目标行的整个配置，每行以最后一次写入为准；覆盖语义由[基础 bundle README](../../bundle/base/README.zh.md) 拥有。

### 你得到什么

本层插入身份、路由、记忆与目标绑定四行，默认值全部未配置、只读：shadow-router 在声明授权根之前不安装任何 `project_*` 工具；project-memory 在提供真实 vaultRoot 之前保持工具只读。hierarchy 行的 worker 面初始为空（fail closed），不预分配 lead 插件范围；dispatch 行挂载 `agent_dispatch` 消费面。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现内部——点击展开</summary>

本包的运行时内容是 [`cordis.patch.yml`](cordis.patch.yml)。在 Web bundle 层之后应用时，patch 按安全默认值插入上述六行；不配置其他内容。

| 文件 | 角色 |
|---|---|
| [`cordis.patch.yml`](cordis.patch.yml) | Web profile 之上的有序 patch |
| [`src/index.ts`](src/index.ts) | 空模块入口；patch 是运行时内容 |
| — | 不发布运行时不变式伴生入口；本包只承载静态 profile patch。被挂载的包拥有其激活的可变关系。 |

</details>

-----

<a id="further-exploration"></a>
## 延伸阅读

- [Experimental 包族](../README.zh.md)——孵化状态与发布排除。
- [Agent dispatch](../agent-dispatch/README.zh.md)——本层挂载的消费面。
- [Agent hierarchy](../agent-hierarchy/README.zh.md)——本层配置的角色策略与插件范围。

-----

<a id="model-experience"></a>
## 模型体验

### DevFrame 行

#### 模型看到什么

模型可见面归被挂载的包所有：`project_*` 工具归 shadow-router，记忆工具归 project-memory，`/devframe-start` 及其 goal 命令归 command-goal-binding，`agent_dispatch` 归 agent-dispatch。本包只改变组合；自身不新增提示词文本或工具 schema。

#### Token 影响

本包加入六行被挂载行贡献的提示词文本与 schema；自身不加入任何。

#### KV Cache 影响

本包 patch 与被挂载行配置不变时，组合前缀稳定。

<a id="known-limitations-and-deferred-work"></a>
## 已知限制与延期工作

- **仅源码 checkout**——本私有包不出现在官方 npm、CLI、Web 或 Python 发布载荷中。
- **需要 Web profile**——patch 依赖 Web bundle 层提供的行 id；它不是独立 profile。
- **默认 fail closed**——shadow-router、project-memory 与 worker 工具面在部署配置前保持惰性；本层不发布预配置的根、vault 或范围。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者工作上下文——点击展开</summary>

无。

</details>
