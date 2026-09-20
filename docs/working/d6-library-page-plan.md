# D6 开发计划：库管理页 + Memory Remote

状态：**待审核**（先经子 agent 审核通过后执行）
关联：docs/working/desktop-product-delivery.md · 任务表 D6
日期：2026-09-18

## 1. 目标

在官方 Desktop 客户端交付「记忆库」管理能力，分两层：

- **Memory Remote**：host 侧 `library` 命名空间，通过 typert Remote 把只读 Obsidian Vault 的浏览操作暴露给 Web UI（快照 / 状态 / 列表 / 预览 / 搜索 / 绝对路径）。
- **库管理页面**：侧边栏「记忆库」入口 + 卡片，支持文件列表、内容预览、搜索、复制绝对路径、插入会话引用；无 Vault 配置时显示 UNAVAILABLE 空态且不崩溃。

D6 验收口径（来自交接文档）：listing / preview / search / paths / references。不包含"最近访问"（无埋点数据源）与"Vault 选择"（属于部署配置，不在 UI 范围）。

## 2. 设计与范围

### 2.1 Host：Memory Remote（project-memory 包）

- `src/client.ts`：client-safe DTO —— `MemoryLibrarySnapshot` / `MemoryLibraryListRequest` / `MemoryLibraryReadRequest` / `MemoryLibraryReadResult` / `MemoryLibrarySearchRequest`，复用并再导出 `library.ts` 的 `LibraryFile` / `LibrarySearchResult` / `LibraryStatus`。
- `src/gateway.ts`：`MemoryLibraryGateway extends TypertRemoteService`，`super(ctx, 'memoryLibraryGateway', { namespace: 'library' })`，5 个 `@Remote` 方法：
  - `view()` → 状态 + 文件列表快照
  - `status()` → 状态
  - `list({ maxDepth? })` → 文件列表
  - `read({ relativePath })` → 内容 + **真实绝对路径**（copy 目标，read 校验通过后才计算）
  - `search({ query, maxResults? })` → 命中列表
- 无 Vault 配置时：gateway 照常挂载，`status`/`view` 返回 UNAVAILABLE 空态，文件类方法抛 `MEMORY_UNAVAILABLE`（fail-closed）。
- `plugin.ts`：构造并挂载 gateway（同 expert-team 的 fiber 注册方式）。
- `package.json`：新增 `./typert`、`./remote`（精确成对）、`./client`（**types-only**，指向 `lib/types/client.d.ts`，避免分析器把浏览器入口纳入导出图）；`files` 精确匹配 `check-workspace-constraints` 的期望清单。
- 生成物：`pnpm run gen-typert`（typert.host + typert.remote-client）；`gen-cordis-catalog` 的 `SERVICE_PAGE` 加 `memoryLibraryGateway → project-memory.md`、`TYPE_LINK_EXEMPTIONS` 加 9 个新类型。

**已完成（本计划提交时已落地，待审核确认）**：client.ts / gateway.ts / plugin 挂载 / package.json / typert 与目录生成 / gateway.spec.ts 11 测试（全包 111 通过）/ tsc 通过。

### 2.2 Client：client-ui-project-memory 包（新建）

镜像 `client-ui-expert-team` 的包结构：

- `package.json`：`@deepseek-ai/dsh-experimental-client-ui-project-memory`，`dsh.client.inject` 含 remotes/locale/slots/ui-conversation/ui-primitives/ui-session/ui-sidebar/ui-workspace/project-memory；`/remote` **不**列入 external（GENERATED_REMOTE 规则内联，无 module-table 行，构建可复现）。
- `src/client/index.ts`：`apply()` 入口，调用 `mountLibraryUi(ctx, memoryLibraryRemote)`。
- `src/client/mount.ts`：`ctx.remote.$mount(contribution)` + `ctx.inject(['remote.library','slots','locale','conversation','sessions','uiWorkspace'], registerUi)`；注册 `sidebar.footer.action` seat `id: 'project-library', order: 25`（专家 20 之后、影子 30 之前），locale 注册 `NS = 'library'`。
- `src/client/LibraryCard.tsx` + `.module.css`：快照加载（view）→ 状态区（可用/Vault 路径/文件数；UNAVAILABLE 空态）→ 搜索框（search）→ 文件列表（list，展开深度）→ 预览面板（read，Markdown 文本 + 绝对路径）→ 行操作「复制路径」与「引用到对话」。
- `src/client/reference.ts`：引用控制器 —— 复制绝对路径（`navigator.clipboard`）；「引用到对话」把路径追加到当前会话 composer draft（`ctx.conversation.input.for(scope).setDraft(existing + '\n' + ref)`），不新建会话、不覆盖用户已有输入。
- `src/client/locales.ts`：zh/en 双语字典，`declare module '@deepseek-ai/dsh-client-ui-slots'` 合并 `LocaleNamespaceMap`。
- `tests/library-card.client.spec.tsx` + `tests/mount.spec.ts`：镜像 expert-team 的 client 测试 bench。
- tsconfig.json（引用 client 依赖 + `../project-memory`）、tsdown.config.ts（clientBundle）、css-modules.d.ts。

### 2.3 接线

- `packages/experimental/devframe-profile/cordis.patch.yml`：新增 `ui-project-memory` 浏览器行。
- `tsconfig.base.json` / `tsconfig.client.json`：paths 与 project reference。
- `pnpm-lock.yaml`：workspace 依赖更新（pnpm install）。

### 2.4 验证与交付

1. 聚焦测试：新包 client 测试 + project-memory 全包回归。
2. 覆盖率门 `test:coverage`（每文件 100%）。
3. `tsc -b`（host + client 两 face）、`oxlint`、`check-workspace-constraints`、`hygiene`。
4. 文档：project-memory README（中英）补 Remote 说明；`docs/working/desktop-product-delivery.md` 更新 D6 状态。
5. 桌面冒烟：staging profile 在官方 host 真实加载，验证 RPC `library/view` 200 与侧边栏入口。

## 3. 明确不做（防范围蔓延）

- 不引入"最近访问"跟踪（无数据源）。
- 不做 Vault 切换 UI（vaultRoot 属部署配置）。
- 不写库（Vault 是只读真相源；编辑/写入留给后续迭代，D6 验收不含编辑）。
- 不触碰 D7（技能/连接器管理）与 D8（定时任务中心）。

## 4. 验收标准（子 agent 审核与验收共用）

- **P0 功能**：侧边栏出现「记忆库」（order 25，图标文案齐）；打开后展示状态 + 文件列表；预览可读内容；搜索命中；复制绝对路径正确（真实盘上路径）；「引用到对话」把路径追加进当前 composer 且不覆盖原草稿。
- **P0 安全**：无 Vault 时 UNAVAILABLE 空态、无异常弹窗；`../` 穿越路径被拒（MEMORY_PATH_REJECTED）；Remote 全 fail-closed。
- **P1 质量门**：新代码单测覆盖（client 包 + gateway）、覆盖率门通过；tsc host/client、oxlint、workspace-constraints、hygiene 全绿；typert/catalog 再生成无 diff。
- **P1 一致性**：包结构/命名/双语文档/座位序与 expert-team、shadow 既有模式一致；交接文档 D6 状态更新。

## 5. 风险与备注

- 模型供应商欠费（用户侧）：库管理为纯文件 + UI 操作，不依赖模型，D6 不受影响；影子/专家可用性待用户续费。
- `./client` types-only 导出是新模式（expert-team 用 bundle + 手工 d.ts 追加，不可复现）：本计划改走 `/remote` 内联 + DTO types-only，构建全自动可复现；若 `verify-client-packages` 等门禁不认，按门禁要求回退到 expert-team 形态。
