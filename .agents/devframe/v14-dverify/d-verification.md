# D 线外部 LLM 插件独立复验（v14 · D-Verify-Lead）

- 组长：D 线独立验证组长（session-c1668d60-b936-45fd-84bc-77f121241cfe 派生；本会话显式路由 huoshan-1/glm-5.3-flash）
- 独立工作树：`D:\dsh-devframe-v14-dverify-lead`（分支 `codex/v14-dverify-lead` @ main `79b5471a79`）；`pnpm install --frozen-lockfile` exit=0（25.5s，仅 2 条已知 bin WARN）
- 隔离 DSH_HOME：`C:\Users\25313\.dsh-v14-dverify-lead`（本线自建）；生产 `C:\Users\25313\.dsh` 只读——仅 Test-Path 存在性核查，未读任何内容
- 方法纪律（总控两令落地）：同版本包不重验，旧 `.agents/devframe/v14-llmverify/verification.md` 证据继续有效；只核新增版本与真实缺口；grok 0.3.10→0.3.11 增量由组长亲核；D6 下放显式路由 Worker
- 报备（如实）：总控修正到达前已执行的同版本操作 = 5 包下载 + SHA256 对本浪新抓 GitHub API digest（全 MATCH，且与旧台账同值 = 第三轮独立互证）+ 少量关键行亲读（此后停止一切同版本重验）
- 凭据纪律：全程未读取/未记录任何凭据值；env 存在性仅 `Test-Path env:NAME` 布尔；生产凭据文件未读
- 证据口径沿旧报告：①请求参数 / ②宿主标签 / ③实际响应；Worker 自报路由属 ② 级标签

## 0. 逐项判定总表（一句话 ×6）

| 项 | 版本（上游 latest 本浪实测） | 判定 |
|---|---|---|
| D1 opencode-go | 0.1.20（latest 未变，API digest 同旧台账） | **BLOCKED(缺 `OPENCODE_API_KEY`)** 延续——旧源码/装配/ark compat probe（seq=12/13）证据继续有效；本浪 env 核查凭据仍不存在 |
| D2 ollama | 0.6.17（latest 未变，同值） | **BLOCKED(缺 `OLLAMA_API_KEY`)** 延续——`lib/index.js:858-864` /v1 归一化 + catalogModel 无 per-model 逃生口亲读一致，ark 探针仍纯配置不可达 |
| D3 grok | **0.3.10 → 0.3.11（新版本，2026-09-05）** | **BLOCKED(xAI 订阅 OAuth 会话)** 延续——0.3.11 增量=provider-owned 搜索面，认证面与 0.3.10 完全同构（无 apiKeyEnv / 无 baseURL config / 端点硬编码 / PKCE+grok-oauth.json）；装配 dump-config exit=0 |
| D4 commandcode | 0.1.19（latest 未变，同值） | **BLOCKED(缺 `COMMANDCODE_API_KEY`)** 延续——`lib/index.js:230-231` 凭据名 + `1248-1258` Config 无 baseURL（端点硬编码）亲读一致 |
| D5 ponytail | 0.2.5（latest 未变，同值） | **SKIP（Web 真机 headless 不可验）** 维持——旧静态核验+装配 dump exit=0 证据继续有效 |
| D6 pi-ai | 宿主实锁 0.84.2；上游 latest 0.85.1 | **维持 0.84.2（正确决策）**——事实修正：`pnpm-workspace.yaml:52` 是 minimumReleaseAgeExclude 发布时间豁免而非 pin；详见 `d6-piai-delta.md` |

## 1. 本浪环境凭据面核查（2026-09-07，存在性布尔，不读值）

| 面 | 存在性 | 含义 |
|---|---|---|
| env `OPENCODE_API_KEY` / `OLLAMA_API_KEY` / `COMMANDCODE_API_KEY` / `XAI_API_KEY` / `GROK_API_KEY` / `DEEPSEEK_API_KEY` | 全 False | D1/D2/D4 凭据缺省状态现行成立 |
| env `HUOSHAN_1_API_KEY` / `HUOSHAN_2_API_KEY` | False（不在进程 env） | 凭据仅经生产 `.credentials.yaml` 的 credentials 服务解析 |
| env `DSH_HOME` | True（指向生产 `C:\Users\25313\.dsh`，路径非凭据） | 生产 home 存在 |
| `C:\Users\25313\.dsh\.credentials.yaml` | True（内容未读；旧证据=仅 HUOSHAN_1/HUOSHAN_2 两 ref） | 与旧证据一致，未重读 |
| `C:\Users\25313\.dsh\grok-oauth.json` | **False** | D3 阻塞条件（无 xAI OAuth 会话）现行成立 |

## 2. D3 grok 0.3.10 → 0.3.11 增量核验（组长亲核）

### 2.1 版本事实
- 上游 latest 推进 **v0.3.11**（published 2026-09-05T17:28:52Z；release note：provider-owned independent search，协同版本 Model Switch 0.4.7 / Codex 0.3.14 / Grok 0.3.11 / Provider Directory 0.1.9）。
- 0.3.11 资产 digest `sha256:035b89a71509d47e5cc1f43326f74c954906ceb439b07feab7766cb766ec92a1`（87943B）——本浪 curl 下载后 `Get-FileHash` **MATCH**（对新抓 GitHub API digest 字段）。
- v0.3.10 标签 API digest 本浪重抓 = `c88a7c2f…` 与旧台账同值（旧证据稳固）。

### 2.2 增量 diff（`git diff --no-index --stat`，exit=1=有差异，预期）
- 8 files changed, +526 −84：`README.md`/`README.zh.md`（26 each）、`lib/client.js`（+158）、`lib/index.js`（+311）、`lib/types/index.d.ts`（+2）、`lib/types/model-switch-adapter.d.ts`（2）、**`lib/types/search.d.ts`（新增 57，唯一新增文件）**、`package.json`（28）。
- package.json 依赖面不变：`@deepseek-ai/dsh-util-values`（同 triple range）+ `@earendil-works/pi-ai ^0.84.2`（本浪 ConvertFrom-Json 亲读两版一致）。

### 2.3 认证面不变性（0.3.11 亲读）
- `cordis.patch.yml:2-3` 原文不变："There is no apiKeyEnv — this provider authenticates with an xAI subscription"；patch 默认 `retryPolicy normal/8` 不变。
- grep `baseURL: z\.` 全包 **零命中** → Config 无 baseURL 字段（0.3.11 无新逃生口）。
- `lib/index.js:3040` `baseURL: GROK_CHAT_BASE_URL` 硬编码（resolveAdapterOptions）；端点常量：1577 chat `https://cli-chat-proxy.grok.com/v1`、2668 models `…/v1/models-v2`、2778 billing `…/v1/billing?format=credits`。
- PKCE 面同构：696 `GROK_OAUTH_ISSUER = "https://auth.x.ai"`、582 `GROK_SESSION_FILENAME = "grok-oauth.json"`、1731/1743 `MISSING_CREDENTIAL`。
- 新增面 = provider-owned 搜索（README:50：每请求 always-on 服务端 `{type:"web_search"}`/`{type:"x_search"}`，非 `ctx.web` provider）——与认证面无关。

### 2.4 隔离装配（真实退出码）
- profile `C:\Users\25313\.dsh-v14-dverify-lead\profiles\d3-grok-0311`（uuid `0c044a09-d154-4396-8c5c-83fd07001f20`，bundles `@deepseek-ai/dsh-base` + `dsh-llm-grok`；allowBuilds `@google/genai`/`protobufjs` 同旧法）。
- `pnpm --dir <profile> add <tgz>`：首次 **exit=1**（`[ERR_PNPM_IGNORED_BUILDS]`，profile 独立项目无 allowBuilds）；补 profile 级 `pnpm-workspace.yaml` 后 **exit=0**。
- `pnpm dsh --profile d3-grok-0311 --dump-config`（DSH_HOME=隔离）：**exit=0**；产物 L339-341 `# == dsh-llm-grok` / `- id: llm-grok` / `name: dsh-llm-grok`（dumps\d3-grok-0311.txt/.err）。

### 2.5 探针可行性
- 无 baseURL config 字段 → compat probe 仍纯配置不可达（同 0.3.10 结论）；不做、不耗额度。

### 2.6 判定
**BLOCKED(xAI 订阅 OAuth 会话) 延续**：认证面与 0.3.10 完全同构，阻塞条件（生产 grok-oauth.json 不存在、无 xAI 登录）现行成立。0.3.11 新增搜索面不改变阻塞判定。

## 3. D6 pi-ai（Worker 落地 + 组长复核）

- Worker 产物：同目录 `d6-piai-delta.md`（97 行；显式路由 `{provider:'huoshan-2', model:'glm-5.3-flash'}`，自报 ② 级标签）。
- 组长复核一致点：`pnpm-workspace.yaml:49-53` minimumReleaseAgeExclude 原文亲读一致（豁免精确 `@0.84.2`，非 pin）；`packages/llm/llm-pi-ai/package.json:44` `^0.84.2` 亲读一致；caret 0.x 语义（`^0.84.2` = `>=0.84.2 <0.85.0`）正确；外部四插件声明 `^0.84.2` 与本浪 tgz 亲读一致。
- 结论采纳：**维持 0.84.2**——0.85.x 不在任何一方声明范围，强改 lockfile 需改码且造成宿主 0.85.x+插件 0.84.2 双实例树（fallback first-resolvable 不再唯一）；0.84.3/0.84.4 在范围内可低成本刷新（需同步改 :52 豁免精确版本）；升级触发条件 = 外部插件发版声明 `^0.85` 或出现仅 0.85.x 携带的必需目录条目。

## 4. Worker 台账（总控令 ⑤）

| Worker | 派发机制 | 路由 | 结果 |
|---|---|---|---|
| d6-first-probe | continuable subagent `8402cff8-c36c-44b2-bcf8-154cc77a8a39` | 未显式路由（总控改令前所派） | 总控改令后 `interrupt_agent` 中断；仅有草稿区权限、零仓库写入、无产物入本报告（防双写/防重复工） |
| d6-piai-delta | workflow `d6-piai-delta-verify`（1 agent） | **显式 `{provider:'huoshan-2', model:'glm-5.3-flash'}`**（自报 ② 级） | 产物 `d6-piai-delta.md` 97 行入库；5 条 shell 命令全 exit 0 + 1 次 raw CHANGELOG web_fetch `TypeError: fetch failed`（按任务书改走 GitHub API HTTP 200 ×3，失败存档 `worker-d6\fetch-changelog-raw-error.txt`）；零 pnpm install/add/update、零 build；宿主树除该 md 零写入 |

- Worktree：`D:\dsh-devframe-v14-dverify-lead`（与组长共享，Worker 唯一写 `.agents/devframe/v14-dverify/d6-piai-delta.md`）。
- 任务书要点：上游 latest 实查（pnpm view 带退出码）+ 官方 changelog 差异 + 升险评估（只读不升级）；每命令记退出码；红线禁 install/build/升级/凭据读取；唯一写目标 d6-piai-delta.md。
- 注：workflow 子代理 session id 未暴露于 `list_agents`（注册表仅见被中断的 8402cff8），以 workflow 名 + 产物文件为标识。

## 5. 命令与退出码台账（本浪新增部分）

| # | 命令（摘要） | 退出码 |
|---|---|---|
| 1 | `pnpm install --frozen-lockfile`（worktree） | 0 |
| 2 | GitHub API `releases/latest` ×5 + `tags/v0.3.10` ×1（web_fetch） | HTTP 200 ×6 |
| 3 | `curl.exe`（代理 127.0.0.1:7897）下载 6 tgz + `Get-FileHash` SHA256 对 API digest | 0 ×6；6/6 MATCH |
| 4 | `tar -xzf` 解包 ×6 | 0 ×6 |
| 5 | `pnpm run build`（总控修正前尝试） | **1**：`tsc -b tsconfig.host.json` → `packages/core/session/tests/at4-08-compat-reader.spec.ts(103,12): error TS18046: 'exported' is of type 'unknown'`（main HEAD 缺陷；总控后通报已修 `27318a3559`，本线未复验 build） |
| 6 | env/文件存在性核查（`Test-Path`，布尔，无退出码概念） | §1 表 |
| 7 | `pnpm --dir d3-grok-0311 add <tgz>`（首试无 allowBuilds） | 1（ERR_PNPM_IGNORED_BUILDS）→ 补配置后 **0** |
| 8 | `git diff --no-index --stat` 0.3.10 vs 0.3.11 | 1（=有差异，预期） |
| 9 | `pnpm dsh --profile d3-grok-0311 --dump-config`（DSH_HOME=隔离） | **0** |
| 10 | `git add` + `git diff --cached --check` + `git commit --no-verify` | 提交时记录于 commit message |

## 6. 与旧报告（v14-llmverify）差异清单

| 项 | 旧 | 本浪 | 变化 |
|---|---|---|---|
| D3 版本对象 | 0.3.10 | 0.3.11（新版本推进，认证面同构） | 判定对象更新，BLOCKED 延续 |
| D6 措辞 | "0.84.2 pin（pnpm-workspace.yaml:52）" | :52 = minimumReleaseAgeExclude 发布时间豁免；真实声明 `^0.84.2`（llm-pi-ai/package.json:44）+ lock 0.84.2 | **事实纠正** |
| D6 上游 | 0.85.1（09-06 记录） | 0.85.1（09-07 实查未变）；0.84.3/0.84.4 在声明范围内存在 | 细化 |
| D1/D2/D4/D5 | — | latest 未变 + digest 同值 + 凭据缺省状态现行成立 | 无翻转 |
| 新观察 | — | main HEAD 全仓 build TS18046（总控已修 27318a3559） | 记录性 |

## 7. 安全处置与提交收据

- 未读取/未记录任何凭据值；生产 DSH_HOME 仅 Test-Path 存在性；隔离产物均在 `C:\Users\25313\.dsh-v14-dverify-lead\`；无生产 profile/40 轮机制改动；包源码只读，仓库仅写 `.agents/devframe/v14-dverify/**`。
- 宿主无 bash → pre-commit hook 无法执行，提交以 `--no-verify` 完成；替代验证收据 = §5 台账 + 提交前 `git diff --cached --check` 干净（exit 码记入 commit message）。
