# v14-accept lead findings — 环境准备与基线探测

taskId=v14-accept（独立组合集成验收波，用户候选 B）。本文记录验收前的环境事实、key 探测、
隔离方案与可运行组合面清单。基线：main @ c79f85fb81（v14 ledger completeness merge）。

## 1. 基线事实

- Lead worktree：`D:/dsh-devframe-v14-accept-lead`，分支 `codex/v14-accept-lead`，
  HEAD `c79f85fb8149474af238b19979d7121d2cadf270`，起始干净（`git status --short` 空）。
- 主树 `D:/dsh-devframe` 只读；真实 `C:/Users/25313/.dsh` 绝不写入（见 §3 隔离论证）。
- 宿主：Windows（pwsh，无 bash），node v24.19.0，pnpm 11.19.0。
- pre-commit lefthook 因宿主无 bash exit 127（环境事实，与前波记录一致）；
  提交用 `--no-verify`，替代验证：`git diff --cached --check` exit 0 + 每文件恰一尾随换行。

## 2. DEEPSEEK_API_KEY 探测（精确阻塞记录）

| 探测项 | 结果 |
|---|---|
| 根 `.env`（`D:/dsh-devframe/.env`，worktree 同名文件） | 不存在 |
| 进程环境变量 `DEEPSEEK_API_KEY` | 未设置 |
| `$DSH_HOME/.credentials.yaml` | 隔离 DSH_HOME 全新创建，无托管 key |

结论：**真实 API 任务路径（场景 1 主路径）不可运行**。这不是跳过理由，而是要钉住的精确阻塞：
真实宿主 `pnpm dsh --profile headless "<task>"` 在无 key 下仍可完整启动（key 在每次 LLM 请求期
经 `resolveApiKey` 解析，boot 不需要），turn 以 `MISSING_CREDENTIAL` 错误结束、进程 exit 1、
stderr 打印 `dsh: MISSING_CREDENTIAL: ...`。该真实失败输出本身即场景 1 的阻塞证据；
同时免 key 组合面（命令注册/投影/日志落盘）按任务规定替代运行。

## 3. 隔离方案

- **DSH_HOME**：每次运行设 `DSH_HOME=%TEMP%/dsh-accept-home-<uuid>`（`DSH_HOME` env 优先级
  高于 `~/.dsh`，见 `dsh-home-paths`）。已核实的写入面全部落 DSH_HOME 之下：
  - sessions → `dshHomePath('sessions')`（JSONL 每会话一文件）
  - KV storage → `dshHomePath('storages')`（storage-json root）
  - profiles → `$DSH_HOME/profiles/<name>`（首用自动初始化）
  - credentials → `$DSH_HOME/.credentials.yaml`（只读回退为 invocation cwd 的 `.env` 与
    `$DSH_HOME/.env`，均不写真实 home）
  - anonymous id → `$DSH_HOME/.anonymous-user-id`
- **遥测**：`DSH_TELEMETRY_DISABLED=1`（snapshot 套件同款，阻断 OTLP 出网）。
- **进程 cwd**：每次运行独立临时目录（`runLoaderSmoke` 同款 mkdtemp 模式），任务面产生的
  任何文件写都落该 cwd。
- **profile 隔离**：`dsh --profile headless` 在隔离 DSH_HOME 下首用自动初始化
  （PROFILE_TEMPLATES.headless = base + headless bundles）；out-of-tree 实验包经
  `$DSH_HOME/profiles/node_modules` junction 链接（snapshot launcher 同款机制）。
- **in-process 组合**（场景 4/6/7 装载）：`new Context()` + 真实插件序列，存储/日志 root
  全部指向隔离临时目录；不触碰任何全局路径。
- **Vault/项目目录**：场景 6/7 的 Vault 与项目根全部 mkdtemp 于 `%TEMP%` 下。

## 4. 可运行组合面清单（免 key 判定）

真实启动机制（两类，均为产品自有通道，非模拟）：

- **A. 真实 CLI/profile 启动**：`node --import tsx/esm apps/cli/src/bin.ts --profile headless
  [--patch ...] "<task>"`，`TSX_TSCONFIG_PATH` 指向仓库 tsconfig（loader-smoke `src` 模式，
  snapshot 套件同款）。真实 Loader、真实 profile 初始化、真实退出码/stdout/stderr。
- **B. 真实 in-process 组合**：直接 `ctx.plugin(实际插件序列)` 后经产品 seam
  （`ctx.commands.execute`、`ctx.shadowRouter`、`ProjectMemoryService`）驱动，
  真实 JSONL 持久化落盘。包内 `real-composition.spec.ts` 先例证明该组合面即产品组合面。

| 场景 | 面 | 免 key 可真实驱动 | 机制 |
|---|---|---|---|
| 1 真实任务运行 | headless 全链路 | 否（阻塞，记录 MISSING_CREDENTIAL 真实输出） | 机制 A |
| 1F keyless 替代 | 命令注册/投影/日志落盘 | 是 | 机制 A（boot 验证）+ 机制 B（命令注册表驱动） |
| 2 权限 | sandbox/mode + permission/preset 事件 | 是 | 机制 A：`session/created` 钩子 `pinInitialPermission` 落初始三事件；`DSH_PERMISSION_MODE` 双值对照 |
| 3 cwd | session header cwd vs 实际 | 是 | 机制 A：headless runner `meta:{cwd: process.cwd()}` → JSONL header |
| 4 goal + /goal-complete | /goal 命令族 + /goal-complete 真实输出 | 是 | 机制 B：CommandRuntime+GoalService+projection+command-goal-binding 组合，`ctx.commands.execute` 派发；无证据路径钉 NO_VERIFICATION_TEXT |
| 5 重启/续跑 | 同 session 日志二次加载 | 部分 | 机制 A/B：JSONL 冷加载面真实存在（SessionStore restore）；生产 /devframe-resume 组合入口未闭合（v14-compos 在飞）→ 记现状失败 |
| 6 Shadow 跨项目 | openProject/sendToProject/源隔离 | 是 | 机制 B：shadow-router 真实组合（storage 栈+session+workspace+identity），临时两项目根 |
| 7 Memory 冷恢复 | 写入→新进程→读回等值 | 是 | 机制 B×2：真实 session-log receipt store（`createSessionLogReceiptStore`），两进程同一隔离 root+Vault |

已知未闭合（现状失败，供 compos 波落地后复验，非本波阻塞）：

- 生产组合没有构造 AgentEvidenceJournal producer/接线（v14-compos 在飞）→ 真实宿主
  `/goal-complete` 只能到稳定无证据错误，无法走通完成链。
- `/devframe-resume` 宿主入口未落地 → 场景 5 生产续跑面缺失。
- shipped profile（headless/devframe）均不挂 v14 实验包；`--patch` 叠加是当前唯一真实
  profile 级组合通道。

## 5. 组合依赖事实（供 Worker 装载参照）

- `/goal-complete` 组合最小集（包内 real-composition 先例）：SessionStore、
  JsonlSessionPersistence(root)、CommandRuntime、AgentRegistry、SessionProjectionRegistry、
  GoalService、command-goalBinding 插件（config: workspaceId 必填、workspaceRoot 可选）。
  稳定拒绝文本已核：NO_CURRENT_GOAL_TEXT / NO_BINDING_TEXT / NO_VERIFICATION_TEXT /
  NO_REVIEW_TEXT / GOAL_ALREADY_COMPLETE_TEXT / PROJECTION_FAILURE_TEXT / WORKTREE_REQUIRED_TEXT。
- Shadow 组合最小集（helpers 先例）：agent-loop-testkit 依赖 + SessionProjectionRegistry +
  AgentLoop + Storage + StorageJson + StorageDomain + JsonlSessionPersistence + WorkspaceRegistry +
  AgentBindingRegistry(session-identity) + ShadowRouter(authorizedRoots)。agent 创建经
  `ctx.agentLoop.create(provider:'mock')`（组合脚手架，路由状态机不走 LLM）。
- Memory 组合：`resolveMemorySpec` + `ProjectMemoryService` +
  `createSessionLogReceiptStore(session)`（receipt 经 `memory/receipt` 事件落真实 session log，
  冷启动 `rehydrateMemoryReceipts` 重放）。
- goal 命令族：`/goal [<objective>|clear|edit <objective>|pause|resume]`（command-goal，
  base 已挂）；goal phase 词汇 = active/paused/blocked/complete（×activation armed/disarmed）。
- 权限事件：`permission/preset` + `sandbox/mode` + `approval/policy` 三事件在
  `session/created` 时钉入；`DSH_PERMISSION_MODE` 控 sandbox-policy 默认
  （`workspace-write` 缺省，`danger-full-access` 时 approval=never）。

## 6. 探针实测（lead 亲自运行，非推断）

- `pnpm install --frozen-lockfile`：exit 0（23.4s；两条 `dsh` bin ENOENT WARN 系未构建
  lib/ 的预期事实，源码经 tsx 启动）。
- `pnpm run gen:typert`：exit 0。**必要前置**：source 模式 profile boot 中 typert-loader
  会按包 exports 导入 `lib/typert.host.js`；未生成时 boot 崩溃（4 contributor
  ERR_MODULE_NOT_FOUND，实测探针 1）。gen:typert 无需先验构建即可产出该工件。
- keyless 真跑探针（隔离 DSH_HOME + DSH_TELEMETRY_DISABLED=1 + 临时 root）：
  `node --import tsx/esm apps/cli/src/bin.ts --profile headless "reply with the single word ok"`
  → **exit 1**，stderr 末行 `dsh: MISSING_CREDENTIAL: llm-deepseek: no API key for provider
  route "deepseek-official"; store DEEPSEEK_API_KEY through the credentials service (the web
  Models page writes it), or export DEEPSEEK_API_KEY in the launching environment`，
  stdout 空。该输出即场景 1 精确阻塞的实测形态。
- 同探针 session 日志（zstd JSONL，落 `$DSH_HOME/sessions/<cwd编码>/session-*/`）实测 19 事件：
  `permission/preset:1, sandbox/mode:1, approval/policy:1`（session/created 初始钉入，场景 2
  证据面成立）；首记录 header `cwd:"D:\\dsh-devframe-v14-accept-lead"` == 实际进程 cwd
  （场景 3 证据面成立）；`user/message:4, request/header:1, turn/end:1`（错误收尾）。
- in-process 组合工具链验证：`pnpm exec vitest run
  packages/experimental/command-goal-binding/tests/real-composition.spec.ts` → 16/16 pass
  （8.46s），证明本 worktree 可运行 §5 全部组合面。

## 7. 待办后续

- findings 提交后写 design.md（场景定稿：命令、期望面、通过判据、预期现状失败标注、产物路径）。
- 建 Worker worktree `D:/dsh-devframe-v14-accept-w1`（分支 `codex/v14-accept-w1`，自本 lead HEAD），
  经 workflow 工具派发唯一 Worker（huoshan-2/glm-5.3-flash）编写验收装载
  （`.agents/devframe/v14-accept/worker/harness/**`）。
- Lead 亲自执行全部场景并记录真实结果至 results.md。

环境事实补记：探针运行时 cwd 为 lead worktree（session 落盘的项目作用域路径由此编码）；
正式场景运行 cwd 一律用独立临时目录，session 落 `<DSH_HOME>/sessions/<编码cwd>/`，
仍在隔离域内。
