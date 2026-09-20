# 阶段一评审报告：DevFrame 插件自包含分发改造清单（路径 A）

- 评审对象：`docs/working/plugin-self-contained-distribution-plan.md`（2026-09-19 版）
- 评审身份：独立第三方评审（只读，未修改任何源码/原设计文档）
- 评审日期：2026-09-19
- 评审方法：逐条打开 `packages/experimental/*/package.json`、`packages/workflow/worktree-registry/package.json`、`vendor/logger-console/package.json`、`D:\dsh-upstream-latest\apps\{cli,desktop-host}\package.json`、`packages/experimental/devframe-profile/{package.json,cordis.patch.yml}`、`scripts/desktop-plugin-delivery/desktop.devframe.cordis.patch.yml` 实测比对。

---

## 一、总体结论

**有条件通过（需修订后进入详细设计）。**

清单的主干架构判断正确：路径 A（npm 包 + desktop-host deps → asar）、P0 数据包 files 缺口、schemastery/dsh-llm 两条消歧依据、worktree-registry 只进 desktop-host 不进 profile 层、overlay 令牌 fail-loud 设计，均经实测成立。但存在 **1 个 P0 阻断级遗漏**（发布清单中的 worktree-registry 与 vendor/logger-console 仍把 schemastery/dsh-brand/cosmokit 作为运行时 dependencies，与清单自己 §2.2 的"宿主单例 peer"决策直接冲突，正是本次改造要根治的双实例风险）和 3 个必须在详细设计前修正的事实/流程项（包数自相矛盾、publishConfig 被降级为"建议"、9 包缺 repository）。修订这些后可开工。

---

## 二、逐项评审意见（带实测证据）

### 1. 事实准确性

**1.1 devframe-profile 13 个依赖 —— 通过。**
实测 `packages/experimental/devframe-profile/package.json` dependencies 恰好 13 个：agent-dispatch、agent-hierarchy、command-goal-binding、client-ui-expert-team、client-ui-project-memory、expert-pack-dev、expert-pack-paper、expert-team、project-memory、session-identity、shadow-controller、shadow-router、`@deepseek-ai/dsh-worktree-registry`。与 §1.1 表格逐行一致；§1.1 标注的两个"D1 未列"（client-ui-project-memory、worktree-registry）实测均在 deps 中。

**1.2 cordis.patch.yml 三 process.cwd() 硬编码与 logger-console insert —— 通过。**
实测 `devframe-profile/cordis.patch.yml`：
- L20-21 `logger-console` insert 行（`@deepseek-ai/cordis-plugin-logger-console`）存在；
- L50 `workspaceRoot: !!js process.cwd()`、L61 `checks[0].cwd: !!js process.cwd()`、L91-92 `packs: [process.cwd()+'/packages/experimental/expert-pack-paper', ...expert-pack-dev]` 三处硬编码均与 §1.3/§P4 描述一致；
- L39 `shadow-controller/shadow-agent` 子路径加载，与 §8 不确定项"exports map 子路径"对应（实测 shadow-controller exports 确有 `./shadow-agent`，files 已含 `lib/shadow-agent.js`，现状健康）。

**1.3 expert-pack-dev / expert-pack-paper 的 files 缺口 —— 通过（P0 成立）。**
实测两包 `files` 均仅为 `lib/index.js`、`lib/types/**/*.d.ts`；而目录下实际存在 `experts/`、`schemas/`、`skills/`、`team.yml`（expert-pack-paper 另有 `team.m2-draft.yml`）。这些数据散文件在 patch.yml 中由 `packs` 路径运行时加载，不进 tarball 即发布即坏。§1.3 与 P0 判断准确。

**1.4 外部依赖版本与引入方 —— 通过（含一处小遗漏）。**
实测：
- `zod@^4.4.3` 出现在 8 个 experimental 包 deps（expert-team、project-controller、project-memory、shadow-router、agent-evidence、devframe、agent-hierarchy、session-identity），与 §2.1"8 个 experimental 包"一致；**另** `worktree-registry` deps 也含 `zod@^4.4.3`（§2.1 未单列，因它属 workflow 组，可接受，但详细设计应点明）。
- `ajv@^8.20.0`、`js-yaml@^4.2.0` 仅 expert-team；`react@^18.2.0` 仅 client-ui-expert-team、client-ui-project-memory。均与 §2.1 一致。
- `dsh-llm` deps 在 expert-team、project-memory；peer 在 project-controller、shadow-routing、shadow-controller、agent-dispatch。与 §2.4 一致。

### 2. 18 包清单完整性 —— 有条件通过（计数自相矛盾）

- `packages/experimental/` 实测有 **32 个**均带 `package.json` 且 `private: true` 的目录，不是 §1.2 所称"全部 17 个"。
- 我逐一核对了未列入清单的 14 个（agent-reliability、agent-team、agent-team-profile、agent-team-web-profile、agent-worktree、client-ui-agent-team、client-ui-shadow-entry、code-runtime-python、inspector、shadow-bridge、shadow-web-profile、tool-agent-team、webworker-packer、webworker-runtime）：它们自成 agent-team / webworker / shadow-bridge 三个独立子图，**不被** 18 个目标包的 dependencies 闭包引用（反向：如 client-ui-shadow-entry、shadow-bridge 反过来 peer 引用已列入的 shadow-controller/shadow-routing）。故排除它们是对的，但清单没有写"闭包已核对、其余 14 个不在 DevFrame 闭包内"这句结论，读者无法判断是有意排除还是漏数。
- **计数硬伤**：§1.2 枚举 17 个（无 project-contracts），而 §3 发布表把 project-contracts 列为 P1 第一行——§3 实际枚举 18 个 experimental + worktree-registry = **19 个包**，与表头"18 个包"及 §1.2"17 个"两处都对不上。详见必修订项 R2。

### 3. 依赖三分与消歧决策 —— 依据成立，但 P3 漏了两个发布包

- **(a) schemastery 宿主必带 —— 成立。** 实测 `D:\dsh-upstream-latest\apps\cli\package.json`（即 `@deepseek-ai/dsh`）dependencies 直接声明 `@deepseek-ai/schemastery: workspace:^`；`apps/desktop-host/package.json` 依赖 `@deepseek-ai/dsh`，故 schemastery 经传递必在 Desktop node_modules。§2.2 改纯 peer 的依据成立。
- **(b) dsh-llm 宿主不保证 —— 成立且清单已诚实标注不确定。** 实测 upstream cli deps 无 dsh-llm；desktop-host 亦无。清单 §8 已把"构建后 grep dsh-llm node_modules 实测"列为不确定项，处理得当。
- **P3 漏项（阻断）**：§2.4/P3 只把 schemastery 从 4 个 experimental 包（expert-team、project-controller、project-memory、shadow-router）的 deps 移除，但实测：
  - `packages/workflow/worktree-registry/package.json` L41-45 dependencies 含 `@deepseek-ai/schemastery: workspace:^` **和** `@deepseek-ai/dsh-brand: workspace:^`；
  - `vendor/logger-console/package.json` L37-41 dependencies 含 `@deepseek-ai/schemastery: workspace:^` **和** `@deepseek-ai/cosmokit: workspace:^`。
  这两个包都在 §3 发布清单内。`workspace:^` 发布时转真实 semver 后，npm 极可能在它们自己的 node_modules 下嵌套第二份 schemastery（及 dsh-brand/cosmokit）——这恰是 §7 风险表"双实例"要防的事。清单 §2.2 自己把 schemastery、dsh-brand 列为"宿主单例 peer，严禁自带"，却让这两个发布包继续自带，自相矛盾。

### 4. P0–P7 风险遗漏 —— 主干齐全，补 4 处

- 已覆盖：P0 数据 files、P1 private、P2 workspace:^ 转换、P3 消歧、P4 路径自包含 overlay、P5 desktop-host 单行 worktree-registry（D5 duplicate loader entry 实证）、P6 peer 范围、P7 preflight 脚本。
- 遗漏：
  - **R1（P0）**：上述 worktree-registry / logger-console 的 schemastery(+dsh-brand/cosmokit) 未纳入 P3。
  - 无任一发布包声明 `engines` 字段；AGENTS.md 要求 Node `^22.19 || >=24`，详细设计应统一补 `engines`（非功能阻断）。
  - 9/18 包缺 `repository` 字段（实测：project-contracts、session-identity、devframe、agent-evidence、agent-hierarchy、project-controller、shadow-routing、shadow-router、project-memory 无 repository；worktree-registry、shadow-controller、client-ui 两包、expert-pack 两包、devframe-profile 有）。
  - agent-dispatch 的 peer 含 `dsh-agent-presets`、`dsh-session-persistence-jsonl`、`dsh-deepseek-llm-api-extensions`，§2.2 宿主提供清单未枚举这三者；虽有加载器 fail-loud 兜底，详细设计应明确它们由哪个宿主包携带。
  - P6 称"dsh-llm 的 peer 标记 optional"，但 §2.4 同时决定 dsh-llm 保留 deps——dep 已保证安装，再把同名列 peer 标 optional 语义重复，需澄清。

### 5. 验收标准可测性 —— 基本可测，1 处命令与标题不符

§6 九项中，1/2/3/4/5/8/9 均可在本机用具体命令判定（pack --dry-run、空目录 pnpm add、find node_modules、--dump-config、typecheck/lint/vitest）。第 6/7 项是端到端人工验收（专家团召唤、重启保留配置），可接受但需在详细设计给出录屏/快照证据形式。
- **小错**：§6.4 标题写"cordis/schemastery 单例核对"，但给出的命令 `find node_modules -name cordis` 只查 cordis。鉴于 R1，应改为同时断言 schemastery、dsh-brand、cosmokit 无嵌套副本。

### 6. 边界与红线一致性 —— 通过（1 处措辞需收紧）

- 未要求公开 npm 发布（P7 明确需授权、先走私有/tarball）；未动 `D:\dsh-upstream-latest`；未合并 browser-use/computer-use；devframe-profile 层不重复 worktree-registry 行（实测 patch.yml 确实无该行，与 §P5 一致）；overlay 模板 `scripts/desktop-plugin-delivery/desktop.devframe.cordis.patch.yml` 存在且 `<DSH_WORKSPACE_ROOT>`/`<PACK_PAPER_DIR>`/`<PACK_DEV_DIR>` 令牌保持未替换即失败的 fail-loud 设计。
- §9 第 5 步"顺带解除 merge-to-single-dir 启动阻塞——apps/cli 依赖回本仓库集合后不再引用 0.1.6 缺包"措辞越界：用户红线明确"本任务不扩大到 apps/cli/package.json 启动修复，除非详细设计证明同源"。应改写为"观察项，不在本任务修改 apps/cli"，避免实现阶段顺势改 cli。

---

## 三、必须修订项（按严重度排序）

### P0 阻断级（1 项）

- **R1：把 worktree-registry 与 vendor/logger-console 纳入 P3 消歧。**
  证据：`packages/workflow/worktree-registry/package.json` L41-45 deps 含 `@deepseek-ai/schemastery`、`@deepseek-ai/dsh-brand`；`vendor/logger-console/package.json` L37-41 deps 含 `@deepseek-ai/schemastery`、`@deepseek-ai/cosmokit`。两者均在 §3 发布清单。处置：schemastery 从两者 deps 移入 peer（与官方 cli 直带对齐）；dsh-brand（worktree-registry）按"branded id 单例"原则同样改 peer；cosmokit 作为 cordis 同构生态包，随 cordis peer 对齐或核实宿主携带后改 peer。否则本次改造的核心目标（消除框架双实例）在这两个包上不成立。

### P1 必须修订（3 项，开工前改文档即可）

- **R2：修正包数自相矛盾。** §1.2"全部 17 个 experimental 包"与 §3 表头"18 个包"均与实测枚举（18 个 experimental + worktree-registry = 19 个发布对象；仓库 experimental 目录实有 32 个 private 包）不符。统一为："DevFrame 闭包内 18 个 experimental 包 + worktree-registry + vendor/logger-console = 20 个发布对象；其余 14 个 private experimental 包经闭包核对不在本任务范围"（logger-console 是否计入"18"由清单作者统一定名，但数字必须与表格逐行对得上）。
- **R3：`publishConfig.access: public` 从"建议"升级为强制。** 实测 18 个包中仅 worktree-registry 已带 `publishConfig: {access: public}`，其余 17 个均无。scoped 包 `@deepseek-ai/*` 在 npm 默认 restricted，无此字段发布即被拒。P1 应改为"17 个包逐一补 publishConfig.access=public"，并在详细设计落成逐包 diff。
- **R4：补齐 9 个包的 `repository` 字段。** 实测缺 repository 的 9 包：project-contracts、session-identity、devframe、agent-evidence、agent-hierarchy、project-controller、shadow-routing、shadow-router、project-memory。按 worktree-registry 现有格式补 `git+https://github.com/deepseek-ai/deepseek-harness.git` + 各自 directory。

---

## 四、建议但非阻断项

1. §6.4 验收命令扩展为同时断言 schemastery / dsh-brand / cosmokit 无嵌套副本（R1 的验收镜像）。
2. 18 包统一补 `engines: {node: "^22.19 || >=24"}`，与 AGENTS.md 对齐。
3. 明确 agent-dispatch 的三个宿主 peer（dsh-agent-presets、dsh-session-persistence-jsonl、dsh-deepseek-llm-api-extensions）由宿主哪条依赖链携带，写入 §2.2 表。
4. 澄清 P6"dsh-llm peer optional"与 §2.4"dsh-llm 保留 deps"的语义关系（建议：保留 deps 自带，peer 不标 optional，或反之，二者择一）。
5. expert-pack-paper 额外存在 `team.m2-draft.yml`，P0 补 files 时在详细设计里列出确切 glob 清单（含/不含该草稿文件由作者决定，但要写死）。
6. §9 第 5 步删除"顺带解除 merge-to-single-dir 启动阻塞"表述，改为观察项，避免触碰 apps/cli 红线。
7. 建议在 §3 补一句"闭包计算依据：从 devframe-profile deps 起做传递依赖闭包，peer 不计入发布"，把"为何不含其余 14 包"写成可复核结论。

---

## 五、复审结论

按 R1–R4 修订后（R1 必须落进 P3 改造点，R2–R4 为文档事实修正），本清单可进入详细设计阶段。其余建议项可在详细设计文档中一并吸收，不阻断开工。
