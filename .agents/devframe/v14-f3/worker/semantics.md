# v14-f3 GAP F3 语义核实报告：persistent pwsh 与基座原生 pwsh 双注册撞车

任务：v14-f3-w1-semverify（父任务 v14-f3-proposal）。工作树 `D:/dsh-devframe-v14-f3-w1`，基点 `c93b86c43e0a7fa9c5720ea70575241b0c990a22`。所有行号以该树为准；标注"未核实"的条目除外。

## 1. (a) 基座原生 pwsh 工具的注册/替换/冲突语义

### 1.1 `ctx.tools.register()` 完整语义

`packages/core/tools/src/index.ts:1028-1053` 是唯一注册入口，行为分四段：

1. **形状校验**（1030-1041）：`output { schema, render, presentationMeta? }` 缺失或非函数抛 `TypeError`；`output.schema` 必须是受支持 JSON Schema；`timeoutMs` 必须为正有限数。
2. **保留名**（1045-1047）：`run_code` 无条件保留给 PTC 模式传输层，任何 scope 都不得注册或 shadow。
3. **写入**（1048-1052）：`this.layers.effect(ctx, layer => layer.tools.insert(name, definition), { label: 'tools.register()' })`。
4. **返回值**：`ctx.effect()` 返回的精确 disposer（`@returns the exact disposer that unregisters the tool`，1026）。

**重名行为**：`packages/core/tools/src/index.ts:719-721`（`ToolLayer` 构造器）为 `NamedEntries` 注入 duplicate 诊断；两条文案分别是——

- 全局层（`scope === undefined`）：`tool "<name>" is already registered (for a per-agent variant, register through that agent's `agent.ctx` instead)`（720）
- 某个 scope 层内：`tool "<name>" is already registered in this scope`（721）

实际抛出点在 `packages/core/scope/src/store.ts:43-54`（`NamedEntries.insert`）：`if (data.has(name)) throw this.duplicateError(name)`——**同名即抛，无任何替换、幂等或合并路径**；成功插入返回幂等 undo（47-53），只删自己那一条。类文档（store.ts:23-29）明确这是"caller-owned duplicate diagnostics"的唯一命名表。

**scope 规则**：

- 注册解析 scope 的依据是调用方的 ctx：`ScopedLayers.effect` 先 `scopeOf(ctx)`（store.ts:231），`undefined` 写入全局层（236-237），否则写该 scope 的专属层（238-247，层不存在才创建，失败回滚 249-255）。
- 可见性：scoped 条目 shadow 全局同名条目，沿 scope 链"最近的 scope 赢"（`ScopedLayers.merge`，store.ts:208-217；JSDoc 见 `index.ts:1022-1024` "Scoped tools shadow globals; duplicates within one layer and the reserved `run_code` name fail"）。
- **重名检查是逐层（per-layer）的**：全局层与 agent scope 层各有一张 `NamedEntries`（`ToolLayer` 每 scope 一张，`index.ts:707-722`；`ScopedLayers.scoped` 为 `Map<ScopeKey, L>`，store.ts:163）。跨层同名不抛错，语义是 shadow——这是 (d) 对照面成立的关键。
- `tools.restrict()` 只允许 scoped ctx 调用（`index.ts:1062-1066`），佐证"作用域属于 agent 侧"的分工。

**disposer 与归属 fiber**：`ScopedLayers.effect` 把 undo 绑进 `ctx.effect(...)`（store.ts:233-263）；Cordis 侧契约是"effect body 立即执行，disposer 在 fiber 卸载时（或手动调用时）运行"（`vendor/cordis/src/fiber.ts:402-410`）。所以注册发生在**插件激活（apply）= 加载期**，注销跟随注册 fiber 的生命周期——这正是 spec 里 "unregisters on fiber dispose (HMR safety)" 的机制。

**替换/幂等路径：不存在。** `register()` 只有 `insert` 一条写路径（index.ts:1048-1052），`NamedEntries` 无 replace API（store.ts:30-105 全部公开成员为 insert/get/has/keys/entries/values/isEmpty）。未核实到任何"已存在则跳过/覆盖"分支。

### 1.2 spec 断言

`packages/core/tools/tests/tools.spec.ts:1984-1996`：

- 1986-1987：同名二次 `ctx.tools.register(echoTool)` 抛 `'already registered'`——**重名抛错是测试钉死的行为契约**。
- 1989-1995：经 `ctx.plugin(...)` 挂载的子 fiber 注册后随 `fiber.dispose()` 注销——HMR 安全断言。
- 1998-2007：`register()` 返回的 disposer 单独可调用、幂等。

### 1.3 两个插件都从 apply()（激活期）在根 ctx 上注册 `pwsh`

- 原生：`packages/shell/tool-pwsh/src/index.ts:194`（`export function apply`）→ `250-251` `ctx.tools.register(defineTool({ name: 'pwsh', ...`。插件身份 `name: 'tool-pwsh'`、`inject: ['tools','shell','systemPrompt','shellEnv']`（47-48）。
- 持久：`packages/shell/tool-pwsh-persistent/src/index.ts:492-512`（`apply`）→ `511` `registerPersistentPwsh(ctx, resolved)` → `441-442` `ctx.tools.register(defineTool({ name: 'pwsh', ...`。插件身份 `name: 'tool-pwsh-persistent'`、`inject: ['tools','terminals']`（468-469）。

宿主组合里两个插件都挂在根 include 树上，apply 收到的是无 scope 的根 ctx，`scopeOf` 为 `undefined`，都写**全局层**——同一个 `NamedEntries`，第二个必然抛 720 行的全局文案。

### 1.4 抛错如何变成"加载失败"

`ctx.tools.register` → `ScopedLayers.effect` → `ctx.effect(generator)`；Cordis 的 effect body **立即执行**（`vendor/cordis/src/fiber.ts:407` "`execute` runs immediately"），所以 insert 抛错同步传播出 apply，插件激活失败。装配层两条兜底（`packages/boot/app-boot/src/index.ts`）：

- `assertEntriesActivated`：`FIBER_FAILED` 的 fiber 重新 await 收集原因，最终抛 `<bin>: N entries did not activate`（720-747）。
- `boot()` 整体 try/catch：stage 置为 `plugin tree failed to load`（795），rethrow 时折叠各层 wrap 并附 deepest cause 的原始栈（808-825，注释 814-818 明确"deepest cause is the plugin's own thrown error"）。

结论：**重名注册 = 加载期 fail loud，dsh 进程非零退出**；这正是 AGENTS.md "Misconfiguration fails loud at load when self-contained" 与 "Registrations are effects" 的落点，也是 fs 双注册先例（`packages/bundle/base/README.md:76` "mounting `dsh-fs-local` alongside it would double-register `ctx.fs` and fail the load"；同文件 127 行 Known Limitations 重述）的同类机制。

## 2. (b) 快照场景 persistent pwsh 的注册路径与分层

### 2.1 headless profile 如何叠加 dsh-base

- profile 模板：`packages/boot/app-boot/src/profile.ts:317-319`，`headless: { bundles: ['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-headless'], patchReload: 'startup' }`。
- 层序：架构文档 `docs/architecture.md:27`——空 entry 列表上依次应用每个 bundle（按 profile 列表序）、profile 自己的 `cordis.patch.yml`、home 层、最后 `--patch` overlay；`:29`——headless 这类 one-shot profile 全部层只在启动时应用一次。
- dsh-base 是"对空根的**一次 insert**"（`packages/bundle/base/cordis.patch.yml:1-4, 15`），其中 shell 相关行：
  - `tool-bash`：`disabled: !!js process.platform === 'win32'`（252-254，win32 上禁用）；
  - `tool-pwsh`：`disabled: !!js process.platform !== 'win32'`（256-258，**win32 上启用**）；
  - 执行器双胞胎 `bash-sandbox` / `pwsh-sandbox` 用同样对称的表达式（220-228）。
  平台门控的文档在 `packages/bundle/base/README.md:76`（"The patch gates the two shell stacks by platform on its own rows … exactly one shell stack is available per machine"，同页 54 行还写了手动切换必须成对 disable/enable 否则加载失败）。
- dsh-headless 在其上覆盖 system-prompt/tools 行并 insert workspace、code-runtime、runner 等行（`packages/bundle/headless/cordis.patch.yml` 全文 36 行），不触碰任何 shell 行。

### 2.2 场景 composition 如何叠上去（insert 语义与录制/回放差异）

- 场景清单：`snapshots/session/persistent-pwsh-tool-turn/snapshot.yml`——`profile: headless`（3）、`composition: persistent-pwsh`（4）、`recording: live`（5）、`header.class: persistent-pwsh / pin: true`（6-8）、`platform: pwsh`（9）。`composition` 字段的语义是"composition id，其唯一 pin 拥有该 profile 的 patches"（`packages/test-support/session-snapshot/src/manifest.ts:110-111`）；`platform: pwsh` 是宿主要求（manifest.ts:37，`SnapshotPlatform = 'posix' | 'pwsh'`），只影响 skip 判断。
- 场景发现与 composition 归属：`snapshots/session/headless.snapshot.ts:440-459` 扫描 `snapshots/session/*/snapshot.yml`；`:472-475` 拥有 `cordis.yml` 的场景是该 composition 的**唯一 owner**（多个 owner 直接抛错）；`persistent-pwsh-tool-turn` 自己就是 `persistent-pwsh` composition 的 owner。
- patch 源序列：`headless.snapshot.ts:661-671`——`[default composition 的 cordis.yml（owner 为 text-turn）, 本场景 composition patch, model.cordis.yml]`，其中 composition patch 回放取 `cordis.snapshot.yml`、录制取 `cordis.yml`（`:666` `replaying ? 'cordis.snapshot.yml' : 'cordis.yml'`；composition === default 且录制时跳过第二层）。`:690-694` 组装为 `dsh --profile headless --patch <default> --patch <composition> --patch <model> <task>`（经 `runLoaderSmoke` 启动 `apps/cli/src/bin.ts`）。`cordis.snapshot.yml` 会先经 `materializeProfilePatch` 物化（重写相对插件名为 URL、链接 bare 包，`packages/test-support/session-snapshot/src/launcher.ts:416-441`；headless.snapshot.ts:719-725 调用）。
- **insert 行为语义**：patch 对同名 id 行"整行替换 config，或插入新行"（`docs/architecture.md:27`；`packages/bundle/base/cordis.patch.yml:1-10` 头注——"A patch replaces the targeted row's whole config … or inserts new rows"）。场景 composition 里：
  - `- id: tool-bash … disabled: true`：按 id 打中 dsh-base 的 `tool-bash` 行并置为禁用（cordis.snapshot.yml:89-91 / cordis.yml:81-83）；
  - `- insert: - id: tool-pwsh-persistent / name: '@deepseek-ai/dsh-tool-pwsh-persistent'`：**新插入一行**（cordis.snapshot.yml:93-95 / cordis.yml:85-87）；
  - **两个文件都没有任何针对 `tool-pwsh` 的行**（全文检索仅命中 `tool-pwsh-persistent`）。
- **persistent pwsh 在哪注册**：插入行使 `@deepseek-ai/dsh-tool-pwsh-persistent` 进入组合树，激活期其 `apply` → `registerPersistentPwsh` → `ctx.tools.register({ name: 'pwsh' })`（见 1.3）。
- **录制与回放差异**只在与 shell 无关的层：录制 `cordis.yml` 用真 LLM（`llm-deepseek` 活、compression zstd，2-7/38 行）；回放 `cordis.snapshot.yml` 停用 `llm-deepseek`、insert `llm-replay`（2-15）、compression none（46）。两文件的 tool 层完全一致（disable tool-bash + insert tool-pwsh-persistent）。
- skip 规则：`headless.snapshot.ts:644-645`——`platform: 'pwsh'` 且宿主无可用 pwsh 时 skip（`hasPwsh` 探针 462-466）；win32 且装了 pwsh 的宿主上该场景**会执行**。

### 2.3 同语料的现成反例（组合写法本可避免撞车）

`snapshots/session/pwsh-tool-turn`（composition `pwsh`，同为 `platform: pwsh`）的 composition 显式同时表态两行：`- id: tool-bash … disabled: true` 与 `- id: tool-pwsh … disabled: false`（cordis.snapshot.yml:83-91 一带）。即"composition 接管 shell 栈时必须对两行都表态"的写法在同语料中已存在，`persistent-pwsh-tool-turn` 恰恰缺了 `tool-pwsh` 那一行。

## 3. (c) 撞车机制链与 POSIX 绿因

### 3.1 因果链（win32 宿主）

1. `pnpm run test:snapshot -t persistent-pwsh-tool-turn` → `headless.snapshot.ts` 场景测试启动 `dsh --profile headless --patch×3 <task>`。
2. profile headless = dsh-base 一次 insert + dsh-headless patch（profile.ts:317-319）；dsh-base 的 `tool-pwsh` 行在 win32 上 `disabled: false`（`process.platform !== 'win32'` 为假，cordis.patch.yml:256-258）。
3. 随后三层 `--patch`：default cordis.yml（不动 shell 行）、场景 `cordis.snapshot.yml`（disable `tool-bash`、insert `tool-pwsh-persistent`、**未 disable `tool-pwsh`**）、model.cordis.yml。
4. 生效组合同时含两个活跃插件：`tool-pwsh`（基座行，win32 启用）与 `tool-pwsh-persistent`（场景 insert）。
5. 激活期两个插件的 `apply` 都在根 ctx 全局层注册 `name: 'pwsh'`（1.3）。先注册者成功；后注册者被 `NamedEntries.insert` 抛 `tool "pwsh" is already registered (for a per-agent variant, register through that agent's `agent.ctx` instead)`（store.ts:45 → index.ts:720）。
6. 抛错同步传播（effect body 立即执行）→ 该插件 fiber FAILED → `boot()` 抛 `dsh: plugin tree failed to load: …`（app-boot index.ts:795,808-825）→ dsh 非零退出。
7. 场景 fixture 的 turn 是 completed → `runLoaderSmoke` `expectedExitCode: 0`（headless.snapshot.ts:696-699），实际非零 → vitest 用例失败，场景红。

**确定性说明**：哪个插件"第二个注册"取决于服务可用性驱动的激活顺序（两者 inject 集合不同：`shell/systemPrompt/shellEnv` vs `terminals`），而 patch 行序不承载加载语义（base cordis.patch.yml:12-13 头注）；但"必有一方失败"在 win32 上是确定的。

### 3.2 为何 POSIX 录制当时是绿的

录制（cordis.yml，live）发生在 POSIX 宿主：基座 `tool-pwsh` 行 `disabled: !!js process.platform !== 'win32'` 求值为 true（256-258）→ 原生插件根本不挂载；`tool-bash` 被两层 composition disable（cordis.yml:81-83）；场景 insert 的 `tool-pwsh-persistent` 是唯一注册 `pwsh` 的插件 → 全局层一次 insert 成功 → 加载绿。POSIX 上的回放（cordis.snapshot.yml）同理绿。**平台条件式冲突对录制宿主不可见**，这是缺口本质：加载期 fail loud 只在"自我包含"的宿主上响（AGENTS.md："fails loud at load when self-contained, otherwise at the earliest resolvable point"）。

### 3.3 最小复现路径描述（不实际执行）

宿主：win32 且装有可用 pwsh。命令：`pnpm run test:snapshot -t persistent-pwsh-tool-turn`。
预期失败点：vitest 用例 `replays persistent-pwsh-tool-turn through dsh --profile headless`（headless.snapshot.ts:648 生成）在 `runLoaderSmoke` 阶段失败；dsh 子进程非零退出，stderr 含 `dsh: plugin tree failed to load: …` 与 deepest cause `tool "pwsh" is already registered …`（index.ts:720 文案，报错插件取决于激活序）。红证据已由 Battery 链持有，本 Worker 未重跑。

## 4. (d) 对照面：为何这些不撞车

### 4.1 `packages/bundle/sdk-minimal`（独立全显式树）

- 它是"刻意例外：一个 bundle 拥有完整显式 SDK 树、**不叠 dsh-base**"（`docs/architecture.md:25`；profile 模板 bundles 仅 `['@deepseek-ai/dsh-sdk-minimal']`，profile.ts:333-336）——没有基座 `tool-pwsh`/`tool-bash` 行可供撞车。
- 组合内只有持久双胞胎且**同文件成对、反相门控**：`persistent-bash`（`@deepseek-ai/dsh-tool-bash-persistent`，win32 禁用，cordis.patch.yml:130-134）与 `persistent-pwsh`（`@deepseek-ai/dsh-tool-pwsh-persistent`，`disabled: !!js process.platform !== 'win32'`，145-158）。每个平台家族恰好一行活跃。
- 依赖面与之一致：`packages/bundle/sdk-minimal/package.json:62-63` 只依赖 `dsh-tool-bash-persistent` 与 `dsh-tool-pwsh-persistent`，无原生 shell 工具包（63 行即 brief 所指）；`tests/sdk-minimal.spec.ts:59` 断言行→包映射。

### 4.2 `packages/preset/agent-presets/presets/minimal/agent.cordis.yml`（per-agent 作用域）

- 组合同样成对反相门控：`persistent-bash`（36-38，win32 禁用）/ `persistent-pwsh`（58-60，POSIX 禁用），头注（19-20）自述"Exactly one shell stack mounts per host"。
- 关键差异是**挂载域**：preset 挂进 agent 的 scope ctx——`mount.ts:379-383` 拒绝无 scope ctx（"its registrations would apply to every agent in the process"），`:396` `agentCtx.plugin(PresetTree, config)`；模块文档（mount.ts:2-5）与 preset 头注（16-18"the tool registers into this agent's scoped catalog"）一致。
- 因此即便 win32 宿主上基座已全局注册 `pwsh`，preset 的 `persistent-pwsh` 写的是 **agent scope 层**：重名检查逐层进行（store.ts:43-45），跨层同名是"scoped shadow 全局"（index.ts:1022-1024；store.ts:208-217）——不抛错，且 shadow 是**有意语义**。同类：`persistent-bash` 与原生 `tool-bash` 同名 `bash`（tool-bash-persistent/src/index.ts:402、tool-bash/src/index.ts:242），同机制不撞。

### 4.3 对照面结论

两处不撞车分别靠"**无第二行可撞**"（sdk-minimal：不叠 dsh-base）与"**不在同一层**"（minimal preset：per-agent scoped shadow）。`persistent-pwsh-tool-turn` 两条件都不满足：它叠在 dsh-base 之上、又把第二个 `pwsh` 注册者插进**根全局层**——跨层 shadow 救不了同层双注册。

## 5. 证据总表

| # | 断言 | 证据 |
|---|---|---|
| 1 | register 唯一入口、返回精确 disposer | packages/core/tools/src/index.ts:1022-1053 |
| 2 | 重名即抛（无替换/幂等路径） | packages/core/scope/src/store.ts:43-45；index.ts:719-721 |
| 3 | 插入返回幂等 undo | store.ts:46-54 |
| 4 | scope 由 ctx 决定；全局层 vs scope 层 | store.ts:226-247 |
| 5 | scoped shadow 全局、最近者赢 | store.ts:208-217；index.ts:1022-1024 |
| 6 | disposer 随 fiber 卸载运行（HMR） | vendor/cordis/src/fiber.ts:402-410；store.ts:233-263 |
| 7 | spec：重名抛错 + fiber dispose 注销 | packages/core/tools/tests/tools.spec.ts:1984-1996（1998-2007 disposer） |
| 8 | tool-pwsh 激活期注册 pwsh | packages/shell/tool-pwsh/src/index.ts:194,250-251 |
| 9 | tool-pwsh-persistent 激活期注册 pwsh | packages/shell/tool-pwsh-persistent/src/index.ts:441-442,492-512 |
| 10 | 激活抛错 → `plugin tree failed to load` | packages/boot/app-boot/src/index.ts:779-826（stage 795；deepest cause 814-824）；`N entries did not activate` 720-747 |
| 11 | headless 模板叠 dsh-base + dsh-headless | packages/boot/app-boot/src/profile.ts:317-319 |
| 12 | 层序与 --patch overlay 语义 | docs/architecture.md:27,29 |
| 13 | dsh-base 一次 insert；tool-pwsh win32 启用 | packages/bundle/base/cordis.patch.yml:1-4,15,252-258；README.md:54,76 |
| 14 | snapshot.yml 声明 | snapshots/session/persistent-pwsh-tool-turn/snapshot.yml:3-9 |
| 15 | composition owner 规则 | snapshots/session/headless.snapshot.ts:472-475；packages/test-support/session-snapshot/README.md:77 |
| 16 | patch 源序列与 --patch 装配 | snapshots/session/headless.snapshot.ts:661-675,684-695 |
| 17 | 场景 disable tool-bash、insert persistent | snapshots/session/persistent-pwsh-tool-turn/cordis.snapshot.yml:89-95；cordis.yml:81-87 |
| 18 | 两 composition 均无 tool-pwsh 行 | 两文件全文检索仅命中 `tool-pwsh-persistent`（93-95 / 85-87） |
| 19 | 同语料反例：两行都表态 | snapshots/session/pwsh-tool-turn/cordis.snapshot.yml:83-91 |
| 20 | platform: pwsh skip 规则 | headless.snapshot.ts:643-647,462-466；manifest.ts:37,330-336 |
| 21 | sdk-minimal 不叠 dsh-base、成对门控 | docs/architecture.md:25；profile.ts:333-336；packages/bundle/sdk-minimal/cordis.patch.yml:130-134,145-158；package.json:62-63 |
| 22 | minimal preset per-agent scoped 挂载 | packages/preset/agent-presets/presets/minimal/agent.cordis.yml:19-20,36-38,58-60；packages/preset/agent-presets/src/mount.ts:2-5,379-396 |
| 23 | fs 双注册 fail-loud 先例 | packages/bundle/base/README.md:76,127 |
| 24 | 行序无加载语义 | packages/bundle/base/cordis.patch.yml:12-13 |

未核实项：无（Battery 链已持有的 win32 红证据未在本机重跑，按任务边界仅给出预期失败点，见 3.3）。
