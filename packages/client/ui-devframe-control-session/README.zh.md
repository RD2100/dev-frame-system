# `@deepseek-ai/dsh-client-ui-devframe-control-session`

[English](README.md) | 中文

把 version 1 `controller/identity` Session 事件投影到 DSH 原生会话界面的浏览器端插件。该插件注册一个 `ConversationNodeDefinition`、locale 词典和一个按 key 分发的 `conversation.chat.node` renderer；dispose 会移除这 3 项由 effect 持有的注册。

## 投影与隐私

投影只接受各角色精确的字段集合，并校验 payload 内的确定性 Session ID 是否与长度受限的 profile ID 或 workspace ID 匹配。合法事件会渲染角色、Session ID、作用域 ID、schema version 和 `identity-recorded`。畸形、不匹配、null、数组或含额外字段的 payload 会渲染 ID 为空的有界 `blocked` 状态，不会回显输入。

事件契约要求规范 cwd，但身份卡不会选取它。绝对路径、凭据、提示词、嵌套 payload 和未知字段同样不会被渲染。所有值都作为 React 文本节点渲染。本包不拥有持久存储、网络访问、控制器生命周期或第二个工作台。

## 模型体验

### 浏览器身份投影

#### 模型看到的内容

没有直接内容。该插件只把日志中的 `controller/identity` 事件渲染为浏览器会话节点，不添加提示词内容、工具、消息或模型请求。

#### Token 影响

直接 token 影响为零，因为浏览器渲染不会进入模型上下文。

#### KV Cache 影响

仅浏览器侧的投影不会创建模型请求前缀，也不会使其失效。

## 已知限制与延期工作

- **身份依据，不是实时就绪状态**：`identity-recorded` 只表示有界事件通过了客户端校验；它不能证明 Host 控制器仍然存活或能够执行工作。
- **仅为 payload 投影**：浏览器节点无法独立证明该 payload 属于当前 Session header，也无法证明完整日志中恰好只有一个 identity 事件；这些校验仍以 Host 控制器为权威。
- **只读节点**：该界面不提供打开、重试、修复、派发或策略操作。
- **只支持 version 1**：其他 schema version 都会失败关闭为有界 `blocked` 视图，直到本包增加并测试显式迁移。
