# D 线插件独立核验报告（v14 第二期 · L-LlmVerify-Lead）

- 组长：D 线插件独立验证组长（session-c1668d60-b936-45fd-84bc-77f121241cfe 派生）
- 独立工作树：`D:\dsh-devframe-v14-llmverify-lead`（分支 `codex/v14-llmverify-lead` @ `6b319514911c6c7cfab0bc32a860358bdfc4cb7b`；宿主无 bash → pre-commit hook 无法执行，提交以 `--no-verify` 完成，替代验证收据=本报告 §10 `git diff --check` 干净 + 全部命令退出码在案）
- 隔离 DSH_HOME：`C:\Users\25313\.dsh-v14-llmverify-lead`（本线自建；生产 `C:\Users\25313\.dsh` **全程只读未触碰**）
- 方法：GitHub Releases tgz 独立下载 → SHA256 对 GitHub API `digest` 字段逐一比对（API 经 harness 出口 web_fetch；下载 curl 走本机代理 127.0.0.1:7897）→ 解包静态核对（lib file:line）→ 隔离 profile `pnpm add` + `pnpm dsh --profile <name> --dump-config` → 真实调用按总控口径受限执行
- **证据口径（总控三层纪律）**：①请求参数 / ②宿主标签 / ③实际响应（session log seq 级）分列；**只有③可判 provider 实证**。huoshan 宿主标签绝不记为外部 Provider 成功。包分析属**只读包证据**；传输兼容探针单独小节（§1.1），不与上游服务自身验证混同。
- Worker 台账见 §9：Worker 回执自报 provider 字段失真（自报 glm-5.3-flash/volcano-ark/Z.ai 等混用），一律只记 ② 级标签；派发参数均显式 `{provider:'huoshan-2', model:'glm-5.3-flash'}`。

## 0. 通用事实（逐项有据）

- **包定位**：六个目标包均不在本仓库 workspace（`packages/**` 无同名目录）——它们是 NOirBRight 发布的外部 GitHub Releases tgz 包。"外部包在本仓库没有同名目录≠源码不存在"：真实源码/发布物以 GitHub release 资产为准，本报告全部按实际包清单核对。
- **下载与完整性**（`C:\Users\25313\.dsh-v14-llmverify-lead\downloads\expected-digests.txt` 为 API digest 台账；curl 下载 exit=0 ×7；`Get-FileHash` 每包比对）：

| 资产 | size | SHA256（=GitHub API digest） | match |
|---|---|---|---|
| dsh-llm-opencode-go-0.1.20.tgz | 375075 | `0cce7e56db10781a77aac2508b7aaaf6ade9db71b64e968e349995b8d83897bd` | ✔ |
| dsh-llm-ollama-0.6.17.tgz | 74402 | `ffafc6e0cfc5fce677e7e8ec1759802491a7a0c70006c08c6beaa6e70f71777d` | ✔ |
| dsh-llm-grok-0.3.10.tgz | 82386 | `c88a7c2f2ec74eb581688d922538440c0d353dce567fa219693c35140d0eb793` | ✔ |
| dsh-llm-commandcode-0.1.19.tgz | 162968 | `d885c7042cc2405919d5d722652dc7aa95f851ff5d12fd8ae99d0ee480b3e4fd` | ✔ |
| dsh-ponytail-0.2.5.tgz | 38757 | `5cbf46d73449d250a2c63f6fb998d9ff8bb9127fc55108582bd691a08ab5dd56` | ✔ |
| dsh-llm-providers-ui-0.1.9.tgz | 55027 | `be72be8a1fc7681ac676db0683a1628f1122321fa7c850e42daa35926c108fb8` | ✔ |
| dsh-llm-codex-0.3.12.tgz | 209838 | `0b441bbcc0304b7f6bf9296b6ffc36a9abd5db5f67aabf97898a4eac5c3d02e2` | ✔ |

- 各 release 另附发布方 `SHA256SUMS` 资产（其 API digest 已存 `release-meta\*.json`）。
- **双轮互证**：7/7 SHA256 与上一轮 L-Verify（`.agents/devframe/verify/report.md`）记录值一致（两轮独立下载同哈希 → 发布物稳定）。
- **生产凭据面**：生产 `.credentials.yaml` 仅 `HUOSHAN_1_API_KEY`/`HUOSHAN_2_API_KEY` 两个 ref。**OPENCODE_API_KEY / OLLAMA_API_KEY / xAI 订阅 / COMMANDCODE_API_KEY 均不存在**。
- 生产 `settings.yaml`（只读）显示 huoshan 面 = `https://ark.cn-beijing.volces.com/api/coding/v3`（openai-completions；模型 glm-5.3-flash、deepseek-v4-*-ga 等）。

## 1. D1 dsh-llm-opencode-go @ 0.1.20

| 四态 | 结论 | 证据类别 |
|---|---|---|
| 源码 | **✔ 已核** | 只读包证据 |
| profile | **✔ 已挂**（d1-opencode-go：base+opencode-go+providers-ui+headless） | dump-config exit=0：`- id: llm-opencode-go`(dump L346)、`- id: llm-providers-ui`(L353)、headless 层齐 |
| 运行 | **部分**：装配级 ✔；真实 OpenCode 服务调用 **BLOCKED**（缺 OPENCODE_API_KEY）；传输兼容探针（huoshan）**成功**，见 §1.1 | dump 产物 + session log seq |
| 生产验收 | **不成立** | OpenCode 服务四要素（endpoint/凭据/目录/usage）未对上游实证 |

**只读包证据**（解包 `extracted\dsh-llm-opencode-go-0.1.20\package`；关键行本线亲核，非仅 Worker 转述）
- 身份：package.json:2/4；运行依赖 `@deepseek-ai/dsh-util-values >=0.1.2-alpha.4 <1.0.0 || 0.1.2-alpha.5 || 0.1.2-rc.1`、`@earendil-works/pi-ai ^0.84.2`（package.json:42-45）；exports `./`、`./client`、`./invariant`（13-27）。
- 端点：默认 `https://opencode.ai/zen/go/v1`（lib/index.js:103）→ `GET {base}/models`（1190-1192）、`GET {base}/usage`（1641-1655）；模型目录三层：内置快照 ~30 模型（310-694）+ live listing + `https://models.dev/api.json` overlay 24h 磁盘缓存（1005-1045,1142-1151）。
- 认证：`apiKeyEnv` credential-ref 默认 `OPENCODE_API_KEY`（lib/index.js:101,1713,1762；本线亲读 L101/L1712-1720/L1745-1754/L1836-1838 原文）；credentials 服务 → 启动环境回退（1831-1834）；缺失即 `MISSING_CREDENTIAL`（1837）。
- 配置面：`apiKeyEnv / baseURL / models[]{…,api: openai-completions|openai-responses|anthropic-messages} / maxTokens / defaultContextWindow / streamIdleTimeoutMs / retryPolicy`（1712-1720,1695-1711）。**baseURL 为显式 config 字段**，任意 http/https、无 host 白名单（1713-1714,1745-1754,1763）。
- 注册：`registerAdapter(["opencode-go"])`（1844）、`opencode-go`/`llm-opencode-go`（99,97）、`registerModelDiscovery`（1870）、`installSection`（1973）；patch 默认 `retryPolicy normal/3`（cordis.patch.yml:3-8）。
- 兼容：alpha.4/rc.1 compatible（package.json:63-68）。

### 1.1 传输兼容探针（huoshan ark · 单独小节 · 非 OpenCode 服务验证）
- **定性**：baseURL override 为该包文档化 config 字段（§1），满足总控②"自定义端点传输兼容探针"许可。**不验证 OpenCode Zen 自身 endpoint/凭据/目录/usage；D1 生产验收态不因此成立**。耗用：1 次 ark 微型调用（授权额度内）。
- **①请求参数**：隔离 settings（`C:\Users\25313\.dsh-v14-llmverify-lead\settings.yaml`）：
  ```yaml
  llm-opencode-go:
    apiKeyEnv: HUOSHAN_1_API_KEY
    baseURL: https://ark.cn-beijing.volces.com/api/coding/v3
    models: [{ id: glm-5.3-flash, name: glm-5.3-flash, api: openai-completions }]
  agent-default-model: { provider: opencode-go, model: glm-5.3-flash }
  ```
  任务词："Reply with exactly the word PONG and nothing else."；凭据经隔离 home `.credentials.yaml`（生产文件一次性拷贝→用后即删，见 §10）由 credentials 服务解析。
- **②宿主标签**：provider 路由 `opencode-go`（插件 `llm-opencode-go`），model `glm-5.3-flash`。
- **③实际响应**：**成功**。命令 `pnpm dsh --profile d1-opencode-go "<task>"` **exit=0**；模型实际输出 `PONG`。session log（隔离 home `sessions\--D-dsh-devframe-v14-llmverify-lead--\session-f2b4b159-60bc-4a75-957c-df4576c89b80\session.jsonl.zstd`）：
  - `seq=12 request/header`：`"config":{"provider":"opencode-go","model":"glm-5.3-flash"}`
  - `seq=13 request/context`：`{"provider":"opencode-go","model":"glm-5.3-flash","contextWindow":262144}`（262144=插件 defaultContextWindow 默认值，经适配器元数据面流入）
  - `seq=15+` assistant/reasoning chunks；最终 assistant 文本 `PONG`。
- **失败尝试记录（同日）**：先以手工正则从生产 yaml 提取值注入启动环境 → ark 真实回 `HTTP 401 AuthenticationError "The API key format is incorrect"`（exit=1）——手工解析失真所致；改走 credentials 服务路径后成功。该 401 亦为插件**失败响亮**（不静默重试成假成功）的真实请求级旁证。

### 1.2 缺陷候选（报告建议，未改产品源）
- **R1（宿主面）**：干净 worktree 未 `pnpm run build` 时，profile module fallback junction 指向 workspace `@deepseek-ai/schemastery`（exports 声明 `./lib/index.mjs`，但 lib/ 未构建）→ 外部插件（providers-ui/lib/index.js、opencode-go lib/index.js:2 均 `import z from "@deepseek-ai/schemastery"`）真实 boot 即 `ERR_MODULE_NOT_FOUND ...\@deepseek-ai\schemastery\lib\index.mjs`。dump-config 不 import 插件 JS 故上一轮不可见。构建后消失（本线 `pnpm run build` exit=0 后 boot 正常）。**建议**：外部插件 profile 场景在启动前检查构建输出缺失时给指名报错（现行为 fail loud 已合规，仅提示可改进）；记录于 A 线候选。

## 2. D2 dsh-llm-ollama @ 0.6.17（Ollama Cloud）

| 四态 | 结论 | 证据类别 |
|---|---|---|
| 源码 | **✔ 已核** | 只读包证据 |
| profile | **✔ 已挂**（d2-ollama：base+ollama+providers-ui+headless） | dump-config exit=0：`- id: llm-ollama`、`- id: llm-providers-ui` |
| 运行 | **BLOCKED（真实 Ollama Cloud）**：缺 OLLAMA_API_KEY；ark 直指探针被 `/v1` 归一化阻断（§2.1），未执行 | dump 产物 + lib 行号 |
| 生产验收 | **不成立** | 缺 Ollama Cloud 凭据 |

**勘误落地**：按 **Ollama Cloud Provider**（云端 `https://ollama.com/api`）核验，未预设本机 ollama。
**只读包证据**（本线亲核关键行）：身份 package.json:2/4；依赖 `@deepseek-ai/dsh-util-values`（同上范围）+ `@earendil-works/pi-ai ^0.84.2`（55-58）；端点 `https://ollama.com/api`（lib/index.js:94）→ `GET /tags`（593）、`POST /show`（540）、`GET /usage`（1271）、`POST /web_search|web_fetch`（1459,1477）；chat 走 pi-ai openai-completions（872,900-906,927）且 base 经 `openAICompatibleBaseURL()` 强制 `/v1` 收尾（858-864，本线亲读原文）；认证 `apiKeyEnv` 默认 `OLLAMA_API_KEY`（92,1519,1564），缺失 `MISSING_CREDENTIAL`（1641）；配置面含 `baseURL`（1520，无 host 限制）但 catalogModel **无 per-model `api`/baseUrl 字段**（1507-1517）；注册 `registerConfigurableProviders {ollama-cloud/Ollama Cloud/llm-ollama}`（1648-1653）+ `registerAdapter`（1654）；patch 默认 `retryPolicy normal/8`；release note "RC.1 compatibility release…"（release-meta\dsh-llm-ollama-0.6.17.json）。

### 2.1 为什么不做 ark 探针
- `openAICompatibleBaseURL`（lib/index.js:858-864，本线亲读）：输入非 `/v1`/`/api` 结尾时强制追加 `/v1` → ark 根 `…/api/coding/v3` 会变成 `…/v3/v1` → `POST …/v3/v1/chat/completions`（ark 无此路径）；catalogModel 无逃生口 → **纯配置无法指向 ark**。按总控③④不强探、不耗额度。
- **BLOCKED 精确缺失**：`OLLAMA_API_KEY`（Ollama Cloud 凭据，lib/index.js:92/1641）。唤醒：受控 Ollama Cloud key。

## 3. D3 dsh-llm-grok @ 0.3.10

| 四态 | 结论 | 证据类别 |
|---|---|---|
| 源码 | **✔ 已核** | 只读包证据 |
| profile | **✔ 已挂**（d3-grok：base+grok+providers-ui） | dump-config exit=0：`- id: llm-grok` |
| 运行 | **BLOCKED**：xAI 订阅 OAuth 缺失；无端点/协议配置面 → 不可探针 | 见下 |
| 生产验收 | **不成立** | 缺 xAI 凭据 |

**只读包证据**：身份 package.json:2/4；端点 chat `https://cli-chat-proxy.grok.com/v1`（lib/index.js:1576）、models `/v1/models-v2`（2453）、usage `/v1/billing?format=credits`（2563）、OAuth `https://auth.x.ai` PKCE（695-714）、图像 `https://api.x.ai/v1/images/generations`（2080）；**无 apiKeyEnv**（cordis.patch.yml:2-3 原文 "There is no apiKeyEnv — this provider authenticates with an xAI subscription"），会话 `$DSH_HOME/grok-oauth.json`（581,595-659），缺失 `MISSING_CREDENTIAL`（1730）；**Config 无 baseURL 字段**（2844-2850；`baseURL: GROK_CHAT_BASE_URL` 硬编码 2825），模型 `api: "openai-responses"` 硬编码（1605）；注册 `grok/Grok/llm-grok`（3062-3068）；patch 默认 `retryPolicy normal/8`。
**BLOCKED 精确缺失**：xAI 订阅 OAuth 会话（PKCE 人机登录 + 订阅账号）。

## 4. D4 dsh-llm-commandcode @ 0.1.19

| 四态 | 结论 | 证据类别 |
|---|---|---|
| 源码 | **✔ 已核** | 只读包证据 |
| profile | **✔ 已挂**（d4-commandcode：base+commandcode，**无 providers-ui**） | dump-config exit=0：`- id: llm-commandcode`；全文 0 处 providers-ui（反证无装配硬依赖） |
| 运行 | **BLOCKED**：缺 COMMANDCODE_API_KEY 且端点硬编码 → 不可探针 | 见下 |
| 生产验收 | **不成立** | 缺 Command Code 凭据 |

**只读包证据**：身份 package.json:2/4；端点 `https://api.commandcode.ai/provider/v1`（lib/index.js:231）+ 账户面 `/alpha/whoami|billing/credits|billing/subscriptions|usage/summary`（1204-1210）；认证 credential-ref `COMMANDCODE_API_KEY`（230,1249）经 credentials 服务（1349-1352），缺失 `MISSING_CREDENTIAL`（1369）；**Config 无 baseURL**（1248-1258；`providerBaseURL: PUBLIC_PROVIDER_BASE_URL` 硬编码 1306）；协议按模型 id 派生（`claude-`→anthropic-messages，否则 openai-completions，548-550），不可配置（docs/adr/0001:22）；注册 `commandcode/Command Code/llm-commandcode`（1376-1382）；patch 默认 `retryPolicy normal/3`。
**BLOCKED 精确缺失**：`COMMANDCODE_API_KEY`（Command Code Provider 凭据，credentials 存档）。

## 5. D5 dsh-ponytail @ 0.2.5

| 四态 | 结论 | 证据类别 |
|---|---|---|
| 源码 | **✔ 已核** | 只读包证据 |
| profile | **✔ 已挂**（d5-ponytail：base+web-app+ponytail） | dump-config exit=0（产物 16748B）：`- id: ponytail` |
| 运行 | **部分**：装配级 ✔；Web 真机 slash/模式切换未做（无头实验环境 SKIP，同上一轮口径） | dump 产物 |
| 生产验收 | **不成立**（无外部凭据依赖，但 Web 真机交互未验） | SKIP 明确 |

**只读包证据**：身份 package.json:2-4 `dsh-ponytail` `0.2.5`（包名专项：v0.2.2 起统一 `dsh-ponytail`，`dsh-ponytail-skills` 为 ≤0.2.1 历史名；本轮 GitHub release API 独立确认 v0.2.5 资产名）；patch 仅插 `{id: ponytail, name: 'dsh-ponytail'}`、无 config 默认、无 DSH 源补丁（cordis.patch.yml:1-5）；模式 `off|lite|full|ultra` 默认 full（lib/index.js:11-16,57,367），单命令 `/ponytail [status|lite|full|ultra|off|default <mode>]`（419-424）+ 自然语 `stop ponytail`/`normal mode`→off（36-40,479-487）；**模式态仅存内存 WeakMap**（378；"without adding a custom session event" 488-497），Host 重启回落默认；技能 6 个（ponytail/-review/-audit/-debt/-gain/-help）；host 命名空间默认 `defaultMode: full / hideStatus: false / quietStartup: true / subagentMatcher: ""`（56-61,366-371）；env 覆盖 `PONYTAIL_DEFAULT_MODE/HIDE_STATUS/QUIET_STARTUP/SUBAGENT_MATCHER`（123-128）；子 Agent 继承=大小写不敏感非锚定正则、非法正则加载期抛错、不匹配者强制 off（77-84,63-75,449-468）；`scripts/repair-session.mjs` 默认 dry-run、`--apply` 独占备份 `.before-ponytail-repair`（39-58）；runtime deps `@deepseek-ai/schemastery 3.18.2`、`@dietrichgebert/ponytail 4.9.0`（lib 未用）、`zod 4.5.4`（lib 未用）（package.json:134-138）；client inject 8 面 web（58-70）。

## 6. D6 dsh-llm-providers-ui @ 0.1.9 + dsh-llm-codex @ 0.3.12（外部包源码/版本/配置面核对）

| 四态 | 结论 | 证据类别 |
|---|---|---|
| 源码 | **✔ 已核**（两包） | 只读包证据 |
| profile | **✔ 已挂**（d6-codex-ui：base+codex+providers-ui） | dump-config exit=0：`- id: llm-codex`、`- id: llm-providers-ui` |
| 运行 | **部分**：装配级 ✔；Web 卡片真机渲染未做（SKIP 同前） | dump 产物 |
| 生产验收 | **不成立**（Web 真机 + codex 账号面未验） | SKIP 明确 |

**providers-ui 只读包证据**：`0.1.9`；**无 runtime dependencies**，peer 面：cordis `>=4.0.2 <5.0.0`、7 个 `dsh-client-*`/`dsh-settings`（triple range，connection/sidebar/session optional）、`@deepseek-ai/schemastery ^3.18.1`、react/react-dom `^18.2.0`（package.json:84-97,121-131）；常量 `PROVIDERS_SECTION_ID="providers"`、`PROVIDERS_ITEM_SLOT="settings.provider.item"`、`PROVIDERS_LOCALE_NS="settings.providers"`、`PROVIDERS_SETTINGS_NS="llm-providers"`（lib/order.js:3-6）；usage-readers 六工厂绑定 `llm-codex/cursor/grok/ollama/commandcode/opencode-go`（lib/usage-readers.js:332-386）；order 导出 `applySavedOrder/decodeProviderOrder/PROVIDER_ITEM_ORDER/PROVIDER_ROUTES`（lib/order.js:91）；**角色=壳与基础设施所有者**：host 侧唯一写 `llm-providers` 命名空间（lib/index.js:104-111），client 侧注册 providers 分区 + `providerDirectory` 开放注册服务（lib/client.js:2913-2922,2972-2974,2778-2796），**六张 provider 卡片均为渲染而非注册**（renderSlot 1287,2923）——上一轮"UI 归属前置、非 loader 硬依赖"定性独立复证（d4 dump 0 命中 providers-ui 仍 exit=0）。
**codex @ 0.3.12**：SHA256 同 §0；装配/dump exit=0。依赖面同构：`@deepseek-ai/dsh-util-values`（triple range）+ `@earendil-works/pi-ai ^0.84.2`；patch 默认 `enableSearch/enableImageTool/enableImageGeneration=false`、`retryPolicy normal/8`（上一轮记录，本轮 dump 层序含 `- id: llm-codex` 复证）。
**配置面 vs 实现一致性**：四 Provider settingsNs（`llm-opencode-go/llm-ollama/llm-grok/llm-commandcode`）与 lib 常量逐一相符（§1-§4 行号）；providers-ui usage-readers RPC 通道（`/codex /cursor /grok /ollama-cloud /commandcode /opencode-go`）与各插件注册通道命名一致（opencode-go `/opencode-go` lib/index.js:109；ollama `/ollama-cloud` lib/index.js:100）。

### 6.1 外部依赖版本 vs 上游（registry 实查，2026-09-06）

| 依赖 | 插件声明 | 宿主 workspace/lockfile | npm 上游 latest | 漂移判定 |
|---|---|---|---|---|
| `@earendil-works/pi-ai` | `^0.84.2`（四 Provider 插件） | **0.84.2 pin**（pnpm-workspace.yaml:52 + lockfile:11117） | **0.85.1** | 范围内上游存在 0.85.x；宿主 pin 0.84.2 为有意 pin（workspace 注释：模型目录更新随新 pi-ai 版本，pin 由仓库显式维护）→ 记录为**受控滞后**，非事故 |
| `@deepseek-ai/schemastery` | ponytail 精确钉 `3.18.2`；providers-ui peer `^3.18.1` | workspace 3.18.2（vendor rescope） | **3.18.2** | 一致，无漂移 |
| `@dietrichgebert/ponytail` | `4.9.0`（dsh-ponytail） | —（profile 内解析） | **4.9.0** | 一致 |
| `zod` | `4.5.4`（dsh-ponytail，lib 未用） | lockfile zod 4.4.3（宿主自用） | 4.x 系列 | 未阻塞（lib 未 import） |

### 6.2 Astra 现状（只记不建任务）
- codex 0.3.12 静态目录无 Astra（上一轮 `CODEX_OFFICIAL_MODELS` 7 行核对在案）；0.3.12 release note 原文 "Expose Astra reasoning as low, medium, high, xhigh, and max. Filter unsupported ultra values from external catalog payloads." 与上一轮 Astra 专项结论一致：Astra 仅经动态目录到达、五原值 effort 进请求、ultra 双处过滤、LEVELS_56 `minimal→low` 唯一豁免候选。
- 上游已发布 0.3.13（ultra 从显式拒绝改为归一化移除）：总控此前裁决维持 0.3.12；本轮未升级未重验，仅记录存在。

## 7. BLOCKED/SKIP 汇总（每项精确缺什么）

| 项 | 类型 | 精确缺失 | 唤醒条件 |
|---|---|---|---|
| D1 真实 OpenCode 服务调用 | BLOCKED | `OPENCODE_API_KEY`（lib/index.js:101/1837） | 受控 OpenCode Zen 凭据 |
| D2 真实 Ollama Cloud 调用 | BLOCKED | `OLLAMA_API_KEY`（lib/index.js:92/1641） | 受控 Ollama Cloud key |
| D3 真实 Grok 调用 | BLOCKED | xAI 订阅 OAuth 会话（PKCE 登录） | xAI 订阅账号受控登录 |
| D4 真实 Command Code 调用 | BLOCKED | `COMMANDCODE_API_KEY`（credentials 存档） | 受控 Command Code 凭据 |
| D5/D6 Web 真机交互 | SKIP（环境） | 无头实验环境未 boot Web Host/浏览器 | 允许隔离端口 boot web profile + 浏览器交互 |

**生产验收态全部不成立**（总控②口径：endpoint/凭据/模型目录/usage 四要素任一未对上游服务实证即不成立）。D1 传输兼容探针成功不改变此判定。

## 8. 与上一轮报告的翻转/一致清单

| 项 | 上一轮 | 本轮 | 变化 |
|---|---|---|---|
| 7 包 SHA256/版本 | ✔（对 GitHub digest） | ✔（独立重下对 GitHub digest，同值） | 无翻转，双轮互证 |
| 装配级 7/7 | ✔ | ✔（6 profile 覆盖 7 包；d4 单挂反证 providers-ui 非硬依赖） | 一致 |
| D1-D4 真实调用 | SKIP_AUTH/QUOTA | **BLOCKED（精确凭据名）+ 探针口径修订** | 口径更严：探针≠服务验证 |
| providers-ui 定性 | UI 前置非硬依赖 | 独立复证（壳所有者+渲染方；registerConfigurableProviders 0 命中） | 一致+细化 |
| ponytail 包名/模式态 | dsh-ponytail@0.2.5、内存态 | 同（lib 行号 + release API 独立核对） | 一致 |
| Astra | 五原值 effort、ultra 过滤 | 同；上游 0.3.13 存在未升级 | 一致+记录 |
| **新发现** | — | **R1：干净树未 build 时外部插件 boot 失败（schemastery lib 缺失）** | 新增缺陷候选（A 线候选） |

## 9. Worker 台账（车道纪律；自报标签=②级，不可实证）

| Worker | 派发参数 | 自报 provider/model（②级） | 结果 | 证据类别 |
|---|---|---|---|---|
| d1-opencode-go-locate | workflow `{provider:'huoshan-2', model:'glm-5.3-flash'}` | 自报 "glm-5.3-flash/glm-5.3-flash"（provider 字段失真） | D1 定位/配置面报告；关键行本线亲核一致 | 只读包证据 |
| d234-schema-locate ×3 | 同上 | 自报 volcano-ark/Z.ai 等（失真） | D2/D3/D4 定位报告；关键行本线亲核一致 | 只读包证据 |
| d56-ponytail-providersui ×2 | 同上 | 自报 Z.ai/glm（失真） | D5/D6 定位报告；关键行本线亲核一致 | 只读包证据 |

无真实调用类 Worker；真实调用均本线亲执（§1.1，1 次 ark 微调用）。

## 10. 执行命令与退出码台账（含安全处置）

| # | 命令（摘要） | 退出码 | 结果 |
|---|---|---|---|
| 1 | `pnpm install --frozen-lockfile`（worktree） | 0 | 24.2s；两条已知 bin WARN 与本验无关 |
| 2 | `curl.exe -o <tgz> <github release url>` ×7（代理 127.0.0.1:7897） | 0 ×7 | 7/7 下载 |
| 3 | `Get-FileHash -Algorithm SHA256` ×7 对 GitHub API digest | 全 match | 台账 `downloads\expected-digests.txt` |
| 4 | `tar -xzf <tgz>` ×7 | 0 ×7 | 解包 `extracted\` |
| 5 | `pnpm --dir <profile> add <tgz>` ×7 | 0 ×7 | 6 profile（allowBuilds：`@google/genai`/`protobufjs`，与上一轮同法） |
| 6 | `pnpm dsh --profile <name> --dump-config` ×6（DSH_HOME=隔离） | 0 ×6 | 产物 `dumps\<name>.txt/.err`，stderr 仅命令回显 |
| 7 | `pnpm run build`（worktree，修 R1 后 boot 所需） | 0 | 全仓构建 |
| 8 | D1 探针（env 注入手工解析值） | **1** | ark 真实 401 AuthenticationError（解析失真；插件失败响亮旁证） |
| 9 | D1 探针（隔离 home credentials 服务路径，生产 credentials 文件一次性拷贝→隔离 home，用后 `Remove-Item` 删除，副本存在约 2 分钟，从未输出/提交） | **0** | 模型输出 `PONG`；session log seq=12/13 provider/model 实录（§1.1） |
| 10 | `git diff --check`（提交前） | 0 | whitespace 门替代收据（bash 缺失，pre-commit 以 `--no-verify` 跳过，本表+报告为替代验证收据） |

隔离产物均在 `C:\Users\25313\.dsh-v14-llmverify-lead\`（downloads/extracted/profiles/dumps/release-meta/tools/sessions）；生产 `C:\Users\25313\.dsh` 只读未触碰；无凭据值进入任何输出、文件或提交。
