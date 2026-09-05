---
description: built-bin 全程冒烟验证证据（P22 锚点，W3 归属）：五轮记录——R1/R2 构建失败 fail-loud；R3 build 绿+dump 6/6 绿，快照三家族红灯 fail-loud；R4 bundlefix 复验被 at2c 类型红阻塞 fail-loud；R5（at2c-fix c79da5d895）build 绿、built-bin e2e 22/22 全绿（A 族 tool-worktree pending 启动级消除）、快照 90F（A 族 130→0，残余=B 族根传播 bash 平台门控 vs pinned 头 + C 族 scaffold 转义在途），三 bundle 依赖声明缺项实证登记（安装闭包兜底走通）。
---

# built-bin 全程冒烟验证证据（P22 锚点，W3 归属）

- 执行者：L2 前台 Worker（归 L-Verify 看护）；单命令串行，无下级 Agent，未在线请求任何模型。
- 执行日期：2026-09-06（本地时间，以命令记录为准）。
- 结论：**fail-loud**。`pnpm run build` 在干净基线树上失败（非环境原因，详见 §3/§9），按任务规则禁止修复并停止后续验证执行；built bin 产物不存在，步骤 4 运行项、步骤 5、步骤 6 全部未执行。
- 隔离声明：全程未写入 `C:\Users\25313\.dsh`、`.dsh-integration`、`.dsh-verify`、`.dsh-product`；未对这三个非生产 home 做任何写操作（本次也无需只读复用其资产，因步骤 6 未执行）。本文件是本次唯一落盘的仓库内变更。

## 1. 工作树核实（步骤 1）

| 命令 | 退出码 | 关键输出 |
| --- | --- | --- |
| `git branch --show-current` | 0 | `p/builtbin` |
| `git log --oneline -1` | 0 | `9dbf3911f0 merge: integrate p/docfix-2 (close remaining documentation-standard gaps, 15/15 doc gates)` |
| `git status --short` | 0 | （无输出，工作树干净） |

- HEAD 全称：`9dbf3911f0afd0409351414f0fc527477ee4aab8`。
- 环境：Node `v24.19.0`，pnpm `11.19.0`，Windows x64（win32）。

## 2. `pnpm install --frozen-lockfile`（步骤 2）

- 退出码：0，`Done in 27.8s using pnpm v11.19.0`，280 个 workspace 项目，1000 包全部复用本地 store（下载 0）。
- Lockfile 校验：`Lockfile passes supply-chain policies`、`Lockfile is up to date, resolution step is skipped`。
- pnpm ≥10 allowBuilds 提示：未出现交互式提示（构建脚本类 postinstall 正常执行：`subprocess-local`、`install-lefthook`）。
- 关键 WARN（记录备查，构建前预期状态）：
  - `native/landlock-run/packages/linux-arm64|linux-x64 | [WARN] Unsupported platform`（Linux 目标平台在 Windows 宿主上的预期告警）。
  - `[WARN] Failed to create bin at ...\packages\sdk\client\node_modules\.bin\dsh. ENOENT: ... apps\cli\lib\bin.js.EXE`（lib 未构建导致 bin shim 创建失败，构建后本应消失；本次构建失败，该状态持续）。
  - `[WARN] There are cyclic workspace dependencies: ...`（与构建失败无直接关联，照实记录）。

## 3. `pnpm run build`（步骤 3）——失败

- 退出码：1，总耗时 63.6s。
- 失败位置：`build:lib:host` 阶段，即 `node --max-old-space-size=4096 ./node_modules/typescript/bin/tsc -b tsconfig.host.json`；`tsdown` 未执行。
- 汇总错误：`Error: build: build:lib exited with 2`（`scripts/build.ts:27`），随后 `[ELIFECYCLE] Command failed with exit code 2 / 2 / 1`。
- 产物状态：`apps/cli/lib/` 下仅有 tsc 增量产物（`tsconfig.tsbuildinfo`、`lib/types/**` 的 `.d.ts`/`.js`/`.map`）；**`apps/cli/lib/bin.js` 不存在，`apps/cli/dist/` 不存在** —— 无任何 built bin 可用。
- 未重试理由：错误为 TypeScript 编译期错误（类型不匹配、配置文件列表缺失），非网络瞬断，重试无意义。

## 4. built bin 入口定位（步骤 4，查阅部分完成，运行部分未执行）

只读查阅结果：

- 根 `package.json`：无 `bin` 字段（`bin: null`）；`test:snapshot` = `vitest run --config vitest.snapshot.config.ts`；`build` = `tsx scripts/build.ts`。
- `apps/cli/package.json`：`"name": "@deepseek-ai/dsh"`，`"bin": { "dsh": "lib/bin.js" }`。
- `apps/cli/tests/built-bin.e2e.ts` 的 `runBuiltBin` helper：`execa(process.execPath, [dshBin, ...args])`，其中 `dshBin = join(repoRoot, 'apps/cli/lib/bin.js')`，`repoRoot` 为仓库根。即约定的 built bin 调用路径为：
  - **`node D:\dsh-devframe-p-builtbin\apps\cli\lib\bin.js <args>`**
- 该路径当前不存在（`Test-Path` = False），因此约定的 `--help` / `--version` 冒烟命令**未执行**（无产物可跑；任务硬边界禁止改用 source 入口替代）。
- 佐证：`built-bin.e2e.ts` 整个 describe 为 `describe.skipIf(!existsSync(dshBin))`——无产物时该 built-bin 冒烟面整体跳过，与本次观察一致。

## 5. 快照回放（步骤 5）——未执行

- `pnpm run test:snapshot` **未执行**：前置构建失败触发 fail-loud 停止（任务步骤 3 规则），且构建产物缺失使"built-bin 等效子集"分支（`apps/cli/tests/built-bin.e2e.ts` 的 shipped profiles 用例）无从谈起（该 describe 会因 `skipIf(!existsSync(dshBin))` 整体跳过）。
- 用例总数/通过/跳过摘要：无（未运行）。未设置 `DEEPSEEK_API_KEY`（keyless 设计未被触碰）。

## 6. 无钥匙组合验证（步骤 6）——未执行

- 全部三个子项（6a 五插件验证 profile、6b 集成 profile 等价重建、6c 逐 profile `--dump-config`）**未执行**：6c 硬性要求用 built bin 跑 `--profile <name> --dump-config`，产物不存在；6a/6b 的安装与重建只服务于 6c，单独重建不产生任何验证价值，且任务硬边界禁止用 source 入口替代 built bin。
- `p22/anchor-matrix.md`（只读查阅）结论：该文件为 AT1–AT4 验收锚点矩阵与遗留清单（基线 `p/anchors` @ `213682a800`），**未定义"五插件验证 profile"的权威组成**（全文无 `dsh-llm-codex` / `dsh-llm-providers-ui` / `dsh-llm-ollama` / `dsh-llm-grok` / `dsh-llm-opencode-go` 任何命中）。若复跑，按任务文本给定的组成执行即可。
- 因此未发生任何 tgz SHA256 复核（预期值清单保留在任务文本中，未消费）；`.dsh-builtbin` home 未创建。

## 7. 与 source 模式差异观察（基于只读查阅，非实测）

- `vitest.snapshot.config.ts`：`pnpm run test:snapshot` 的 include 面为 `scripts/session-snapshot-corpus.corpus.ts` + `snapshots/**/*.snapshot.ts`；`apps/web/tests/**/*.snapshot.ts` 仅在 `DSH_EXAMPLE_MODE === 'lib'` 时加入。配置注释明示："source mode remains the zero-build path, while lib mode requires a prior build"——即默认快照回放是零构建路径。
- `docs/testing.md`：§"Test resolution: source plane only" —— 每个 vitest 配置经 `vite-tsconfig-paths` 指向 `tsconfig.base.json`，bare workspace 导入一律解析到 `src`，**从不**经 package `exports` 进 built `lib/`；built 产物只被显式消费（`lib`-mode subprocesses 与 built smokes）。§"Test subprocess launch modes" —— CI 与 build-having lanes 经 shared dual-mode launcher 从 built `lib/` 起子进程。
- `packages/test-support/loader-smoke/src/index.ts`：dual-mode launcher 以 `DSH_EXAMPLE_MODE` 判定，**未设（默认）= `src`**（`node --import tsx <srcBin>` + `TSX_TSCONFIG_PATH`，tsx 源码入口）；`lib` 模式（CI 设置）才是 `node <libBin>` plain-Node built 产物路径。本次环境未设该变量。
- 观察（本次未实测，仅静态结论）：在默认环境下 `pnpm run test:snapshot` 的快照回放走 **source 模式（tsx）**，不是 built-bin 路径；任务所关注的 built bin 冒烟面由 `apps/cli/tests/built-bin.e2e.ts`（`test:e2e` 通道）承载，且其以 `existsSync(dshBin)` 为前提。构建失败时两路的表现：source 快照理论上可跑（零构建），built-bin 冒烟整体跳过——这正是 built-bin 验证必须独立存在的原因。
- `docs/testing.md` 亦明确 "Real entry path" 的价值：built `lib/bin.js` under plain `node` 暴露 tsx 会掩盖的失败（settle races、模块解析、吞掉的加载失败）。本次构建失败恰在 tsx 通道之外再次印证了该主张的必要性。

## 8. 执行清单与退出码汇总

| # | 步骤 | 命令 | 退出码 | 结果 |
| --- | --- | --- | --- | --- |
| 1 | 工作树核实 | `git branch --show-current` / `git log --oneline -1` / `git status --short` | 0 / 0 / 0 | 通过 |
| 2 | 依赖安装 | `pnpm install --frozen-lockfile` | 0 | 通过（27.8s） |
| 3 | 构建 | `pnpm run build` | **1** | **失败，fail-loud 停止** |
| 4 | 入口定位 | 只读查阅（package.json / built-bin.e2e.ts / docs / vitest 配置） | — | 查阅完成；`node ...lib\bin.js --help/--version` 未执行（无产物） |
| 5 | 快照回放 | `pnpm run test:snapshot` | — | 未执行（前置失败） |
| 6 | 无钥匙组合验证 | profile 重建 + built bin `--dump-config` | — | 未执行（无产物） |
| 7 | 证据文件 | 本文件 | — | 已写入 |
| 8 | 门禁与提交 | `git add` + `git diff --cached --check` + `git commit --no-verify` | 见提交记录 | 已提交（仅本文件） |

## 9. 缺陷清单（fail-loud，未修）

### 缺陷 1（阻断级）：干净基线树 `pnpm run build` 失败于 `tsc -b tsconfig.host.json`

- 现象：exit 1，63.6s，`Error: build: build:lib exited with 2`（`scripts/build.ts:27`），`tsdown` 未执行，`apps/cli/lib/bin.js` 不存在。
- 环境排除依据：工作树干净、基线正确（`9dbf3911f0`）、`pnpm install --frozen-lockfile` exit 0、无网络依赖参与编译、错误全部为树内 TypeScript 编译错误。shadow-router 为基线内既有代码（`git log -- packages/experimental/shadow-router` 最近提交为 docs 类：`7689ce3bb5`、`3fb4ab3950`、`20d641a9c5`）。
- 错误分三类（原始关键行摘录）：

  1. **remote 子路径导出解析失败**（12+ 处 `TS2307` + 连带 `TS2339`）：
     - `packages/api/remotes/src/client/index.ts(4..15)`: `error TS2307: Cannot find module '@deepseek-ai/dsh-agent-presets/remote'`（及 dsh-commands、dsh-api-settings-controller、dsh-goal、dsh-llm、dsh-cordis-host-runner、dsh-host-plugin-inventory、dsh-message-feedback、dsh-session-reference、dsh-subagent、dsh-api-session-controller、dsh-api-workspace-controller 的 `/remote`）。
     - `packages/api/session-controller/src/client/transport.ts(3,21)`、`packages/api/workspace-controller/src/client/model.ts(4,21)` 同类；连带 `Property 'session'/'workspace'/'settings'/'directoryPicker' does not exist on type 'ClientRemote'`（`packages/client/ui-chat/src/client/apply.ts(124,45)` 等）。
     - 只读佐证：`@deepseek-ai/dsh-api-session-controller` 的 `./remote` 导出指向 `./lib/typert.remote-client.d.ts`（构建产物），而其 `src/` 下不存在 `typert.remote-client.ts` 源文件（`Get-ChildItem -Filter typert*` 为空）——该产物在本次构建中从未生成，host 程序解析失败。
  2. **shadow-router 文件不在 host 程序文件列表**（`TS6307`，5 处）：`packages/experimental/shadow-router/src/{index,errors,ids,spec,service,tools}.ts` 与 `tests/helpers.ts` 报 `File ... is not listed within the file list of project 'tsconfig.host.json'`。只读佐证：根 `tsconfig.host.json` 的 include 含 `packages/*/*/tests/**/*.ts`（拉入 shadow-router 测试并传递拉入其 src），但 references 数组**没有** `./packages/experimental/shadow-router` 项目。
  3. **shadow-router 源码级类型错误**（tests 目录，约 25 处）：`tests/aliases.spec.ts` `TS6133` 未使用导入；`tests/delivery-recovery.spec.ts` `TS2783` 属性重复指定、`TS2322` `string` 不可赋给 branded `ShadowMessageId`/`ShadowRequestId`/`SessionId`；`tests/provisioning.spec.ts` branded `WorkspaceId`/`SessionId` 同类不匹配；`tests/status.spec.ts` `string | undefined` 不可赋给 `string`（exactOptionalPropertyTypes）与 cursor 参数类型不匹配；`tests/helpers.ts(77,22)` `Property 'shadowRouter' does not exist on type 'Context'`。

- 判定：非环境原因的产品/配置缺陷（branded 类型不匹配与 tsconfig 项目列表缺失均为树内事实），**未修复**，按任务规则如实上报，修复归属由 L1/产品波决定。
- 影响面：built bin 不可用 → 本任务全部 built-bin 冒烟目标（`--help`/`--version`、快照 built 等效子集、五插件/集成 profile `--dump-config`）无法执行；`pnpm install` 阶段 `.bin\dsh` shim 创建失败（ENOENT）为同一根因的下游表现。

### 观察（非缺陷定级）：pnpm 循环 workspace 依赖告警

- `pnpm install` 报 cyclic workspace dependencies（`packages/client/locale`、`test-support/client-runtime`、`ui-chat`/`ui-layout`/`ui-theme`、`ui-conversation`/`ui-workspace`、`e2b`/`fs-e2b`、`sandbox-local`/`sandbox-windows-acl`、`subagent-spawn-in-process`/`tool-subagent`、`vendor/cordis`/`vendor/include`）。仅记录，不判定为缺陷，不评估修复。

---

# 第二轮重验（buildfix 39b32f6bcb，p/builtbin-2）——仍 fail-loud

- 执行者：L-Verify 亲自执行（L0 指令"自行 pnpm install + pnpm run build"）；未创建下级 Agent。
- 结论：**build 仍红，立即 fail-loud，未修复（build 链归 L-Foundation）**。步骤 4-6（built bin 定位与 --help、test:snapshot built 模式、五插件/集成 profile dump-config）全部未执行——`apps/cli/lib/bin.js` 不存在（`Test-Path` = False）。

## R2-1. 分支切换（L0 指定）

| 命令 | 退出码 | 关键输出 |
| --- | --- | --- |
| `git status --short` | 0 | （干净） |
| `git cat-file -t 39b32f6bcb` | 0 | `commit` |
| `git checkout -b p/builtbin-2 39b32f6bcb` | 0 | `Switched to a new branch 'p/builtbin-2'` |
| `git log --oneline -1` | 0 | `39b32f6bcb merge: integrate p/buildfix (typert remote contracts pre-generation + host reference)` |
| 证据文件继承 | exit 0 | `cat-file -e 39b32f6bcb:.agents/devframe/p22/builtbin-smoke-evidence.md` 通过；`merge-base --is-ancestor b93e91b198 39b32f6bcb` 通过（第一轮证据提交在 buildfix 链祖先上） |

## R2-2. `pnpm install --frozen-lockfile`

- 退出码 0：`Scope: all 280 workspace projects` / `Already up to date` / `Done in 596ms`。

## R2-3. `pnpm run build`——失败（两次：增量与 clean 重建）

- 第一次（存在上轮残留产物的树上）：exit 1，失败点提前到 `build:lib:host` 的第一步 `gen:typert`（`tsx scripts/gen-typert.ts`），错误唯一且与第一轮缺陷 3 同族：`packages/experimental/shadow-router/tests/helpers.ts(77,22): error TS2339: Property 'shadowRouter' does not exist on type 'Context'.`
- 为排除增量残留干扰，按 clean 树语义执行 `pnpm run clean`（exit 0，`clean: removed 243 paths`）后重建：**同点同错**，`Error: build: build:lib exited with 2`（`scripts/build.ts:27`），tsc 主体与 tsdown 均未到达。
- 完整日志存档：`C:\Users\25313\.dsh-builtbin\build-retry.log`、`C:\Users\25313\.dsh-builtbin\build-clean.log`（隔离 home 内）。
- 失败源码行（只读摘录，`packages/experimental/shadow-router/tests/helpers.ts` L77 上下文）：

  ```ts
  const router = ctx.shadowRouter
  router.markShadow(shadow)
  const worker = await ctx.agentLoop.create(SessionId('session-worker'), { provider: 'mock', model: 'mock' })
  ```

- 判定：确定性树内缺陷，非残留状态（clean 重建复现）、非环境原因（install 绿、无网络参与）。gen:typert 的扫描面包含 shadow-router 的 tests/helpers.ts，而该 helper 使用的 `ctx.shadowRouter` 能力面在其扫描的 Context 类型上不存在——与第一轮缺陷 2/3（shadow-router 未进 host references + tests 类型错误）同根因族的残留面。
- 影响面：与前轮相同，built bin 冒烟全部目标无法执行；本轮未复用也未下载任何 tgz 资产，未触碰生产 home 与既有隔离 home（`.dsh-builtbin` 仅存放两个 build 日志）。
- 提交：本节追加后 `git diff --cached --check` + `git commit --no-verify` 于 `p/builtbin-2`（SHA 见最终报告）。

---

# 第三轮（总控裁定后：merge main + sfix，任务继续）

- 裁定输入：第二轮红 = 基线过期（39b32f6bcb 早于 sfix `1bca752bca`，Context.shadowRouter 声明合并即 helpers.ts TS2339 修复；主树 bea230b9f9 权威 clean build 绿）。
- 结论：**build 绿，dump-config 6/6 绿，built bin 基本面可用；快照门（lib 与 src 两模式）与 built-bin e2e 的 sdk/acp/headless 启动在本机红灯，fail-loud 上报未修**（详见 §R3-4/R3-5，为超出"build 仍红"预设路径的新发现）。

## R3-1. merge main（总控指定）

| 命令 | 退出码 | 关键输出 |
| --- | --- | --- |
| `git merge main --no-edit` | 0 | 合并 `bea230b9f9`（含 sfix）；改动 `packages/experimental/shadow-router/src/service.ts +7` 等；合并提交 `5c2530ba10`；28e72efbcf 保留在链上 |

## R3-2. install + build——绿

- `pnpm install --frozen-lockfile` exit 0（Already up to date，665ms）。
- `pnpm run build` **exit 0**（日志 `C:\Users\25313\.dsh-builtbin\build-r3.log`；末尾 `build: recorded 220 client artifact(s) with 2 public value(s)`）。
- `apps/cli/lib/bin.js` 存在（Test-Path=True）。

## R3-3. built bin 定位与 --help/--version（步骤 4）

- 入口：`node D:\dsh-devframe-p-builtbin\apps\cli\lib\bin.js`（依据 apps/cli `bin` 字段 + built-bin.e2e `runBuiltBin`）。
- `--version` exit 0 → `0.1.2-alpha.4`；`--help` exit 0（Usage 页正常）。

## R3-4. test:snapshot built 模式（步骤 5）——红

- 开关依据（只读）：`packages/test-support/loader-smoke`——`DSH_EXAMPLE_MODE=lib` 即 built 模式（CI 由 run-gates 设 lib；未设 = src；其他值 fail loud）；`vitest.snapshot.config.ts` 仅在 lib 模式纳入 `apps/web/tests/**/*.snapshot.ts`。
- `$env:DSH_EXAMPLE_MODE='lib'; pnpm run test:snapshot` → **exit 1**（日志 `snapshot-lib.log`）：Test Files 5 failed / 1 passed (6)，Tests **91 failed / 17 passed / 11 skipped**（119）。
- 失败三类签名：
  1. `Error: dsh: plugin tree failed to load: dsh: 1 entry did not activate` + `@deepseek-ai/dsh-tool-worktree: pending (waiting for services: workspaceRegistry, worktreeRegistry)` —— headless/sdk/acp 全部场景阻断（含 ACP 桥 dispose、jsonrpc inactive context 下游错误）。
  2. Web 持久化回放断言失败：minimal-preset `persisted replay` 含 `Error: unknown tool "bash"`（`ToolNotFoundError/UNKNOWN_TOOL`）——tool 行在但调用期 unknown tool。
  3. `SyntaxError: Bad escaped character in JSON at position 99` 一处。
- **src 模式对照**（同树，未设 DSH_EXAMPLE_MODE）→ **exit 1**：89 failed / 16 passed / 10 skipped——同类失败面，**非 built 模式特有**。
- 环境排除：Playwright 浏览器在位（`%LOCALAPPDATA%\ms-playwright`：chromium-1228 + headless shell + ffmpeg）；失败非"缺浏览器"形态。平台注意：本机 Windows，CI 矩阵为 Linux；仓库存在已知 Windows 失败的诊断机制（`check:windows-wine`），**本地无法区分"Windows 平台已知失败"与"树回归"，不判定，如实上报**。

## R3-5. built-bin e2e 子集（等效 built 入口）

- `pnpm exec vitest run --config vitest.e2e.config.ts apps/cli/tests/built-bin.e2e.ts`（DSH_EXAMPLE_MODE=lib）→ **exit 1**：22 用例 3 失败（`sdk`、`acp`、`headless` 三个 profile 启动），签名与快照完全一致（tool-worktree pending）；其余 19 用例通过（含 web dump 面）。
- 决定性取证：`node <bin> --profile headless --dump-config` exit 0，组合树含 `- id: tool-worktree`（`@deepseek-ai/dsh-tool-worktree`）但**无任何 `workspace` / `worktree-registry` 服务提供者行**（dump 全文 `C:\Users\25313\.dsh-builtbin\dumps\headless.txt`）——pending 的直接原因是组合树缺这两个服务行。参考：集成线证据曾记录"workspace + worktree-registry（insert；base 的 tool-worktree 硬注入这两个服务，自定义 profile 无安装态 web-app 层，须显式补齐）"。是否属 CI(Linux) 同样缺失/门禁已红，本地无 CI 数据，不判定。

## R3-6. 无钥匙组合验证 dump-config（步骤 6）——6/6 绿（built bin）

- 隔离 home：`C:\Users\25313\.dsh-builtbin`（生产与既有隔离 home 未触碰；本轮 5 个 tgz 全新下载自 GitHub release URL 至 `.dsh-builtbin\downloads`，SHA256 全部 match=True：codex 0b441b…、providers-ui be72be…、opencode-go 0cce7e…、ollama ffafc6…、grok c88a7c…）。
- 五插件 profile 组成（同第一链）：codex/opencode-go/ollama/grok 各 = base + 目标 + providers-ui（providers-ui 依赖已装入各 profile）+ providers-ui 单独 profile；`pnpm --dir <profile> add <tgz>` 9 次**全部 exit=0**。
- 集成 profile：只读核对 `C:\Users\25313\.dsh-integration\profiles\integration\package.json`（bundles `[base, headless]`）后等价重建，patch overlay 用本树 `.agents/devframe/integration/cordis.patch.yml`（9 insert + 1 restate）。**复刻口径：dump 级**——其 workspace 实验包依赖为 `workspace:^` 链接（指向集成链树），不在本链跨树链接；boot 期模块闭包不在本步验证面。
- built bin dump 结果（`$env:DSH_HOME` 隔离）：

| profile | exit | 行数 | stderr | 关键行 |
| --- | --- | --- | --- | --- |
| dsh-llm-codex | 0 | 351 | 0 字节 | `- id: llm-codex`、`# == dsh-llm-providers-ui` |
| dsh-llm-providers-ui | 0 | 341 | 0 字节 | `- id: llm-providers-ui` |
| dsh-llm-opencode-go | 0 | 348 | 0 字节 | `- id: llm-opencode-go` |
| dsh-llm-ollama | 0 | 348 | 0 字节 | `- id: llm-ollama` |
| dsh-llm-grok | 0 | 348 | 0 字节 | `- id: llm-grok` |
| integration（--patch 档案层） | 0 | 470 | 0 字节 | `agent-hierarchy`、`project-memory`、shadow-router 面等（行数 vs 集成线源 dump 461：树演进差异） |

- 对照 shipped headless dump（R3-5 取证用）：exit 0，层树正常但如上缺 worktree 服务行。

## R3-7. 与 source 模式差异观察

1. built bin（`node lib/bin.js`）dump-config 的 **stderr 为 0 字节**，而源码 tsx 模式 stderr 回显 `$ node --import tsx/esm …` 命令行——built 入口更干净。
2. `test:snapshot` 的模式开关是 `DSH_EXAMPLE_MODE=lib`（非 'built'）；lib 模式额外纳入 `apps/web` 浏览器快照（src 模式 4 文件 115 用例 vs lib 模式 6 文件 119 用例），两模式在本机同红且失败族一致 → 快照红与 built 产物装配无特异性关联（tool-worktree 签名两模式同现）。
3. `built-bin.e2e.ts` 的 `describe.skipIf(!existsSync(dshBin))` 在无产物轮整体跳过、本轮真实执行——22 用例中 19 绿说明 built bin 对 web/dump 类面完全可用，红面集中在 sdk/acp/headless 三个 profile 启动。
4. 集成线 dump 行数 470（built bin + 当前树） vs 其记录 461（源 CLI + 当时的树）：行数差异来自树演进，非 built/源差异信号。

## R3-8. 本轮合规

- 未触碰生产 home 与既有隔离 home（`.dsh-verify` 本轮零读写；`.dsh-integration` 只读核对 1 个 package.json；`.dsh-product` 未存在未触碰）。
- 未改 src/tests；未修复任何缺陷（快照/e2e 红灯与 tool-worktree 组合缺口均 fail-loud 上报，修复归属 L-Foundation/产品链）。
- 门禁：`git diff --cached --check` exit 0；`git commit --no-verify` 于 `p/builtbin-2`（SHA 见最终报告）；未 push。

---

# 第四轮（bundlefix c42c8b4518 复验）——build 红阻塞全部复验，fail-loud

- 结论：`pnpm run build` 在 `c42c8b4518` 上**增量与 clean 重建双红**（新签名，非 R2 残留非 R3 产物问题）；clean 后 `apps/cli/lib/bin.js` 不存在（Test-Path=False）且失败重建未再生成——**built-bin e2e 三 profile 复验、快照 A 族 delta、bundlefix 启动级验证全部阻塞**。stale 产物不可用（clean 已删，且即使存在也不含 bundlefix 行，用它产证即假证据）。delta 计数：本轮不可测。

## R4-1. 分支与构建

| 步骤 | 退出码 | 关键输出 |
| --- | --- | --- |
| `git checkout -b p/builtbin-4 c42c8b4518` | 0 | `merge: integrate p/bundlefix (workspace/worktree-registry provider rows for headless, acp, sdk bundles)` |
| `pnpm install --frozen-lockfile` | 0 | Already up to date，645ms |
| `pnpm run build`（增量） | **1** | 日志 `build-r4.log` |
| `pnpm run clean` | 0 | removed 277 paths |
| `pnpm run build`（clean 重建） | **1** | 日志 `build-r4-clean.log`，**同错复现** |

**失败签名（3 处，全部在 at2c 链新增测试文件，host 程序严格模式）**：

1. `packages/experimental/agent-evidence/tests/at2c-04-bytask-trail-query.spec.ts(33,88): error TS2749: 'GoalId' refers to a value, but is being used as a type here.`
2. `packages/experimental/session-identity/tests/at2c-02-cold-restore-rebind.spec.ts(57,55): error TS2379` — `BindAgentRequest` 在 `exactOptionalPropertyTypes: true` 下不接受 `parentSessionId/pluginId/taskId: T | undefined` 实参
3. 同文件 `(68,46): error TS2379`（`taskId` 同类）

**区间归因（只读 git 取证）**：R3 绿基线 `5c2530ba10`（内容=main bea230b9f9+sfix）之后 main 依次合入 `483f109a44`（p/at2c："AT2B/AT2C twelve scenario drafts materialized as 37 executable cases"，新增 experimental tests 1536 行）→ `b80b3de7fd`（devframe-exports）→ `06d6950c38`/`c42c8b4518`（bundlefix，仅 3 个 bundle patch 各 +6 行 YAML）。红来自 **at2c 新测试文件在 `tsconfig.host.json` 程序（include 拉入 tests）下的类型错误**——与第一轮 shadow-router TS2339 同类（"tests 纳入 host 程序"面），sfix 只修了彼例。at2c 当时"五包 79/79"为 vitest 运行面，host tsc 类型面此前未覆盖这批新文件。

**附带**：`BindAgentRequest` 的 TS2379 是否兼涉契约类型收紧（agent-hierarchy/session-identity 契约面）由 L-Foundation 判定；`GoalId` TS2749 疑与 devframe-exports 深路径导出解析到 value 工厂相关（`73b388a119`/`e74e6a7268`），同样留裁决。

## R4-2. 步骤 2-4 阻塞记录

- built-bin.e2e.ts 三 profile（sdk/acp/headless）复验：**未执行**（无产物）。
- test:snapshot built 模式 A 族 delta：**未执行**（无产物；91F 基线维持 R3 记录）。
- 三 bundle 依赖声明缺项实证（步骤 4）：**未执行**（需 built 启动才可暴露运行时解析失败；组合级佐证可注：bundlefix 06d6950c38 仅补 patch 行，未动三个 bundle package.json 的依赖声明，`@deepseek-ai/dsh-workspace`/`@deepseek-ai/dsh-worktree-registry` 是否在安装闭包内需启动面验证——登记为后续项）。
- 组合级旁证尝试（stale bin + 当前 patch 磁盘文件）：**不可行**——clean 已删 bin.js，失败重建未再生（`Cannot find module ...lib/bin.js`，`dumps\headless-r4.err`）。

## R4-3. 本轮合规

- 零修复：at2c 测试类型错误未动；bundlefix 未动；未改 src/tests/profile/语料。
- 隔离 home 沿用 `.dsh-builtbin`（仅新增日志与 dumps）；生产与既有隔离 home 未触碰。
- 门禁：`git diff --cached --check` exit 0；`git commit --no-verify` 于 `p/builtbin-4`（SHA 见最终报告）；未 push。

---

# 第五轮（at2c-fix c79da5d895 复验）——build 绿；A 族启动级消除；残余 90F = B 族根传播 + C 族

- 结论：**build 绿，built-bin e2e 22/22 全绿（A 族 tool-worktree pending 启动级消除，bundlefix 行生效）**；快照 built 模式 90F/18P/11S（总 119 与 R3 持平）——A 族签名 **130→0**，残余 90F 主族为 B 族根传播（base/minimal 的 bash 平台门控 vs pinned 头期待 bash 工具），C 族（scaffold JSON 转义）1 处维持（webfix 在途）。三 bundle 依赖声明缺项实证登记（boot 当前经安装闭包兜底走通，补声明归后续）。

## R5-1. 分支与构建——绿

| 步骤 | 退出码 | 关键输出 |
| --- | --- | --- |
| `git checkout -b p/builtbin-5 c79da5d895` | 0 | main HEAD="merge: integrate p/at2c-fix (at2c host-tsc type corrections, build green)" |
| `pnpm install --frozen-lockfile` | 0 | Already up to date，542ms |
| `pnpm run build` | **0** | 日志 `build-r5.log`；`build: recorded 220 client artifact(s) with 2 public value(s)`；`bin.js=True` |

（对照 R4：at2c 三处类型错误（TS2749+TS2379×2）已由 p/at2c-fix 消除，host 程序类型面过。）

## R5-2. built-bin.e2e 三 profile 启动复验——全绿（A 族消除）

- `DSH_EXAMPLE_MODE='lib'; pnpm exec vitest run --config vitest.e2e.config.ts apps/cli/tests/built-bin.e2e.ts` → **exit 0**：Test Files 1 passed (1)，**Tests 22 passed (22)**（R3 基线 3 败 = sdk/acp/headless 启动）。
- 全日志 `did not activate` / `pending (waiting` 命中 **0 处**——R4 阻塞的启动级复验完成：bundlefix `06d6950c38`（headless/acp-app/sdk-app 各 +6 行 provider 行）启动级生效。

## R5-3. 快照 built 模式 A 族 delta

- `$env:DSH_EXAMPLE_MODE='lib'; pnpm run test:snapshot` → exit 1（日志 `snapshot-lib-r5.log`）：Test Files 5 failed / 1 passed (6)，**Tests 90 failed / 18 passed / 11 skipped (119)**。
- **对 R3 基线（91F/17P/11S）delta**：A 族签名（`did not activate`/pending）**130→0**；`unknown tool` 提及 2→17；`Bad escaped character` 1→1；净 -1F（91→90）。
- 机理：boot 解锁后此前被 `plugin tree failed to load` 整体阻断的场景真正跑到内容层，暴露下一层失败面——残余 90F 分解：
  1. **B 族根传播（主族）**：pinned replay 断言 `request/header #1 diverged from the pinned header`——pinned 头 tools 含 `"name": "bash"`（描述 "Execute a bash command (bash -c)…"），实收头无该行。根在平台门控：`packages/bundle/base/cordis.patch.yml` **L252-254** `- id: tool-bash` `disabled: !!js process.platform === 'win32'`（L256-258 tool-pwsh 反向门控）+ minimal preset L36-38 同门控——与 shipped-profile-defects.md 缺陷二同根因（有意平台设计 vs POSIX 语义语料），非 bundlefix/snapshot 链回归。受面：headless "matches the expected outputs" 套件、`snapshots/sdk/sdk.snapshot.ts` 16/16F、acp 套件等。CI(Linux) 判别不变：预期绿。
  2. **web minimal-preset 2F**：`sends the exact RL prompt and schemas…`（26ms，schema 断言同 B 族根）、`expands the completed persistent Bash call…`（31300ms waitFor 超时，同根 UI 层下游）。
  3. **C 族 1 处**：`message-feedback-protocol.snapshot.ts` 套件级 `Bad escaped character`——webfix 在途，维持 R3 钉行（scaffold L987/L668）。
- 失败测试行计数：snapshot-lib-r5.log 中 90 × `×` 行，无任何 A 族签名残留。

## R5-4. 三 bundle 依赖声明缺项实证（步骤 5）

- 提供者包在树：`packages/workspace/workspace`（`@deepseek-ai/dsh-workspace`）、`packages/workflow/worktree-registry`（`@deepseek-ai/dsh-worktree-registry`）。
- **声明缺项**：`packages/bundle/headless/acp-app/sdk-app` 三个 package.json 的 dependencies/devDependencies **均未声明**这两个包（bundlefix 仅补 patch 行）；对照 `packages/bundle/web-app/package.json` **两者皆有声明**；`apps/cli/package.json` 亦未直接声明（仅 dsh-web-app）。
- **启动面实证**：boot 当前**走通**（e2e 22/22）——解析经安装闭包兜底（launcher.ts L394 注释 "The package may instead belong to the dsh installation; profile boot heals those links"；pnpm nodeLinker hoisted 工作区闭包供链）。风险登记：若消费侧安装闭包缺这两个包（如打包 release 裁剪），boot 将在模块解析失败——补依赖声明归属 bundle owner（后续项，本链不动）。

## R5-5. 本轮合规

- 零修复：未改 src/tests/profile/语料/依赖声明；B/C 族残余如实上报（B 属产品平台设计面裁决、C 属 webfix 在途）。
- 隔离 home 沿用 `.dsh-builtbin`（新增 build-r5.log、snapshot-lib-r5.log、builtbin-e2e-r5.log）；生产与既有隔离 home 未触碰。
- 门禁：`git diff --cached --check` exit 0；`git commit --no-verify` 于 `p/builtbin-5`（SHA 见最终报告）；未 push。
