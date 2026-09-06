# v14-accept 验收场景定稿（design）

taskId=v14-accept。本文定稿 7 个验收场景的命令、期望面、通过判据、预期现状失败标注与产物路径。
基线事实与隔离论证见 findings.md（commit 2893337b37）。执行者=lead 本人；装载作者=唯一 Worker
（huoshan-2/glm-5.3-flash，经 workflow 工具单次 agent 调用；lead 自身不派 subagent，
huoshan-1 车道事实如实登记为"未使用"）。

## 0. 总则

- **每 pass 必须挂在真实运行产物上**：真实退出码、真实 stdout/stderr 原文、真实落盘文件
  （session 日志解析出的真实事件、真实路由状态、真实 Vault 文件）。静态配置检查或模拟输出
  不算通过。
- **无 LLM 触碰不变量**：场景 2–7 全部免 key 运行；in-process 组合使用 harness 自带的最小
  mock adapter（仅满足路由注册；其 `run` 被调用即抛错 fail-loud）。任何场景触达 LLM = 该场景
  FAIL。mock adapter 为 harness 自有代码，不导入任何 `packages/**/tests` 路径（零触碰禁区）。
- **隔离**：每场景独立 `%TEMP%/dsh-accept-<scenario>-<uuid>/` 根；`DSH_HOME` 指向其下
  `dsh-home/`；`DSH_TELEMETRY_DISABLED=1`；进程 cwd 为场景专属临时目录。绝不写
  `C:/Users/25313/.dsh` 与主树。
- **运行机制**（findings §4）：机制 A=真实 CLI/profile 启动（`node --import tsx/esm
  <tree>/apps/cli/src/bin.ts --profile headless`，`TSX_TSCONFIG_PATH=<tree>/tsconfig.json`，
  前置 `pnpm install --frozen-lockfile` + `pnpm run gen:typert`）；机制 B=真实 in-process
  Cordis 组合（`new Context()` + 真实插件序列 + 产品 seam 驱动）。
- **verdict 语义**：每场景产出 `verdict.json`（逐检查项 pass/fail + 证据相对路径 + pinned
  现状失败标注）。场景判定：全部检查项 pass（含"钉住的预期失败按文档形态复现"类检查）=
  PASS；真实不可运行面 = BLOCKED（附精确阻塞）；检查项真实失败 = FAIL。
- **产物布局**：证据统一收进 lead 树 `.agents/devframe/v14-accept/lead/evidence/<场景>/`
  （harness `--out` 先写临时，lead 复核后原样收档；results.md 引用收档路径）。

## 1. 装载规格（Worker 交付物，`.agents/devframe/v14-accept/worker/harness/**`）

全部为 ESM `.mjs`/`.ts` 脚本，自包含、无包外新依赖（只用 repo 已装依赖与 workspace 源码，
经 tsconfig paths 解析；zstd 读取复用 `<tree>/packages/session/session-persistence-jsonl/src`
的导出，v14/tools/read-session-log.mjs 先例）。共享库 `lib/`：

- `lib/launch.mjs`：机制 A 的 spawn 助手（隔离 env 组装、退出码/stdout/stderr 捕获、超时）；
  机制 B 的 `bootComposition(plugins, root)` 助手。
- `lib/logread.mjs`：多帧 zstd session 日志读取 → `{header, events[]}`（逐事件原文保留）。
- `lib/evidence.mjs`：`--out` 目录写入（文本原文 + JSON），verdict 组装与退出码规则。
- `lib/mock-adapter.mjs`：最小 LLM adapter（注册 'mock' 路由；`run` 被调用即抛
  `ACCEPTANCE_LLM_TOUCHED`）。

场景脚本（命令行接口固定，lead 按此执行）：

| 脚本 | 接口 |
|---|---|
| `s1-headless-run.mjs` | `node s1-headless-run.mjs --tree <worktree> --out <dir>` |
| `s2-permission-modes.mjs` | 同上（内部跑 3 个子运行） |
| `s3-cwd.mjs` | 同上 |
| `s4-goal-complete.mjs` | 同上（机制 B 单进程） |
| `s5-resume.mjs` | `--tree --out --phase write\|resume --root <共享隔离根> --session <id>` |
| `s6-shadow-routing.mjs` | `--tree --out [--phase cold --root <根>]` |
| `s7-memory-cold.mjs` | `--tree --out --phase write\|read --root <共享隔离根>` |

Worker 边界（重申）：只写 `worker/harness/**`；零触碰 `packages/**/src`、`packages/**/tests`、
`scripts/**`、`snapshots/**`、`vendor/**`、`.agents/devframe/v14/next/**`、主树、其他链
worktree；禁创建任何 Agent（不派生 subagent/worker；装载代码内经产品 API 组合 agent 是被测
面本身，不属此禁）；不执行验收运行（仅允许 `node --check` 级语法自检与纯静态审读）；
提交 `--no-verify` + 收据（staged `git diff --check` exit 0 + 每文件恰一尾随换行）；
禁 push/PR/发布/删除。

## 2. 场景定稿

### S1 真实任务运行（keyless 阻塞钉住）— 预期 BLOCKED

- **命令**：机制 A，`--profile headless "reply with the single word ok"`，隔离 DSH_HOME，
  超时 120s。
- **期望面**：真实 profile 初始化、真实 turn 启动、LLM 凭据解析失败收尾。
- **通过判据（作为"钉住"成立）**：exit code = 1；stderr 含
  `dsh: MISSING_CREDENTIAL: llm-deepseek: no API key for provider route "deepseek-official"`；
  stdout 为空；`$DSH_HOME/sessions/` 下真实落盘 1 个 session 目录。
- **判定**：**BLOCKED（真实 API 路径）**——DEEPSEEK_API_KEY 缺失（findings §2），上述真实
  输出即精确阻塞证据；keyless 替代面由 S2–S7 覆盖。
- **产物**：`s1/exitcode.txt`、`s1/stdout.txt`、`s1/stderr.txt`、`s1/session-listing.txt`、
  `s1/verdict.json`。

### S2 权限：sandbox 模式与 permission preset 真实生效

- **命令**：机制 A × 3 子运行，仅 `DSH_PERMISSION_MODE` 不同：`<unset>`、`read-only`、
  `danger-full-access`；各隔离 DSH_HOME + 独立 cwd；同一任务串。
- **期望面**：每次运行 session 日志钉入初始权限三事件
  （`permission/preset`、`sandbox/mode`、`approval/policy`），值由 env 决定。
- **通过判据**：逐子运行解析日志：unset → preset `workspace-write`/sandbox `workspace-write`/
  approval `ask`；read-only → 三值 `read-only`/`read-only`/`ask`；danger-full-access →
  `danger-full-access`/`danger-full-access`/`never`。三事件各恰 1 条。env → 事件值的真实
  因果即"真实生效"。
- **产物**：`s2/<mode>/stderr.txt`、`s2/<mode>/events.json`（三事件原文）、`s2/verdict.json`。

### S3 cwd：任务运行的 cwd 解析与记录

- **命令**：机制 A，专属临时 cwd（目录名含可辨识 uuid）。
- **期望面**：session 日志首记录（header）`cwd` == 实际进程 cwd。
- **通过判据**：header.cwd 与 spawn cwd 经 realpath + 大小写归一后相等；同时记录
  `$DSH_HOME/sessions/<编码路径>` 与该 cwd 的对应关系。
- **产物**：`s3/header.json`、`s3/session-path.txt`、`s3/verdict.json`。

### S4 goal 流转 + /goal-complete 真实输出（钉住无证据错误）

- **命令**：机制 B 单进程组合：agent-loop-testkit 依赖 + SessionProjectionRegistry +
  AgentLoop + JsonlSessionPersistence(root=隔离) + CommandRuntime + GoalService +
  command-goal-binding 插件（config：`workspaceId: 'ws-v14-accept'`，
  `workspaceRoot: <隔离根>/worktree`）；经 `ctx.agentLoop.create` 建真实 agent
  （provider 'mock'）；全部命令经 `ctx.commands.execute` 派发。
- **期望面**：goal 命令族真实流转 + /goal-complete 稳定拒绝链 + 事件落盘。
- **通过判据**（逐检查项）：
  1. `/goal-complete`（无 goal）→ error 文本 = NO_CURRENT_GOAL_TEXT 原文；
  2. `/goal <objective>` → success；日志含 `goal/change`（phase active）；
  3. `/goal pause` → paused；`/goal resume` → active（各对应 goal/change）；
  4. `/goal-complete` → error 文本 = NO_BINDING_TEXT 原文（goal 无 completion binding）；
  5. 经组合 start lane `startBinding`（README 标注 test-visible；宿主 start 面未交付，如实
     标注）成功后，`/goal-complete` → error 文本 = **NO_VERIFICATION_TEXT 原文**
     （**钉住**：生产组合无 producer 接线，v14-compos 在飞）；
  6. 每次派发日志含配对 `command/run`+`command/done`；拒绝后 goal phase 不变；
  7. `/goal clear` → cleared。
- **判定**：1–7 全部按文档形态复现 = PASS（含钉住项 5）；完成链走通（ admitted 路径）在
  本基线不可达，记为现状失败清单条目（非场景 FAIL）。
- **产物**：`s4/command-results.json`（逐次派发的 result 原文）、`s4/log-events.json`
  （全事件）、`s4/verdict.json`。

### S5 重启：同 session 日志二次加载/续跑

- **命令**：机制 B 两进程，同一隔离根 + 固定 session id：
  - `--phase write`：建 agent + `/goal <objective>` 派发落盘，flush，exit 0；
  - `--phase resume`：同组合新进程，`ctx.agents.resume({resumeSessionId})`（AgentLoop 工厂
    → JSONL 冷加载），断言 header/events 恢复，再派发 `/goal pause` 成功（恢复前缀之后
    追加新事件）。
- **期望面**：持久层冷恢复 + 恢复后续跑。
- **通过判据**：resume 进程 exit 0；恢复 session 的 id/cwd/事件数与写入进程一致；goal
  projection 恢复为 active + objective 等值；续跑事件 seq 单调接续；两进程分别落真实
  stdout/exitcode。
- **现状失败标注**：生产 `/devframe-resume` 宿主入口未交付（v14-compos 在飞）——本场景
  验证的是其下的真实冷加载/续跑面；入口缺失单独记入现状失败清单（grep 证据：shipped
  profile 无该命令注册）。
- **产物**：`s5/write.json`、`s5/resume.json`（各含 exitcode/派发结果/恢复断言明细）、
  `s5/verdict.json`。

### S6 Shadow 跨项目源路由

- **命令**：机制 B：testkit + SessionProjectionRegistry + AgentLoop + Storage + StorageJson +
  StorageDomain + JsonlSessionPersistence + WorkspaceRegistry + AgentBindingRegistry +
  ShadowRouter（`authorizedRoots: [<隔离根>/projects]`）；markShadow 于真实 agent；
  `<隔离根>/projects/` 下两个项目目录 A/B。
- **期望面**：跨项目真实路由状态机与源隔离。
- **通过判据**（逐检查项）：
  1. openProject A/B → state `ready`；workspaceId、controllerSessionId 两两不同；
     profileKey `devframe`；binding 记录 exact cwd = 各项目目录；
  2. sendToProject A → status `received`；A 的 deliveries 含该 message；**B 的 deliveries
     不含**（不串项目）；
  3. setActiveGoal A/B 各自生效，互不覆盖；
  4. stop A → A 队列/绑定进入停止态；**B 绑定 state 与队列原样**（停止隔离）；
  5. 同 requestId 异输入重发 → `SHADOW_REQUEST_CONFLICT` 真实错误面；
  6. （次级）`--phase cold` 第二进程同根重启：绑定与 received 投递行级恢复。
- **判定**：1–5 必查全过 = PASS（6 为加分记录，失败不判 FAIL 但如实记录）。
- **产物**：`s6/routing-log.json`（每步真实返回/状态）、`s6/cold.json`（如跑）、
  `s6/verdict.json`。

### S7 Memory 冷恢复：写入→新进程→恢复读回等值

- **命令**：机制 B 两进程，同一隔离根 + 同一 Vault 根 + 固定 session id：
  - `--phase write`：建 agent；`resolveMemorySpec({vaultRoot, writeEnabled: true,
    workspaceId: 'ws-accept'})` + `ProjectMemoryService` +
    `createSessionLogReceiptStore(agent.session)`；append 两条 note（project 域 + user 域）；
    flush；exit 0；
  - `--phase read`：新进程 `ctx.agents.resume` 恢复 session →
    `rehydrateMemoryReceipts` → 新 `ProjectMemoryService`（同 Vault、同 spec）。
- **期望面**：receipt 经 `memory/receipt` 事件落真实 session 日志；冷启动后读回等值。
- **通过判据**：read 进程 exit 0；按 noteId `read` → `found` + `verified: true` + 内容与
  写入返回等值（逐字段）；`search` 两域各命中 1；同 sourceRef 重试 append →
  `already_exists`（幂等）；Vault 内 2 个真实 `.md` 文件存在。
- **产物**：`s7/write.json`、`s7/read.json`、`s7/vault-listing.txt`、`s7/verdict.json`。

## 3. 执行协议（lead）

1. Worker worktree `D:/dsh-devframe-v14-accept-w1`（分支 `codex/v14-accept-w1`，自 lead HEAD）
   内 `pnpm install --frozen-lockfile` + `pnpm run gen:typert`（运行前置，findings §6 已证）。
2. 逐场景新开隔离根执行；`--out` 指向临时，复核后收档至
   `lead/evidence/<场景>/`；`results.md` 逐场景记 pass/fail/blocked + 证据路径 + 逐笔 SHA。
3. 装载若存在妨碍执行的最小缺陷，lead 在 worker 树做机械性修正并逐条登记为偏差
   （前波先例：worker deviations verified non-semantic and accepted）；语义性缺陷退回重写。
4. 结算报告（九态、逐场景结果、现状失败清单、环境事实、逐笔 SHA、Worker 车道、GAP）
   呈交总控 session-c1668d60。
