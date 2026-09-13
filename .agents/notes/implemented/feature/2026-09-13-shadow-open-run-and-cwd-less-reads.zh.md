# Agent Note: The shadow host open records the authorized run, and the read faces admit cwd-less sessions

Status: implemented

[English](2026-09-13-shadow-open-run-and-cwd-less-reads.md) | 中文

## Problem

R2 真实模型端到端验证（2026-09-12）用真模型跑通了完整影子闭环，留下三个只能靠手工补救的产品面缺口。通过面板或 Shadow 对话打开项目会供给出一个 `ready` 绑定，但没有任何环节记录该绑定的授权运行——`setActiveGoal` 是没有任何产品面调用的宿主专用缝——因此在验证把运行手工注入 `shadow_router` 存储之前，每一次宿主投递都被 `SHADOW_GOAL_NOT_AUTHORIZED` 拒绝。路由器的 `controllerProfile` 默认 `'devframe'`，而没有任何已发布 preset 提供这个 id，于是每个被供给的控制器会话都带着一个在消费方解析时会失败的 `agentPreset`。另外，Shadow 对话会话——因为指定会话没有工作区 cwd 而持久化在 `sessions/_no-cwd/` 下——无法从 Web 历史加载：session controller 的冷列表丢弃所有无 cwd 的行，其历史面把所有无 cwd 观察以 `session/not-found` 拒绝，尽管 `cwd` 是可选的 `SessionHeader` 字段且 live 读面工作正常。

## Decision

本轮实现的授权语义裁定：**人类通过面板或 Shadow 对话发起的 open 即人类授权动作，由宿主桥记录该授权。影子与模型不能自授权——模型面工具路径保持其门禁，`setActiveGoal` 保持宿主专用。**

- **`openProjectForHost` 记录运行**（shadow-router；契约措辞在 shadow-routing 定义包）。当受门禁的 open 落到 `ready` 且绑定尚未记录授权运行时，桥会至多一次地记录运行——`host-run-<回执revision>` 配对 `open-run-<回执revision>`——并在操作链内重读绑定，因此与 open 竞态的停止会跳过记录而不是授权一个已关闭的接收方。重复 open、重放的请求 id、以及之后显式的宿主 `setActiveGoal` 都按既有的 Goal 切换语义保留或替换该记录；open 回执携带的修订可能比持久绑定落后一。
- **`controllerProfile` 默认 `'standard'`**——一个已发布的 preset id——使被供给的控制器会话固定在可解析的 preset 上；README config 行写明新默认值，并有行为用例钉住它。
- **无 cwd 的 Session 是一等读取行**（session-controller）。历史源不再把无 cwd 观察映射为 `session/not-found`，冷列表不再丢弃无 cwd 行，且跟随无 cwd 源不会调度后台激活，因为通用恢复面仍按项目 cwd 限定（其所有者——Shadow 对话宿主——自己恢复该会话）。搜索目前仍按项目限定；该边界记录在 session-controller README 中。

## Alternatives considered

**在 shadow-controller 的调用点记录运行**（面板 Remote 与对话工具各自在 open 后调用 `setActiveGoal`）。否决：两个调用点重复记录，且未来任何宿主面调用方都会静默跳过；路由器桥是两个人类面已经汇合的唯一收口，也正是裁定放置记录的位置。

**每次宿主 open 都重新授权一次新运行。** 否决：重复 open 会每次重新铸造 `host-run-<新revision>`，修订无限递增，并把已排队投递孤立在旧运行之外；运行至多建立一次，宿主 `setActiveGoal` 仍是切换它的唯一途径。

**把授权运行绑定到 per-project `/devframe-start` goal 流**，让验收哈希指向真实 Goal 的准入而非宿主标签。作为未来收紧路径推迟：它需要影子家族目前不依赖的 per-project goal 栈。`host-run-<revision>` 标签为该迁移保留了空间，而不让路由器预先承诺。

**让无 cwd 的 Session 在 Shadow 卡片之外保持不可见**（列表、历史、搜索都按工作区限定）。否决：可选的 `SessionHeader.cwd` 是一等持久状态，live 面早已展示这类会话，`session/not-found` 拒绝让已持久化对话在用户拥有的 Web 历史里成为死路。

**发布一个 `'devframe'` preset** 让旧默认可解析。否决：preset 集合由 agent-presets 拥有，且当前没有使用方提供该人设；路由器应默认指向存在的 preset，而不是为一个默认值新造一个。

## Consequences

换来的：open 后接 send 无需手工注入存储即可端到端走通，由路由器宿主桥测试和跨同一根重启的两段 boot 真 Loader 组合测试钉住；被供给的控制器固定在存在的 preset 上；持久化的 Shadow 对话可从 Web 历史列表化并分页读取，且不会调度注定失败的后台激活。付出的：open 回执的 `bindingRevision` 可能比持久绑定落后一（已在桥上注明）；无 cwd 会话可列表、可读取，但经通用面不可恢复、不可搜索；桥的检查-记录跨越两段操作链，同一工作区的两次并发首次 open 可能以多一次修订递增记录同一运行——值完全相同，投递不受影响。
