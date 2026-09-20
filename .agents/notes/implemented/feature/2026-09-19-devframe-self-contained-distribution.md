# Agent Note: DevFrame 插件族自包含分发改造（路径 A）

Status: implemented

## 背景

DevFrame 插件族此前全部 `private: true`，随官方 Desktop 分发时依赖由宿主环境决定，新老版本依赖不一致会导致插件静默不可用。本改造按详细设计 `docs/working/detailed-design-self-contained-distribution.md`（已吸收阶段一评审 R1–R4 与 §F 五条偏差修正）把 20 个发布对象改造为可自包含发布的 npm 包。

## 决策

- **20 个 package.json 逐包改造（§A）**：18 个 experimental 移除 `private`、版本对齐 `0.1.6-alpha.1`、补 `publishConfig.access=public`、`repository`、`engines: {node:"^22.19 || >=24"}`；`logger-console` 保留自身版本线 `1.0.2`。
- **P0 数据包 files 修复**：`expert-pack-dev`/`expert-pack-paper` 的 `files` 追加 `experts/**`、`skills/**`、`schemas/**`、精确 `team.yml`；paper 因 `team.yml` 写死而天然排除 `team.m2-draft.yml`。
- **框架单例消歧（R1/P3）**：把 `@deepseek-ai/schemastery` 从 6 个包 deps 删除并提升为 peer（expert-team/project-controller/project-memory/shadow-router/worktree-registry/logger-console）；worktree-registry 另把 `dsh-brand`、logger-console 另把 `cosmokit` 一并 deps→peer。`supports-color`/`zod` 等非单例运行时保留 deps。
- **desktop-host 依赖追加（P5/§C）**：`apps/desktop-host/package.json` dependencies 末尾追加 19 行 `workspace:^`；`worktree-registry` 只在此层出现一次（profile 层不重复，避免 duplicate loader entry）。
- **加载期 fail-loud 守卫（P6/§D）**：新增 `apps/desktop-host/src/peer-satisfaction.ts`，在 `desktopComposition()` 于 cordis 实例化之前校验已加载 bundle 的框架单例 peer 是否被宿主满足；缺装或版本不符即抛 §D.2 模板文案。`workspace:*` 范围内短路（in-repo 单实例天然满足），仅对发布后 concrete semver 范围强制。
- **本地 preflight（P7/§B）**：新增 `scripts/release/devframe-preflight.ts` 与根脚本 `release:devframe:preflight`，离线逐包断言可发布性与单例不嵌套、expert-pack 数据文件入包、paper 草稿缺席；本任务不执行任何公开发布。

## 备选与边界

- **不碰 `apps/cli/package.json`**：merge-to-single-dir 启动修复不在本任务范围。
- **不合并上游 browser-use/computer-use**；`D:\dsh-upstream-latest` 只读对照未改动。
- **semver 判定自包含实现**：仓库未提供 `semver` 依赖且不新增运行时依赖，守卫内置 `^`/`~`/`>=`/精确号最小子集。
- 运行时守卫仅做薄接线；in-repo 全部 peer 为 `workspace:^`，对现有 dev 启动零行为变化。

## 测试

六个配套测试：20 包可发布性静态断言、expert-pack files 覆盖与草稿排除、worktree-registry 与 logger-console 单例消歧、desktop-host 19 行闭包、peer 守卫 fail-loud 语义。另用 `pnpm pack --dry-run --json` 实证 expert-pack 两包 tarball 内容。

## 相关

概要设计 `docs/working/plugin-self-contained-distribution-plan.md`；阶段一评审 `docs/working/review-plan-stage1.md`；详细设计 `docs/working/detailed-design-self-contained-distribution.md`。
