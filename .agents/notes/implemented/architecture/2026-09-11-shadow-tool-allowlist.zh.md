# Agent Note：Shadow 对话宿主在其组合的作用域上强制设计工具 allowlist

Status: implemented

[English](2026-09-11-shadow-tool-allowlist.md) | 中文

## 问题

指定的 Shadow 会话经普通 agent 注册表创建，因此继承了部署的整个全局工具集——包括 shell、文件、会话控制与插件工具——而影子路由器的 `markShadow` 又把它的四个模型面 `project_*` 工具装进同一 agent 作用域，与对话宿主的四个 `shadow_*` 工具并列，一个会话上并存两套项目工具面。设计（[detailDesign-part2.zh.md](../../../../docs/detailDesign-part2.zh.md) Project tools 一节）要求的恰恰相反：Shadow 的模型面 allowlist 只含其路由工具与显式启用的用户 memory 访问，没有任意文件系统/shell 执行、原始会话控制工具、插件自我修改或不受限的 MCP 访问。shadow-controller 此前对此没有任何强制，README 也把两套面并存记为已知限制、推迟到路由器契约的后续决策。

## 决策

对话宿主的工厂 setup（`shadow-agent.ts` 的 `shadowSetup`）在其组合的作用域上强制 allowlist：在安装四个对话工具与人设段落之后，做三个随 agent 作用域一起解除的效果式注册：

1. `agentCtx.tools.restrict({ allow: enabledMemoryTools })` 隐藏所有继承的部署工具，只留 project-memory 插件实际挂载的 memory 工具（`memory_search`、`memory_read`、`memory_append`）——setup 时对全局层做存在探测，因为 `restrict()` 对未知全局工具名会大声失败。空 allow 列表合法，隐藏全部继承面；allow 列表（而非 deny 列表）语义使之后注册的全局工具同样被隐藏。
2. `agentCtx.tools.presentAs('native')` 把呈现钉死为原生，使 PTC 模式部署既不能把面折叠成 `run_code`，也不能把任意程序执行交给 Shadow。
3. `agentCtx.tools.guard(shadowAllowlistGuard)` 以单调、fail-closed 的方式拒绝指定 agent 上一切名字不在 allowlist（四个对话名加三个 memory 名）内的执行。守卫对每个就绪执行都在 dispatch 之前运行，因此该拒绝同样覆盖被限制隐藏或从未注册的名字。

allowlist 的名字是固定字符串——设计安全不变量，不是部署可调项。

### 为什么守卫是机制的一部分

`tools.restrict()` 只过滤作用域继承的东西——全局层与祖先作用域——因为注册表有意豁免作用域自有注册，让被委托的子代理保留它赖以回答的工具（并且 `restrict()` 对作用域本地名字会大声失败）。路由器把 `project_*` 注册进指定 agent 的自有层（`agent.ctx`）——与对话宿主注册工具的同一层——所以任何限制都藏不掉它们。守卫封住这条仍然可见的执行路径：模型调用 `project_open` 会自带 `request_id`，绕过对话面与设计保留给宿主的请求 id 托管，即使路由器会授权该指定调用者。

## 被否决的备选方案

**只用 restrict。** 否决：自有层豁免使路由器的 `project_*` 面完整可见且可执行——这正是本次收敛要消除的重复；而且 allow 列表点名作用域本地工具时 restrict 会大声失败，连四个对话工具都列不进去。

**subagent 的 persona/toolFilter 机制。** 读后否决：`SubagentStartRequest.toolFilter` 在子代理创建窗口里就是 `childCtx.tools.restrict(...)`（`applyChildComposition`）——同样的语义，没有额外过滤能力——而 `AgentOptions` 根本没有工具过滤字段。

**在宿主 setup 里预注册同名工具来藏掉 `project_*`。** 否决：路由器随后的注册会抛 "already registered in this scope"，`installShadowTools` 回滚并重抛，而同步 `agent/created` 监听失败会否决 agent 发布——在路由器指定的部署里指定会话将永远无法创建。

**仅靠人设引导（提示词点名四个工具）。** 否决：提示词描述行为但无法强制工具权限（[native-development 提案](../../proposed/feature/2026-09-02-devframe-dsh-native-development.zh.md)记录了同样的结论），而一个可见且可执行的 `project_open` 是模型无视人设偏好也能走的绕行道。

**改为收敛到路由器的 `project_*` 面。** 对本宿主否决：对话工具的存在正是为了把请求 id 托管、有界文本与对话面留在宿主手中；设计的调用者不可选会话与宿主保留请求 id 规则由对话面强制，所以在组合出的指定作用域上获胜的是它。

## 后果

买到：组合出的指定作用域其继承面恰为显式启用的 memory 访问；呈现不会漂移到 PTC；该作用域上的执行经执行器 fail-closed 收敛到 allowlist（真实组合套件在有无 memory 工具两态、`project_open` 拒绝、全局面与兄弟代理面不受影响、以及释放解除各点上钉住行为）。其他代理与全局注册表不受影响，resume 重新组合出同一面。

代价与剩余缺口：路由器的四个 `project_*` schema 在指定作用域的 `schemas()` 中仍然可见——同层自有注册按设计豁免于限制——模型仍看得到它们，只是执行被拒。消除可见性残余需要路由器侧契约变更（每个指定会话一套工具面）；shadow-router README 的 "the designated Shadow scope gains exactly four tools" 表述与本包的已知限制条目如今从两侧描述同一事实。两个较小代价：会话创建之后才挂载的 memory 工具保持隐藏（allow 列表在 setup 时编译——fail-closed），以及在指定作用域上未知工具名的拒绝消息是 allowlist 文案而非通用 unknown-tool 错误。
