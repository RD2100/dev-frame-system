---
description: built-bin 全程冒烟验证证据（P22 锚点，W3 归属）：在 p/builtbin 基线 9dbf3911f0 上构建失败，fail-loud 未修，built bin 不可用，后续验证未执行。
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
