# V1.4 C 线核验报告（C1）：Agent 树折叠/单层展开与 SessionID 复制

- 工作树：`D:/dsh-devframe-v14-product-lead`（分支 `codex/v14-product-lead`，只读核验，无 git 写操作）
- 核验范围：`packages/client/ui-workspace`（Agent 树组件、SessionID 复制交互、默认折叠与单层展开）
- 核验方式：源码 file:line 证据 + 三个既有客户端测试实跑

## 一、Agent 树组件定位

| 组件 / 关注点 | 位置 |
| --- | --- |
| 树行派生类型 `AgentNode`（直接子级、最新在前） | `packages/client/ui-workspace/src/client/tree.ts:57-62` |
| 子节点索引与树行构建（parentId 归属、环防护） | `packages/client/ui-workspace/src/client/tree.ts:309-357` |
| Agent 树行组件 `AgentNodeItem` | `packages/client/ui-workspace/src/client/rows/Rows.tsx:598-779`（JSDoc 572-597） |
| 平铺会话行 `SessionNodeItem`（共用菜单/复制 hook） | `packages/client/ui-workspace/src/client/rows/Rows.tsx:445-570` |
| 树容器 `SessionTree`（展开状态、打开子级、目录通告） | `packages/client/ui-workspace/src/client/rows/WorkspaceBrowser.tsx:269-644` |
| 展开状态与 toggle | `packages/client/ui-workspace/src/client/rows/WorkspaceBrowser.tsx:352-359` |
| 行打开时子级地址解析 `openAgent` | `packages/client/ui-workspace/src/client/rows/WorkspaceBrowser.tsx:362-368` |
| 展开行消费子级目录（announce/withdraw） | `packages/client/ui-workspace/src/client/rows/WorkspaceBrowser.tsx:372-398` |
| SessionID 复制 hook / 菜单项 / Toast | `packages/client/ui-workspace/src/client/rows/Rows.tsx:37-45、60-86、89-101` |
| 对应测试 | `packages/client/ui-workspace/tests/agent-tree-rows.client.spec.tsx`、`tests/session-id-copy.client.spec.tsx`、`tests/workspace-browser.client.spec.tsx:1322-1416` |

`packages/client/ui-workspace/README.md:54` 为该面的文档契约：有子级的 Agent 默认折叠并渲染展开箭头，箭头恰切换一层直接下级，行激活打开会话同时切换下级。

## 二、三项现状核验

### A. Agent 树默认折叠 —— 结论：一致

证据：

- `WorkspaceBrowser.tsx:352-354`：注释 "Agent-tree expansion starts collapsed so the sidebar stays compact"，`const [expandedAgents, setExpandedAgents] = useState<string[]>([])` —— 初始为空数组，即所有有子级的 Agent 行默认折叠；状态为浏览器本地瞬态（不持久化）。
- `WorkspaceBrowser.tsx:355-356`：`agentExpanded` 以该数组为展开谓词，仅命中的行渲染下级。
- `Rows.tsx:756-757`：`{expanded && hasChildren && (` —— 展开与否完全由该谓词驱动，初始必为折叠。
- 组装级测试 `workspace-browser.client.spec.tsx:1334-1353`（"starts agent rows collapsed…"）：展开 Workspace 分组后总控行可见而其直接下级 `DSH-G1-Lead` 不可见，且未触发目录通告（`setSubagentCatalogOpen` 未以 true 调用）。

结论：与 README.md:54 "Agents with children render an expand chevron and start collapsed" 及组件 JSDoc（Rows.tsx:575-576）一致，实装存在且有测试锁定。

### B. 箭头仅展开下一层 —— 结论：一致

证据：

- `Rows.tsx:678-690`：仅 `hasChildren` 时渲染箭头按钮（`IconTriangleRightFill14`，`css.arrow` / 展开时 `css.arrowOpen`），无子级行渲染占位 `span`（690 行），即子级行无展开控件（另见测试 `agent-tree-rows.client.spec.tsx:66-71`）。
- `Rows.tsx:684-685`：箭头 `aria-expanded={expanded}`，`onClick` 为 `e.stopPropagation(); onToggle(node.id)` —— 箭头是纯切换，不导航（JSDoc Rows.tsx:578 "the chevron toggles without navigating"）。
- `Rows.tsx:756-776`：展开时仅渲染 `node.children`（直接下一层），每个子行经 `AgentNodeItem` 递归渲染且各自默认折叠；孙级仅在子行自身 id 也进入 `expandedAgents` 后出现。
- `WorkspaceBrowser.tsx:357-359`：`toggleAgent` 按 id 逐个切换（`toggled`，352 行上方 70-72 行的不可变切换），无级联展开全部后代。
- 单层语义测试：`agent-tree-rows.client.spec.tsx:73-136` —— 展开 root 后孙行 `Title executor` 保持隐藏（109-110 行），单独展开 child 后孙行才出现（122 行），收起 root 后整层消失（134-135 行）；组装级 `workspace-browser.client.spec.tsx:1355-1363` 验证箭头一次点击恰好亮出直接下级。
- 附加行为：行激活也切换一层（`Rows.tsx:636-640`：`openRow` 调 `onOpen` 后 `if (hasChildren) onToggle(node.id)`；测试 `agent-tree-rows.client.spec.tsx:138-164` 与 `workspace-browser.client.spec.tsx:1393-1415`），与 README.md:54 的描述一致。

结论：箭头恰切换一层直接下级，实装、文档、测试三者一致。

### C. SessionID 直接复制 —— 结论：一致（存在"操作菜单直复制"路径）；任务询问的三种更直接交互均缺失

证据（现有实现）：

- 菜单项：`Rows.tsx:37-45` `sessionRowMenuItems` 第 43 行 `{ id: 'sessionId', label: t('menu.sessionId'), icon: <IconCopyOutline16 /> }`，Agent 行与平铺行共用（`Rows.tsx:706`、`472`）。
- 复制 hook：`Rows.tsx:60-86` `useSessionIdCopy` —— `writeClipboard(String(sessionId))`（74 行）直写剪贴板，单飞防重（62-63、70-72 行），行卸载使在途结果失效（65-68 行）。
- 结果反馈：`Rows.tsx:89-101` `SessionIdCopyToast` 成功/失败双态，渲染于 `Rows.tsx:565-567`（平铺行）与 `753-755`（Agent 行）。
- 菜单接线：`Rows.tsx:536`（平铺行）、`Rows.tsx:712`（Agent 行）——选中 `sessionId` 菜单项即 `copySessionId()`；不打开会话、无对话框（测试 `session-id-copy.client.spec.tsx:59-67`）。
- ID 可见性：`Rows.tsx:730-740` Agent 行元行以纯文本显示完整 durable id（`title` 属性亦含 id，733 行），可用文本选择手动复制。
- 测试：`session-id-copy.client.spec.tsx:58-122` 共 5 例 —— 直复制完整 id（69-83）、Agent 行同一动作（85-99）、剪贴板被拒时明示失败（101-114）、中英双语词条（116-121）。

证据（任务询问的三种直接交互，均不存在）：

- 无独立复制按钮：ui-workspace/src 内 `writeClipboard` 仅被 `useSessionIdCopy` 使用（grep 全包仅 `Rows.tsx:74` 一处调用）；行上唯一的复制型 affordance 是 HoverCard 的 copy 按钮，但其复制的是行标题而非 id（`Rows.tsx:561`、`749` `copyText={... node.title}`）。
- 无点击复制：行点击语义是打开会话（`Rows.tsx:484`、`636-651`）；id 元行（`Rows.tsx:730-740`）未绑定任何点击处理器。
- 无右键复制：`packages/client/ui-workspace/src` 全目录无 `onContextMenu`/`contextmenu` 处理器（grep 零命中）。

结论：当前 "SessionID 直接复制" = 行操作（省略号）菜单项 → 直写剪贴板 + Toast，与 README.md:40 "Session ID copies the row's full id directly from the actions menu" 及组件 JSDoc（Rows.tsx:5-6、595-596）一致；复制按钮 / 右键 / 点击 id 即复制三种交互不存在。

## 三、缺失项

1. Agent 树行（及元行）上的 SessionID 无独立复制按钮 —— 复制须两跳（打开省略号菜单 → 选"复制会话 ID"）。
2. ID 元行文本（Rows.tsx:730-740）无点击复制行为。
3. 无右键（contextmenu）复制路径。

Agent 树默认折叠（A）与箭头单层展开（B）无缺失。

## 四、可自动测面结论

命令（工作树根目录执行）：

```sh
pnpm exec vitest run packages/client/ui-workspace/tests/agent-tree-rows.client.spec.tsx packages/client/ui-workspace/tests/session-id-copy.client.spec.tsx packages/client/ui-workspace/tests/workspace-browser.client.spec.tsx
```

结果：exit code **0**；Test Files **3 passed (3)**；Tests **61 passed (61)**，0 失败（vitest 4.1.8，Duration 4.82s；stderr 仅 `vite-tsconfig-paths` 弃用提示，不影响结果）。

失败清单：无。

三个目标面均已有可自动测的锁定用例：默认折叠+目录通告（workspace-browser.client.spec.tsx:1334-1372、1393-1415）、箭头单层展开语义（agent-tree-rows.client.spec.tsx:73-136）、菜单直复制成功/失败/双语（session-id-copy.client.spec.tsx:58-122）；"复制按钮/右键/点击复制"的缺失面无负向断言用例（属预期，缺失交互无测试锚点）。

## 五、修复建议

无必须修复项：A、B 与文档契约（README.md:54）完全一致；C 的"菜单直复制"亦与 README.md:40 一致，现有 `useSessionIdCopy`（Rows.tsx:60-86）+ `SessionIdCopyToast`（Rows.tsx:89-101）可整体复用。

可选增强（若 C 线产品目标要求更短复制路径）：在 Agent 行元行（Rows.tsx:730-740）的 id 文本上加挂 `copySessionId` 的点击处理并 `stopPropagation`（避免触发行的打开语义，Rows.tsx:636-651），复用现有 Toast 反馈，同时在 locale 词典补充对应 aria/文案词条（`verify-client-ui-i18n` 约束文案走词典）；右键路径若要做需新增 `onContextMenu`，目前整包无先例，收益存疑，可不作为本项范围。

## 六、四态结论与三层证据分列（组长汇总）

四态（对应 remaining/WORKLIST.md C1 行四列）：

| 子项 | 源码 | profile | 运行 | 生产验收 |
| --- | --- | --- | --- | --- |
| A Agent 树默认折叠 | 存在（一致）WorkspaceBrowser.tsx:352-354 | client 挂载在案 web-app/cordis.patch.yml:246-247（ui-workspace） | 组件级自动化绿 61/61 exit 0（§四） | 技术验收通过；无新增真用户动作 |
| B 箭头仅展开下一层 | 存在（一致）Rows.tsx:678-690、756-776 + WorkspaceBrowser.tsx:357-359 | 同上 | 同上 | 同上 |
| C SessionID 直接复制 | 存在（一致）Rows.tsx:43、60-86、89-101、536/712 + locales.ts:48-50/124-126；契约 README.md:40 | 同上 | 同上（session-id-copy 5 例） | 同上 |

三层证据分列（车道纪律）：

| 层 | 内容 |
| --- | --- |
| ①请求参数 | workflow agent {provider:'huoshan-1', model:'glm-5.3-flash'} |
| ②宿主标签 | c1-report-slice（Worker 673d61fe，落盘本报告）；前置同面只读核验轮 C1-agent-tree-verify |
| ③实际响应 | c1-report-slice：总控侧提取请求级载荷 seq13/14 = huoshan-1/glm-5.3-flash @22:10:44Z（provider 实证以此为准）；C1-agent-tree-verify 回执 61/61 exit 0 |

缺失项处置：§三 三项为超描述增强选项（README.md:40 钉死 actions-menu 直复制为现行契约），总控已采信零缺失、不派修复切片。
