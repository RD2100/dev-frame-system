---
description: L-Integration 真实组合集成候选线的逐包 Cordis 接入盘点与缺口判定（基线 cda26762d7 → main 4bc507e332 → e3d4d6ad02 → b78f54ebfc，工作树 D:\dsh-devframe-p-integration）。
---

# 集成候选缺口清单（gaps）

- 状态：清点完成；第二（project-memory）、三（shadow-router）、四（hierarchy 在线拒绝）、五（shadow 组合面）轮组合重验完成。
- 基线：`p/integration` @ `cda26762d7`，先后 fast-forward 合并 main 至 `4bc507e332`（纳入 P21-M）、`e3d4d6ad02`（纳入 p/memory-seam S1–S3 切片，merge `fb1519cd19`）、`b78f54ebfc`（纳入 shadow-router merge `eff2e5b6af` 及 AT2 场景对齐）；第四、五轮分别以 `07569a65be`、`c42c8b4518` 为基开分支 `p/integration-2`、`p/integration-3`（后者含 p/bundlefix `06d6950c38`）。
- 隔离 home：`C:\Users\25313\.dsh-integration`（本线专用；绝不触碰 `C:\Users\25313\.dsh`）。
- 判定口径：机械缺口 = 缺 cordis.yml / 入口声明 / profile 挂线 / spec 挂线，可直接补齐且不改 src 语义；语义缺口 = 缺 Provider/Consumer/工具实现或产品面，归原组长，不代改。
- 挂载约定事实：本仓库"已装插件"的形态不是每包自带 cordis.yml，而是**插件包导出 Cordis Service（default export）+ 某个 profile patch 层以 `id/name/config` 行挂载**（先例：`agent-team` 无自包 cordis.yml，由 `agent-team-profile` 的 cordis.patch.yml insert 行挂载）。故"缺自包 cordis.yml"本身不算缺口；缺的是可挂载的 Service 面或挂载层。

## 逐包盘点

### 1. project-contracts（P00）— 非插件，契约库
- cordis.yml：无（不需要）。
- Service Definition：无 `extends Service`、无 default export、无 `declare module` Context 扩增（`src/index.ts` 只导出类型/工厂/守卫）。
- inject：不适用；Provider/Consumer：不适用（类型词汇与 branded ID，被下游五包 import）。
- 工具注册 / effect 注册：无。Config schema：无。
- **判定：非插件**。不进 profile 行；作为依赖随五包被解析（tsconfig paths / peerDependencies 已挂）。

### 2. session-identity（P01）— 已就绪插件
- cordis.yml：无自包文件（按挂载约定不算缺口）。
- Service Definition：`AgentBindingRegistry extends Service`，default export（src/registry.ts:118），注册 `ctx.agentBindings`（Context 扩增 registry.ts:25-29）。
- inject：`['sessions', 'storageDomain']`（registry.ts:119）——base 树均提供（dsh-session、dsh-storage-domain）。
- effect 注册：`ctx.effect(domainClose)`（registry.ts:131）。
- 工具注册：无（纯服务）。Config schema：无（无配置面）。
- 持久化：`session_identity` 域，init 内冷恢复全表（registry.ts:129-140）。
- **判定：机械缺口仅"profile 挂载层"——可挂。**

### 3. agent-hierarchy（P02）— 已就绪插件
- cordis.yml：无自包文件。
- Service Definition：`AgentHierarchy extends Service`，default export（src/service.ts:45），注册 `ctx.agentHierarchy`（service.ts:27-31）。
- inject：`['agentBindings', 'tools', 'agents']`（service.ts:46）——依赖 P01 + base tools/agents；缺失即加载期 fail loud。
- effect/监听：`ctx.tools.guard(...)`（service.ts:71）、`ctx.on('agent/created')`、`ctx.on('agent/disposed')`（72-82）、`ctx.effect(teardown)`（83）。
- 工具注册：无新工具（对既有工具链装守卫与 restrict）。
- Config schema：zod `agentHierarchyConfigSchema`，构造函数第二参（service.ts:60-63）——cordis.yml 行 `config:` 可传。
- 组合级验证（本线第四轮，分支 `p/integration-2`）：在线拒绝探针经真实分派器（live agent + 真实绑定 + `ctx.tools.execute`）驱动——controller 绑定后 `read` 真身成功（allow）；lead 无 pluginId 委派 `subagent` 被 guard 拒（`no plugin scope binding`）；未绑定 agent 受控工具被拒（`no role binding` fail-closed）；冷启动三断言重立 + 绑定行恢复。union 外角色分支为防御面（registry schema 同 union），绑定路径不可驱动，如实登记。该面实测揪出并修正档案层 `bash` 幽灵工具名缺陷（F9，见 e2e-evidence）。
- **判定：机械缺口仅"profile 挂载层 + config 行"；在线拒绝剩余检查项已闭环。**

### 4. project-controller（P04）— 已就绪插件
- cordis.yml：无自包文件。
- Service Definition：`ProjectController extends Service`，default export（src/controller.ts:101），注册 `ctx.projectController`（36-40）。
- inject：`['agentBindings', 'storageDomain']`（102）。
- effect 注册：`ctx.effect(domainClose)`（135）。
- 工具注册：无（任务板服务；命令面/会话级工具属语义缺口，归 P04 线）。
- Config schema：`static Config`（schemastery，`maxActiveTasks` 默认 2，controller.ts:104-106）——cordis.yml 行 `config:` 走 schema 校验。
- 持久化：`project_tasks` 域，init 冷恢复。
- **判定：机械缺口仅"profile 挂载层 + config 行"。**

### 5. agent-evidence（P05）— 已就绪插件
- cordis.yml：无自包文件。
- Service Definition：`AgentEvidenceLedger extends Service`，default export（src/ledger.ts），注册 `ctx.agentEvidence`（38-42）。
- inject：`['storageDomain']`（105）。
- effect 注册：域关闭 effect（init 内，与同构五包一致）。
- 工具注册：无。Config schema：无（无配置面）。
- 持久化：`agent_evidence` 域三轨迹（bindings/submissions/verifications），冷恢复。
- **判定：机械缺口仅"profile 挂载层"。**

### 6. agent-reliability（P06）— 已就绪插件
- cordis.yml：无自包文件。
- Service Definition：`AgentReliability extends Service`，default export（src/service.ts:92），注册 `ctx.agentReliability`（32-36）。
- inject：无（无静态 inject 字段）；运行时值依赖 `@deepseek-ai/dsh-experimental-devframe/reliability`（src/service.ts:27，value import）——该子路径导出必须可解析。
- effect 注册：无（进程内状态：admission 默认 closed，fail-closed）。
- 工具注册：无。Config schema：无。
- 持久化：无自有域（stop 对账身份跨重启保留归 host 语义）。
- **判定：机械缺口仅"profile 挂载层"；devframe 子路径导出解析为装配前置条件。**

### 7. project-memory（P21-M）— 插件形态已落地（第二轮只读装配验证）
- cordis.yml：包内自带 `cordis.patch.yml` 挂载行（S1 切片交付，merge `fb1519cd19`，main `e3d4d6ad02`）。
- Service Definition：**已具备**——`src/plugin.ts` 函数式 Cordis 插件（`name: 'project-memory'`、`inject: ['tools']`、schemastery `Config`、`apply` 内 `ctx.provide('projectMemory', service)`），Context 扩增 `ctx.projectMemory`（S1 落地）。
- 工具注册：三工具已注册 `ctx.tools`（S2 落地；本组合探针实测 `ctx.tools.get('memory_search'/'memory_read'/'memory_append')` 全部非 undefined）。
- Config schema：loader `Config`（`workspaceId` load 期必填、`writeEnabled` 默认 false、`userScopeEnabled` 默认 false、`vaultRoot` 缺省即未配置只读）。
- 持久化：`MemoryReceiptStore` 走会话日志（`src/receipt-log.ts`，S2/S3 落地）；`agent/created` 监听做回执再水化。
- 组合级验证（本线第二轮）：只读装配（`workspaceId: integration`、`vaultRoot: dshHomePath('integration-vault')`、`writeEnabled: false`）——搜索覆盖完整、读路径真实（`memory_missing`）、写拒绝（`MEMORY_APPEND_DISABLED`）、冷启动重断言全绿。回执再水化的 agent 侧路径未驱动（无带回执 agent 可用），记剩余检查。
- **判定：机械挂载缺口已由上游补齐（M6）；组合级四态升格见汇总表。**

### 8. shadow-router（P21-S）— Service 面已就绪（第三轮只读装配验证）
- cordis.yml：无自包文件（按挂载约定不算缺口）。
- Service Definition：`ShadowRouter extends Service`，default export（src/service.ts，注册 `ctx.shadowRouter`），receipt/spec/error/types 全量导出。
- inject：`['sessions', 'storageDomain', 'workspaceRegistry', 'agentBindings']`（service.ts:234）——base 提供前三者，`agentBindings` 由 session-identity 行提供；`workspaceRegistry` 由本线 M4 行提供（安装态原由 web-app 归一化补）。
- 工具注册：四工具（`project_open`/`project_send`/`project_status`/`project_stop`）**仅经 `markShadow(agent)` 入宿主标记 agent 的作用域**，不进全局 registry——本组合无 Shadow agent，探针实测全局零泄漏。
- Config schema：`static Config`（schemastery；`authorizedRoots` fail-closed 默认空、`controllerProfile`、三条限额默认）——`authorizedRoots` 每项须为装载期已存在的绝对目录，否则激活 fail loud（探针 boot 即该校验通过的实证）。
- 持久化：`shadow_router` 域三表（bindings/deliveries/requests），init 冷恢复全表 + 中途态对账（reserving/provisioning 收敛）。
- 组合级验证（本线第三轮）：只读装配（`authorizedRoots: [dshHomePath('integration-shadow-roots')]`，不标记任何 Shadow agent）——四工具全局零泄漏、未标记调用方 fail-closed（`SHADOW_CALLER_FORBIDDEN`）、冷启动重断言成立。`markShadow` 的 agent 侧安装与绑定行级冷恢复未驱动（需真实 Shadow agent），记剩余检查。
- 组合级验证（本线第五轮，分支 `p/integration-3`）：组合面补位——宿主经公开 `markShadow` seam 标记真实组合 agent（S6 包级标记方式升到组合级；cordis.yml 无声明式标记面，装配为探针驱动、不虚构档案行）：标记 agent 作用域四工具全可解析（`tools.get(name, scope)` + `schemas(scope)` 枚举），controller 角色绑定不遮蔽作用域自有层；未标记组合 agent 作用域零解析零枚举；标记 agent 真实绑定行 write-through 落绑定存储并冷恢复角色一致。**S6 剩余检查项（markShadow agent 侧安装）自此在组合级驱动闭环；剩余收口为真实 `project_open`/投递流（需真实投递目标与双项目根，归下一波）。**
- 配套机械缺口：`tsconfig.base.json` 源面 alias 合入时缺失（生成器无法推导），`b83964210f` 手写补齐。
- **判定：机械缺口仅"profile 挂载层 + authorizedRoots 行 + alias"；组合级四态升格见汇总表。**

### 9. 参照面（非本轮插件）
- devframe：支持库（controller/evidence/reliability 的类型与 reliability 实现来源），无 Service default export，不挂载；其 `./reliability`、`./shared`、`./controller/goal-binding` 子路径导出须可解析（已具备）。
- composition-smoke：test-support 客户端冒烟（P07 已交付），不属本 profile。

## 缺口汇总

### 机械已补项（本线在集成 profile 层补齐，不改 src）
| # | 项 | 落点 |
| --- | --- | --- |
| M1 | 七个插件的 profile 挂载行（session-identity / agent-hierarchy / project-controller / agent-evidence / agent-reliability / project-memory 只读装配 / shadow-router 只读装配，含 id/name/config） | `.agents/devframe/integration/cordis.patch.yml` → 隔离 home profile |
| M2 | profile manifest（bundles 栈 dsh-base + dsh-headless；插件与 llm-replay dependencies 声明满足 resolver manifest 约束） | 隔离 home `profiles/integration/package.json` |
| M3 | 插件包 node_modules 链接（十包 junction 进 profile node_modules，built 模式可解析） | 隔离 home profile node_modules |
| M4 | `workspace` + `worktree-registry` 两行补齐（base 的 tool-worktree 硬注入这两个服务；安装态由 web-app 归一化提供、自定义 profile 不携带；shadow-router 亦硬注入 workspaceRegistry）。**第五轮 supersede**：`p/bundlefix`（`06d6950c38`）使 shipped headless 自带同形两行（镜像自本行原 insert），档案层移除该两行避免含 headless 栈内重复 id（F10）；base-only 探针栈由探针自带两行补位 | 原：集成档案 insert 块 → 现：shipped headless 原生 + 探针自带 |
| M5 | `session-persistence-jsonl` `compression: none` restate（sessions root 单一编码 fail-loud 约束） | 集成档案顶层 restate |
| M6 | project-memory 只读装配行（第二轮：`workspaceId: integration` + 探针 Vault + `writeEnabled: false`） | 集成档案 insert 块 |
| M7 | shadow-router 只读装配行（第三轮：fail-closed `authorizedRoots` 指向隔离 home 下探针专属目录 + 目录预建 + junction/manifest 增补）与 `tsconfig.base.json` 源面 alias 手写补齐（`b83964210f`） | 集成档案 insert 块 + 隔离 home + 根 tsconfig |
| M8 | hierarchy 在线拒绝探针补位（第四轮：探针 hierarchy 面三断言 + 冷恢复重断言）及其实测修正——`roleToolPolicies` 三角色名单 `bash` → `pwsh`（F9，allow-face 装置 fail-loud 揪出） | `probe-cold-recovery.ts` + 集成档案 roleToolPolicies |
| M9 | shadow 组合面补位（第五轮：宿主 seam 标记真实组合 agent + 作用域四工具可见 + 未标记零泄漏 + 绑定行 write-through 落盘 + 冷恢复）及 F10 修正——档案层移除 workspace/worktree-registry insert、探针自带两行 | `probe-cold-recovery.ts` + 集成档案 |

### 语义待办项（原组长归属）
| # | 项 | 状态 | 归属 |
| --- | --- | --- | --- |
| S1 | project-memory Service 化（Cordis 插件形态 + Context 扩增 + inject 声明） | **已落地**（上游 `781e2ff9e9`，本线组合验证通过） | L-Memory（已合并） |
| S2 | project-memory 三工具注册 `ctx.tools` | **已落地**（本线探针实测三工具注册成功） | L-Memory（已合并） |
| S3 | project-memory MemoryReceiptStore 落会话日志 | **已落地**（上游 `682c7c6008` receipt-log；agent 侧再水化路径本线未驱动，见剩余检查） | L-Memory（已合并） |
| S4 | 五插件的模型可见工具面（controller 任务板命令、evidence 回执入口等"会话级工具"）——当前五包均为纯服务；project-memory 三工具已全局注册但未纳入 agent-hierarchy 角色允许表（部署选择，待下一波） | 未启动 | P04/P05 原组长 |
| S5 | agent-reliability stop 对账身份的持久化 host 语义（跨重启保留 unresolved 身份） | 未启动 | P06 原组长 |
| S6 | shadow-router 真实 `project_open`/投递流组合驱动（真实投递目标 + 双项目根；属只读装配边界外的生产流） | markShadow agent 侧安装已闭环（第五轮组合面：作用域四工具可见 + 绑定行落盘 + 冷恢复）；投递流未驱动 | P21-S 原组长 |
