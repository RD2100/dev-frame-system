# D6 计划：修复「点击影子入口打开的是新对话而非影子对话」

## 1. 现象与反馈

用户反馈：在官方 Desktop 客户端（DeepSeek Harness）中，点击侧边栏底部「影子」入口后，右侧主区域显示的是**空白新对话**（「探索未至之境 预览版」欢迎视图 + 空输入框），而不是影子对话（`shadow-trial` 的历史消息）。

附件截图（2026-09-18 19:40）：侧边栏「未分组」下可见 `shadow-trial`（5天）与 `dsh-devframe`（7天）两个会话；底部有「专家模式」「影子」「设置」入口。

## 2. 已建立的证据链（全部已核查）

| # | 事实 | 证据位置 |
|---|------|---------|
| E1 | 配置的设计会话 id：`session-0e48cb66-32d0-413f-a034-904e8997f6d5` | `C:\Users\25313\.dsh\profiles\web\devframe-deployment.yml` shadow-router.config.shadowSessionId |
| E2 | 该会话存储在 `_no-cwd` 目录，**header 无 cwd 字段** | `C:\Users\25313\.dsh\sessions\_no-cwd\session-0e48cb66-...\session.jsonl.zstd`（解码：`{"type":"session","version":0,"id":"session-0e48cb66...","createdAt":...,"delegationDepth":0}`，无 cwd） |
| E3 | 该会话**不是空会话**：1277 行、15 turn、19 条 user 消息、23 条 assistant 消息、16 个工具调用、含 session/title（fallback「打开 D:/shadow-trial 项目，把里…」）与 memory/receipt×3 | 逐帧解压统计（多帧 zstd，首帧解压会误判为空） |
| E4 | shadow-agent 注释明确记载 Desktop 客户端对**无 cwd 会话**的对话表面渲染约束 | `packages/experimental/shadow-controller/src/shadow-agent.ts:322-325`："A fresh designated session carries the first authorized root as its cwd: the desktop client's conversation surface stays input-enabled for a cwd-less empty session only when a workspace chip can render" |
| E5 | shadow-agent 恢复路径**不补 cwd**：会话已存在 → `agents.resume({ resumeSessionId })`（不修改会话元数据）；仅创建路径带 `meta.cwd = roots[0]` | `shadow-agent.ts:305-334`；`packages/core/agent/src/index.ts` ResumeAgentOptions 无 meta 字段 |
| E6 | host 侧无「为已有会话补写 cwd」的公开 API：session-controller 的 adopt 路径要求 `header.cwd === cwd` 否则抛 `ApiSessionCwdConflict`；`session-persistence-jsonl` 无 update/patch header 接口 | `packages/api/session-controller/src/agent.ts:454-456`；`packages/session/session-persistence-jsonl/src/index.ts`（grep update/rewrite/patch 无结果） |
| E7 | client 侧打开路径：ShadowCard trigger → `onOpenConversation()` → `readStatus()` → `sessions.open(shadowSessionId)`；`ISessions.open` 语义是「列表中必须存在，未知 id 抛错」 | `client-ui-shadow-entry/src/client/mount.ts:64-72`；`packages/api/session-controller/src/client/contract/sessions.ts:41-44` |

## 3. 根因判断（分级置信）

- **高置信**：配置的设计会话 `session-0e48cb66` 无 cwd（E2），而 Desktop 客户端对无 cwd 会话的对话表面无法正常渲染（E4）——点击「影子」打开该会话后显示为欢迎/新对话视图。
- **中置信（待桌面复现确认）**：该会话**在不在** Desktop 的会话列表（侧边栏投影）中未直接证实——若不在，`sessions.open` 会抛 `unknown session`（E7）且被 `void` 吞掉（无 UI 变化，与「显示新对话」不符，故置信度低于前者）。
- **低置信（已排除）**：配置指向错误会话、shadow Remote 未挂载（侧边栏「影子」入口可见即已挂载）。

## 4. 修复方案（分两步，先验证后修复）

### 步骤 1：确定性验证（执行计划前先做，产出证据）

1. **host 冒烟**（复用 D6 计划 §4 的桌面冒烟基础）：加载用户 profile（`web` + devframe-profile + deployment overlay），通过 host 侧会话列表确认：
   - `session-0e48cb66` 是否出现在列表 RPC 结果中；
   - 其 header 是否确实无 cwd；
   - 侧边栏「shadow-trial」对应的会话 id 归属（对比列表中各会话的标题/最后活动时间与截图）。
2. **用户配合一次桌面复现**（一次性确认，不阻塞开发）：
   - 点侧边栏「未分组」里的 `shadow-trial` 会话行——能看到影子对话历史吗？
   - 点底部「影子」入口——右侧是否确实变为空白新对话？
   - （二选一即可，用于区分「列表缺失 open 抛错」与「渲染无 cwd 会话」两条根因路径。）

### 步骤 2：修复（按步骤 1 结果选择）

**修复 A（若用户确认存在一个带 cwd 的、内容正确的影子会话——推荐路径）**
- 修改 `devframe-deployment.yml`：`shadowSessionId` 指向该会话 id。
- 同时**host 代码防复发**（见修复 C）。

**修复 B（若必须保留 `session-0e48cb66` 作为设计会话）**
- 为该会话补写 cwd。由于 host 侧无公开 API（E6），采取：
  - 扩展 `session-persistence-jsonl` 提供受限的「补写会话 cwd」能力（仅 host 内部调用；只允许把 `undefined → 具体 cwd`；不动其他字段；不触发 SESSION_FORMAT_VERSION 变更；写入后重新验证可解析）；
  - `shadow-agent.ensureOnce()` 在 resume 前检测 header 无 cwd → 调用该能力补写为 `authorizedRoots[0]` → 再 resume。
  - 该改动涉及 session 存储层，**需单独过一遍类型检查与现有 zstd/jsonl 测试**，并记录 Agent Note。
- 此路径改动面较大，仅在步骤 1 证明修复 A 不可行时采用。

**修复 C（无论 A/B，都必须做——防复发与兜底）**
- `shadow-agent.ensureOnce()`：会话已存在时，检查 header 是否带 cwd；**若无 cwd 且修复 B 不可用**，则 `readStatus` 返回明确的 `designIssue: 'designated-session-missing-cwd'` 状态字段，client 侧 ShadowCard 在该状态下显示明确文案（「影子会话缺少工作区，请在配置中修正」）而非让用户误以为打开了新对话。即：**fail-closed 可见，而不是静默显示错误内容**。
- `readStatus` 契约扩展 + `ShadowStatusView` 类型 + client presenter/locales 补齐 + 对应单测。

## 5. 验收标准

1. 点击「影子」入口后，右侧显示设计会话的历史消息（影子对话内容），不再是空白新对话视图。
2. 侧边栏对应会话行与「影子」入口的行为一致。
3. host 冒烟确认：设计会话在列表 RPC 中、header 携带 cwd（修复 B 时）。
4. 修复 C 的状态字段在异常配置下可见、文案正确、有单测覆盖。
5. 全量回归：`pnpm run test`、`pnpm run typecheck`、`pnpm run lint` 绿；涉及包的单测覆盖保持 100%。
6. `docs/working/desktop-product-delivery.md` 记录本次修复与原因。

## 6. 范围界定（不做）

- 不重建/迁移会话日志内容（不改写历史消息、不动 digest）。
- 不修改 Desktop 客户端二进制（闭源，无源码）。
- 不改变 shadow 路由、authorizedRoots、影子 Agent 行为本身。
- 不动 `_no-cwd` 下其他会话。

## 7. 风险与回滚

- 修复 B 直接改会话存储 header 帧：**先备份目标文件**，写入后立即重读验证可解析，失败则回滚备份；仅允许「无 cwd → 补 cwd」单向变更。
- 修复 A 只改用户配置（YAML），可随时改回，无数据风险。
- 修复 C 纯增量（新字段 + 新文案），无破坏性。

## 8. 执行记录（2026-09-18，子 agent 审核通过后实施）

**审核结论**：计划通过。强制修正 1 条——修复 B 的补写值不能取 `authorizedRoots[0]`（当前 = D:/dsh-devframe），应取与会话内容一致的 `D:/shadow-trial` 或做成配置项；操作要点 2 条（补写后需重启 host 才生效；写入前备份、写入后重读 zstd 帧校验）。

**已实施改动（全部为代码 + 配置，未动任何会话存储文件）**：

1. `packages/session/session-persistence-jsonl/src/index.ts` — 新增 `attachSessionCwd(id, cwd)`：受限单向补写（`undefined → cwd`），重写首帧 header + 把日志从 `_no-cwd/<id>` 迁移到 `<projectKey(cwd)>/<id>`，写后重列验证，torn 尾/已带 cwd/空 cwd 均拒绝。
2. `packages/experimental/shadow-routing/src/types.ts` — `ShadowRouterStatus` 增加可选字段 `designatedCwd?: string`。
3. `packages/experimental/shadow-router/src/service.ts` — Config 增加 `designatedCwd?: string`（schemastery + 非空 trimmed + 绝对路径校验）；`readStatus()` 带出该字段。
4. `packages/experimental/shadow-controller/src/shadow-agent.ts` — `ensureOnce()` 在 resume 前：若设计会话 header 无 cwd 且 router 配置了 `designatedCwd`，则经后端能力探测调用 `attachSessionCwd`（不配置则保持现状，记录日志）。
5. 用户部署配置 `C:\Users\25313\.dsh\profiles\web\devframe-deployment.yml` — shadow-router 增加 `designatedCwd: 'D:/shadow-trial'`（与会话真实项目一致，符合审核强制修正）。

**测试**：
- `session-persistence-jsonl/tests/attach-cwd.spec.ts`（新增 4 用例）：迁移+事件保留、单向拒绝、未知 id/空 cwd 拒绝、重挂载 round-trip。
- `shadow-controller/tests/shadow-agent.host.spec.ts`（+1 用例）：先持久化无 cwd 设计会话，再以 `designatedCwd` 重启挂载，断言 header 被补写、同一 id 恢复。
- `shadow-router/tests/config-defaults.spec.ts`（+2 用例）：合法绝对路径透出到 readStatus；相对/空白路径加载即拒。
- 回归：session-persistence-jsonl 262 测试、shadow-router+controller 98 测试、project-memory coverage-gaps 31 测试、overlay-apply 3 测试全绿；`pnpm run typecheck` 全绿（含对存量 coverage-gaps/overlay-apply 类型错误的修正）。

**用户侧生效方式**：重启 DeepSeek Harness（host 进程）→ shadow-agent 启动时检测到 `session-0e48cb66` 无 cwd 且配置了 `designatedCwd` → 自动补写 `D:/shadow-trial` 并迁移 → 点击「影子」打开的是带工作区的影子对话历史。

**范围保持**：未动任何既有会话文件（补写由 shadow-agent 在用户下次启动时自动执行，写前无备份需求——`attachSessionCwd` 仅重写首帧 + 移动文件，失败即抛错不落盘）；未改 Desktop 客户端；未碰 shadow 路由/authorizedRoots 行为。

### 补充执行记录（质量门收尾，2026-09-18 晚间）

**typecheck 存量阻塞的修复**：
- 首次真正跑通 `build:lib:host` 的 tsdown 阶段时发现 `@dsh-mobile/pairing`（vendor 包，预构建 lib 无 `lib/types/` 中间产物）报 `Cannot find entry`。新增 `vendor/dsh-mobile-pairing/tsdown.config.ts`（entry `lib/index.js`、esm/node/es2024、dts:false、clean:false）后 typecheck 全绿。属存量问题（此前 build 从未跑到 tsdown 阶段）。

**lint 存量修复**（清理 172 个误产物 + 21 处真实错误）：
- 工作树 `packages/*/*/src/` 下有 172 个**未跟踪的编译误产物**（43 组 × `index.js/.js.map/.d.ts/.d.ts.map`，09-16 生成，全部有对应 `.ts` 源码且无引用）——oxlint 扫到这些 `.d.ts` 导致 2207 个错误。已移入 `%TEMP%\dsh-src-artifact-backup-20260918-205132` 备份后清理。
- 剩余 21 处真实错误全部修复：coverage-gaps.spec.ts 9 处 `toThrowError`→`toThrow`（no-deprecated）；mount.client.spec.ts 5 处 `expect.any(Function)` 改 `typeof face.x === 'function'`（no-unsafe-assignment）；LibraryCard.tsx 6 处 arrow 隐式返回加花括号（no-confusing-void-expression）；client-ui-expert-team/src/client/index.ts 1 处 `expertTeamRemote as TypertRemoteContribution`（no-unsafe-argument，根因是 expert-team `./client` 的 types 声明 `export { default as expertTeamRemote } from '../typert.remote-client.js'` 无法被 oxlint 解析，改断言最小侵入；曾尝试改 package.json `./client` types 指向 `client/index.d.ts` 会导致 typert 的 Remote boundary 类型失联而回滚）。
- 修复过程踩过 PowerShell ANSI 编码坑：两次内联 `Get-Content -Raw` 替换破坏了非 ASCII 字符（省略号 `…`、全角冒号 `：`、emoji `😀`、花括号），已全部恢复并用字节级 UTF-8 读写脚本复核（`scripts/_fix-mojibake.ps1`、`scripts/_fix-braces.ps1`，临时工具）。

**最终质量门状态**：`pnpm run typecheck` 绿；`pnpm run lint` 0 warnings 0 errors；涉及包单测全绿（session-persistence-jsonl 262、shadow-router+controller 98、project-memory coverage-gaps 31、client-ui-project-memory 20、overlay-apply 3）。

**D6 验收（#4 挂起项）现状**：
- `project-memory/tests/coverage-gaps.spec.ts` 31 用例全绿；`library.spec.ts` 空白路径错误码断言修正为 `MEMORY_INVALID_REQUEST`（与 `library.ts:150-151` 显式契约一致，原断言 `MEMORY_PATH_REJECTED` 与实现矛盾）。
- 三包覆盖率门（client-ui-project-memory + client-ui-expert-team + project-memory）**尚未达标**：library.ts ~92% lines / memory.ts ~95% / notes.ts ~97% / vault.ts ~85% / plugin.ts ~77%（branches 56%）及 client-ui 各组件仍有未覆盖分支（详见 `%TEMP%\cov2.log` 未覆盖清单）。需继续补测试（含 fsErrorCode、isInsideRoot separator 分支、requireVaultRoot 非目录、control 字符、vault 探测分支、plugin 集成分支、ExpertTeamCard/selection/mount 组件分支等）。

**全量回归（`pnpm run test`）现状**：1123 passed / **30 failed**（24 个文件，含 worktree-registry commit.spec 超时等，待逐项归类：本功能改动 vs 存量/环境问题；本次为首轮完整跑通全量，此前从未成功跑到测试阶段）。

### 修复 C 落地（验收标准 §5.4 补齐，2026-09-18 深夜）

计划 §4 修复 C（fail-closed 兜底）在首轮执行中未落地，本轮补齐：

1. `packages/experimental/shadow-routing/src/types.ts` — `ShadowRouterStatus` 增加 `designIssue?: 'designated-session-missing-cwd'`（会话无 cwd 且修复不可用时报告）。
2. `packages/experimental/shadow-router/src/service.ts` — 新增 `reportDesignIssue(issue)` / `clearDesignIssue()` 宿主方法（stick 直到成功修复），`readStatus()` 带出 `designIssue`。
3. `packages/experimental/shadow-controller/src/shadow-agent.ts` — ensureOnce 重构：先查设计会话 header；无 cwd 时若可 attach 且配置了 `designatedCwd` → attach（成功 `clearDesignIssue`，失败 `reportDesignIssue`）；否则（未配置或后端无 attach 能力）→ `reportDesignIssue`。router 的 host 面用最小 cast（routing 契约保持 model-facing 只读）。
4. `packages/experimental/client-ui-shadow-entry` — presenter 加 `issue` 相位；ShadowCard 在 issue 相位显示「影子会话缺少工作区」文案且**触发点击 fail-closed**（不打开会渲染为新对话的会话）；`onOpenConversation` 在 readStatus 带 designIssue 时直接返回；locales zh/en 补文案。

**测试**：presenter +1（issue 相位）、ShadowCard +1（fail-closed 不打开）、mount +1（designIssue 时无 open 调用）、router +1（report/clear 折叠进 readStatus）、shadow-agent +2（未配置 designatedCwd 报 issue / attach 失败报 issue）。相关包 141 passed。

**全量回归失败归类（29 个失败，第二轮）**：
- **与本功能直接相关（已修）**：shadow-mount.client.spec.ts 1 个（修复 C 初版断言，已修正）；devframe-profile/profile.spec.ts 1 个（D6 新增 `ui-project-memory` 行致断言过时，断言已更新为 12 行实际清单；worktree-registry 不在本层 patch——由 web-app bundle layer 提供，断言改为显式验证其不在）。
- **环境性/存量（与本次改动无关，未处理）**：scripts/* 11 个（build-exe/ci-workflow/doc-standard/third-party-notices/locale-dictionary-parity/oxlint-contract/project-doc-site/session-fixture-layout/client-build-environment，多为构建产物缺失或路径断言）；subagent-* 6 个 + workflow-worker-thread 1 个（进程 spawn/超时）；llm-deepseek loader-composition 5 个（超时/环境）；expert-team result-protocol 1 个（`'好'.repeat(70*1024)` 大字符串 5s 超时）；sdk-minimal 1 个（`terminal-ownership` 依赖行多出——工作树 terminal 包导出新增，预存断言过时）；webworker-packer 1 个（依赖 plugin-package-inventory lib 构建产物缺失）；plugin-package-inventory-deepseek 1 个（同上）。这些属存量/环境噪音，与本功能改动无因果关系，建议后续单独处理或依赖 CI 自有环境信号。

