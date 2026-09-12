# Agent Note: The Shadow trigger opens the designated session

Status: implemented

[English](2026-09-11-shadow-trigger-opens-designated-session.md) | 中文

## 问题

侧栏影子入口需要一个没有歧义的去处，而两种实现都背离了人类的意图：自制弹窗聊天面板不是产品的对话界面；每次点击新建会话的触发器则会在会话列表里堆出未分组的「新对话」行。影子是一个永久独立的代理，因此它的入口就是那个代理唯一的常驻对话，由主聊天使用的同一个界面渲染。

显而易见的接线——触发器触发时由客户端创建指定会话——不可能成立。宿主在启动时经代理路径创建指定会话，而代理创建的会话不记录 `cwd`；`session/create` RPC 的收编路径要求已存在会话记录的 `cwd` 与请求匹配，因此它总是返回 `session/conflict`（"records no cwd and cannot be adopted"）。于是对指定 id 调用 `create()` 的客户端每次点击都失败，而即发即忘的 `void onOpenConversation()` 吞掉拒绝——在人类看来就是按钮毫无反应。

## 决策

触发器通过标准会话界面打开影子的指定会话。`onOpenConversation` 读取 `shadow/readStatus`，取 `shadowSessionId`，在该 id 尚未列出时刷新宿主权威的会话列表，再调用 `sessions.open(id)`；它绝不调用 `sessions.create`，因为打开是代理创建会话唯一正确的路径，而 `refresh()` 覆盖宿主尚未发布该 id 的启动竞速。卡片把面板保留为触发器旁「管理」按钮背后的二级界面（仅宽侧栏）；面板以对话视图为主，项目管理视图收在切换键之后。

## 落选的备选

**把自制弹窗聊天面板留作触发器的去处。** 否决：影子必须与主聊天在同一个对话界面中渲染；一个纯文本行加轮询的自制面板是另一种产品，人类明确拒绝。

**每次点击都新建一个会话。** 否决：它在会话列表里为每次点击产生一个未分组的「新对话」行，且每个这样的对话都是空的——与「一个永久代理」正好相反。

**让触发器指向带完整历史的既有指定会话。** 否决：人类要求重开一个指定对话，因此部署的 `shadowSessionId` 被重置而非复用。

**调用 `sessions.create({ sessionId })` 并把冲突当作重试信号。** 否决：对代理创建的会话而言，该冲突是确定性的而非瞬时的，重试永不可能成功；`open` 才是正确路径，`refresh` 只覆盖列表竞速。

**在宿主侧为指定会话记录 `cwd`，使 `create` 可以收编它。** 推迟而非否决：那会让 `create` 可行，但打开一个既有会话才是永久对话的诚实操作，且无需改动宿主，因此宿主侧 `cwd` 缺口仍是独立决策。

## 后果

点击影子永远落在同一个常驻对话上，会话列表也不会因点击而增加行。把指定会话本身挡在会话浏览器之外，属于伴随本改动的[内部会话分类](2026-09-11-internal-session-classification.zh.md)。一次失败的 `open`——状态读取失败，或状态未指定会话——会让触发器看起来毫无反应，即发即忘的调用只在控制台呈现拒绝，因此面向用户的错误呈现仍待补。

## 测试

`shadow-mount.client.spec.ts` 钉住 `onOpenConversation` 的四条路径——状态 ok 且已列出（仅 open）、状态 ok 且未列出（先 `refresh` 再 `open`）、状态读取失败、状态未指定会话——并断言绝不发生 `sessions/create` 调用。`shadow-card.client.spec.tsx` 钉住触发器点击到达 `onOpenConversation` 以及管理按钮打开面板。

## 相关

[从 Web 卡片抵达指定影子的对话](../bug-fix/2026-09-10-shadow-conversation-reachability.zh.md) 拥有面板与标准界面读写的对话面。
