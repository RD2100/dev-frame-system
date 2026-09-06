# shipped profile 只读装配探针：v14 三包挂载差异报告

对象：`apps/cli/config/examples/cordis/cordis.yml`（web profile 之上的 `--patch` overlay）。组合顺序：`packages/bundle/base/cordis.patch.yml`（dsh-base 层）→ `packages/bundle/web-app/cordis.patch.yml`（dsh-web-app 层）→ 用户 overlay（同层 sibling patch，逐 id 后写胜出；`apps/cli/config/examples/cordis/cordis.yml:4-7`、`packages/bundle/base/cordis.patch.yml:1-4`）。本报告只读，未修改除本文件外的任何文件。

## 现有挂载面清单（web 组合相关行）

### base 层（packages/bundle/base/cordis.patch.yml，503 行，一条 insert 覆盖空 profile 根）

| id | 包名 | 行 | 提供的 Cordis 服务（证据） |
|---|---|---|---|
| session | @deepseek-ai/dsh-session | base:33-34 | `sessions`（packages/core/session/src/index.ts:861，default export :1223） |
| commands | @deepseek-ai/dsh-commands | base:292-293 | `commands`（packages/interaction/commands/src/index.ts:266） |
| goal | @deepseek-ai/dsh-goal | base:298-299 | `goals`（packages/goal/goal/src/index.ts:291） |
| session-projection | @deepseek-ai/dsh-session-projection | base:138-139 | `sessionProjections`（packages/session/session-projection/src/index.ts:208） |
| tools | @deepseek-ai/dsh-tools | base:476-477（web 层重述 config，未停用） | `tools`（packages/core/tools/src/index.ts:820） |
| storage-domain | @deepseek-ai/dsh-storage-domain | base:153-156（`config.backend: json`） | `storageDomain`（packages/storage/storage-domain/src/index.ts:217 `provide('storageDomain', …)`，插件 name :42，包名 package.json:2） |
| storage / storage-json | @deepseek-ai/dsh-storage / -storage-json | base:145-146 / 148-151（json root `dshHomePath('storages')`） | storageDomain 的 json 后端栈 |
| settings | @deepseek-ai/dsh-settings-file | base:90-91 | settings 文档（$DSH_HOME/settings.yaml） |
| credentials | @deepseek-ai/dsh-credentials-local | base:97-98 | 凭据解析 |
| llm-pi-ai | @deepseek-ai/dsh-llm-pi-ai | base:107-108 | 休眠挂载，settings `llm-pi-ai:` 节点亮活 |
| agent-default-model | @deepseek-ai/dsh-agent-default-model | base:75-79 | 默认模型（deepseek-official / deepseek-v4-flash） |
| agent | @deepseek-ai/dsh-agent | base:67-68 | `agents`（packages/core/agent/src/index.ts:260） |
| sandbox-policy | @deepseek-ai/dsh-sandbox-policy | base:214-218 | `workspaceRoot: !!js process.cwd()`（L218）——**!!js process.cwd() 先例** |

### web-app 层（packages/bundle/web-app/cordis.patch.yml，452 行）

| id | 包名 | 行 | 说明 |
|---|---|---|---|
| workspace | @deepseek-ai/dsh-workspace | web-app:61-62 | 提供 `workspaceRegistry`（packages/workspace/workspace/src/index.ts:115；包名 package.json:2）。base 层无 workspace 行 |
| tools | （重述） | web-app:31-37 | `mode: !!js process.env.DSH_TOOLS_MODE` |
| webserver | @deepseek-ai/dsh-host-webserver | web-app:121-129 | base 层无 webserver；默认 127.0.0.1:3080 |
| cordis-host-runner | @deepseek-ai/dsh-cordis-host-runner | web-app:108-109 | overlay 亦 insert 同 id（cordis.yml:15-17），逐 id 后写胜出 |
| agent-presets | @deepseek-ai/dsh-agent-presets | web-app:448-452 | preset 机制宿主行 |

### 用户 overlay（apps/cli/config/examples/cordis/cordis.yml，19 行全文）

- L10-13：`webserver` 钉 `host: 127.0.0.1` / `port: 3081`。
- L15-19：`insert` 两条 —— `cordis-host-runner`（@deepseek-ai/dsh-cordis-host-runner）、`tool-cordis`（@deepseek-ai/dsh-tool-cordis）。

### agentBindings 在 web 组合里的挂载状态：**证实缺失**

- provider 是 `@deepseek-ai/dsh-experimental-session-identity`（package.json:2），default export `AgentBindingRegistry` 服务类（src/index.ts:14），注册为 `ctx.agentBindings`（src/registry.ts:126 `super(ctx, 'agentBindings')`；Context 声明 :25-29），其 `static inject = ['sessions', 'storageDomain']`（registry.ts:119）。
- base（503 行）、web-app（452 行）、overlay（19 行）三层均无 `agentBindings`/`session-identity` 行——上文清单即逐行核对结果。
- 全仓 yml grep（pattern `agentBindings|session-identity|shadow-router|command-goal-binding|project-memory`，include `*.yml`）唯一命中 `packages/experimental/project-memory/cordis.patch.yml:1,8,9`（该包自带 patch 自引用）。**没有任何 yml 挂载 session-identity / shadow-router / command-goal-binding**。
- 结论：`agentBindings` 在整个 web 组合中未挂载；三包 yml 挂载现状为零（project-memory 仅有包内默认层，未被任何 profile/overlay 引入）。

## v14 三包挂载缺口

### 1) command-goal-binding — @deepseek-ai/dsh-experimental-command-goal-binding（package.json:2）

- **loader name / 入口**：函数插件，named exports only；`export const name = 'command-goal-binding'`（src/index.ts:64）。
- **inject**：`['commands', 'goals', 'sessions', 'sessionProjections']`（src/index.ts:67）。四个服务在 web host plane 全部活跃（清单见上节），运行时服务面无缺口。
- **必填配置**（src/config.ts）：
  - `workspaceId`（Schema required :83；非空 re-check :136-139）。
  - `checks`：`{ version: 1, checks: [{ checkId, executable, arguments?, cwd }] 且 min 1 }`（Schema :71-79、:85）。
  - `taskIds`：非空、去重、trimmed（:86，:92-107）。
  - `maxAttempts`：正 safe integer（:87，:172-177）。
  - 可选 `workspaceRoot` 一旦出现必须绝对路径（:146-148）；可选 `maxGoalRounds` 正整数（:88，:172-177）。
  - **checks 每项 `cwd` 必须绝对路径**，相对即 `TypeError`（:110-118，throw :113-114）。
- **缺省行为**：无默认面。缺任一必填在 `apply`/激活时 fail loud（index.ts:70-77 JSDoc；config.ts:120-131），不会把命令降级成无名路径。
- **缺口**：
  1. 无任何 yml 挂载（grep 证实，见上）。
  2. `apps/cli/package.json` dependencies（L30-101）与 devDependencies（L102-146）均无该包；所有 bundle manifest 亦无（pwsh 扫描 `packages/bundle/*/package.json` 对 `experimental` 零命中）。→ 一旦写进 examples overlay，`validateAppResolution` 将报 "must be declared in apps/cli/package.json dependencies or a bundle manifest"（scripts/verify-cordis-config.ts:36-38、:232-248、:441-463）。
  3. **tsconfig.base.json paths 无 `@deepseek-ai/dsh-experimental-command-goal-binding` 映射**（grep 仅命中另一个包 `@deepseek-ai/dsh-command-goal`，tsconfig.base.json:270）。→ `validateSourcePlaneResolution` 会失败（verify-cordis-config.ts:426-437），tsx 源码启动回退 built `lib/`，干净树断。这是三包中唯一缺 tsconfig paths 映射的。
  4. 自身 dependencies 携带 `dsh-experimental-devframe` + `dsh-experimental-agent-evidence`（package.json:23-26），不需要宿主额外补。

### 2) shadow-router — @deepseek-ai/dsh-experimental-shadow-router（package.json:2）

- **loader name / 入口**：Service 类包，default export `ShadowRouter`（src/index.ts:42；类声明 src/service.ts:252），注册为 `ctx.shadowRouter`（index.ts:5-6 模块文档）。
- **static inject**：`['sessions', 'storageDomain', 'workspaceRegistry', 'agentBindings', 'agents']`（service.ts:253）。
- **static Config**（service.ts:255-264）：
  - `authorizedRoots`：默认 `[]`——**空即不授权任何项目根**（:256；:275-276 注释 "empty authorizes nothing"）；每项载入时必须绝对路径且为已存在目录（validateAuthorizedRoots :351-372）。
  - `controllerProfile`：默认 `'devframe'`（:257）。
  - `shadowSessionId`：可选；未配置则无 Shadow 会话（:260）。
  - `maxPendingDeliveries` 16 / `maxMessageChars` 20000 / `statusPageSize` 20（:261-263）；构造器正整数深校验（:289-304）。
- **缺省行为（安全默认面）**：不配 `authorizedRoots` 与 `shadowSessionId` 时，路由器挂载但不授权任何根、不标记任何 Shadow 会话；四个 `project_*` 工具只在会话被标记 Shadow 后经 whitelist 安装（src/tools.ts:2-8 模块文档；`SHADOW_TOOL_NAMES` :20；指定机制 service.ts:335-348）。挂载本身安全。
- **缺口**：
  1. **缺 `agentBindings` 服务**：provider 包 `@deepseek-ai/dsh-experimental-session-identity` 未被任何 yml 挂载（grep 证实）。组合激活是 service-availability 驱动（base:12-13），缺 provider 即装配不齐，fail loud。
  2. 其余 inject 在 web host plane 均满足：`sessions`（base:33-34）、`storageDomain`（base:153-156）、`workspaceRegistry`（web-app:61-62）、`agents`（base:67-68）。
  3. `apps/cli/package.json` 与所有 bundle manifest 均无该包（同上，resolution gate 会拦）。
  4. tsconfig paths 已有映射（tsconfig.base.json:240）；session-identity 亦已有（:234）。
  5. 需要同时补挂 `session-identity` 行（其 inject `sessions`/`storageDomain` base 层已满足，registry.ts:119）。
- 测试 harness 佐证装配形状：shadow-router 全组合 = agent-loop + projection + storage 栈 + jsonl persistence + workspace + AgentBindingRegistry + ShadowRouter（packages/experimental/shadow-router/tests/helpers.ts:60-69），再 `markShadow`（:78）；session-identity 组合 = session + storage + json + storageDomain(json) + registry（packages/experimental/session-identity/tests/helpers.ts:37-41）。

### 3) project-memory — @deepseek-ai/dsh-experimental-project-memory（package.json:2）

- **loader name / 入口**：函数插件，`export const name = 'project-memory'`（src/plugin.ts:23）。
- **inject**：`['tools']`（plugin.ts:25）。web host plane 的 `tools` 活跃（base:476-477；web-app:31-37 重述未停用）。
- **必填配置**：`workspaceId` 在 loader schema 标 required（plugin.ts:52；apply 再查 :335-338，无 host 默认值）。
- **可选与缺省**：`vaultRoot`（省略 = 未配置，工具报 `MEMORY_UNAVAILABLE`，plugin.ts:30-33）；`writeEnabled` 默认 false（:50）；`userScopeEnabled` 默认 false（:51）；`currentSnapshot` 可选（:53）。`writeEnabled=true` 且无 `vaultRoot` → 激活时 fail loud（:347-349）。spec 解析层同样 `writeEnabled ?? false` / `userScopeEnabled ?? false`（src/config.ts:99-100），内置 limits/retry 默认（:8-21）。
- **缺省行为（安全默认面）**：不配 vaultRoot 时只读、工具报 MEMORY_UNAVAILABLE；工具注册进 `ctx.tools` 全局层（plugin.ts:361-363）。
- **自带 patch**：`packages/experimental/project-memory/cordis.patch.yml:7-13`（id `project-memory`，`workspaceId: default`，write/userScope false，无 vaultRoot）；package.json 声明 `dsh.bundle.patch`（:24-28）。注意 `bundleManifestPaths`（verify-cordis-config.ts:363-368）扫 `packages/*/*/package.json` + `dsh.bundle.patch`，**该实验包今日已被当作 bundle 计入**，其自 patch 行是自引用（:384 self-skip），现状通过；但若从 app overlay 挂载，仍需把包名补进 app 解析面。
- **缺口**：
  1. 无 profile/overlay 挂载（唯一 yml 命中是它自己的包内 patch）。
  2. `apps/cli/package.json` 与 bundle manifests 均无该包 → app overlay 引用会被 resolution gate 拦。
  3. tsconfig paths 已有（tsconfig.base.json:237）。

## 建议挂载差异（建议行 + manifest 增补，逐条带依据）

### A. yml 建议行（追加进 `apps/cli/config/examples/cordis/cordis.yml`，或部署自己的 --patch overlay；只读任务，本报告不落盘）

```yaml
- insert:
    - id: session-identity
      name: '@deepseek-ai/dsh-experimental-session-identity'
    - id: shadow-router
      name: '@deepseek-ai/dsh-experimental-shadow-router'
      config:
        authorizedRoots: [!!js process.cwd()]
        controllerProfile: devframe        # 缺省即此，可省
        # shadowSessionId: <既有会话 id>    # 不配则无 Shadow 会话、无 project_* 工具
    - id: command-goal-binding
      name: '@deepseek-ai/dsh-experimental-command-goal-binding'
      config:
        workspaceId: dsh-devframe
        workspaceRoot: !!js process.cwd()
        maxAttempts: 3
        taskIds: ['v14-udeliver-lead']     # 部署期真实任务 id，非空去重
        checks:
          version: 1
          checks:
            - checkId: typecheck
              executable: pnpm
              arguments: ['run', 'typecheck']
              cwd: !!js process.cwd()
    - id: project-memory
      name: '@deepseek-ai/dsh-experimental-project-memory'
      config:
        workspaceId: dsh-devframe
        # vaultRoot: <用户 Vault 绝对路径>   # 不配则只读 + MEMORY_UNAVAILABLE
        writeEnabled: false
        userScopeEnabled: false
```

逐条依据：
1. **session-identity 先行**：shadow-router static inject 含 `agentBindings`（service.ts:253），provider 即该包（registry.ts:126）；其自身 inject `['sessions','storageDomain']` base 层已满足（registry.ts:119）。
2. **command-goal-binding 全必填**：`workspaceId/checks/taskIds/maxAttempts` 缺一即激活失败（config.ts:82-89、:120-131）；`checks[].cwd` 必须绝对（:113-114）。**`cwd: !!js process.cwd()` 有直接先例**——base patch 的 sandbox-policy 行 `workspaceRoot: !!js process.cwd()`（base:218，该行 L214-218）；`!!js` 允许面覆盖 plugin `config`（AGENTS.md:99：cordis.yml allows `!!js` under plugin `config` and entry `disabled`）。`workspaceRoot` 可选但出现即须绝对（config.ts:146-148），同样可用 `!!js process.cwd()`。注意 Loader 对整个 `config` 子树插值（scripts/verify-cordis-config.ts:4-7），`authorizedRoots` 数组内 `!!js` 标量按此应被插值，**但仓库先例均为标量值（base:113、151、193、196、217、218、222、228、233）——数组内用法未证实，稳妥替代是绝对路径字面量或单标量表达式**。
3. **project-memory**：`workspaceId` loader required（plugin.ts:52）；包内默认 patch 的形状即此（cordis.patch.yml:7-13），安全默认面照抄即可。
4. **web 组合服务面**：建议行不与 web-app 的 disable 冲突——web 层停用的是 `command-goal`/`tool-goal`/`plan-mode` 等 preset 行（web-app:376-383），而 `commands`/`goal`/`sessions`/`sessionProjections`/`tools`/`storage-domain`/`workspace` 全部 host-plane 活跃（清单见上）；goal 服务与 driver 留 host plane 有注释明示（web-app:373-374）。

### B. manifest 增补（resolve gate 要求）

1. **apps/cli/package.json `dependencies` += 四个包名**：`@deepseek-ai/dsh-experimental-session-identity`、`@deepseek-ai/dsh-experimental-shadow-router`、`@deepseek-ai/dsh-experimental-command-goal-binding`、`@deepseek-ai/dsh-experimental-project-memory`。依据：examples overlay 属 `appOverlayFiles`（verify-cordis-config.ts:36-38），解析面 = `apps/cli/package.json` **dependencies**（不是 devDependencies）+ 所有 `packages/bundle/*/package.json` 的 dependencies（:232-240），缺失即报错（:244-248、:441-463）。现状四包在 apps/cli 两种 deps 与全部 bundle manifest 中均无（apps/cli/package.json:30-146；pwsh 扫描 bundle manifests 对 `experimental` 零命中；dsh-base deps base/package.json:37-121、dsh-web-app deps web-app/package.json:42-113 亦无）。备选：产品化时改挂到 `packages/bundle/web-app/package.json` dependencies，随 web profile 分发（同一 gate 合并）。
2. **tsconfig.base.json `paths` += `"@deepseek-ai/dsh-experimental-command-goal-binding": ["./packages/experimental/command-goal-binding/src"]`**。依据：yml 引用的本地包 specifier 必须经 tsconfig paths 解析到 `.ts` 源码，否则 `validateSourcePlaneResolution` 报错（verify-cordis-config.ts:426-437）；现状该包无映射（tsconfig.base.json 仅 L270 命中同名的 `dsh-command-goal`），另两包与 session-identity 已有（:234、:237、:240）。

## 风险与注意

1. **patch 替换语义**："A patch replaces the targeted row's whole `config`"，不合并（cordis.yml:7、base:6-7、web-app:5-6）。若未来在更晚层重述 `tools`、`storage-domain`、`project-memory` 等 id，必须整行重述全部键——漏键即静默丢配置。
2. **行序无加载语义**，激活由服务可用性驱动（base:12-13）；因此 shadow-router 缺 `agentBindings` 不会"部分工作"，而是装配不齐 fail loud——不要指望行序兜底。
3. **`!!js` 边界**：仅 plugin `config` 与 entry `disabled` 允许（AGENTS.md:99）；metadata（id/name/inject 等六字段，verify-cordis-config.ts:39）必须字面量，`!!js` 会被拒（:503-525）。`disabled` 表达式仅 parse 校验（:527-543）。
4. **config 无法停用一行**：launcher 层用 `disabled`，config 做不到（base:178-179 注释）；本报告建议行均为启用行，无此问题。
5. **preset 平面分离 gate**：host 组合活跃行不得再进 agent preset（verify-cordis-config.ts:137-161）；本报告建议行挂在 app overlay（host plane），不要再复制进 `packages/preset/agent-presets/presets/*/agent.cordis.yml`。
6. **持久化副作用**：session-identity 打开 `session_identity` storageDomain（registry.ts:129-139），shadow-router 打开 `shadow_router` domain（service.ts:307-313），均落 `storage-domain(backend json)` → `$DSH_HOME/storages`（base:148-156）。挂载即产生持久写，测试组合佐证（session-identity/tests/helpers.ts:37-41）。
7. **command-goal-binding 的 checks 是真实执行面**：默认执行脸以真实子进程跑 required checks（composition.ts:109-111 注释、:120 AgentEvidenceJournal 装配），`/devframe-start` 产出真实验证证据——`checks` 清单是"人批准"的语义，不要配置未审过的命令。
8. **project-memory 全局工具层**：工具注册进 `ctx.tools`（plugin.ts:361-363）；web 上 registry 呈 host+per-scope 分层、host 层全局可见（web-app:358-365 以 skill registry 类比 tools-registry shape）——host-plane 注册的 memory 工具对所有会话可见，此点为注释级推断，未运行时验证。另 `memory_append` 需 calling agent 并先落 session-log receipt（plugin.ts:288-314）。
9. **shadow-router 需显式指定 Shadow 会话**：挂载后仍无工具，直到 `shadowSessionId` 命中会话并被 markShadow（service.ts:335-348；tests/helpers.ts:78）；`authorizedRoots` 条目必须在载入时已存在的绝对目录（:351-372），相对路径或不存在路径直接 fail loud。
10. **自引用 bundle 计入**：project-memory 因 `dsh.bundle.patch`（package.json:24-28）已被 `bundleManifestPaths`（verify-cordis-config.ts:363-368）当作 bundle；若有人把它整体搬进 `packages/bundle/`，其 patch 行将改按 bundle 自身 dependencies 校验（:257-265、:377-388），自引用仍通过，但叠加 app overlay 引用后两处 gate 都要满足。

## 车道回执

- **实际请求 provider/model**：glm-5.3-flash（运行时上下文原文："You are a coding agent powered by the glm-5.3-flash model"；宿主为 DeepSeek Harness，provider 名称未在上下文中单独标注）。
- **有无 retry/429**：无。本次会话全部工具调用（read/grep/glob/pwsh/write）均一次成功，未观察到 429 或 retry 事件。
- **结论一句话**：shipped web 组合（base 503 行 + web-app 452 行 + cordis.yml overlay 19 行）证实未挂载 agentBindings（provider 包 `@deepseek-ai/dsh-experimental-session-identity` 全仓零 yml 引用），v14 三包亦零挂载；挂载缺口为 apps/cli dependencies 四包全缺 + command-goal-binding 缺 tsconfig paths 映射 + shadow-router 缺 session-identity 前置行，三者配置面均已从源码逐行核实并给出建议 yml/manifest 差异。
- **证据文件清单**（均带 :行号，正文已引）：
  - apps/cli/config/examples/cordis/cordis.yml（1-19）
  - packages/bundle/base/cordis.patch.yml（33-34、75-79、90-98、107-108、138-139、145-156、214-218、292-299、476-477）
  - packages/bundle/web-app/cordis.patch.yml（31-37、61-62、108-109、121-129、358-383、448-452）
  - packages/experimental/command-goal-binding/{package.json, src/index.ts, src/config.ts, src/composition.ts}
  - packages/experimental/shadow-router/{package.json, src/index.ts, src/service.ts, src/tools.ts, tests/helpers.ts}
  - packages/experimental/project-memory/{package.json, src/plugin.ts, src/config.ts, cordis.patch.yml}
  - packages/experimental/session-identity/{package.json, src/index.ts, src/registry.ts, tests/helpers.ts}
  - scripts/verify-cordis-config.ts（36-38、39、137-161、227-267、363-368、377-388、399-439、441-463、503-543）
  - apps/cli/package.json（30-146）
  - packages/bundle/base/package.json（37-121）、packages/bundle/web-app/package.json（42-113）
  - tsconfig.base.json（234、237、240、270）
  - 服务 provider 证据：packages/core/session/src/index.ts:861、packages/interaction/commands/src/index.ts:266、packages/goal/goal/src/index.ts:291、packages/session/session-projection/src/index.ts:208、packages/core/tools/src/index.ts:820、packages/core/agent/src/index.ts:260、packages/workspace/workspace/src/index.ts:115、packages/storage/storage-domain/src/index.ts:42,217
  - AGENTS.md:99（!!js 允许面）
  - 全仓 grep 记录：yml pattern `agentBindings|session-identity|shadow-router|command-goal-binding|project-memory` 仅命中 project-memory 包内 patch；`packages/bundle/*/package.json` 对 `experimental` 零命中（pwsh Select-String）
