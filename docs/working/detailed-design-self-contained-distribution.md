# DevFrame 插件自包含分发——详细设计（文件级 diff）

> 输入：`plugin-self-contained-distribution-plan.md`（概要设计，已吸收评审 R1–R4）+ `review-plan-stage1.md`（评审报告）+ 20 个发布对象当前 `package.json` 实测 + `expert-pack-dev`/`expert-pack-paper` 实际目录树 + `apps/desktop-host/package.json`。
> 本文件只设计，不改任何源码/package.json/脚本。所有 diff 均为"目标态"，实现阶段照此逐文件落地。
> 实测日期：2026-09-19。仓库：`D:\dsh-devframe`。

---

## 0. 实测事实基线（写 diff 的唯一依据）

### 0.1 版本现状（逐包实读）

| 版本 | 包 |
| --- | --- |
| `0.1.2-alpha.4` | 18 个 experimental 全部 + `@deepseek-ai/dsh-worktree-registry`（共 19） |
| `1.0.2` | `@deepseek-ai/cordis-plugin-logger-console`（vendor/logger-console，rescoped 自上游 Shigma 包） |
| `0.1.6-alpha.1` | `@deepseek-ai/dsh-desktop-host`（apps/desktop-host，**非发布对象**，仅 P5 改它的 deps） |

### 0.2 `private` / `publishConfig` / `repository` / `engines` 现状（逐包实读）

- `private: true`：18 个 experimental **全部**带；`worktree-registry`、`logger-console` **无** private 字段（无需移除）。
- `publishConfig.access=public`：仅 `worktree-registry`、`logger-console` 两处已有；**18 个 experimental 全部缺**（概要设计 P1 写"17 个"，实测为 18，见 §F-D1）。
- `repository` 已有（9 个）：`shadow-controller`、`expert-team`、`client-ui-expert-team`、`client-ui-project-memory`、`expert-pack-dev`、`expert-pack-paper`、`devframe-profile`、`worktree-registry`、`logger-console`。
- `repository` 缺失（**实测 11 个**，概要设计 P1 写"9 个"）：`project-contracts`、`session-identity`、`devframe`、`agent-evidence`、`agent-hierarchy`、`project-controller`、`shadow-routing`、`shadow-router`、`project-memory`、**`agent-dispatch`、`command-goal-binding`**（后两个概要设计/评审 R4 漏列，见 §F-D2）。
- `engines`：**20 个发布对象全部无**（与评审"无任一发布包声明 engines"一致）。

### 0.3 schemastery / dsh-brand / cosmokit 的 deps 实测落点（P3 消歧依据）

| 包 | deps 中 | peer 中是否已有 |
| --- | --- | --- |
| `expert-team` | `@deepseek-ai/schemastery` | **无**（只在 deps）→ 需新增进 peer |
| `project-controller` | `@deepseek-ai/schemastery` | **无**（只在 deps）→ 需新增进 peer |
| `project-memory` | `@deepseek-ai/schemastery` | **无**（只在 deps）→ 需新增进 peer |
| `shadow-router` | `@deepseek-ai/schemastery` | **无**（只在 deps）→ 需新增进 peer |
| `worktree-registry` | `@deepseek-ai/schemastery`、`@deepseek-ai/dsh-brand` | **无**（两者都只在 deps）→ 均需新增进 peer |
| `logger-console` | `@deepseek-ai/schemastery`、`@deepseek-ai/cosmokit` | **无**（两者都只在 deps）→ 均需新增进 peer |
| `command-goal-binding` | schemastery 不在 deps | peer 已有（L38）→ **不动** |

> 关键纠正：概要设计 §2.4/P3 措辞"从 deps 移除，**保留** peer"对前 6 个包不成立——这 6 个包的 schemastery（及 worktree-registry 的 dsh-brand、logger-console 的 cosmokit）**当前根本不在 peerDependencies**。正确动作是"从 deps 删除 **且** 新增进 peerDependencies"。见 §F-D3。
> `logger-console` deps 中的 `supports-color@^9.4.0` 是终端着色运行时小工具，**不是框架单例**，保留 deps，不动。

### 0.4 expert-pack 两包实际目录树（files glob 写死依据）

`expert-pack-dev`（非 lib、非 node_modules）：
```
team.yml
README.md  README.zh.md  README.i18n.yaml
experts/  architect.md  code-reviewer.md  engineer.md  product-manager.md  qa.md  tech-lead.md
schemas/  design-summary.schema.json  implementation-summary.schema.json  prd-summary.schema.json
          review-summary.schema.json  tasks-summary.schema.json  test-report-summary.schema.json
          test-results-summary.schema.json
skills/   acceptance-checklist/{SKILL.md, references/checklist.md}
          code-review-checklist/{SKILL.md, references/checklist.md}
src/index.ts
```

`expert-pack-paper`（非 lib、非 node_modules）：
```
team.yml  team.m2-draft.yml      ← 草稿文件，明确不进包
README.md  README.zh.md  README.i18n.yaml
experts/  experimenter.md  idea-selector.md  literature-reviewer.md  method-designer.md
          reviewer-1.md  reviewer-2.md  reviewer-3.md  topic-scout.md  writer.md
schemas/  draft-summary.schema.json  experiments-summary.schema.json  research-questions-summary.schema.json
          review-summary.schema.json  revision-plan-summary.schema.json  survey-summary.schema.json
skills/   review-checklist/{SKILL.md, references/checklist.md}
          statistics-checklist/{SKILL.md, references/checklist.md}
src/index.ts
```

---

## A. 逐 package.json 改造 diff 表（20 个发布对象全覆盖）

> 约定：
> - 版本目标：**19 个包**（18 experimental + worktree-registry）`version` 由 `0.1.2-alpha.4` → **`0.1.6-alpha.1`**；`logger-console` **保留 `1.0.2`**（§0.1 例外，见 §F-D5）。
> - 所有新增 `repository.url` 一律 `git+https://github.com/deepseek-ai/deepseek-harness.git`，`directory` 为包相对仓库根路径。
> - 所有新增 `engines` 一律 `{ "node": "^22.19 || >=24" }`。
> - 所有新增 `publishConfig` 一律 `{ "access": "public" }`。
> - 表中"deps 改动"只列**增删项**；未列的 deps 原样保留。
> - peer 版本写法：in-repo 仍 `workspace:^`（与现状一致）；`pnpm publish/pack` 时自动转真实 semver（P7 preflight 强制校验无 `workspace:` 泄漏）。

### A.1 project-contracts — `packages/experimental/project-contracts/package.json`

| 项 | 现状 | 目标 |
| --- | --- | --- |
| `private` | `true` | **删除该行** |
| `version` | `0.1.2-alpha.4` | `0.1.6-alpha.1` |
| `files` | `["lib/index.js","lib/types/**/*.d.ts"]` | 不变 |
| `dependencies` | 无 | 不变（无） |
| `peerDependencies` | cordis/dsh-brand/dsh-session/dsh-worktree-registry | 不变 |
| `publishConfig` | 无 | **新增** `{ "access": "public" }` |
| `repository` | 无 | **新增** `{ type:git, url:<标准>, directory:"packages/experimental/project-contracts" }` |
| `engines` | 无 | **新增** `{ node: "^22.19 || >=24" }` |

### A.2 session-identity — `packages/experimental/session-identity/package.json`

| 项 | 现状 | 目标 |
| --- | --- | --- |
| `private` | `true` | 删除 |
| `version` | `0.1.2-alpha.4` | `0.1.6-alpha.1` |
| `files` | `["lib/index.js","lib/types/**/*.d.ts"]` | 不变 |
| `dependencies` | `zod@^4.4.3` | 不变（自带） |
| `peerDependencies` | cordis/dsh-brand/project-contracts/dsh-session/dsh-storage-domain/dsh-worktree-registry | 不变 |
| `publishConfig` | 无 | 新增 `{ access: public }` |
| `repository` | 无 | 新增（directory=`packages/experimental/session-identity`） |
| `engines` | 无 | 新增 |

### A.3 devframe — `packages/experimental/devframe/package.json`

| 项 | 现状 | 目标 |
| --- | --- | --- |
| `private` | `true` | 删除 |
| `version` | `0.1.2-alpha.4` | `0.1.6-alpha.1` |
| `files` | `["lib/index.js","lib/types/**/*.js","lib/types/**/*.d.ts"]` | 不变 |
| `dependencies` | `zod@^4.4.3` | 不变 |
| `peerDependencies` | 10 项（dsh-brand/cordis/dsh-agent/dsh-goal/dsh-jobs/dsh-session/dsh-session-persistence/dsh-subprocess/dsh-timeout/dsh-worktree-registry） | 不变 |
| `publishConfig` | 无 | 新增 |
| `repository` | 无 | 新增（directory=`packages/experimental/devframe`） |
| `engines` | 无 | 新增 |

### A.4 agent-evidence — `packages/experimental/agent-evidence/package.json`

| 项 | 现状 | 目标 |
| --- | --- | --- |
| `private` | `true` | 删除 |
| `version` | `0.1.2-alpha.4` | `0.1.6-alpha.1` |
| `files` | `["lib/index.js","lib/types/**/*.d.ts"]` | 不变 |
| `dependencies` | `zod@^4.4.3` | 不变 |
| `peerDependencies` | 7 项 | 不变 |
| `publishConfig` | 无 | 新增 |
| `repository` | 无 | 新增（directory=`packages/experimental/agent-evidence`） |
| `engines` | 无 | 新增 |

### A.5 agent-hierarchy — `packages/experimental/agent-hierarchy/package.json`

| 项 | 现状 | 目标 |
| --- | --- | --- |
| `private` | `true` | 删除 |
| `version` | `0.1.2-alpha.4` | `0.1.6-alpha.1` |
| `files` | `["lib/index.js","lib/types/**/*.d.ts"]` | 不变 |
| `dependencies` | `zod@^4.4.3` | 不变 |
| `peerDependencies` | 8 项 | 不变 |
| `publishConfig` | 无 | 新增 |
| `repository` | 无 | 新增（directory=`packages/experimental/agent-hierarchy`） |
| `engines` | 无 | 新增 |

### A.6 project-controller — `packages/experimental/project-controller/package.json`

| 项 | 现状 | 目标 |
| --- | --- | --- |
| `private` | `true` | 删除 |
| `version` | `0.1.2-alpha.4` | `0.1.6-alpha.1` |
| `files` | 6 个 lib JS + `lib/types/**/*.d.ts` | 不变 |
| `dependencies` | `@deepseek-ai/schemastery@workspace:^`、`zod@^4.4.3` | **删除 schemastery**；zod 保留 |
| `peerDependencies` | 14 项（无 schemastery） | **新增** `"@deepseek-ai/schemastery": "workspace:^"` |
| `publishConfig` | 无 | 新增 |
| `repository` | 无 | 新增（directory=`packages/experimental/project-controller`） |
| `engines` | 无 | 新增 |

### A.7 shadow-routing — `packages/experimental/shadow-routing/package.json`

| 项 | 现状 | 目标 |
| --- | --- | --- |
| `private` | `true` | 删除 |
| `version` | `0.1.2-alpha.4` | `0.1.6-alpha.1` |
| `files` | `["lib/index.js","lib/types/**/*.js","lib/types/**/*.d.ts"]` | 不变 |
| `dependencies` | 无 | 不变 |
| `peerDependencies` | 6 项 | 不变 |
| `publishConfig` | 无 | 新增 |
| `repository` | 无 | 新增（directory=`packages/experimental/shadow-routing`） |
| `engines` | 无 | 新增 |

### A.8 shadow-router — `packages/experimental/shadow-router/package.json`

| 项 | 现状 | 目标 |
| --- | --- | --- |
| `private` | `true` | 删除 |
| `version` | `0.1.2-alpha.4` | `0.1.6-alpha.1` |
| `files` | `["lib/index.js","lib/types/**/*.d.ts"]` | 不变 |
| `dependencies` | `shadow-routing@workspace:^`、`schemastery@workspace:^`、`zod@^4.4.3` | **删除 schemastery**；shadow-routing、zod 保留 |
| `peerDependencies` | 10 项（无 schemastery） | **新增** `"@deepseek-ai/schemastery": "workspace:^"` |
| `publishConfig` | 无 | 新增 |
| `repository` | 无 | 新增（directory=`packages/experimental/shadow-router`） |
| `engines` | 无 | 新增 |

### A.9 shadow-controller — `packages/experimental/shadow-controller/package.json`

| 项 | 现状 | 目标 |
| --- | --- | --- |
| `private` | `true` | 删除 |
| `version` | `0.1.2-alpha.4` | `0.1.6-alpha.1` |
| `files` | index/shadow-agent/typert.host/typert.remote-client JS+DTS + types glob | 不变（已含 `./shadow-agent`、`./typert` 子导出对应文件） |
| `dependencies` | 无 | 不变 |
| `peerDependencies` | 7 项 | 不变 |
| `publishConfig` | 无 | 新增 |
| `repository` | 已有 | 不变 |
| `engines` | 无 | 新增 |

### A.10 agent-dispatch — `packages/experimental/agent-dispatch/package.json`

| 项 | 现状 | 目标 |
| --- | --- | --- |
| `private` | `true` | 删除 |
| `version` | `0.1.2-alpha.4` | `0.1.6-alpha.1` |
| `files` | `["lib/index.js","lib/types/**/*.d.ts"]` | 不变 |
| `dependencies` | 无（仅 peer） | 不变 |
| `peerDependencies` | 16 项 + `peerDependenciesMeta.dsh-agent-presets.optional=true` | 不变（presets 保持 optional；其余两项 host peer：`dsh-session-persistence-jsonl`、`dsh-deepseek-llm-api-extensions` 维持非 optional，由 desktop-host 层保证安装——见 §C） |
| `publishConfig` | 无 | 新增 |
| `repository` | 无 | **新增**（directory=`packages/experimental/agent-dispatch`）【概要设计/评审 R4 漏列】 |
| `engines` | 无 | 新增 |

### A.11 command-goal-binding — `packages/experimental/command-goal-binding/package.json`

| 项 | 现状 | 目标 |
| --- | --- | --- |
| `private` | `true` | 删除 |
| `version` | `0.1.2-alpha.4` | `0.1.6-alpha.1` |
| `files` | `["lib/index.js","lib/types/**/*.d.ts"]` | 不变 |
| `dependencies` | `agent-evidence`、`devframe`、`project-controller`（均 workspace:^） | 不变（发布时转真实 semver） |
| `peerDependencies` | 11 项（schemastery 已在 peer L38） | 不变（schemastery 已是纯 peer，**不动**） |
| `publishConfig` | 无 | 新增 |
| `repository` | 无 | **新增**（directory=`packages/experimental/command-goal-binding`）【概要设计/评审 R4 漏列】 |
| `engines` | 无 | 新增 |

### A.12 expert-team — `packages/experimental/expert-team/package.json`

| 项 | 现状 | 目标 |
| --- | --- | --- |
| `private` | `true` | 删除 |
| `version` | `0.1.2-alpha.4` | `0.1.6-alpha.1` |
| `files` | index/client/typert.host/typert.remote-client + types DTS | 不变 |
| `dependencies` | `dsh-llm`、`schemastery`、`ajv@^8.20.0`、`js-yaml@^4.2.0`、`zod@^4.4.3` | **删除 schemastery**；其余保留（dsh-llm 自带兜底，§2.4；ajv/js-yaml/zod 自带） |
| `peerDependencies` | 10 项（无 schemastery） | **新增** `"@deepseek-ai/schemastery": "workspace:^"` |
| `publishConfig` | 无 | 新增 |
| `repository` | 已有 | 不变 |
| `engines` | 无 | 新增 |

### A.13 project-memory — `packages/experimental/project-memory/package.json`

| 项 | 现状 | 目标 |
| --- | --- | --- |
| `private` | `true` | 删除 |
| `version` | `0.1.2-alpha.4` | `0.1.6-alpha.1` |
| `files` | index + `cordis.patch.yml` + typert 双端 + types DTS | 不变（`cordis.patch.yml` 已在 files 与 exports） |
| `dependencies` | `schemastery`、`zod`、`dsh-llm` | **删除 schemastery**；zod、dsh-llm 保留 |
| `peerDependencies` | 5 项（无 schemastery） | **新增** `"@deepseek-ai/schemastery": "workspace:^"` |
| `publishConfig` | 无 | 新增 |
| `repository` | 无 | 新增（directory=`packages/experimental/project-memory`） |
| `engines` | 无 | 新增 |

### A.14 client-ui-expert-team — `packages/experimental/client-ui-expert-team/package.json`

| 项 | 现状 | 目标 |
| --- | --- | --- |
| `private` | `true` | 删除 |
| `version` | `0.1.2-alpha.4` | `0.1.6-alpha.1` |
| `files` | `["lib/index.js","lib/client.js","lib/types/**/*.d.ts"]` | 不变 |
| `dependencies` | `react@^18.2.0` | 不变（renderer 端自带；asar 内扁平化单实例） |
| `peerDependencies` | 9 项 | 不变 |
| `publishConfig` | 无 | 新增 |
| `repository` | 已有 | 不变 |
| `engines` | 无 | 新增 |

### A.15 client-ui-project-memory — `packages/experimental/client-ui-project-memory/package.json`

| 项 | 现状 | 目标 |
| --- | --- | --- |
| `private` | `true` | 删除 |
| `version` | `0.1.2-alpha.4` | `0.1.6-alpha.1` |
| `files` | `["lib/index.js","lib/client.js","lib/types/**/*.d.ts"]` | 不变 |
| `dependencies` | `react@^18.2.0` | 不变 |
| `peerDependencies` | 12 项 | 不变 |
| `publishConfig` | 无 | 新增 |
| `repository` | 已有 | 不变 |
| `engines` | 无 | 新增 |

### A.16 expert-pack-dev — `packages/experimental/expert-pack-dev/package.json`（P0）

| 项 | 现状 | 目标 |
| --- | --- | --- |
| `private` | `true` | 删除 |
| `version` | `0.1.2-alpha.4` | `0.1.6-alpha.1` |
| `files` | `["lib/index.js","lib/types/**/*.d.ts"]` | **改为** `["lib/**/*.js","lib/types/**/*.d.ts","experts/**","skills/**","team.yml","schemas/**"]` |
| `dependencies` | 无 | 不变 |
| `peerDependencies` | cordis | 不变 |
| `publishConfig` | 无 | 新增 |
| `repository` | 已有 | 不变 |
| `engines` | 无 | 新增 |

> 说明：`team.yml` 单独列出（该包无 `team.m2-draft.yml`）；README.md 由 npm 约定自动打包，README.zh.md/README.i18n.yaml 为文档非运行时加载，不列入 files（patch.yml `packs` 只加载 experts/skills/team.yml/schemas）。

### A.17 expert-pack-paper — `packages/experimental/expert-pack-paper/package.json`（P0）

| 项 | 现状 | 目标 |
| --- | --- | --- |
| `private` | `true` | 删除 |
| `version` | `0.1.2-alpha.4` | `0.1.6-alpha.1` |
| `files` | `["lib/index.js","lib/types/**/*.d.ts"]` | **改为** `["lib/**/*.js","lib/types/**/*.d.ts","experts/**","skills/**","team.yml","schemas/**"]` |
| `dependencies` | 无 | 不变 |
| `peerDependencies` | cordis | 不变 |
| `publishConfig` | 无 | 新增 |
| `repository` | 已有 | 不变 |
| `engines` | 无 | 新增 |

> 关键：files 写死 `team.yml`（精确文件名），**不写 `team*.yml`**，从而显式排除 `team.m2-draft.yml`（§0.4 实测该文件存在）。preflight 断言 tarball 内**不含** `team.m2-draft.yml`。

### A.18 devframe-profile — `packages/experimental/devframe-profile/package.json`

| 项 | 现状 | 目标 |
| --- | --- | --- |
| `private` | `true` | 删除 |
| `version` | `0.1.2-alpha.4` | `0.1.6-alpha.1` |
| `files` | `["lib/index.js","cordis.patch.yml","lib/types/**/*.d.ts"]` | 不变（`cordis.patch.yml` 已在 files + exports + `dsh.bundle.patch`） |
| `dependencies` | 13 项 workspace:^（含 worktree-registry） | 不变（发布转真实 semver） |
| `peerDependencies` | cordis | 不变 |
| `publishConfig` | 无 | 新增 |
| `repository` | 已有 | 不变 |
| `engines` | 无 | 新增 |

> 观察（非阻断）：`description` 文本仍写 "Private profile bundle"，删除 `private` 后该词仅为描述文案，不影响发布；实现阶段可顺手改为自包含描述，也可保留（本设计不强制）。保持该包现有 4 空格-ish 缩进风格，diff 只动上述字段。

### A.19 worktree-registry — `packages/workflow/worktree-registry/package.json`（R1）

| 项 | 现状 | 目标 |
| --- | --- | --- |
| `private` | 无 | 不变（无） |
| `version` | `0.1.2-alpha.4` | `0.1.6-alpha.1` |
| `files` | `["lib/index.js","lib/types/**/*.js","lib/types/**/*.d.ts"]` | 不变 |
| `dependencies` | `dsh-brand@workspace:^`、`schemastery@workspace:^`、`zod@^4.4.3` | **删除 dsh-brand、schemastery**；zod 保留 |
| `peerDependencies` | cordis/dsh-storage-domain/dsh-subprocess/dsh-timeout/dsh-workspace | **新增** `@deepseek-ai/dsh-brand`、`@deepseek-ai/schemastery`（均 workspace:^） |
| `publishConfig` | 已有 `{access:public}` | 不变 |
| `repository` | 已有 | 不变 |
| `engines` | 无 | 新增 |

### A.20 logger-console — `vendor/logger-console/package.json`（R1）

| 项 | 现状 | 目标 |
| --- | --- | --- |
| `private` | 无 | 不变 |
| `version` | `1.0.2` | **保留 `1.0.2`**（不并入 0.1.6-alpha.1 发布线；§F-D5） |
| `files` | index/browser/types DTS+MAP + `src` | 不变（上游 vendored 布局，含 `src`；本设计不裁剪，发布体量由 preflight 大文件断言兜底） |
| `dependencies` | `cosmokit@workspace:^`、`schemastery@workspace:^`、`supports-color@^9.4.0` | **删除 cosmokit、schemastery**；`supports-color` 保留（终端着色运行时，非框架单例） |
| `peerDependencies` | cordis | **新增** `@deepseek-ai/cosmokit`、`@deepseek-ai/schemastery`（均 workspace:^） |
| `publishConfig` | 已有 `{access:public}` | 不变 |
| `repository` | 已有 | 不变 |
| `engines` | 无 | 新增 |

---

## B. 发布脚本设计（新增于 `scripts/`，本阶段只设计不写代码）

### B.1 `release:devframe:preflight`（本地必跑，失败即阻断）

目的：在**不连接公网 registry** 的前提下，用 `pnpm pack --dry-run` 对 20 个对象逐个断言。

逐包步骤（伪流程，顺序与 §A 一致）：

```
for each pkg in <20 对象路径>:
  out = pnpm --filter <pkg> pack --dry-run --json
  // 断言 1：tarball 内 package.json 无 workspace: 残留
  assert out.contents.packageJson 不含任何 "workspace:" 子串
  // 断言 2：files 字段与 §A 目标一致（pack --dry-run 的 included files 列表）
  assert out.files 覆盖 §A 该包 files 清单
  // 断言 3（仅 expert-pack 两包）：数据散文件在场、草稿缺席
  assert out.files 含 experts/**、skills/**、team.yml、schemas/**
  assert out.files 不含 "team.m2-draft.yml"  // 仅 paper
  // 断言 4（R1 双实例防护）：tarball 自身 deps 不含框架单例
  assert out.contents.packageJson.dependencies 不含 cordis / schemastery / dsh-brand / cosmokit
  // 断言 5：无意外大文件
  assert 无单文件 > 5 MB（源码/产物阈值）；logger-console 因含 src 单独阈值放宽到 20 MB 并打印告警
```

逐包校验命令（实现时用仓库自带 pnpm，`node_modules/.bin/pnpm`）：
- 通用：`pnpm --filter <pkg-name> pack --dry-run`（终端打印 included files）+ 解析输出 JSON 跑上述断言。
- 断言 1 的机器实现：`pack --dry-run --json` 输出含 tarball 内 package.json 副本，对其字符串扫描 `workspace:`。
- 断言 3 的机器实现：对 included files 路径列表做 glob 匹配。

退出码：任一断言失败 → 进程退出码非 0，打印包名 + 失败断言编号。

### B.2 `release:devframe:publish`（**需用户另行授权，本次只设计不执行**）

标注：本脚本**本任务不运行**。流程仅设计如下，待用户明确"授权公开发布"后启用。

伪流程：

```
# 前置：preflight 全绿
# 拓扑顺序（概要设计 §3，先底层后上层）：
ORDER = [
  project-contracts, session-identity, devframe, agent-evidence, agent-hierarchy,
  worktree-registry, project-controller, shadow-routing, shadow-router, shadow-controller,
  agent-dispatch, command-goal-binding, expert-team, project-memory,
  client-ui-expert-team, client-ui-project-memory, expert-pack-paper, expert-pack-dev,
  devframe-profile, logger-console
]
for pkg in ORDER:
  pnpm --filter <pkg> publish --access public --no-git-checks
  assert 远端可拉取：npm view <pkg>@0.1.6-alpha.1 version
# 空目录 install 验证（关键闭环）：
mkdir /tmp/verify && cd /tmp/verify && pnpm init
pnpm add <18 包名@^0.1.6-alpha.1> worktree-registry@^0.1.6-alpha.1 cordis-plugin-logger-console@1.0.2
assert node_modules 内 20 包齐全
assert node_modules 内 cordis/schemastery/dsh-brand/cosmokit 各仅 1 份（无嵌套副本）
```

### B.3 不触碰的边界

- **不改** `apps/desktop-host` 现有 `electron-builder` 脚本（`createElectronBuilderConfig`）；本设计仅在 §C 追加 dependencies 行，Builder 既有 `files: {dsh, dsh/node_modules} → asar` 通道不变。
- **不改** `apps/cli/package.json`（红线：不扩大到 merge-to-single-dir 启动修复）。

---

## C. desktop-host dependencies 追加清单（P5）

文件：`apps/desktop-host/package.json`，在现有 `dependencies`（13 行 workspace:^）**末尾追加**下列行；版本写法与现有条目一致用 `workspace:^`（in-repo 构建解析；公网分发时等价 `^0.1.6-alpha.1`）。

| # | 追加依赖 | 版本写法 | 说明 |
| --- | --- | --- | --- |
| 1 | `@deepseek-ai/dsh-experimental-project-contracts` | `workspace:^` | **概要设计 P5 传递包清单漏列**；该包在全族仅作 peer、从无 runtime deps 引用，pnpm 不会自动安装，必须显式列（§F-D4） |
| 2 | `@deepseek-ai/dsh-experimental-session-identity` | `workspace:^` | profile 13 leaf 之一 |
| 3 | `@deepseek-ai/dsh-experimental-devframe` | `workspace:^` | 传递（command-goal-binding deps） |
| 4 | `@deepseek-ai/dsh-experimental-agent-evidence` | `workspace:^` | 传递（command-goal-binding deps） |
| 5 | `@deepseek-ai/dsh-experimental-agent-hierarchy` | `workspace:^` | profile 13 leaf 之一 |
| 6 | `@deepseek-ai/dsh-experimental-project-controller` | `workspace:^` | 传递（command-goal-binding deps） |
| 7 | `@deepseek-ai/dsh-experimental-shadow-routing` | `workspace:^` | 传递（shadow-router deps） |
| 8 | `@deepseek-ai/dsh-experimental-shadow-router` | `workspace:^` | profile 13 leaf 之一 |
| 9 | `@deepseek-ai/dsh-experimental-shadow-controller` | `workspace:^` | profile 13 leaf 之一 |
| 10 | `@deepseek-ai/dsh-experimental-agent-dispatch` | `workspace:^` | profile 13 leaf 之一 |
| 11 | `@deepseek-ai/dsh-experimental-command-goal-binding` | `workspace:^` | profile 13 leaf 之一 |
| 12 | `@deepseek-ai/dsh-experimental-expert-team` | `workspace:^` | profile 13 leaf 之一 |
| 13 | `@deepseek-ai/dsh-experimental-project-memory` | `workspace:^` | profile 13 leaf 之一 |
| 14 | `@deepseek-ai/dsh-experimental-client-ui-expert-team` | `workspace:^` | profile 13 leaf 之一 |
| 15 | `@deepseek-ai/dsh-experimental-client-ui-project-memory` | `workspace:^` | profile 13 leaf 之一 |
| 16 | `@deepseek-ai/dsh-experimental-expert-pack-dev` | `workspace:^` | profile 13 leaf 之一（P0 数据包） |
| 17 | `@deepseek-ai/dsh-experimental-expert-pack-paper` | `workspace:^` | profile 13 leaf 之一（P0 数据包） |
| 18 | `@deepseek-ai/dsh-worktree-registry` | `workspace:^` | **只在 desktop-host 层加这一行**；devframe-profile 层不重复（D5 实证 duplicate loader entry 启动失败） |
| 19 | `@deepseek-ai/cordis-plugin-logger-console` | `workspace:^` | patch.yml insert 行对应包 |

明确**不**追加：
- `@deepseek-ai/dsh-experimental-devframe-profile`：经 `cordis.patch.yml` bundle 加载，不作为 desktop-host npm dep。
- `zod` / `ajv` / `js-yaml` / `react`：作为上述 17 个 experimental 包的 dependencies，由 pnpm 解析自动入 node_modules，不显式列。
- `dsh-llm`：随 expert-team/project-memory 的 deps 自带，不显式列。

---

## D. 版本兼容校验机制设计（P6）

### D.1 peer 满足性校验落点

- **层**：宿主插件加载器在 `plugins.add(spec)` 真正 cordis 实例化**之前**的钩子。即：Desktop 插件管理器解析完插件包名→定位 node_modules→读其 package.json→在 `ctx.plugin(...)` 注册调用之前，插入一段 peer 满足性检查。
- **检查对象**：被加载插件 `peerDependencies` 中以下"框架单例"键是否在宿主 `node_modules` 满足 semver：`@deepseek-ai/cordis`、`@deepseek-ai/schemastery`、`@deepseek-ai/dsh-brand`、`@deepseek-ai/cosmokit`、`@deepseek-ai/dsh-session`、`@deepseek-ai/dsh-agent`、`@deepseek-ai/dsh-tools`、`@deepseek-ai/dsh-goal`、`@deepseek-ai/dsh-worktree-registry`。
- **cordis peer 范围写法**：in-repo 保持 `workspace:^`；发布产物中 pnpm 解析为 cordis 当前发布线的 `^x.y.z`（实现时从 pnpm-lock 读取 cordis 实际版本号后固化，本设计不臆造版本号）。插件族统一 0.1.6-alpha.1 发布线，cordis 与插件版本对齐。

### D.2 失败 fail-loud 文案模板

任一 peer 不满足时，**立即抛错并中止加载**（不静默降级、不跳过插件），文案：

```
[devframe-plugin] peer dependency not satisfied:
  plugin: <pkg-name>@<plugin-version>
  requires: <peer-name>@<range>
  host provides: <peer-name>@<actual-version> (or: NOT INSTALLED)
  action: upgrade host Desktop to a release bundling <peer-name>@<range>,
          or pin this plugin to a version compatible with the host.
```

### D.3 双实例防护（与 §6.4 验收对齐）

- 构建期（preflight）：断言任一发布 tarball 的 `dependencies` 不含 cordis/schemastery/dsh-brand/cosmokit（§B.1 断言 4）。
- 产物期（desktop 构建后）：对 `node_modules` 树 `find` 这四个包名，断言各仅一份、无嵌套副本。

---

## E. 配套测试设计（实现阶段新增，本阶段只列路径与断言）

| 测试文件（建议路径） | 断言 |
| --- | --- |
| `scripts/desktop-plugin-delivery/preflight.test.ts` | 对 20 包 fixture 跑 §B.1 五条断言：tarball 无 `workspace:` 残留、files 覆盖目标、expert-pack 含数据散文件且 paper 不含 `team.m2-draft.yml`、deps 无框架单例、无意外大文件 |
| `scripts/desktop-plugin-delivery/files-coverage.test.ts` | 仅 expert-pack-dev / expert-pack-paper：断言 `experts/**`、`skills/**`、`team.yml`、`schemas/**` 路径在 pack --dry-run included files 中逐目录至少命中一个文件；paper 额外断言 `team.m2-draft.yml` **不在** included files |
| `packages/workflow/worktree-registry/test/peer-singleton.test.ts` | 断言发布后 package.json：`dependencies` 不含 `@deepseek-ai/dsh-brand`、`@deepseek-ai/schemastery`；二者出现在 `peerDependencies` |
| `vendor/logger-console/test/peer-singleton.test.ts` | 断言发布后 package.json：`dependencies` 不含 `@deepseek-ai/cosmokit`、`@deepseek-ai/schemastery`；二者出现在 `peerDependencies`；`supports-color` 仍在 deps |
| `apps/desktop-host/test/devframe-deps.test.ts` | 断言 desktop-host dependencies 含 §C 全部 19 行；**不含** `zod`/`ajv`/`js-yaml`/`react`/`devframe-profile`；`@deepseek-ai/dsh-worktree-registry` 仅 1 行 |
| 宿主加载器校验单测（随 P6 钩子落点） | 构造一个 cordis 版本不满足 peer range 的插件 fixture → 加载器抛 §D.2 模板文案且不注册；构造满足 fixture → 正常加载 |

> 这些测试描述**行为**（行为在不在、文件进没进包、失败响不响），不凑数断言内部实现。

---

## F. 与概要设计的偏差记录（实测后修正，不静默改）

| # | 概要设计/评审原文 | 本设计实测修正 | 依据 |
| --- | --- | --- | --- |
| D1 | P1 / 评审 R3："其余 **17** 个均无 publishConfig" | **18** 个 experimental 全部缺 `publishConfig`（worktree-registry、logger-console 两个已有）。补全清单按 18 个列 | §A 全表逐包实读：18 个 experimental package.json 均无 publishConfig 键 |
| D2 | P1 / 评审 R4："缺 repository 的 **9** 包" | **11** 个：除已列 9 个外，**`agent-dispatch`、`command-goal-binding` 实测也无 repository**（原文漏列） | §A.10、§A.11 实读两份 package.json 无 repository 键 |
| D3 | §2.4/P3："从 deps 移除，**保留 peer**" | 对 expert-team / project-controller / project-memory / shadow-router / worktree-registry / logger-console 这 6 处，被移项**当前不在 peerDependencies**。动作是"从 deps 删除 **且新增进 peer**"，非"本就在 peer" | §0.3 表逐包核对 peerDependencies 字段 |
| D4 | P5 传递包清单：agent-evidence/devframe/project-controller/shadow-routing（未含 project-contracts） | desktop-host 追加清单**补 `project-contracts`**：该包在全族仅作 peer、从无 runtime deps 引用，pnpm 不自动安装，不显式列则运行时导入失败 | 全族 20 份 package.json 的 `dependencies` 字段扫描：project-contracts 仅出现在 peerDependencies |
| D5 | §3："全部 0.1.x，首次发布升 0.1.6-alpha.1" | `logger-console` **保留 `1.0.2`**，不并入 0.1.6-alpha.1 线（rescoped 自上游 Shigma 包，自带版本源流）；其余 19 个升 0.1.6-alpha.1 | §A.20；vendor 包版本独立性 |

> 除上述 5 条外，概要设计主干（路径 A、P0 数据包 files、schemastery/dsh-llm 消歧依据、worktree-registry 只进 desktop-host、overlay 令牌 fail-loud）经实测均成立，无其他事实偏差。

---

## 附：本设计自检清单

- [x] 20 个发布对象每个在 §A 有独立 diff 子表（A.1–A.20）。
- [x] R1（worktree-registry 的 dsh-brand/schemastery、logger-console 的 cosmokit/schemastery）在 A.19/A.20 逐行可核对 deps 删除 + peer 新增。
- [x] schemastery 6 处 deps 移除点（expert-team/project-controller/project-memory/shadow-router/worktree-registry/logger-console）全部在 §A 标注。
- [x] files glob（expert-pack 两包）写死，paper 显式排除 `team.m2-draft.yml`。
- [x] 除"保留/不动"外无"建议/待确认"模糊项；cordis peer 范围版本号标注为"实现时从 pnpm-lock 固化"，未臆造。
- [x] 本阶段未改任何源码/package.json/脚本，仅产出本设计文档。
