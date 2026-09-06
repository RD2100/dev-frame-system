# C3 复验：模型切换 / 侧栏 / 用量监测

复验对象：分支 codex/v14-product-lead，工作树 D:/dsh-devframe-v14-product-lead（本轮除本报告外未创建/修改/删除任何文件，无 git 写操作）。以下 file:line 均已逐条打开核对，与首轮回执一致，未发现不符。

## 一、三面现状

### 1. 模型切换（双入口，共享 per-session 目录）

- 双入口 A（/model popup）：packages/client/ui-model-selection/src/client/index.ts:126-155 —— `ctx.inject(['commandUi', 'modelDirectories'], ...)` 内 `command.register({ name: 'model', ui: { kind: 'popupSelect', ... } })`（popupSelect 在 L135），options/onSelect 均经 `models.directoryFor(session.sessionId)`；addressed subagent 会话两条路径均显式不可用（L133、137-139、143-145）。
- 双入口 B（composer 座位）：index.ts:158-179 —— `ctx.inject(['slots', 'modelDirectories'], ...)` 内 `scope.slots.inject('conversation.input.model', ...)`（L161），同一 `directoryFor` 解析目录；文件头注释（L1-11）声明双入口共享一份状态，与实现一致。
- 同一 per-session 目录：src/client/service.ts:68-111 —— `directoryFor` 命中即复用（L70-71），新建后写入 `live.directories` Map（Map 声明 L31，写入 L84），由 session scope disposer `dispose()` 并从 Map 删除（L106-109）。
- 单一 SnapshotStore：src/client/directory.ts:39-43 —— `ModelDirectory` 持有唯一 `createSnapshotStore` 的 `store`（L41-43），即两个入口的同一渲染源。
- 适配器阻断/恢复：service.ts:90-105 —— `routable === false` 时向 `conversation.blocks` 推 block（publish L92-97），scope 内订阅 store，清理时恢复为 `undefined`（L98-104）；`routable` 由 directory.ts:166 依 Host 目录 `routableProviders.includes(current.provider)` 计算，`null`（未加载或上次失败）不阻断，避免慢/不可达 Host 锁死可用 composer（L85-89 注释）。
- 事件刷新：service.ts:57-59 —— `llm/adapters-updated`、`settings/document-updated`、`credentials/reference-updated` 三个 Host 事件均触发 `catalog.refresh()`。
- 输入侧消费：packages/client/ui-conversation/src/client/apply.ts:280 —— 座位声明 `'conversation.input.model': { kind: 'single', scope: 'session' }`；skeleton/InputBar.tsx:119-125 —— blocked 参与 `disabled`（L119），model seat 是 block 下唯一保持可用的控件（L121-124 注释 + `modelSeatLocked = removed || inert || !live` L125）；InputBar.tsx:467 以 `{ locked: modelSeatLocked }` 挂载该座位。

结论：双入口单状态、适配器阻断/恢复、Host 事件刷新、输入侧座位消费全部落实，锚点逐条相符。

### 2. 侧栏（折叠/落定/宽内容，冷启动静态 rail，toggle）

- 三态几何：packages/client/ui-sidebar/src/client/SidebarRoot.tsx:52-79 —— `SidebarRoot({ collapsed, width, startSession, toggleSidebar, ... })`；`settled` 由 collapsed 起 `COLLAPSE_SETTLE_MS` 定时器落定（L62-67），`wide = !collapsed || !settled`（L68）；常量 `COLLAPSE_SETTLE_MS = 150` 在 L27，与"匹配 150ms 宽内容淡出"注释一致。
- 冷启动静态 rail：SidebarRoot.tsx:76-79 —— `everWide` ref 初始 `!collapsed`，仅展开过才置 true；SidebarRoot.tsx:129-133 —— className 中 `css.railIn` 仅在 `!wide && everWide.current` 时附加（L130），故刷新直入折叠态时 railIn 不附加、rail 静态渲染（L76-77 注释明确该意图）。
- toggle：SidebarRoot.tsx:171-186 —— 面板图标按钮 `onClick={() => { toggleSidebar() }}`（L176），tooltip/aria-label 按 collapsed 切换，rail 静息态显示品牌标记、悬停切换展开图形（L178-184）。
- 状态源：packages/client/ui-layout/src/client/stores.ts:56-59 —— `toggleSidebar` 动作：窄态翻转 `narrowExpanded` 覆盖位，宽态在 `0` 与 `SIDEBAR_DEFAULT` 间翻转 `sidebar`（宽度偏好不被破坏，L54-55 注释）。

结论：侧栏折叠/落定/宽内容、冷启动静态 rail、toggle 写路径与状态源逐条相符。

### 3. 用量监测（turn 用量 + 会话统计 + 上下文占用）

- turn 用量链路：packages/client/ui-chat/src/client/conversation-nodes/turn-tail.ts:164-166 —— turn/start 匹配时 `deriveTurnTokenUsage(...)`（import 自 `@deepseek-ai/dsh-token-meter/client`，L8）从会话事件推导 `tokenUsage` 并入 tail 数据（L175）→ chat/TurnTailNodeView.tsx:54 —— `data.tokenUsage !== undefined && <TurnUsagePanel usage={data.tokenUsage} t={t} />` → chat/TurnUsagePanel.tsx:99-178 —— 触发按钮 + portal 明细面板（模型路由、缓存命中、未缓存输入/缓存读/缓存写、输出与推理分项）。
- 会话统计：chat/StatsLine.tsx:163-209 —— `StatsLine` 读 `tokenUsage`（L165）与 `sessionStats` 投影（L170，投影缺失时回退窗口内 fold），组 counts/耗时/速度/缓存命中/tokens 行（L173-205），全空则整行不渲染（L207）；上下文占用明确不在此处（L191-192 注释，单一归属 ContextMeter）。
- 上下文占用：packages/client/ui-conversation/src/client/context-occupancy.ts:15-24 —— `contextOccupancy` 从 pressure 投影求 `percent/usedTokens/contextWindow`，分子或容量未知返回 null → skeleton/ContextMeter.tsx:55-167 —— `ContextMeter` 环形读数 + 明细面板，读 `contextPressure`/`contextBreakdown`（L56-57），模型切换致容量暂失时自动收起面板（L63-67）；挂载于 skeleton/InputBar.tsx:468（与模型座位同一行内）。
- 宿主投影（只读引用）：packages/llm/token-meter/src/projection.ts:69-75 —— `SessionProjectionMap` 声明 `tokenUsage`/`contextPressure`/`contextBreakdown`（L71/73/75）；客户端仅经 `useProjection` 只读消费（ui-chat StatsLine 用 `tokenUsage`，ui-conversation ContextMeter 用 `contextPressure`/`contextBreakdown`）。

结论：turn 级用量、会话级统计、上下文占用三条数据流、挂载点与投影来源逐条相符。

## 二、组合挂载证据（profile 态）

四个 client 插件的组合清单在 packages/bundle/web-app/cordis.patch.yml 的浏览器 roster（`dsh.client` 行）节内——位于 L43 起的单一 `- insert:` 块，L156 节注释 "browser plugin roster (dsh.client rows)"；L41-42 注明 `dsh.client` 行即浏览器 roster，node 半部扫入 `window.__DSH_BOOT__` 并按 `/plugins/<id>/client.js` 供包，即 profile 态实际挂载来源：

| 插件 | 组合行（cordis.patch.yml） | 依赖行（packages/bundle/web-app/package.json） |
| --- | --- | --- |
| @deepseek-ai/dsh-client-ui-sidebar | L197-198（`- id: ui-sidebar` / `name: '@deepseek-ai/dsh-client-ui-sidebar'`） | L76 |
| @deepseek-ai/dsh-client-ui-chat | L218-219（`- id: ui-chat` / `name: '@deepseek-ai/dsh-client-ui-chat'`） | L56 |
| @deepseek-ai/dsh-client-ui-workspace | L246-247（`- id: ui-workspace` / `name: '@deepseek-ai/dsh-client-ui-workspace'`） | L86 |
| @deepseek-ai/dsh-client-ui-model-selection | L286-288（L286 注释 "Model selection: the /model popupSelect + composer seat"；`- id: ui-model-selection` / `name: '@deepseek-ai/dsh-client-ui-model-selection'`） | L65 |

旁证与范围核对：

- apps/web/tests/built-boot.expected.e2e.ts:159 断言组装态含 layout/sidebar/conversation/tool 四插件；L165/L169 断言 `exclude` 掉 `@deepseek-ai/dsh-client-ui-chat` 后 boot entries 不含该插件——组装态含 ui-chat 的行为旁证。
- packages/client/web 是 Web boot kernel（静态模块表 + loader），本身不含四插件组合行；六份 bundle patch.yml（acp-app/base/headless/sdk-app/sdk-minimal/web-app）经 grep 全量核对，仅 web-app 引用这四个插件。
- 缺失情况：无。四个插件名在组合清单（patch.yml 组合行 + bundle package.json 依赖行）中均有对应行。

## 三、可自动测面

命令（工作树根目录执行，PowerShell）：

```
pnpm exec vitest run packages/client/ui-model-selection/tests packages/client/ui-sidebar/tests packages/client/ui-chat/tests/turn-usage-panel.client.spec.tsx packages/client/ui-chat/tests/chat-stats.client.spec.tsx packages/client/ui-conversation/tests/context-meter.client.spec.tsx
```

- exit code：0（无失败标记）。
- 通过数：Test Files 12 passed (12)，Tests 101 passed (101)；Duration 5.31s。
- 覆盖：ui-model-selection/tests 3 个 spec（browser-plugin / catalog / model-select）、ui-sidebar/tests 6 个 spec（apply / pointer-scrollbars / scrollbar-quiet-styles / sidebar-root / sidebar-snapshot / sidebar-styles）、ui-chat 2 个（turn-usage-panel / chat-stats）、ui-conversation 1 个（context-meter）。
- 失败清单：无。

## 四、缺陷与最小修复建议

首轮回执与本轮复验均未发现缺陷：三面锚点 file:line 逐条相符，组合挂载四行齐全，聚焦测试全绿。无修复项。

补充观察（非缺陷）：

- 适配器阻断仅由 Host 明确报告的 `routable === false` 触发，`null`（未加载/失败）不锁 composer——与 InputBar.tsx:121-124 的注释契约一致。
- bundle 清单中 `ui-schedule` 行带 `disabled: true`（cordis.patch.yml:269-271），与本报告四插件无关，仅说明 roster 支持显式禁用行。

## 五、四态结论与三层证据分列（组长汇总）

四态（对应 remaining/WORKLIST.md C3 行，三子面同态）：

| 态 | 结论 |
| --- | --- |
| 源码 | 存在（一致）：模型切换 §一.1、侧栏 §一.2、用量监测 §一.3 全部 file:line 锚点逐条相符 |
| profile | client 挂载在案：ui-model-selection web-app/cordis.patch.yml:286-288、ui-sidebar :197-198、ui-chat :218-219（§二；ui-workspace :246-247 旁证 C1） |
| 运行 | 组件级自动化绿：12 files / 101 tests，exit 0（§三） |
| 生产验收 | 技术验收通过：无缺陷（§四）；无新增真用户动作 |

三层证据分列（车道纪律）：

| 层 | 内容 |
| --- | --- |
| ①请求参数 | workflow agent {provider:'huoshan-1', model:'glm-5.3-flash'} |
| ②宿主标签 | C3-model-sidebar-usage-verify（首轮核验）+ c3-report-slice（复验并落盘本报告） |
| ③实际响应 | 两轮回执均自报 unknown（无自证能力）——provider 实证待总控侧按会话日志 request/header+context 载荷提取回填；model=glm-5.3-flash 为运行时声明；测试首轮 92+9、复验 101/101 均 exit 0 |

缺失项处置：无缺失项（零缺陷），不派修复切片。
