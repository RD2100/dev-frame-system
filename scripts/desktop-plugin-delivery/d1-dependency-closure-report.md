# D1 DevFrame 插件依赖闭包分析

审计时间：2026-09-17
审计对象：`packages/experimental/devframe-profile`

---

## 1. 直接依赖清单

`devframe-profile/package.json` 声明的 `dependencies`（均为 `workspace:^`），以及 `cordis.patch.yml` 中 `insert` 行引用的额外插件。

### 1.1 package.json dependencies

| 包名（短名） | 类型 | Desktop-host 已有？ | 需要打包？ |
|---|---|---|---|
| dsh-experimental-agent-dispatch | workspace 本地包 | ❌ 否 | ✅ 是 |
| dsh-experimental-agent-hierarchy | workspace 本地包 | ❌ 否 | ✅ 是 |
| dsh-experimental-command-goal-binding | workspace 本地包 | ❌ 否 | ✅ 是 |
| dsh-experimental-client-ui-expert-team | workspace 本地包 | ❌ 否 | ✅ 是（Host 端 inert；Web 端 /client export 需打包） |
| dsh-experimental-expert-pack-dev | workspace 本地包（数据包） | ❌ 否 | ✅ 是（见第3节路径风险） |
| dsh-experimental-expert-pack-paper | workspace 本地包（数据包） | ❌ 否 | ✅ 是（见第3节路径风险） |
| dsh-experimental-expert-team | workspace 本地包 | ❌ 否 | ✅ 是 |
| dsh-experimental-project-memory | workspace 本地包 | ❌ 否 | ✅ 是 |
| dsh-experimental-session-identity | workspace 本地包 | ❌ 否 | ✅ 是 |
| dsh-experimental-shadow-controller | workspace 本地包 | ❌ 否 | ✅ 是 |
| dsh-experimental-shadow-router | workspace 本地包 | ❌ 否 | ✅ 是 |

> desktop-host `package.json` 无任何 `dsh-experimental-*` 包；`apps/desktop/package.json` 仅有 `electron-updater`、`semver`（运行时）和构建工具（devDeps）。

### 1.2 cordis.patch.yml insert 引用的额外插件

| 行 id | 插件名 | 来源 | Desktop-host 已有？ | 需要打包？ |
|---|---|---|---|---|
| logger-console | `@deepseek-ai/cordis-plugin-logger-console` | vendor/logger-console（workspace:^，已 rescope） | ❌ 否 | ✅ 是 |

> `shadow-agent` 行引用 `@deepseek-ai/dsh-experimental-shadow-controller/shadow-agent`，是 shadow-controller 的子导出，无需额外包。

---

## 2. workspace 包递归依赖（一层）

### 2.1 外部 npm 包（来自各直接依赖包的 `dependencies` 字段）

| 外部包 | 版本约束 | 引入来源 | Desktop-host 已有？ | 需要打包？ |
|---|---|---|---|---|
| `zod` | `^4.4.3` | agent-hierarchy, session-identity, project-memory, shadow-router, expert-team | ❌ 否 | ✅ 是 |
| `ajv` | `^8.20.0` | expert-team | ❌ 否 | ✅ 是 |
| `js-yaml` | `^4.2.0` | expert-team | ❌ 否 | ✅ 是 |
| `react` | `^18.2.0` | client-ui-expert-team | ⚠️ 未确认（web frontend 可能携带） | ⚠️ 需验证 |

### 2.2 workspace 传递依赖（来自直接依赖包的 `dependencies` 字段，非 peer）

| 传递包（短名） | 引入来源 | 需要打包？ |
|---|---|---|
| dsh-experimental-agent-evidence | command-goal-binding | ✅ 是 |
| dsh-experimental-devframe | command-goal-binding | ✅ 是 |
| dsh-experimental-project-controller | command-goal-binding | ✅ 是 |
| dsh-experimental-shadow-routing | shadow-router, shadow-controller（peer） | ✅ 是 |
| `@deepseek-ai/schemastery` | expert-team, project-memory, shadow-router | ⚠️ 需验证（可能经 dsh 主包传递） |
| `@deepseek-ai/dsh-llm` | expert-team, project-memory | ⚠️ 需验证（可能经 dsh 主包传递） |

---

## 3. 资源路径风险点

### 风险 1 — workspaceRoot 绑定到 Desktop 进程 cwd

**文件**：`packages/experimental/devframe-profile/cordis.patch.yml`，第 50 行
```yaml
workspaceRoot: !!js process.cwd()
```
**风险**：Desktop（Electron）主进程 `process.cwd()` 返回应用安装目录或 OS 默认值，**不是用户的项目根目录**。`command-goal-binding` 以此值作为 goal worktree 根，导致 git 操作在错误目录执行。**必须通过 Desktop overlay 显式覆盖为用户所选路径。**

---

### 风险 2 — required-checks cwd 同样绑定到进程 cwd

**文件**：`packages/experimental/devframe-profile/cordis.patch.yml`，第 61 行
```yaml
cwd: !!js process.cwd()
```
**风险**：`git diff --check` 子进程工作目录与风险 1 同源。若 cwd 不是实际 git worktree，命令将在错误目录静默通过或因非 git 目录报错。**与风险 1 同批次修复。**

---

### 风险 3 — expert-team packs 路径硬编码为源码检出结构

**文件**：`packages/experimental/devframe-profile/cordis.patch.yml`，第 87–88 行
```yaml
packs:
  - !!js process.cwd() + '/packages/experimental/expert-pack-paper'
  - !!js process.cwd() + '/packages/experimental/expert-pack-dev'
```
**风险**：假定进程 cwd 为 monorepo 根且源码目录存在。Desktop 打包产物中源码目录不存在，`ExpertCatalog.load()` 在 load 时抛出 `EXPERT_TEAM_CATALOG_INVALID`（fail-loud crash）。**Desktop overlay 必须将 packs 替换为打包后数据包的实际绝对路径。**

---

### 风险 4 — expert-team artifactsDir 相对路径回退到 process.cwd()

**文件**：`packages/experimental/expert-team/src/plugin.ts`，第 125 行
```typescript
return resolve(process.cwd(), artifactsDir)
```
**风险**：当 `artifactsDir` 为相对路径时，以 `process.cwd()` 为基准解析。当前 profile 已用 `dshHomePath('expert-team-runs')` 提供绝对路径，正常不触发；但若 Desktop overlay 误传相对路径将静默落到错误位置。**建议 Desktop overlay 始终传绝对路径（当前 profile 已符合）。**

---

### 风险 5 — process.platform 分支（信息项，无需修复）

**文件**：`packages/experimental/devframe-profile/cordis.patch.yml`，第 72–74 行
```yaml
inheritedTools: !!js "[...(process.platform === 'win32' ? ['pwsh'] : ['bash']), ...]"
```
**说明**：已有平台分支，Windows 选 `pwsh`，非 Windows 选 `bash`。Desktop 打包时行为正确。**无需修复，但需确认 Desktop 产物中对应 shell 工具已注册。**

---

## 4. Desktop 插件加载机制

参考：`apps/desktop-host/config/desktop.cordis.patch.yml`（upstream）。

### 4.1 组合方式

Desktop-host 复用 Web 组合配置树，通过 `desktop.cordis.patch.yml` 覆盖差异行：

- **禁用** Web 独有行：`web-startup`、`webserver`、`web-runtime`、`client-hmr`、`open-in-app`、`ui-open-in-app`、`directory-picker`（均 `disabled: true`）
- **替换** `connection` 行：注入 `credentials`，config 置空
- **新增** `directory-picker-native`、`ui-directory-picker-native`

### 4.2 插件解析路径

Desktop-host `package.json` 所有依赖均为 `workspace:^`，由 Electron Builder 打包进 asar/node_modules。Cordis 运行时通过插件 `name` 字符串从 node_modules 解析模块。

**关键约束**：所有插件包必须出现在打包后的 node_modules 树中，否则 Cordis 加载行 fail-loud。当前 desktop-host 无任何 `dsh-experimental-*` 包，devframe-profile 引入的所有 experimental 插件必须通过以下方式之一交付：
1. 加入 `desktop-host/package.json` dependencies → 进入常规打包流程（**推荐**）
2. 通过外部机制（sideload/unpacked resource）注入，并保证 Cordis resolver 可达

### 4.3 `!!js` 求值时机

`!!js` 表达式在 Cordis loader 解析该 YAML 行时**同步求值**，发生在进程启动阶段，`process.cwd()` 已固定。这是风险 1–3 的根源——Desktop 启动时的 cwd 与 monorepo 开发环境完全不同。

---

## 5. 打包缺口总结

### 5.1 必须自带的依赖

**Workspace 本地包（共 14 个，含传递 dep）：**
- dsh-experimental-agent-dispatch
- dsh-experimental-agent-hierarchy
- dsh-experimental-agent-evidence
- dsh-experimental-command-goal-binding
- dsh-experimental-devframe
- dsh-experimental-project-controller
- dsh-experimental-project-memory
- dsh-experimental-session-identity
- dsh-experimental-shadow-controller
- dsh-experimental-shadow-router
- dsh-experimental-shadow-routing
- dsh-experimental-expert-team
- dsh-experimental-client-ui-expert-team
- cordis-plugin-logger-console（vendor/logger-console）

**外部 npm 包（确认缺失，共 3 个）：**
- `zod` ^4.4.3
- `ajv` ^8.20.0
- `js-yaml` ^4.2.0

### 5.2 必须修复的路径

1. **[高] expert-team packs**（cordis.patch.yml L87–88）：替换为打包后数据包绝对路径
2. **[高] workspaceRoot**（cordis.patch.yml L50）：替换为用户所选项目目录
3. **[高] required-checks cwd**（cordis.patch.yml L61）：同 workspaceRoot
4. **[中] expert-pack-dev / expert-pack-paper 打包策略**：确定以何种形式（asar 内 vs. extraResources 解包）存放数据包散文件（`experts/`、`skills/`、`team.yml`）

### 5.3 需要新增的配置

1. **Desktop overlay patch**（`desktop.cordis.patch.yml` 或新增 `desktop-devframe.cordis.patch.yml`）：覆盖 `command-goal-binding.config.workspaceRoot`、`checks[0].cwd`、`expert-team.config.packs`。
2. **desktop-host package.json**：将所有 `dsh-experimental-*` 包加入 `dependencies`。
3. **expert-pack 资源策略**：建议作为 `extraResources` 解包至 `resourcesPath`，并在 overlay 中用绝对路径绑定。

---

## 6. 不确定项

| 项目 | 问题 | 影响 |
|---|---|---|
| `react` 是否已在 Desktop asar | `dsh-web-frontend` 打包产物是否包含 react；client-ui-expert-team `/client` export 由 renderer 还是 host 加载 | 决定是否需要额外声明 react 依赖 |
| `@deepseek-ai/schemastery` 传递链 | `@deepseek-ai/dsh`（已在 desktop-host deps）是否经依赖链带入 schemastery | 需检查 `packages/dsh/package.json` deps |
| `@deepseek-ai/dsh-llm` 传递链 | 同上 | 同上 |
| `dshHomePath` 在 Desktop 中的路径 | `dshHomePath('expert-team-runs')` 展开的绝对路径是否可写（不在 asar 内） | 若落在 asar 内将无法写入 |
| shadow-agent 子导出可达性 | shadow-controller `./shadow-agent` 子导出在 Electron asar 中 exports map 是否完整保留 | 若 asar 不保留 exports 字段，子路径 import 可能失败 |

---

## 7. 落地记录（2026-09-17 接替恢复后）

### 7.1 已产出：Desktop overlay 补丁模板

文件：`scripts/desktop-plugin-delivery/desktop.devframe.cordis.patch.yml`。

- 覆盖第 5.2 节三条「必须修复的路径」：`command-goal-binding.config.workspaceRoot`、`checks[0].cwd`、`expert-team.config.packs`（其余行字段原样保留）。
- 三个替换令牌 `<DSH_WORKSPACE_ROOT>` / `<PACK_PAPER_DIR>` / `<PACK_DEV_DIR>` 故意保持非法路径值：D5 staging 若忘记替换，加载时将以非法路径响亮失败，而不是静默挂空。
- `dshHomePath('required-checks.json')` 与 `dshHomePath('expert-team-runs')` 保持表达式形式——`dshHomePath` 由 app-boot `boot()` 提供（已核实 `apps/desktop-host` 的 `runDesktopHost` 流程），在 Desktop 进程内可用。
- 应用方式：D5 staging 生成绝对路径后写入 staging 项目 profile 的用户补丁层（`projectDir/cordis.patch.yml`），或并入 Desktop composition；desktop-host 的叠加顺序为 bundle layers → 用户补丁层 → `desktop.cordis.patch.yml`，后层按 id 整行覆盖 config。

### 7.2 验证

`scripts/desktop-plugin-delivery/overlay-apply.spec.ts`（3 项，vitest）：

1. 用 `applyEntryPatches` 按 Desktop 实际叠加顺序组合 bundle + overlay，断言三条路径字段被替换、其余字段（maxAttempts、taskIds、artifactsDir、requiredChecksPath 表达式）原样保留。
2. 令牌未替换时以字面字符串保留，加载期 fail-loud。
3. bundle 行列表完整、按 id 打补丁、无告警跳过。

### 7.3 留给 D5 的输入

- 以何种形式打包 expert-pack 数据包（asar 内 vs. `extraResources` 解包）后，把实际绝对路径代入三个令牌。
- `desktop-host package.json` 加入全部 `dsh-experimental-*` 依赖与 `zod`/`ajv`/`js-yaml`（见第 4、5.1 节）。
- 验证 `react`/`schemastery`/`dsh-llm` 可达性与 `dshHomePath` 可写性（见第 6 节不确定项）。
