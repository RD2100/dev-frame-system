# DevFrame 插件自包含分发改造清单（路径 A）

> 依据：D1 报告（`scripts/desktop-plugin-delivery/d1-dependency-closure-report.md`）+ 2026-09-19 全量复核（13 个 profile 依赖、experimental 包 manifest、官方 `D:\dsh-upstream-latest` 对照）。
> 目标：DevFrame 插件族发布为**自包含 npm 包**，随官方 Desktop 分发自带依赖，不再依赖仓库 workspace 版本解析，根治"新老版本依赖不一致导致插件不可用"。
> 修订记录：2026-09-19 经 `review-plan-stage1.md` 独立评审（有条件通过），吸收 R1–R4 与 7 项建议。

## 0. 决策摘要

| 维度 | 决策 |
| --- | --- |
| 路径 | A：发布 npm 包 + 加入 `desktop-host` dependencies → Electron Builder 常规打包进 asar |
| 自带范围 | 外部依赖（zod/ajv/js-yaml/react）+ 插件间 workspace 依赖 + dsh-llm |
| peer 范围（宿主单例） | cordis、schemastery、dsh-session、dsh-agent、dsh-tools、dsh-goal、dsh-brand 等框架核心 |
| 版本策略 | 插件发布线统一 0.1.x；cordis peer `^0.1.x`；宿主加载时校验兼容面（见 §4.9） |
| 发布前置 | 需发布授权（D5 记录"公开发布需另行授权"）；先行私有 registry / 本地 tarball 验证 |
| 边界 | 不改官方 Desktop 插件管理器（`plugins.add(spec)` npm 精确版本）；不合并上游其他包；不删 `D:\dsh-upstream-latest` |

---

## 1. 审计基线（2026-09-19 复核，与 D1 差异已标注）

### 1.1 devframe-profile 实际依赖（13 个，比 D1 的 11 个多 2 个）

| # | 包（短名） | 目录 | 类型 | Desktop-host 现有 |
| --- | --- | --- | --- | --- |
| 1 | dsh-experimental-agent-dispatch | packages/experimental | 插件 | ❌ |
| 2 | dsh-experimental-agent-hierarchy | packages/experimental | 插件 | ❌ |
| 3 | dsh-experimental-command-goal-binding | packages/experimental | 插件 | ❌ |
| 4 | dsh-experimental-client-ui-expert-team | packages/experimental | 插件（client export） | ❌ |
| 5 | **dsh-experimental-client-ui-project-memory** | packages/experimental | 插件（client export） | ❌ 【D1 未列】 |
| 6 | dsh-experimental-expert-pack-dev | packages/experimental | 数据包 | ❌ |
| 7 | dsh-experimental-expert-pack-paper | packages/experimental | 数据包 | ❌ |
| 8 | dsh-experimental-expert-team | packages/experimental | 插件 | ❌ |
| 9 | dsh-experimental-project-memory | packages/experimental | 插件 | ❌ |
| 10 | dsh-experimental-session-identity | packages/experimental | 插件 | ❌ |
| 11 | dsh-experimental-shadow-controller | packages/experimental | 插件 | ❌ |
| 12 | dsh-experimental-shadow-router | packages/experimental | 插件 | ❌ |
| 13 | **dsh-worktree-registry** | packages/workflow/worktree-registry | 插件 | ❌（官方 0.1.6 bundle 不含）【D1 未列】 |

另有 `cordis.patch.yml` insert 行：`@deepseek-ai/cordis-plugin-logger-console`（vendor/logger-console，已 rescope）。

### 1.2 experimental 包清点（评审 R2 修正）

- `packages/experimental/` 目录实有 **32 个** `private: true` 的包。本任务闭包 = 从 `devframe-profile` deps 起做传递依赖闭包（peer 不计入发布），闭包内 **18 个**：

`project-contracts`、`session-identity`、`devframe`、`agent-evidence`、`agent-hierarchy`、`project-controller`、`shadow-routing`、`shadow-router`、`shadow-controller`、`agent-dispatch`、`command-goal-binding`、`expert-team`、`project-memory`、`client-ui-expert-team`、`client-ui-project-memory`、`expert-pack-dev`、`expert-pack-paper`、`devframe-profile`。

- 其余 14 个（agent-reliability、agent-team、agent-team-profile、agent-team-web-profile、agent-worktree、client-ui-agent-team、client-ui-shadow-entry、code-runtime-python、inspector、shadow-bridge、shadow-web-profile、tool-agent-team、webworker-packer、webworker-runtime）自成 agent-team / webworker / shadow-bridge 三个独立子图，**不被** 闭包内 18 包的 dependencies 引用（反向：如 client-ui-shadow-entry、shadow-bridge 反过来 peer 引用已列入的 shadow-controller/shadow-routing），故不在本任务范围。
- **发布前必须移除这 18 个 experimental 包的 private 标志或走发布专用 overlay。**

### 1.3 依赖设计现状：peer 为主、deps 为辅

- **deps（自带）**：zod（8 个 experimental 包 + `dsh-worktree-registry`）、ajv / js-yaml（expert-team）、react（2 个 client-ui 包）、dsh-llm（expert-team、project-memory）、schemastery（expert-team、project-controller、project-memory、shadow-router、**worktree-registry、vendor/logger-console**——评审 R1 补）、shadow-routing（shadow-router）、agent-evidence / devframe / project-controller（command-goal-binding）、**dsh-brand（worktree-registry）、cosmokit（vendor/logger-console）**——后两者评审 R1 补。
- **peer（宿主提供）**：cordis、dsh-agent、dsh-session、dsh-tools、dsh-goal、dsh-brand、dsh-subagent、dsh-workspace、dsh-storage-domain、dsh-session-persistence、dsh-worktree-registry、dsh-experimental-project-contracts、dsh-typert-protocol、**dsh-agent-presets、dsh-session-persistence-jsonl、dsh-deepseek-llm-api-extensions**（agent-dispatch peer，评审建议 3 补枚举）等。
- **双声明（deps 与 peer 并存）**：`dsh-llm`、`schemastery` → 需消歧（§2.4）。
- **expert-pack-dev / expert-pack-paper 的 `files` 仅含 `lib/index.js` + `lib/types/**/*.d.ts`**：`experts/`、`skills/`、`team.yml`、`schemas/` 数据散文件**不进发布包** → D1 风险 3 的深层原因，必须修（§4.4）。

### 1.4 官方对照（D:\dsh-upstream-latest，0.1.6）

- 官方 `desktop-host` deps 无任何 `dsh-experimental-*`，也无 dsh-llm / react。
- 官方 `apps/cli`（`@deepseek-ai/dsh`）**直接声明 `@deepseek-ai/schemastery`** → schemastery 经 `@deepseek-ai/dsh` 传递**必在 Desktop node_modules**（走 peer 安全）。
- 官方 cli deps **无 dsh-llm**（dsh-llm 位于 packages/llm/llm，其消费者链不含官方 cli 直接依赖）→ dsh-llm **不能假设宿主必带**，保留自带（§2.4）。
- 官方 Desktop 打包：`electron-builder` files = `lib/*.js` + `renderer/**/*` + `{dsh, dsh/node_modules}` → asar。**desktop-host dependencies 里有什么，分发物就带什么**——这就是"插件自带依赖"的落地通道。

---

## 2. 依赖处置决策（核心表）

### 2.1 必须自带（随插件包发布，进入 dependencies）

| 依赖 | 版本约束 | 引入方 | 处置 |
| --- | --- | --- | --- |
| `zod` | ^4.4.3 | 8 个 experimental 包 | 自带（保留 deps） |
| `ajv` | ^8.20.0 | expert-team | 自带 |
| `js-yaml` | ^4.2.0 | expert-team | 自带 |
| `react` | ^18.2.0 | client-ui-expert-team、client-ui-project-memory | 自带（renderer 端解析；asar 内 node_modules 扁平化，单实例） |
| `@deepseek-ai/dsh-experimental-shadow-routing` | workspace:^ | shadow-router | 自带（发布为独立包） |
| `@deepseek-ai/dsh-experimental-agent-evidence` | workspace:^ | command-goal-binding | 自带（发布为独立包） |
| `@deepseek-ai/dsh-experimental-devframe` | workspace:^ | command-goal-binding | 自带（发布为独立包） |
| `@deepseek-ai/dsh-experimental-project-controller` | workspace:^ | command-goal-binding | 自带（发布为独立包） |
| `@deepseek-ai/dsh-llm` | workspace:^ | expert-team、project-memory | **保留自带**（宿主不保证携带，见 §2.4） |

### 2.2 必须 peer（宿主单例，严禁自带）

| 依赖 | 理由 |
| --- | --- |
| `@deepseek-ai/cordis` | 插件注册/事件/服务单例契约；双实例 = 静默失效。AGENTS.md 强制 peer |
| `@deepseek-ai/schemastery` | config schema 类型互操作；官方 cli 已直接声明 → 宿主必带。**含 worktree-registry、vendor/logger-console 两处历史 deps，评审 R1 必须一并改 peer** |
| `@deepseek-ai/dsh-brand` | branded id 类型单例；worktree-registry 历史 deps，评审 R1 改 peer |
| `@deepseek-ai/cosmokit` | cordis 同构生态包（vendor/logger-console 历史 deps）；与 cordis 一并走宿主单例，评审 R1 改 peer |
| `@deepseek-ai/dsh-agent`、`dsh-session`、`dsh-tools`、`dsh-goal`、`dsh-subagent`、`dsh-workspace`、`dsh-storage-domain`、`dsh-session-persistence*`、`dsh-worktree-registry`、`dsh-experimental-project-contracts`、`dsh-typert-protocol` | 宿主运行面 API；Desktop 由 web profile 组合携带或由 DevFrame 包注入 |
| `dsh-agent-presets`、`dsh-session-persistence-jsonl`、`dsh-deepseek-llm-api-extensions` | agent-dispatch 的 peer，评审建议 3 补枚举；宿主由 web/desktop profile 组合携带，加载器 fail-loud 兜底 |

> 注意：`dsh-worktree-registry` 官方 0.1.6 bundle **不含**（D5 已实证）。DevFrame 若以 peer 引用它，则 Desktop 分发必须显式携带 → 它是**插件族的一部分，随 devframe-profile 的 dependencies 进入 desktop-host**（§5），同时对插件仍以 peer 声明（单例）。

### 2.3 插件间依赖（deps 形式）→ 全部发布 + 随包解析

见 §2.1 后 4 行。npm 发布后 `workspace:^` 转换为真实 semver（pnpm publish 内置行为，§4.2 实测确认）。

### 2.4 双声明消歧

| 包 | 现状 | 决策 | 依据 |
| --- | --- | --- | --- |
| `@deepseek-ai/schemastery` | expert-team / project-controller / project-memory / shadow-router 为 deps；command-goal-binding 为 peer | **统一改纯 peer**，从 4 个包的 deps 移除 | 官方 cli 直接声明 → 宿主必带；双实例风险 > 冗余保险收益 |
| `@deepseek-ai/dsh-llm` | expert-team / project-memory 为 deps；多处 peer | **保留 deps（自带）+ peer 共存；peer 不标 optional** | 宿主不保证携带（官方对照 §1.4）；自带兜底，peer 允许宿主覆盖。评审建议 4 澄清：dep 已保证安装，peer 再标 optional 语义重复，故统一不标 optional |

---

## 3. 发布清单与顺序（20 个发布对象 = 18 experimental + worktree-registry + vendor/logger-console；评审 R2 修正计数）

闭包计算依据：从 `devframe-profile` deps 起做传递依赖闭包（peer 不计入发布）；闭包外 14 个 experimental 包见 §1.2，不在本任务范围。

按依赖拓扑（先底层后上层，每层可并行）：

| 序 | 包 | 依赖上层 |
| --- | --- | --- |
| 1 | dsh-experimental-project-contracts | （无，契约底座） |
| 2 | dsh-experimental-session-identity | P1 |
| 3 | dsh-experimental-devframe | P1 |
| 4 | dsh-experimental-agent-evidence | P1、P3 |
| 5 | dsh-experimental-agent-hierarchy | P1、P2 |
| 6 | dsh-worktree-registry（workflow 组） | 官方包，随族发布 |
| 7 | dsh-experimental-project-controller | P1、P3、P4 |
| 8 | dsh-experimental-shadow-routing | P3 |
| 9 | dsh-experimental-shadow-router | P8、P2 |
| 10 | dsh-experimental-shadow-controller | P8 |
| 11 | dsh-experimental-agent-dispatch | P2、P3、P7、P9、P10、P6 |
| 12 | dsh-experimental-command-goal-binding | P3、P4、P7 |
| 13 | dsh-experimental-expert-team | P1、P2 |
| 14 | dsh-experimental-project-memory | P13 线 |
| 15 | dsh-experimental-client-ui-expert-team | P13 |
| 16 | dsh-experimental-client-ui-project-memory | P14 |
| 17 | dsh-experimental-expert-pack-paper / expert-pack-dev | （数据包，随 expert-team） |
| 18 | dsh-experimental-devframe-profile | 以上全部（组合入口，含 cordis.patch.yml） |
| 19 | `@deepseek-ai/cordis-plugin-logger-console`（vendor/logger-console） | cordis 生态，随 patch.yml insert 行加载 |

> 版本统一发布线：全部 `0.1.x`（当前 0.1.2-alpha.4 → 首次发布建议升 `0.1.6-alpha.1` 与 desktop-host 对齐，避免语义错位）。

---

## 4. 代码与配置改造点（按优先级）

### P0 — 数据包发布形态（阻断发布，对应 D1 风险 3）
- `expert-pack-dev`、`expert-pack-paper` 的 `files` 追加：`experts/**`、`skills/**`、`team.yml`、`schemas/**`（按实际目录核对）。评审建议 5：expert-pack-paper 另有 `team.m2-draft.yml`，详细设计写死 glob 清单——默认**不含**该草稿文件。
- 决策数据包进 asar 还是 `extraResources` 解包：**建议进包内**（`files` 全量，运行时经 `import.meta.url` 解析自身目录，不写死 cwd）——D1 5.3 曾建议 extraResources，但进包内更简单、路径天然自包含；若存在"运行期可写"需求（当前无）再改 extraResources。

### P1 — private 与发布属性（阻断发布）
- 18 个 experimental 包移除 `private: true`（或经发布 overlay 置 false）。
- **`publishConfig.access: public` 强制补全（评审 R3）**：实测仅 worktree-registry 已带，其余 17 个均无；scoped 包 `@deepseek-ai/*` 在 npm 默认 restricted，无此字段发布即被拒。逐包补。
- **`repository` 字段补全（评审 R4）**：实测缺 repository 的 9 包：project-contracts、session-identity、devframe、agent-evidence、agent-hierarchy、project-controller、shadow-routing、shadow-router、project-memory。按 worktree-registry 现有格式补 `git+https://github.com/deepseek-ai/deepseek-harness.git` + 各自 `directory`。
- **`engines` 字段统一补全（评审建议 2，非阻断）**：全部发布对象补 `engines: {node: "^22.19 || >=24"}`，与 AGENTS.md 对齐。
- `devframe-profile` 保留 `"dsh": {"bundle": {"patch": "./cordis.patch.yml"}}` 且 `files` 已含 `cordis.patch.yml`（已确认）→ 发布后 patch 随包分发。

### P2 — 依赖协议转换
- 发布时 `workspace:^` → 真实 semver：pnpm 11.7.0 内置转换（publish/pack 时）。**必须先 `pnpm pack --dry-run` 实测**转换结果，确认无 `workspace:` 泄漏进 tarball 的 package.json。

### P3 — 双声明消歧（§2.4，评审 R1 扩围）
- schemastery：从 expert-team / project-controller / project-memory / shadow-router 的 deps 移除，保留 peer。
- **评审 R1 必补**：`packages/workflow/worktree-registry/package.json` deps 中的 `@deepseek-ai/schemastery`、`@deepseek-ai/dsh-brand` 移入 peer；`vendor/logger-console/package.json` deps 中的 `@deepseek-ai/schemastery`、`@deepseek-ai/cosmokit` 移入 peer。否则这两个发布对象会在自己的 node_modules 下嵌套第二份 schemastery/dsh-brand/cosmokit，正是本次改造要根治的双实例风险。
- dsh-llm：保持 deps + peer，peer 不标 optional（§2.4 澄清）。

### P4 — 资源路径自包含（对应 D1 风险 1/2/3/4）
- `cordis.patch.yml` 中 `workspaceRoot`、`checks[0].cwd`、`packs` 三条 `!!js process.cwd()` 硬编码 → 由 Desktop overlay（`desktop.devframe.cordis.patch.yml`，已产出）以绝对路径覆盖；令牌替换为发布后数据包实际路径。
- `expert-team/src/plugin.ts` artifactsDir 相对路径回退（L125）：保持绝对路径传入约定（现状 profile 已符合），发布验收中加一条"相对路径 fail-loud 或拒绝"。

### P5 — desktop-host 集成
- `apps/desktop-host/package.json` dependencies 追加：13 个 profile 依赖（§1.1）+ `@deepseek-ai/cordis-plugin-logger-console` + 传递包（agent-evidence、devframe、project-controller、shadow-routing）。**注意：devframe-profile 层不得重复 worktree-registry 行**（D5 实证 `duplicate loader entry id` 启动失败）——该包只进 desktop-host 部署层。
- 外部包 zod/ajv/js-yaml/react：作为上述包的 dependencies 随 pnpm 解析自动进入 node_modules（无需显式加）。

### P6 — 版本兼容策略（防复发核心）
- 每个插件声明 `peerDependencies: { "@deepseek-ai/cordis": "^0.1.x" }`（发布线对齐）。
- 插件对宿主 API 面（dsh-session / dsh-agent / dsh-tools 等 peer）声明 semver 范围；**宿主加载时校验**（加载器/安装器在 cordis 解析前检查 peer 满足性，不满足 fail-loud 并提示安装的宿主版本，不静默降级）。
- dsh-llm 保留 deps 自带，其 peer 不标 optional（§2.4 澄清；评审建议 4）。

### P7 — 发布/打包流程脚本（新增，根 scripts）
- `release:devframe:preflight`：pack --dry-run 全包 → 校验 tarball 无 workspace: 泄漏、files 含数据散文件、无意外大文件。
- `release:devframe:publish`（需授权）：按 §3 顺序发布 + 校验 registry 拉取后 `pnpm install` 于空目录可解析。
- `desktop:build`：desktop-host 依赖装齐 → electron-builder（现有 `createElectronBuilderConfig`）。

---

## 5. Desktop 分发闭环（改造后形态）

```
npm registry（DevFrame 18 包 + logger-console）
      │ 发布（workspace:^ → semver；zod/ajv/js-yaml/react/dsh-llm 自带）
      ▼
desktop-host package.json dependencies（13 插件 + 传递包 + logger-console）
      │ Electron Builder files: {dsh, dsh/node_modules} → asar
      ▼
Desktop 分发物（自包含）：所有 DevFrame 包 + 外部依赖在 node_modules 树内
      │ Cordis 运行时按 name 从 node_modules 解析；cordis/schemastery 走宿主单例
      ▼
插件加载：路径经 overlay 绝对化 → 功能可用，与用户环境其他 DSH 版本无关
```

---

## 6. 验收清单（发布后逐项实测）

1. 每个 tarball：`package.json` 中无 `workspace:` 残留；`files` 覆盖数据散文件（expert-pack 两包）。
2. 空目录 `pnpm add <18 包>` 成功解析（不含 workspace 链接）。
3. Desktop 构建产物 `node_modules` 树核对：18 包 + zod + ajv + js-yaml + react 全部在场。
4. cordis/schemastery/dsh-brand/cosmokit 单例核对（评审建议 1 扩围）：产物树中无嵌套重复实例（`find node_modules` 对这四个包名各仅一份）。
5. 官方 Desktop 插件管理器安装（精确版本）→ 加载无 `fail-loud`；`--dump-config` 组合通过。
6. 专家团召唤（Gateway 写操作 + 审批 UI）、影子会话、记忆库三工具 + 库 UI、技能/MCP 面板：功能端到端。
7. 重启 Desktop：插件配置与版本保留；升级到新插件版本后配置不丢。
8. 与官方 0.1.6 基线对照：不含 devframe-profile 的 profile 无任何 DevFrame 行（禁用语义不回归）。
9. `pnpm run typecheck`、`pnpm run lint` 全绿；DevFrame 域 vitest 全量通过。

---

## 7. 风险与回滚

| 风险 | 概率/影响 | 缓解 |
| --- | --- | --- |
| 发布授权缺失（registry 认证） | 中/高 | 先私有 registry 或本地 tarball 验证全链路；公开发布单独授权（D5 记录） |
| peer 版本漂移：宿主升级后 cordis peer 不满足 | 中/中 | 发布线统一 0.1.x；加载器版本校验 fail-loud；升级文档写明兼容矩阵 |
| cordis/schemastery 双实例 | 低/高 | 验收项 4 强制；发布 preflight 检查 tarball 不含 cordis |
| 数据包路径在打包后失效 | 中/高 | P4 绝对路径 overlay + 令牌未替换 fail-loud（已实现，保持） |
| pnpm pack 转换非预期 | 低/中 | P7 preflight 强制 `--dry-run` + tarball 内容断言 |
| 回滚 | — | 版本号回退重发 + 安装器降级；插件配置按包版本隔离；保留 `D:\dsh-upstream-latest` 与当前工作树不提交集 |

---

## 8. 不确定项（构建/发布时实测，勿凭推断验收）

| 项 | 判定方法 |
| --- | --- |
| `dsh-llm` 在官方 0.1.6 Desktop 产物 node_modules 的可达性 | 构建后 `grep dsh-llm node_modules` 实测；结果不影响决策（已自带兜底） |
| `react` 在 renderer 端是否与宿主共存单实例 | 构建后核对 node_modules 树（asar 内扁平化预期单实例） |
| `dshHomePath('expert-team-runs')` 在 Desktop 展开路径可写性 | 运行期写入实测（不可写则改 DSH_HOME 下的可写目录） |
| asar 中 `exports` map 是否保留（shadow-controller `./shadow-agent` 子导出） | Desktop 加载实测；失败则改主入口导出 |
| `pnpm publish` 对 `workspace:^` 的转换结果 | `pack --dry-run` 实测（P7 强制） |

---

## 9. 实施步骤（按序）

1. **P0**：expert-pack 两包 files 补数据散文件 → `pnpm pack --dry-run` 验证内容。
2. **P3**：schemastery 消歧（4 包 deps 移除）；同步更新包 README 与依赖声明。
3. **P1**：17 包 private 处置 + publishConfig。
4. **P7**：写 preflight/publish 脚本；本地 registry 或 tarball 全链路试发。
5. **P5**：desktop-host dependencies 追加（注意 worktree-registry 单行）；`pnpm install` 全量通过。评审建议 6：apps/cli 启动是否解除阻塞仅作观察项记录，**不在本任务修改 apps/cli/package.json**（红线）。
6. **P4**：overlay 令牌替换为发布后实际路径；D5 复验（load + RPC + 重启）。
7. **P6**：peer 范围声明 + 加载器版本校验。
8. §6 验收清单全项执行；写收尾 Agent Note 与双语交接更新。

> 本清单为工作文档（docs/working，过期性材料）；稳定契约落地后归入各包 README 与 docs/subsystems 对应页面。
