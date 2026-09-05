---
description: L-Integration 真实组合集成候选线的逐包 Cordis 接入盘点与缺口判定（基线 cda26762d7 + main 4bc507e332 fast-forward，工作树 D:\dsh-devframe-p-integration）。
---

# 集成候选缺口清单（gaps）

- 状态：清点完成（源码阅读逐包核实；行号随基线，合并 main 后为 4bc507e332 树）。
- 基线：`p/integration` @ `cda26762d7`，本轮 fast-forward 合并 main 至 `4bc507e332`（纳入 P21-M project-memory）。
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
- **判定：机械缺口仅"profile 挂载层 + config 行"。**

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

### 7. project-memory（P21-M）— 未达插件形态（语义缺口在册）
- cordis.yml：无自包文件。
- Service Definition：**无 Cordis Service**——`ProjectMemoryService` 为普通类（src/memory.ts:186，非 `extends Service`），入口无 default export（src/index.ts），无 `declare module` Context 扩增，无 static inject。宿主需自行接线 workspace 身份/consent/回执存储。
- 工具注册：三工具未注册 `ctx.tools`（总控通报；L-Memory 在 p/memory-seam 分支处理，本线不代改）。
- Config schema：`resolveMemorySpec`（src/config.ts）为库级 spec 解析，非 loader Config 面。
- 持久化：Obsidian Vault 文件面 + `MemoryReceiptStore` 接缝（src/receipt.ts），回执未落会话日志（语义缺口在册）。
- **判定：语义缺口（Service 化 + 工具挂载 + 回执落日志），归 L-Memory；本轮不进 profile，不代改。**

### 8. 参照面（非本轮插件）
- devframe：支持库（controller/evidence/reliability 的类型与 reliability 实现来源），无 Service default export，不挂载；其 `./reliability`、`./shared`、`./controller/goal-binding` 子路径导出须可解析（已具备）。
- composition-smoke：test-support 客户端冒烟（P07 已交付），不属本 profile。

## 缺口汇总

### 机械已补项（本线在集成 profile 层补齐，不改 src）
| # | 项 | 落点 |
| --- | --- | --- |
| M1 | 五个已就绪插件的 profile 挂载行（session-identity / agent-hierarchy / project-controller / agent-evidence / agent-reliability，含 id/name/config） | `.agents/devframe/integration/cordis.patch.yml` → 隔离 home profile |
| M2 | profile manifest（bundles 栈 dsh-base + dsh-headless；六包 dependencies 声明满足 resolver manifest 约束） | 隔离 home `profiles/integration/package.json` |
| M3 | 插件包 node_modules 链接（六包 junction 进 profile node_modules，built 模式可解析） | 隔离 home profile node_modules |

### 语义待办项（归原组长，本线不代改）
| # | 项 | 归属 |
| --- | --- | --- |
| S1 | project-memory Service 化（default export Cordis Service + Context 扩增 + inject 声明） | L-Memory（p/memory-seam） |
| S2 | project-memory 三工具注册 `ctx.tools` | L-Memory（p/memory-seam） |
| S3 | project-memory MemoryReceiptStore 落会话日志 | L-Memory（p/memory-seam） |
| S4 | 五插件的模型可见工具面（controller 任务板命令、evidence 回执入口等"会话级工具"）——当前五包均为纯服务，模型/命令面待产品波次 | P04/P05 原组长 |
| S5 | agent-reliability stop 对账身份的持久化 host 语义（跨重启保留 unresolved 身份） | P06 原组长 |
