# Agent Note: Reach the designated Shadow's conversation from the Web card

Status: implemented

[English](2026-09-10-shadow-conversation-reachability.md) | 中文

## 问题

DevFrame Web profile 组合了 shadow-controller 宿主层，`ctx.remote.shadow` 也早已携带对话面（`postMessage`、`readConversation`）——但人类在 GUI 里只看到一个状态面板：影子会话从未上线，而且根本不存在对话界面。四个互相独立的缺陷叠成这条死路：

- `session_identity` 存储里一条手写记录把被指定的影子会话绑成角色 `controller`。agent-hierarchy 的 `agent/created` 监听器随后安装其工具限制，但标准工具允许列表是会话作用域的，而 Web 宿主的工具注册表是全局的，`tools.restrict()` 拒绝未知名字，`agents.create` 回滚——影子从未存在。
- `ShadowAgent.ensureOnce()` 在 loader 结束前就要求影子路由器，启动期 ensure 与兄弟插件挂载竞速，对着未挂载的路由器失败，而 Web profile 缺失的 logger 导出器吞掉了警告；也从未有重试。
- 客户端卡片只渲染状态与项目表面；GUI 里没有任何地方能发消息或读对话。
- DevFrame profile 省略了 console logger 导出器，失败的 ensure 无处呈现。

## 决策

被指定的影子会话不携带持久角色绑定：它的八个 Agent 作用域、非受控工具凭指定运行，`session_identity.json` 里过期的 controller 行已被移除——绑定只经 `bind()` 发生，而 `bind()` 要求代理先存在。`ensureOnce()` 在要求路由器之前先等待 loader，启动期 ensure 因此观察到已完成的组合；对话读取路径仍会 ensure，真正的缺失会在下一条对话动词上重试并响亮失败。DevFrame profile 把 logger-console 导出器作为首个插入行组合进来，Web 部署的宿主警告得以到达控制台。

Shadow 卡片承载对话界面。`ShadowConversationController` 把尾部加载与越过游标的增量轮询折叠进一个快照 store，使用与状态 store 相同的被取代读取守卫；失败的读取保留已有行并发布失败。面板展开且影子在线时，卡片在展开时加载尾部、每三秒轮询一次、经 `onPostMessage` 投递；每行显示角色、文本与紧凑的时刻，未在线时面板渲染诚实的离线提示，无行时渲染空态文案，读取或发送失败逐字呈现。区域字典以双语新增 `chat.*` 键。

## 落选的备选

**用空允许列表绑定影子会话。** 否决：hierarchy 守卫把持久绑定当作会话的权威记录，空允许列表错述其权力，且日后任何角色调整都会重新进入全局注册表无法服务的同一条限制路径。默认不绑定、以指定为权威，才是非受控工具集的诚实模型。

**手写绑定并带上 hierarchy 的继承允许列表。** 否决：失败是结构性的，与名字对错无关——会话作用域的标准工具对 Web 宿主的全局注册表不可见，任何允许列表都无法让受限创建在那里成功。

**用定时器重试 ensure。** 否决：轮询重试是在掩盖组合竞速而不是消除它。等待 loader 让启动期调用观察到最终组合；读取路径的 ensure 让重试无需定时器仍然可用。

**投递被接受后乐观追加聊天行。** 否决：读取行不携带客户端铸造的 id 可供去重，乐观行会与权威行重复。被接受的投递后立即做一次增量轮询，让该行从会话日志落地。

## 后果

对话从 GUI 端到端可达：投递、代理循环、持久表面上的回复，以及卡片的增量轮询；面板只在展开且影子在线时轮询，关闭的面板从不读取。移除手写绑定同时把影子会话从 hierarchy 的限制机制中整体摘出——今后若想限制影子的工具，应走会话工具作用域，而不是角色绑定。再往外一步的地雷仍在：路由器在打开项目时把项目控制器绑成角色 `controller`，Web 部署中这些会话在创建时会撞上同一的全局注册表拒绝；这需要单独决策，此处推迟而非修复。

## 测试

`shadow-agent.host.spec.ts` 在 hierarchy 守卫激活时以无角色绑定创建会话并分发存活的 `shadow_status` 应答，并在种子绑定把 hierarchy 工具面拖入创建时响亮失败。profile 与 loader-composition 套件钉住以 logger-console 开头的九行插入。客户端套件覆盖对话 store（尾部加载、增量轮询、游标回退、失败表面、最新读取所有权）与卡片表面（尾部渲染、空态与离线态、回车提交、逐字失败、展开时的三秒轮询与关闭后无轮询）以及对话 face 的挂载接线。
