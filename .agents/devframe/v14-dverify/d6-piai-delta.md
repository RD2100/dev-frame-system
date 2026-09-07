# D6 pi-ai 版本漂移核验（dverify Worker）

## 路由标签声明

- 显式路由：`{provider: huoshan-2, model: glm-5.3-flash}`。
- 该路由标签为 Worker 自报，属 **2 级标签**（本报告未对其做独立验证）。

## 已纠正事实（直接引用，不重推导）

1. `pnpm-workspace.yaml` 第 52 行是 `minimumReleaseAgeExclude` 下的条目 `- '@earendil-works/pi-ai@0.84.2'` —— **发布时间豁免，不是版本 pin**（纠正旧报告措辞）。
2. 真实依赖声明 = `packages/llm/llm-pi-ai/package.json` 第 44 行 `"@earendil-works/pi-ai": "^0.84.2"`；lockfile 解析 **0.84.2**。
3. 四个外部插件 **dsh-llm-opencode-go@0.1.20 / dsh-llm-ollama@0.6.17 / dsh-llm-grok@0.3.11 / dsh-llm-commandcode@0.1.19** 均声明 `^0.84.2`（本轮 GitHub Releases tgz package.json 亲读所得，引用即可）。

## 步骤命令 / 退出码 / 结果表

| # | 命令 / 操作 | 退出码 / 状态 | 结果 |
|---|---|---|---|
| 1 | `pnpm view @earendil-works/pi-ai version` | exit 0 | 上游 latest = **0.85.1** |
| 2 | `pnpm view @earendil-works/pi-ai versions --json` | exit 0 | 共 45 个版本；0.84.x = 0.84.0–0.84.4（**0.84.2 后有 0.84.3、0.84.4**）；0.85.x = **0.85.0、0.85.1**；末尾 15 个：0.80.8 … 0.85.1。完整清单存草稿区 `C:/Users/25313/.dsh-v14-dverify-lead/worker-d6/pi-ai-versions.json` |
| 3 | `pnpm view @earendil-works/pi-ai time --json` | exit 0 | 0.84.2 = `2026-08-14T10:07:54.869Z`；0.84.3 = `2026-08-24T11:06:27.239Z`；0.84.4 = `2026-08-28T22:05:13.974Z`；0.85.0 = `2026-09-04T10:13:48.137Z`；latest(0.85.1) = `2026-09-05T12:05:47.996Z`。完整存草稿区 `C:/Users/25313/.dsh-v14-dverify-lead/worker-d6/pi-ai-time.json` |
| 4 | 宿主树证据（read/grep 文件工具，无 shell 退出码） | — | 引行见下方版本对照表；lockfile grep 命中 3 处：6552 / 11129 / 16991 行 |
| 5a | web_fetch `https://registry.npmjs.org/@earendil-works/pi-ai/latest` | HTTP 200 | 0.85.1 packument：repository = `git+https://github.com/earendil-works/pi.git`（directory `packages/ai`）；deps/exports 见变更面；0.85.1 带 npm provenance/attestation（SLSA v1，trusted publisher GitHub Actions）；engines node `>=22.19.0` |
| 5b | web_fetch `https://raw.githubusercontent.com/earendil-works/pi/main/packages/ai/CHANGELOG.md` | **失败**：`Error: web fetch failed: TypeError: fetch failed`（无 HTTP 状态） | 首个错误行如前，完整失败存档 `C:/Users/25313/.dsh-v14-dverify-lead/worker-d6/fetch-changelog-raw-error.txt`；按规则改走 GitHub API，未重试 |
| 5c | web_fetch `https://api.github.com/repos/earendil-works/pi/releases?per_page=30` | HTTP 200 | 取得 v0.85.1 / v0.85.0 / v0.84.3 release body |
| 5d | web_fetch `…/releases/tags/v0.85.0` 与 `…/releases/tags/v0.84.4` | HTTP 200 ×2 | 两个 release body 补齐 |
| 5e | `curl.exe -sS -L -o pi-ai-0.85.1.tgz https://registry.npmjs.org/@earendil-works/pi-ai/-/pi-ai-0.85.1.tgz`（草稿区） | HTTP=200，exit 0 | tgz 落草稿区 |
| 5f | `tar -xzf pi-ai-0.85.1.tgz -C upstream-0.85.1`（草稿区） | exit 0 | 解出 `package/{dist, package.json, README.md}` |
| 5g | pwsh cmdlet 脚本：deps/exports diff + dist 文件清单 diff + 宿主采用子路径存在性 + 模型数据文件名集对比（对比基线 = 宿主 `node_modules/.pnpm/@earendil-works+pi-ai@0.84._a706abba28764463b0950f15a1dae6cf/node_modules/@earendil-works/pi-ai`，glob 单一命中） | 进程退出码 0（全 cmdlet，无原生子进程） | 结果见变更面总结 |

未发生沙箱拒绝；未执行任何 pnpm add / install / update，未构建，宿主树除唯一目标 md 外零写入。

## 版本对照表

| 维度 | 值 | 证据（文件 + 行号 + 原文） |
|---|---|---|
| 宿主声明范围 | `^0.84.2` | `packages/llm/llm-pi-ai/package.json:44` `"@earendil-works/pi-ai": "^0.84.2"` |
| lockfile 实锁 | `0.84.2` | `pnpm-lock.yaml:6552-6554`：`'@earendil-works/pi-ai':` / `specifier: ^0.84.2` / `version: 0.84.2(@modelcontextprotocol/sdk@…)(supports-color@9.4.0)(ws@8.21.0)(zod@4.4.3)`；`pnpm-lock.yaml:11129-11131`：`'@earendil-works/pi-ai@0.84.2':` / `resolution: {integrity: sha512-6MzsrYIY…}` / `engines: {node: '>=22.19.0'}` / `hasBin: true` |
| lockfile 依赖闭包 | `@anthropic-ai/sdk 0.91.1`、`@aws-sdk/client-bedrock-runtime 3.1048.0`、`@earendil-works/pi-telemetry 0.84.2`、`@google/genai 1.52.0` | `pnpm-lock.yaml:16991-16996` |
| node_modules 实装 | `0.84.2` | `node_modules/.pnpm/@earendil-works+pi-ai@0.84._a706abba28764463b0950f15a1dae6cf/node_modules/@earendil-works/pi-ai/package.json:3` `"version": "0.84.2"` |
| workspace 条目 | `- '@earendil-works/pi-ai@0.84.2'`（minimumReleaseAgeExclude，发布时间豁免，**精确 @version**） | `pnpm-workspace.yaml:49-53`；英文注释原文（50-51 行）：`# Fresh pi-ai releases carry the model catalog updates that are the whole` / `# point of bumping it; waiting out the release age would defeat that.` |
| 外部四插件声明 | 均 `^0.84.2` | dsh-llm-opencode-go@0.1.20 / dsh-llm-ollama@0.6.17 / dsh-llm-grok@0.3.11 / dsh-llm-commandcode@0.1.19（GitHub Releases tgz package.json 亲读，本轮） |
| 上游 latest（dist-tags.latest） | **0.85.1** | 步骤 1（exit 0）+ 步骤 5a（HTTP 200） |
| 0.84.2 之后同 minor | 0.84.3（`2026-08-24T11:06:27.239Z`）、0.84.4（`2026-08-28T22:05:13.974Z`）——**有 0.84.3+** | 步骤 2/3 |
| 0.85.x 全集 | 0.85.0（`2026-09-04T10:13:48.137Z`）、0.85.1（`2026-09-05T12:05:47.996Z`） | 步骤 2/3 |

## 变更面总结（0.84.2 → 0.85.1）

### 包级 diff（0.85.1 tgz vs 宿主 0.84.2 实装副本，步骤 5e-5g 实测）

- dependencies：`@anthropic-ai/sdk` **0.91.1 → 0.123.0**；`@earendil-works/pi-telemetry` `^0.84.2 → ^0.85.1`；`@opentelemetry/api@1.9.0` 从直接依赖移除；无新增依赖。
- exports：新增 **`./utils/*`** 子路径；其余 `.` / `./api/*` / `./oauth` / `./compat` / `./providers/*` / `./bedrock-provider` / `./bun-oauth` 不变。
- 文件清单：dist 文件 **740 → 748**；新增 `api/cloudflare-ai-binding.*`（`api/cloudflare-gateway-binding.*` 改名消失）、`utils/assistant-message-frame.*`、`utils/sleep.*`。
- `dist/providers/data` 模型数据文件：**40 → 40，文件名集合完全一致**（目录更新为文件内容级，未增删数据文件）。
- engines 不变：node `>=22.19.0`；bin 不变（`pi-ai: dist/cli.js`）。

### Release notes 要点（repo-wide，标 inherited 的条目属 packages/ai）

- **0.84.3**（08-24）：**Breaking**：`GoogleThinkingLevel` 改名 `GoogleApiThinkingLevel` 并新增 `ResolvedGoogleThinkingLevel`；模型目录新增（ZAI 中国区含 GLM-4.6V 视觉、Qwen Token Plan `deepseek-v4-pro-0813`、Anthropic 服务端拒答回退、vLLM/Qwen/SGLang/llama.cpp 思考预算字段）；xAI 切 Responses API + Grok 4.6 默认；各适配器默认 User-Agent 变更；一批目录正确性修复（Z.AI GLM-5.3 reasoning 元数据、Xiaomi MiMo V2 下架、Kimi cached_tokens 计量、Google thinkingLevelMap 等）。
- **0.84.4**（08-28）：新增实验性 `deepseek-v4-flash-vision-exp` 模型、`detectSupportedImageMimeTypeFromFile()` 公开导出；修复 OpenAI 兼容层 thinking signature 重复序列化、Cloudflare AI Gateway workers-ai 目录、OpenRouter reasoning 控制、Mistral 分片 tool call、Vertex HttpsProxyAgent 代理崩溃等。
- **0.85.0**（09-04）：新增 OpenAI 兼容 `vllmPriority` / `supportsMaxOutputTokens` 模型设置；修复 provider 流事件序列不兼容与自定义 tool-call delta；下架 Grok Build 0.1；Fireworks GLM 适配器修正；NO_PROXY 根域/子域匹配；代理 HTTP CONNECT 隧道。**发布事故**：误发布内部实验子路径与依赖导致 SDK import 失败。
- **0.85.1**（09-05）：新增 **GPT-6 Astra** 模型目录（OpenAI API key 与 Codex 订阅）；**修复 0.85.0 的 SDK import 事故**（experimental `client` / `experimental/plugin` 子路径改回 source-only）；GPT-5.6+ Responses 长 prompt-cache TTL 修复。

### 宿主采用面与兼容性观察

- `llm-pi-ai` 源码 import 面（grep 18 处命中）：根导出 `isContextOverflow`、`createProvider`、`createModels`、`getSupportedThinkingLevels` 与类型 `Api` / `AssistantMessage` / `Usage` / `Provider` / `Transport` / `ThinkingBudgets` / `CacheRetention` / `ChatTemplateKwargValue` / `ModelThinkingLevel` / `Auth*` / `Context` / `Message` / `Tool` 等；子路径 `@earendil-works/pi-ai/api/{anthropic-messages,openai-completions,openai-responses}.lazy` 与 `@earendil-works/pi-ai/providers/all`（`builtinProviders` / `getBuiltinModels` / `getBuiltinProviders`）。
- 子路径存在性核验：上述 8 个 `.js` + `.d.ts` 文件在 0.85.1 tgz 中**全部仍存在**（Test-Path 全 True）。
- 0.84.3 的 Breaking 改名（`GoogleThinkingLevel`）与 `cloudflare-gateway` 在宿主 `llm-pi-ai` 源码中 **零引用**（grep 无命中）。
- 限制声明：按只读红线未运行 typecheck/build，类型级兼容**未经编译验证**；本节均为结构性证据。

## 升险评估

**a) `^0.84.2` 的 semver 语义**：按 node-semver caret 规则，0.x 下 caret 锁定最左非零段（minor），故 `^0.84.2` = **`>=0.84.2 <0.85.0`**（docs：https://github.com/npm/node-semver）。因此 **0.84.3 / 0.84.4 在宿主与外部四插件的声明范围内**；**0.85.0 / 0.85.1 不在任何一方范围内**。当前 lockfile 实锁 0.84.2，范围内新版本也不会自动流入，需显式 lockfile 刷新。另注意 `pnpm-workspace.yaml:52` 豁免条目是**精确 `@0.84.2`**——若刷新到 0.84.4，必须同步改该行，否则新版本将重新落入发布时间延迟策略。

**b) 仅强改 lockfile 到 0.85.x 不可行**：宿主 `llm-pi-ai` 自身声明就是 `^0.84.2`（package.json:44），lockfile 解析到 0.85.x 会与 manifest 不同步（CI frozen-lockfile 直接失败）；上 0.85.x 必须先改宿主声明 = 改码。同时外部四插件仍 `^0.84.2`，0.85.x 不满足其范围，解析必然形成 **0.85.x（宿主侧）+ 0.84.2（插件侧）双实例树**：两份模型目录、两份模块实例，profile node_modules fallback 的 first-resolvable 命中在双版本并存下不再唯一（取决于解析顺序，可能命中任一副本）；0.85.0 专门修复的"provider 流事件序列不兼容"这类运行时行为在两副本间不一致，类型身份与目录数据随之漂移。结论：b 场景是三输——要改码、还分裂树、且外部插件拿不到任何收益。

**c) 维持 0.84.2 的代价 = 模型目录滞后**：0.84.2（08-14）之后上游目录新增 GPT-6 Astra、`deepseek-v4-flash-vision-exp`（实验）、`deepseek-v4-pro-0813`、GLM-4.6V（ZAI 中国区）、Qwen3.8 Flash、Grok 4.6 默认切换等，并下架失真条目（Xiaomi MiMo V2、Grok Build 0.1）；`pnpm-workspace.yaml:50-51` 注释自证"目录更新随 pi-ai 新版本走、等待发布龄会毁掉升点的初衷"——即宿主当年豁免发布龄所图的收益面就是目录新鲜度，实锁停留越久该收益衰减越多。但目录滞后是可量化、非破坏性的代价，且 0.84.3/0.84.4 仍在声明范围内，随时可低成本刷新。

**d) 结论与触发条件**：维持现状（实锁 0.84.2）正确——0.85.0 发布事故刚过（0.85.1 是其修复版，09-05 发布，截至今日仅 2 天）、外部四插件未跟进 `^0.85`、0.85.x 的新增面（`./utils/*`、`cloudflare-ai-binding`）宿主均未使用。升级触发条件（满足其一再动，且宿主 + 外部插件协同改）：(1) **外部插件发版声明 `^0.85`** 后，一次性协同升级宿主 `package.json:44`、lockfile、`pnpm-workspace.yaml:52` 豁免精确版本；(2) 出现**宿主必需且仅 0.85.x 携带**的模型目录条目（如 GPT-6 Astra 接入需求）；(3) 过渡选项：仅需 0.84.3/0.84.4 的目录修复时，在声明范围内刷新 lockfile（不改任何声明行），同步更新第 52 行豁免精确版本，成本最低。任何升级后须补 typecheck + 相关快照测试（本轮只读未执行）。

## 一句话结论

维持 0.84.2 实锁是当前正确决策——上游 latest 0.85.1 虽已修复 0.85.0 的发布事故但仅发布 2 天、外部四插件全部仍声明 `^0.84.2`（0.85.x 不在其解析范围）、强改 lockfile 必然制造宿主 0.85.x + 插件 0.84.2 的双版本树；升级等待"外部插件发版声明 `^0.85`"或"出现仅 0.85.x 携带的必需模型目录条目"，中途需要目录修复就先做声明范围内的 0.84.4 刷新（同步改 `pnpm-workspace.yaml:52` 豁免精确版本）。

## 证据 URL 列表

- https://registry.npmjs.org/@earendil-works/pi-ai/latest （HTTP 200，0.85.1 packument：repository/dist/deps/exports/provenance）
- https://registry.npmjs.org/@earendil-works/pi-ai/-/pi-ai-0.85.1.tgz （HTTP 200，curl exit 0，解包对比用）
- https://api.github.com/repos/earendil-works/pi/releases?per_page=30 （HTTP 200，v0.85.1 / v0.85.0 / v0.84.3 body）
- https://api.github.com/repos/earendil-works/pi/releases/tags/v0.85.0 （HTTP 200）
- https://api.github.com/repos/earendil-works/pi/releases/tags/v0.84.4 （HTTP 200）
- https://github.com/earendil-works/pi/releases/tag/v0.85.1 （人类可读入口）
- https://github.com/earendil-works/pi （registry repository 字段指向，pi-ai 位于 `packages/ai`）
- https://github.com/npm/node-semver （caret ranges：`^0.84.2` = `>=0.84.2 <0.85.0`）

## 生成时间戳

2026-09-07T10:39:47+09:00（UTC 2026-09-07T01:39:47Z）
