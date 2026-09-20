---
description: "叠加在 Web profile 之上的私有 DevFrame profile 层，供源码 checkout 用户使用层级栈、专家团队编排与 Web 专家中心入口。"
kind: "package-bundle"
---

# @deepseek-ai/dsh-experimental-devframe-profile

[English](README.md) | 中文

## 概述

`dsh-experimental-devframe-profile` 是把 DevFrame 栈挂载到 Web profile（`dsh-base` + `dsh-web-app`）之上的私有 profile 层。它的 patch 插入 console 日志导出器、会话身份、Shadow 路由与对话、项目记忆、目标绑定、agent hierarchy、agent dispatch、带论文与开发数据包的 expert-team，以及常驻 Web 专家中心入口。必须把本包显式加入已初始化的源码 checkout profile；正式发布排除本包。

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

本层的 patch 以 insert 方式加入十一行，不指向既有行。不要同时通过这些行自带的包层挂载同一行（例如 `dsh plugin --profile <name> add @deepseek-ai/dsh-experimental-project-memory`）：两个 patch 列表重复插入同一行 id 会让启动以重复行 id 错误失败。收窄某行的默认值时，改用后续按 id 指向的 `--patch` 条目（`- id: project-memory, config: …`）——patch 条目替换目标行的整个配置，每行以最后一次写入为准；覆盖语义由[基础 bundle README](../../bundle/base/README.zh.md) 拥有。

### 你得到什么

本层插入身份、路由、状态、对话、记忆、目标绑定、hierarchy、dispatch、expert-team 与 Web 入口各行，默认值全部未配置、只读：shadow-router 在声明授权根之前不安装任何 `project_*` 工具；Shadow 对话宿主在声明 `shadowSessionId` 之前保持惰性；project-memory 在提供真实 vaultRoot 之前保持工具只读。expert-team 挂载论文与开发数据包，并把运行镜像写到 `dshHomePath('expert-team-runs')`；浏览器入口经 Remote 读取宿主状态，不增加工具或 schema，并允许用户为选定专家暂存普通提示。hierarchy 行的 worker 面初始为空（fail closed），不预分配 lead 插件范围；dispatch 行挂载 `agent_dispatch` 消费面；logger-console 行把宿主进程的插件日志输出导出到 stdout。

### 启用 Shadow

本层插入的 shadow-router 行刻意不带 config：没有授权根、没有声明的 Shadow 会话时，router 不在任何作用域安装 `project_*` 工具，[profile-entry spec](../shadow-router/tests/profile-entry.spec.ts) 锁定了这一 fail-closed 默认。三步把该行变成生效条目：

1. 若 profile 缺少 router 包依赖，用 `dsh plugin --profile web add @deepseek-ai/dsh-experimental-shadow-router` 安装；该包未声明 bundle，因此这一步只安装依赖，不新增它自己的层。
2. 给该行真实 config：把 [shadow 示例 patch](../../../apps/cli/config/examples/shadow/cordis.patch.yml) 中的 `shadow-router` 条目粘入 `$DSH_HOME/profiles/web/cordis.patch.yml`，或把该文件作为又一个 `--patch` overlay 传入，并把 `shadowSessionId` 占位符替换为控制器会话 id、`authorizedRoots` 替换为真实值。
3. 让变更按 profile 的 `patchReload` 策略生效：`live` profile（随附的 web 模板）热应用 profile 自身 patch 文件的编辑，`startup` profile 在下次重启时应用。

每个授权根必须是已存在的绝对目录：相对或不存在的条目会在加载时以 `SHADOW_INVALID_CONFIG` 失败，宿主以非零状态退出，而不是带着配置不完整的 shadow 启动。

变更生效后，被声明的会话在创建时被标记——若其已存活则立即标记——其作用域恰好获得 `project_open`、`project_send`、`project_status`、`project_stop` 四个工具；其他作用域一个也解析不到。

### 启用专家模式

默认 patch 同时挂载两个 shipped 数据包：论文流水线与层级软件开发团队。宿主注册 `expert_team_list`、`expert_team_run`、`expert_team_status` 与 `expert_team_approve`；`expert_team_run` 还通过 `expert` 加 `question` 形态处理一次有界的单专家咨询。Web profile 中，常驻专家中心入口出现在侧栏页脚，列出已挂载专家、显示当前进程最近的运行，并允许用户把专家召唤到新的空白对话中且编辑预填提示。启动运行与批准人工关口仍属于模型／宿主操作。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现内部——点击展开</summary>

本包的运行时内容是 [`cordis.patch.yml`](cordis.patch.yml)。在 Web bundle 层之后应用时，patch 按安全默认值插入上述十一行；不配置其他内容。

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

模型可见面归被挂载的包所有：`project_*` 工具归 shadow-router，记忆工具归 project-memory，`/devframe-start` 及其 goal 命令归 command-goal-binding，`agent_dispatch` 归 agent-dispatch，四个专家团队工具归 expert-team。Web 专家中心不新增工具或 schema；召唤操作预填的提示只有在用户提交后才会作为普通用户输入到达模型。

#### Token 影响

本包加入十一行被挂载行贡献的提示词文本与 schema；自身不加入任何。

#### KV Cache 影响

本包 patch 与被挂载行配置不变时，组合前缀稳定。

<a id="known-limitations-and-deferred-work"></a>
## 已知限制与延期工作

- **仅源码 checkout**——本私有包不出现在官方 npm、CLI、Web 或 Python 发布载荷中。
- **需要 Web profile**——patch 依赖 Web bundle 层提供的行 id；它不是独立 profile。
- **默认 fail closed**——shadow-router、project-memory 与 worker 工具面在部署配置前保持惰性；本层不发布预配置的根、vault 或范围。expert-team 使用源码 checkout 数据包与 DSH home 运行镜像挂载，而 memory 仍要提供 Vault 根后才可用。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者工作上下文——点击展开</summary>

无。

</details>
