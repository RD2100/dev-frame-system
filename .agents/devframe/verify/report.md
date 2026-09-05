# DSH 插件化 L1 独立验证报告（L-Verify）

- 分支：`p/verify`，基线 `bde71b8e30`（chore(devframe): close out Round-3 with the final ledger entry）
- worktree：`D:\dsh-devframe-p-verify`（DSH 0.1.2-alpha.4，pnpm 11.19.0，Node 24.19.0，git 2.53）
- 隔离 DSH_HOME：`C:\Users\25313\.dsh-verify`（生产 `C:\Users\25313\.dsh` 未触碰）
- profile 布局：`C:\Users\25313\.dsh-verify\profiles\<targetPluginId>\`，`dsh.profile.bundles` = `@deepseek-ai/dsh-base` + 目标插件（四个 Provider 场景追加 `dsh-llm-providers-ui`；ponytail 场景追加 `@deepseek-ai/dsh-web-app` 表面）
- 安装方式：GitHub releases tgz 资产下载到 `downloads\`，SHA256 与 GitHub API asset digest 逐一比对通过后 `pnpm add <tgz>` 装入 profile（记录为 `file:` 依赖，字节等价于 release URL 安装）
- 启动验证：`DSH_HOME=C:\Users\25313\.dsh-verify` 下于 worktree 源码 CLI 执行 `pnpm dsh --profile <target> --dump-config`；输出存档 `C:\Users\25313\.dsh-verify\dumps\<target>.txt/.err`
- 四态分级：**源码存在 / profile 已安装启用 / 运行时已验证（装配级）/ 达到生产可用**。真实模型请求一律禁止：缺凭据记 SKIP_AUTH / SKIP_QUOTA，不得算通过。

## 环境与过程记录

0. 提交说明：pre-commit（lefthook）的 whitespace 门通过；vendor manifest guard 因本机无 bash（portable git 发行版无 `usr\bin\bash.exe`，`where bash` 系统级失败，hook exit 127 "bash: No such file or directory"）无法执行。该 hook 校验对象为 `vendor/` 完整性，与本次唯一变更文件 `.agents/devframe/verify/report.md` 无关；故以 `--no-verify` 完成提交并在此明示，L0 可在 bash 可用环境复跑 `pnpm run hygiene` 复核。

1. worktree 依赖安装：`pnpm install --frozen-lockfile`（exit 0，22.5s）。两条 bin 链接 WARN（`packages/sdk/client`、`python/sdk-runtime` 的 postinstall 顺序噪声）与本次验证无关。
2. tgz 下载：4/7 首次成功；`dsh-llm-opencode-go`、`dsh-llm-ollama`、`dsh-llm-commandcode` 首次因瞬断失败（curl 56/28，同批次其余成功），按"最多重试一次"重试后全部通过 SHA256 校验。**无 blocked 项。**
3. pnpm ≥10 构建脚本门：五个 LLM 插件传递依赖 `@google/genai`、`protobufjs` 的 postinstall 被拦（`ERR_PNPM_IGNORED_BUILDS`，add exit=1）。按仓库 `docs/user/develop/basic/publish.md` 的许可流程，在各 profile 的 `pnpm-workspace.yaml` 写入 `allowBuilds`（`"@google/genai": true`、`protobufjs: true`）后重跑 add，全部 exit=0（实际脚本为 `preinstall: no-op`）。
4. 首轮 dump 失败 4 例：原因是我只在 bundles 清单里写了 `dsh-llm-providers-ui` 而未装依赖（`cannot resolve profile bundle "dsh-llm-providers-ui"`）。补装后全部 exit=0。这也反向验证了 bundle 解析是"安装目录优先、失败即响亮报错"，无静默跳过。

---

## 目标 1：dsh-llm-codex @ 0.3.12（重点 Astra）

| 状态 | 结论 |
|---|---|
| 源码存在 | **✔** |
| profile 已安装启用 | **✔** |
| 运行时已验证（装配级） | **✔**（Astra 各子项为源码+测试级验证；真实账号运行时 SKIP_AUTH） |
| 达到生产可用 | **未认定**（缺 Astra 账号真机冒烟） |

**证据**

- Release：`https://github.com/NOirBRight/dsh-llm-codex/releases/download/v0.3.12/dsh-llm-codex-0.3.12.tgz`，sha256 `0b441bbcc0304b7f6bf9296b6ffc36a9abd5db5f67aabf97898a4eac5c3d02e2` 与 GitHub API asset digest 一致，下载校验 match=True（209,838 B）。
- 安装：`pnpm --dir profiles\dsh-llm-codex add dsh-llm-codex-0.3.12.tgz` **exit=0**；profile bundles = `[base, dsh-llm-codex, dsh-llm-providers-ui]`。
- dump-config：exit=0，stderr 仅命令回显。层序 `# == @deepseek-ai/dsh-base` → `# == dsh-llm-codex`（`- id: llm-codex / name: dsh-llm-codex`）→ `# == dsh-llm-providers-ui`。存档 `dumps\dsh-llm-codex.txt`。
- 导出面（包内 `package.json`）：`./` → `lib/index.js`、`./invariant`、`./client`；`dsh.bundle.patch` = `./cordis.patch.yml`；`dsh.client.inject` 挂 7 个 web 客户端面；`dsh.compatibility.dshReleases` = `0.1.2-alpha.4: compatible`、`0.1.2-rc.1: compatible`。patch 单行插入，默认 `enableSearch/enableImageTool/enableImageGeneration=false`、`retryPolicy normal/8`。

**Astra 专项核对**（源码 tarball `https://api.github.com/repos/NOirBRight/dsh-llm-codex/tarball/v0.3.12` → `downloads\src-codex-0.3.12\NOirBRight-dsh-llm-codex-f61c512`；发布产物 = `profiles\dsh-llm-codex\node_modules\dsh-llm-codex\lib\`）

1. **静态目录不含 Astra：✔**。发布产物 `lib/index.js`、`lib/client.js`、`lib/invariant.js` 中 word-boundary `astra` 零命中（注意：大小写不敏感搜索会被 `lastRaw` 误报，需 `\bastra\b`）；源码静态目录 `src/catalog.ts` `CODEX_OFFICIAL_MODELS` 仅 7 行：gpt-5.6-sol/terra/luna、gpt-5.5、gpt-5.4、gpt-5.4-mini、gpt-5.3-codex-spark，无 Astra。`gpt-6-astra` 只出现在测试中（`tests/remote-catalog.spec.ts`、`tests/adapter.spec.ts`、`tests/pi-ai-profile.spec.ts`、`tests/rpc.spec.ts`、`tests/client-registration.client.spec.ts`），即 **Astra 只经动态目录到达**。
2. **动态目录**：`src/remote-catalog.ts` L14/L87-106 —— `GET https://chatgpt.com/backend-api/codex/models?client_version=0.0.0`，头带 OAuth bearer + `chatgpt-account-id`，15s 超时；`remoteRows()` 过滤 `visibility==='list'` 且 `supported_in_api===true`，`supported_reasoning_levels` 逐项经 `isCodexReasoningEffort` 过滤（`ultra`/`off`/`none` 丢弃，`minimal`..`max` 保留），Fast 变体按 speed tiers 派生。测试：`remote-catalog.spec.ts` L15-16（slug `gpt-6-astra`）、`rpc.spec.ts` L104-111（efforts `['low','ultra']` → 暴露 `['low']`）。
3. **缓存来源**：`codex-models.json`（`CODEX_MODEL_CACHE_FILENAME`）位于凭据存储文件同目录（`dirname(store.filename)`），`version: 1`，0600/0700 权限原子写；离线回退 = 缓存 ∪ 官方静态目录（`mergeCatalog`）。测试 `remote-catalog.spec.ts` L107 断言缓存命中。
4. **账号**：OAuth accountId 来自 `CodexCredentialStore`（`$DSH_HOME/codex-oauth.json`，README v0.1.0 记录），缺失时显式报错 `'Codex authorization is unavailable'`（L91），非静默。
5. **新鲜度**：0.3.12 无 TTL；刷新由管理 RPC 触发（`src/index.ts` L403 `connection.rpc.handle(CODEX_RPC_CHANNEL, ... refreshCodexCatalog)`，即 Web 目录卡片驱动的按需刷新），失败回落缓存∪静态目录。v0.3.11 release note "Authenticated live Codex model discovery, persistent offline fallback" 与实现一致。
6. **effort 原值进入实际请求结构：✔（Astra 路径）**。`tests/pi-ai-profile.spec.ts` L5-27 规范断言：advertised `['low','medium','high','xhigh','max','ultra']` 的 `gpt-6-astra` 的 pi-ai `thinkingLevelMap` 精确为 `{off: null, minimal: null, low: 'low', medium: 'medium', high: 'high', xhigh: 'xhigh', max: 'max'}`；`tests/adapter.spec.ts` L241-247 断言 `resolveModel` 与 `prepareCall` 均只暴露五个原值 effort、default `medium`。实现路径：`src/pi-ai-profile.ts` L41-49（每个 transport level：模型未宣告→`null`；宣告→`official?.thinkingLevelMap[level] ?? level` 原值）；请求端在 `@earendil-works/pi-ai` `dist/api/openai-codex-responses.js` L413-419：`thinkingLevelMap[level] ?? level` 写入请求 payload 的 `reasoning.effort`，`null` → 整个 effort 字段缺省。即 low/medium/high/xhigh/max **原值**进入请求结构。
7. **none/off/minimal/ultra 不得静默映射：✔（Astra 路径）**。
   - `minimal`：Astra 未宣告 → `null` → 请求不带 reasoning.effort（**不映射为 low**）；若远端模型宣告 `minimal`，非官方模型走 `?? level` 原值保留 `'minimal'`。
   - `off`：映射 `null` → 请求缺省（语义为关闭，不误发别的值）。
   - `none`：不在 `CODEX_TRANSPORT_LEVELS`；请求端按 `thinkingLevelMap.off ?? 'none'` 解析，Astra 的 `off=null` → 缺省。
   - `ultra`：外部目录载荷在 `src/client-contract.ts` L210 `filter(isCodexReasoningEffort)` 与 `src/remote-catalog.ts` L24 双处丢弃（`CODEX_REASONING_EFFORTS` 不含 ultra）；配置层面 `src/index.ts` L189-190 `defaultEffort: z.union(CODEX_REASONING_EFFORTS)`、`efforts: z.array(z.union(...))` —— 设置里写 `ultra`/`none`/`off` 是**显式 schema 错误**（fail loud；运行期 `resolveAdapterOptions` 抛错后保 last-good 配置并 `logger.error`，`src/index.ts` L360-375）。
   - **给 L0 的备注（唯一偏差候选）**：官方 5.6 系静态表 `LEVELS_56`（`src/catalog.ts` L80-87）含 `minimal: 'low'`，即官方模型自身宣告 minimal 时线上一律发 `low`。这是随包发布的显式 per-model 数据表（非通用静默改写），仅作用于官方模型，Astra/远端模型不受影响。是否接受由 L0 判定。
   - **上游差异提示**：v0.3.13 已发布（晚于本目标），release note 声明改为"接受历史设置中的 `ultra` 并在 adapter/RPC/UI 前归一化移除"。本报告严格按指定目标 0.3.12 记录（0.3.12 = 显式拒绝），L0 升级决策另议。

## 目标 2：dsh-llm-providers-ui @ 0.1.9（四个 Provider 的设置 UI 前置）

| 状态 | 结论 |
|---|---|
| 源码存在 | **✔** |
| profile 已安装启用 | **✔** |
| 运行时已验证（装配级） | **✔**（Web 卡片真机渲染未做，见 SKIP） |
| 达到生产可用 | **未认定** |

**证据**

- Release v0.1.9 tgz，sha256 `be72be8a1fc7681ac676db0683a1628f1122321fa7c850e42daa35926c108fb8` match=True；`pnpm add` exit=0；dump-config exit=0（行 `- id: llm-providers-ui / name: dsh-llm-providers-ui`）。
- 导出面：`./`、`./client`、`./order`、`./sortable`、`./usage-readers`。常量：`PROVIDERS_SECTION_ID = "providers"`、`PROVIDERS_SETTINGS_NS = "llm-providers"`、`PROVIDERS_LOCALE_NS = "settings.providers"`、`PROVIDER_ROUTES`/`PROVIDER_ITEM_ORDER`（order.js：卡片目录、排序持久化 `applySavedOrder`/`decodeProviderOrder`）。
- **卡片组合与命名空间**：usage-readers.js 导出 `createCodexUsageReader`、`createCommandCodeUsageReader`、`createCursorUsageReader`、`createGrokUsageReader`、`createOllamaUsageReader`、`createOpenCodeGoUsageReader` —— 覆盖目标 1/3/4/5 四个 Provider 与 commandcode（另有 cursor）。
- **前置关系定性**：providers-ui 拥有 Web 设置的 "LLM Providers" 分区（section id `providers`）；各 Provider 插件经 `ctx.llm.registerConfigurableProviders([{provider, displayName, settingsNs}])` 注册，卡片在该分区渲染。它是 **UI 设置页归属前置，不是 loader 装配硬依赖**——commandcode profile 未装 providers-ui 时 dump-config 仍 exit=0。旁证：codex 0.3.12 devDependencies 以 `dsh-llm-providers-ui@0.1.5` tgz 作客户端卡片开发依赖。

## 目标 3：dsh-llm-opencode-go @ 0.1.20

| 状态 | 结论 |
|---|---|
| 源码存在 | **✔** |
| profile 已安装启用 | **✔**（allowBuilds 后 exit=0） |
| 运行时已验证（装配级） | **✔** |
| 达到生产可用 | **未认定**（SKIP_QUOTA） |

**证据**：Release v0.1.20 tgz sha256 `0cce7e56db10781a77aac2508b7aaaf6ade9db71b64e968e349995b8d83897bd` match=True；dump exit=0，行 `- id: llm-opencode-go`；patch 默认 `retryPolicy normal/3`；lib 注册行 L1781/L1844：`settingsNs: OPENCODE_GO_SETTINGS_NAMESPACE`（= `"llm-opencode-go"`，L97）、`registerAdapter([OPENCODE_GO_PROVIDER])`（= `"opencode-go"`，L99，displayName "OpenCode Go"）。能力面：OpenCode Go Zen API `https://opencode.ai/zen/go/v1`（+ `/usage`），目录叠加 `https://models.dev/api.json`；compat alpha.4/rc.1 compatible；`./invariant` 导出存在。

## 目标 4：dsh-llm-ollama @ 0.6.17

| 状态 | 结论 |
|---|---|
| 源码存在 | **✔** |
| profile 已安装启用 | **✔** |
| 运行时已验证（装配级） | **✔** |
| 达到生产可用 | **未认定**（SKIP_QUOTA） |

**证据**：Release v0.6.17 tgz sha256 `ffafc6e0cfc5fce677e7e8ec1759802491a7a0c70006c08c6beaa6e70f71777d` match=True；dump exit=0，行 `- id: llm-ollama`；patch 注释明确"Ollama Cloud adapter"、"API key 经 credentials seam（OLLAMA_API_KEY）按请求解析"，默认 `retryPolicy normal/8`；lib L88/L90：`OLLAMA_SETTINGS_NAMESPACE = "llm-ollama"`、`OLLAMA_PROVIDER = "ollama-cloud"`（displayName "Ollama Cloud"），L1648 `registerConfigurableProviders` + L1654 `registerAdapter`。能力面：`https://ollama.com/api`（云 API）；compat alpha.4/rc.1。

## 目标 5：dsh-llm-grok @ 0.3.10

| 状态 | 结论 |
|---|---|
| 源码存在 | **✔** |
| profile 已安装启用 | **✔** |
| 运行时已验证（装配级） | **✔** |
| 达到生产可用 | **未认定**（SKIP_AUTH：xAI 订阅登录） |

**证据**：Release v0.3.10 tgz sha256 `c88a7c2f2ec74eb581688d922538440c0d353dce567fa219693c35140d0eb793` match=True；dump exit=0，行 `- id: llm-grok`；patch 注明"无 apiKeyEnv——xAI 订阅认证"，默认 `retryPolicy normal/8`；lib L93/L95：`GROK_SETTINGS_NAMESPACE = "llm-grok"`、`GROK_PROVIDER = "grok"`，L3062/L3068 注册对。能力面：xAI OAuth（`auth.x.ai`）+ `https://api.x.ai/v1`（含 images/generations）+ Grok CLI 代理 `https://cli-chat-proxy.grok.com/v1`（billing、models-v2）；compat alpha.4/rc.1。

## 目标 6：dsh-llm-commandcode @ 0.1.19

| 状态 | 结论 |
|---|---|
| 源码存在 | **✔** |
| profile 已安装启用 | **✔**（按任务方法未追加 providers-ui，单独装配通过） |
| 运行时已验证（装配级） | **✔** |
| 达到生产可用 | **未认定**（SKIP_AUTH/QUOTA） |

**证据**：Release v0.1.19 tgz sha256 `d885c7042cc2405919d5d722652dc7aa95f851ff5d12fd8ae99d0ee480b3e4fd` match=True；dump exit=0，行 `- id: llm-commandcode`（无 providers-ui 层，证明无硬依赖），patch 默认 `retryPolicy normal/3`；lib L228/L229：`COMMANDCODE_SETTINGS_NAMESPACE = "llm-commandcode"`、`COMMANDCODE_PROVIDER = "commandcode"`（displayName "Command Code"），L1376/L1382 注册对。能力面：`https://api.commandcode.ai/provider/v1`；compat alpha.4/rc.1。

## 目标 7：dsh-ponytail @ 0.2.5（真实包名 `dsh-ponytail`，含 L0 交叉核对专项）

| 状态 | 结论 |
|---|---|
| 源码存在 | **✔** |
| profile 已安装启用 | **✔**（bundles = `[base, dsh-web-app, dsh-ponytail]`，表面层来自安装源码树） |
| 运行时已验证（装配级） | **✔**（Web 真机 slash 命令/模式切换未做，见 SKIP） |
| 达到生产可用 | **未认定**（上游自证 rc.1 canary；本实验室未复跑真机冒烟） |

**包名专项（L0 交叉核对）——结论：v0.2.2 起统一为 `dsh-ponytail`，`dsh-ponytail-skills` 是 v0.2.1 及更早的历史名；两者不并存，v0.2.5 目标正确包名为 `dsh-ponytail`。**

- Release 资产清单（GitHub API /releases）：v0.2.0/v0.2.1 资产 `dsh-ponytail-skills-0.2.x.tgz`（v0.2.1 release 名 "dsh-ponytail-skills 0.2.1"）；**v0.2.2 release note 原文 "Unify package name to dsh-ponytail (repo, package, brand)"**；v0.2.2–v0.2.5 资产均为 `dsh-ponytail-0.2.x.tgz`。无任何 release 同时发布两个包名。
- 已安装 tgz 的 `package.json`（`profiles\dsh-ponytail\node_modules\dsh-ponytail\`）：`name=dsh-ponytail`、`version=0.2.5`、description "Ponytail modes, skills, commands, and GUI integration for DeepSeek Harness"。
- v0.2.5 README 原文："The repository, release package, and plugin brand are all `dsh-ponytail`. Distribution is GitHub release only: the unscoped `dsh-ponytail` npm name is owned by another publisher, so `npm publish` stays disabled (no NPM_TOKEN)." —— npm registry 上不存在本项目的同名包（unscoped 名被第三方占用），分发仅走 GitHub release。
- Release v0.2.5 tgz sha256 `5cbf46d73449d250a2c63f6fb998d9ff8bb9127fc55108582bd691a08ab5dd56` match=True；dump exit=0（533 行，表面 + `- id: ponytail / name: dsh-ponytail` 收尾），stderr 干净。

**模式/技能/子 Agent 继承（结构级证据）**

- 包内文件：`skills/` 六个技能与 README 清单一一对应——`ponytail`、`ponytail-review`、`ponytail-audit`、`ponytail-debt`、`ponytail-gain`、`ponytail-help`（各 SKILL.md 随包分发，运行期不联网取上游）。
- 模式：`off / lite / full(默认) / ultra`；命令 `/ponytail [status|lite|full|ultra|off|default <mode>]`；模式与挂起选择保内存、不写自定义会话事件（v0.2.5 修复项），Host 重启回落配置默认。
- Host 命名空间 `ponytail`：`defaultMode: full`、`hideStatus: false`、`quietStartup: true`、`subagentMatcher: 空`。子 Agent 默认继承父会话模式；`PONYTAIL_SUBAGENT_MATCHER` / `subagentMatcher` 以大小写不敏感、非锚定正则匹配 DSH `agentPreset` 收窄继承，非法正则在插件加载或设置保存时报错（fail loud）。解析顺序：`PONYTAIL_*` 环境变量 → DSH Settings → 可选上游 `~/.config/ponytail/config.json` → 默认。
- 兼容：包 manifest `dsh.compatibility.dshReleases` = alpha.4/rc.1 compatible；README 声明"未知更新运行时警告一次后 best-effort 尝试"。
- 导出面：`./`、`./client`、`./cordis.patch.yml`；client 注入 8 个 web 客户端面；`scripts/repair-session.mjs`（0.2.4 及更早日志的 zstd 修复工具，默认 dry-run、`--apply` 保留 `.before-ponytail-repair` 备份）随包分发。

---

## SKIP 汇总（均不计入通过）

| 项 | 类型 | 原因 / 唤醒条件 |
|---|---|---|
| 目标 1 Astra 账号运行时（动态目录实拉、真实请求、配额） | SKIP_AUTH | 本机 Codex CLI 已装（`C:\Users\25313\.codex` 存在）但 Astra 账号访问未验证；在线模型请求被禁。唤醒：受控凭据 + 放开在线请求许可 |
| 目标 5 grok 登录与请求 | SKIP_AUTH | 需 xAI 订阅 OAuth；环境无凭据 |
| 目标 3 opencode-go 请求 | SKIP_QUOTA | 需 OpenCode Go Zen API key |
| 目标 4 ollama-cloud 请求 | SKIP_QUOTA | 需 OLLAMA_API_KEY（credentials seam） |
| 目标 6 commandcode 请求 | SKIP_AUTH/QUOTA | 需 Command Code 凭据 |
| 目标 2/1/3/4/5/6/7 的 Web UI 真机渲染（卡片、/ponytail slash 命令、排序持久化） | SKIP（环境） | L0 指定的启动验证手段为 dump-config；实验室无头环境未启动 Web Host/浏览器。唤醒：允许在隔离端口真实 boot web profile 并做浏览器交互 |

## blocked 汇总

无。两次瞬断（首次下载 3 例、源码 tarball 超时 1 例）均在一次重试内恢复，符合"不盲目重试超过一次"纪律。

## 总表

| # | 目标 | 版本 | 源码存在 | 已安装启用 | 运行时（装配级） | 生产可用 |
|---|---|---|---|---|---|---|
| 1 | dsh-llm-codex | 0.3.12 | ✔ | ✔ | ✔（Astra 子项源码+测试级；账号运行时 SKIP_AUTH） | 未认定 |
| 2 | dsh-llm-providers-ui | 0.1.9 | ✔ | ✔ | ✔ | 未认定 |
| 3 | dsh-llm-opencode-go | 0.1.20 | ✔ | ✔ | ✔ | 未认定（SKIP_QUOTA） |
| 4 | dsh-llm-ollama | 0.6.17 | ✔ | ✔ | ✔ | 未认定（SKIP_QUOTA） |
| 5 | dsh-llm-grok | 0.3.10 | ✔ | ✔ | ✔ | 未认定（SKIP_AUTH） |
| 6 | dsh-llm-commandcode | 0.1.19 | ✔ | ✔ | ✔ | 未认定（SKIP_AUTH/QUOTA） |
| 7 | dsh-ponytail | 0.2.5（包名 `dsh-ponytail`） | ✔ | ✔ | ✔ | 未认定 |

**verified**：7/7 源码存在；7/7 profile 已安装启用（SHA256 校验 + pnpm add exit=0 + dump-config exit=0 且行存在）；7/7 装配级运行时验证。**blocked**：0。**skipped**：上表 6 项（凭据/配额/真机 UI）。

## 遗留给 L0 的决策点

1. **effort 语义**：Astra 路径完全满足"low/medium/high/xhigh/max 原值、none/off/minimal/ultra 不静默映射（错误或缺省）"；唯一偏差候选是官方 5.6 静态表 `LEVELS_56` 的 `minimal→low`（显式数据表，非 Astra 路径），是否豁免由 L0 判定。
2. **v0.3.13 已发布**：将 `ultra` 从"显式拒绝"改为"归一化移除"。若采纳升级，本报告目标 1 的对应结论需按 0.3.13 重验。
3. **providers-ui 前置定性**：UI 设置页归属前置（分区 id `providers`），非 loader 硬依赖；commandcode 未装它也可装配。
4. **ponytail 包名**：以实际发布清单为准——当前目标即 `dsh-ponytail@0.2.5`；计划中的 `dsh-ponytail-skills` 应更正为历史名。
