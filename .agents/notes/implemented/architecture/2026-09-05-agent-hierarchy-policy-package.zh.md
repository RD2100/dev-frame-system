# Agent Note：让插件化代理层级拥有自己的策略包

Status: implemented

[English](2026-09-05-agent-hierarchy-policy-package.md) | 中文

## Problem

插件化层级（P00 契约、P01 session-identity）有了持久角色与绑定，却没有执法：worker 仍能调用 spawn 工具，lead 能委托到任何未获批范围，冷恢复出来的绑定背后没有守卫。devframe 的 `RolePolicy` 覆盖的是另一个封闭的单项目 profile——controller/worker/reviewer 加宿主点名的工具清单——表达不了 lead 插件范围、创建入口全覆盖，也表达不了 P01 冷恢复的身份校验告警。

## Decision

`packages/experimental/agent-hierarchy` 是插件化层级的执法包。它挂载 `ctx.agentHierarchy`，硬注入绑定注册表、工具注册表与 agent 注册表，在两个面上执行同一策略：

- **工具面。** 根工具注册表上的一个 monotonic pre-execute 守卫按执行解析调用方的精确活动身份与绑定记录，依次拒绝：陈旧身份、受控工具上的缺角色（fail closed）、角色 deny 面、一切来自深度 2 的委托（与 seam 的 `SubagentDepthError` 路径并行的绝对预算）、以及 lead 委托到宿主配置未为其 agent id 获批的插件范围。拒绝是原因字符串；任何 post-execute 路径都无法翻案。
- **创建面。** `evaluateCreation(creatorRecord, intent)` 对程序化创建入口的 P00 `CreationIntent` 施行同一策略。

`createChildAgent` 在调用 Agent 工厂前执行此策略：总控只能创建组长，组长只能创建获批范围内的 Worker，Worker 不得创建代理。它在 setup 中通过 `bindPreparedSession` 于发布前持久化身份，Session 的创建和销毁仍由工厂拥有。宿主提供已注册工作树和 preset 装配。同一父会话和任务的重试返回已有活跃子 Agent；身份冲突或已保留但不可用的子 Agent 要求显式恢复。这扩展了 [Agent 生命周期所有权契约](2026-06-18-agent-lifecycle-and-ownership-contracts.zh.md)，不改变工厂发布规则。

角色策略是三态查找表（`controller`/`lead`/`worker`）；退役 `reviewer` 的语义并入 lead 与 worker 的 deny 面，`send_message` 有意保留在两面之外——它是 worker 的授权汇报通道。每角色的 inherited allow 清单来自 zod 校验的宿主配置，并按作用域安装为限制（首次执法时惰性安装、经 `agent/created`、以及由 init 时对已恢复绑定的冷恢复扫描）；它们只是纵深防御——守卫是唯一执法权威，因此本包不发布 invariant companion。冷恢复不需要注册表事件：init 扫描覆盖仍活的已恢复代理，`agent/created` 覆盖之后的代理，守卫的按执行查找无论时机都覆盖一切。

深度预算 2、deny 面与封闭角色联合是安全不变量，保持固定；部署可变的选项（工具名、每角色工具清单、每 lead 获批范围）是经校验的 `Config` 字段。

## Alternatives considered

**扩展 devframe 的 `RolePolicy`。** 它硬编码 reviewer 角色，没有范围概念，还要求宿主显式调用 assign；改造它会让实验性 DevFrame profile 耦合插件化契约，并且家安错了。

**在 subagent seam 里执法。** seam 拥有的是委托机制而非层级策略；让它认识角色会把策略摊到每个创建 provider，还照样漏掉 Team 与 SDK 面。

**让绑定注册表发事件并订阅。** 绑定注册表有意保持为安静的持久权威。事件只服务于限制半边，而守卫的实时查找已经覆盖。

**先创建活跃 Session，再创建其 Agent。** `createBoundSession` 会把 Session 放入 SessionStore，因此后续工厂调用会拒绝该活跃身份。在未发布的 setup 中绑定，既保留唯一生命周期所有者，也让发布观察者能够读取角色。

## Consequences

P02 波次为 P03（controller）与后续波次提供了一个可组合而非重建的执法 seam：写绑定、配置获批范围集合，一切模型可见入口的创建即受 policing。部署必须显式声明每角色工具清单——空的 `inheritedTools` 对该角色拒绝所有全局工具——配置错误在装载时 fail loud。devframe 的 `RolePolicy` 在其迁移波次之前保持原样。
