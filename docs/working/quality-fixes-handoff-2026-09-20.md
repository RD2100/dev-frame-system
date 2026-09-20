# 质量修复阶段交接（2026-09-20）

> 本文件记录「修复质量问题」阶段的完成状态与剩余工作。上一阶段的完整背景见 [desktop-product-delivery.md](desktop-product-delivery.md) 与 [acceptance-quality-stage6.md](acceptance-quality-stage6.md)。
> 本文由收尾 agent 撰写，供下一个 agent 直接接手。

## 一、本阶段已确认并修复的问题（全部有测试证据）

### 1. 安装链断裂（阻断级，已修）
- **症状**：`pnpm install` / 任何 `pnpm run *` 失败：`ERR_PNPM_WORKSPACE_PKG_NOT_FOUND — apps/cli: "@deepseek-ai/dsh-experimental-ptc-runtime-python@workspace:^" 不存在`。此前各 agent 均绕开 pnpm 裸跑 `node node_modules/vitest/vitest.mjs`，所以一直没人发现。
- **根因**：`apps/cli/package.json` 在一次上游版本同步（0.1.2-alpha.4 → 0.1.6-alpha.1）中被整体替换为上游形态，带进 3 个上游独有包（`dsh-experimental-ptc-runtime-python`、`dsh-workflow-ptc`、`dsh-tool-present`，另加 `dsh-http-proxy`、`dsh-mcp-resources`），本仓均不存在；同时误删了本仓依赖的 `dsh-experimental-devframe-profile`、`dsh-experimental-code-runtime-python`、`dsh-experimental-agent-evidence/project-controller/shadow-bridge`、`dsh-workflow-worker-thread`。
- **修复**：`apps/cli/package.json` 把这些包名映射回本仓真实存在的包（保留版本号 0.1.6-alpha.1 与新增的 `agent-loop`/`agent-loop-testkit` devDeps；`node-addon-require-builtin` 回退到 lockfile 已锁定的 ^0.1.4）。
- **验证**：`corepack pnpm install` 成功（17.9s，未触碰 registry）。`pnpm run *` 门不再被依赖自检拦截。

### 2. expert-team `truncateAtCodePoint` O(n²)（已修）
- `packages/experimental/expert-team/src/result-protocol.ts` 每次回退都重新 `Buffer.byteLength(value.slice(0, end))`，70KB 输入实测 5.9s、打爆 5s 测试超时（full-suite.txt 记为失败）。
- **修复**：单次编码为 Buffer，从 `maxBytes` 处按 UTF-8 续字节（`(byte & 0xc0) === 0x80`）回退，`toString('utf8', 0, end)` 解码。
- **验证**：`result-protocol.spec.ts` 12/12 通过，该用例 5938ms → 32ms。

### 3. project-memory devframe-memory 隔离语义三处漂移（已修，按用户确认的「排除」方向）
- **漂移实况**：README + `library-tools.ts` 工具描述 + 测试都说「排除 `devframe-memory`」；`library.ts` 却按 workspace 放行 `user/` 与 `projects/<workspaceId>/`；且库工具构造时**未传 workspaceId**，`library.ts:245` 的隔离检查因此被整个跳过——模型可 `library_read` 到 `devframe-memory/projects/<别的workspace>/*.md`（安全问题）。
- **修复**（结构性消除绕面，非打补丁）：
  - `devframe-memory` 并入 `isForbiddenName`（复用 `vault.ts` 的 `MEMORY_DIR` 常量），与 `.obsidian` 同级；
  - 删除 `isAllowedMemoryPath`、`validateRelativePath` 的 workspace scope 块，以及四个公开函数（`listLibraryFiles`/`readLibraryFile`/`searchLibrary`/`getLibraryStatus`）与 `ListLibraryOptions`/`SearchLibraryOptions` 的 `workspaceId` 参数线程；
  - `MemoryLibraryGateway` 构造函数撤掉第三参 `workspaceId`，`plugin.ts` 构造点同步；`library-tools.ts` 本就未传（绕面不再存在）。
  - 该改动同时消除了此前 `gateway.spec.ts` 11 处「构造参数数量不符」的 tsc 报错（测试本就是 2 参调用）。
- **验证**：`project-memory` 145/145 通过（此前 7 失败）。

### 4. `buildExcerpt` 缺边缘省略号且无字节上限（已修）
- `coverage-gaps.spec.ts` 期望裁切边缘有 `…` 标记，实现只做裸 slice；该函数同时无字节上限（2 MiB 文件可推出巨大 excerpt，与 `memory.ts` 的 `truncateToByteLimit` 不对称）。
- **修复**：前缀/后缀按裁切加 `…`，正文经 `truncateToByteLimit(snippet, 1024)` 约束。
- **验证**：随 project-memory 全量转绿。

### 5. project-memory 模型可见文案编码损坏（已修）
- 17 处 em-dash 被写成 GBK 误读形态（`鈥?`），其中 `plugin.ts` 的 `MEMORY_USAGE_SECTION`（拼进系统提示词的模型可见文案）13 处、`gateway.ts` 3 处（Remote 契约文档）、`library.ts` 1 处（注释）。
- **修复**：统一替换为 `— `（含缺失空格）。全仓扫描确认无其他 GBK 误读字符。

### 6. 热路径调试日志（已修）
- `library.ts` 每次解析 `.md` 都 `console.log('[library] parsed: ...')`，会把 vault 路径与笔记摘要打到 stdout。已删除。

### 7. devframe-profile 测试与分发改造漂移（已修）
- `tests/profile.spec.ts` 仍断言 `private === true` / `publishConfig === undefined`，而 9-19 分发改造已删除 `private` 并加 `publishConfig.access=public`。
- **修复**：断言改为 `private` 未定义 + `publishConfig.access === 'public'`，用例名改为「declares a publishable parseable layer…」。
- **验证**：`devframe-profile` 4/4 通过。

### 8. client-ui-project-memory 库页面 11 用例全红（已修，22/22 通过）
逐项对齐了「先写的测试契约」与实现的漂移：
- `LibraryCard.tsx` 文件计数渲染裸数字，绕过 locale key `fileCount`（违反 Client UI copy is locale-owned）→ 改用 `t('fileCount', { count })`；
- 文件卡是 `<div onClick>`（无 role、不可键盘操作、标题被 `displayTitle` 去掉扩展名）→ 主体改 `<button className={css.cardMain} aria-label={file.relativePath}>`（与 client-ui-expert-team 约定一致），卡内新增相对路径行；
- 移除卡内重复的「复制路径」按钮（与预览面板同名，复制语义应以 absolutePath 为准，保留面板那个）；
- 错误区/预览错误区补 `role="alert"`，hint toast 补 `role="status"`；
- 搜索框补 `aria-label={t('search.label')}`（此前 `search.label` 是死 key）；补 `search.action` 触发按钮（此前只支持回车）；`UNAVAILABLE` 时 `hidden` 搜索栏；
- 预览路径改显 `absolutePath`（测试断言绝对路径）；
- 空态文案按测试契约定稿（`还没有记忆笔记` / `与助手对话产生的重要事实会自动记录在这里。`），同步 zh/en；
- `searching` 状态接入搜索按钮（disabled + 文案），消除未使用变量；
- 补 `.searchBtn` CSS；清理该文件全部 oxlint 违规（`no-confusing-void-expression` 7 处、`arrow-parens` 2 处、未使用 import 3 个）。
- **验证**：`client-ui-project-memory` 22/22；该包 lint 干净。

### 9. desktop-host 缺失 `loadProfileDirectory` 导出（已修）
- Stage 6 报告称之为「9 项存量 tsc 错误」的失配：`apps/desktop-host/src/index.ts` 从上游照抄，import `loadProfileDirectory` 与 `PluginPackages`，但本仓 `app-boot` 只导出前者之外的大部分符号，`profile` 变量退化为 `any`，连带 28 个 `no-unsafe-*` lint 错误。
- **修复**：把上游 `loadProfileDirectory` 移植进 `packages/boot/app-boot/src/profile.ts`，同时抽出 `resolveBundleLayer` + `resolveProfileFromLayers` 两个 helper，让 `loadProfile` 与 `loadProfileDirectory` 共用同一套 layer 解析（保留本仓特有的 `patchReload` 字段与更严的 bundle 校验，未退回上游旧逻辑）；`index.ts` 导出该函数。
- **验证**：`packages/boot/app-boot` 146/146 通过。
- **遗留**：`PluginPackages` 导出在本仓 `app-boot` 仍不存在（`desktop-host/index.ts:352` 用到）。Stage 6 报告称上游 `profile-resolution/service.ts` 有之。**下一个 agent 需决定**：移植上游的 `profile-resolution` 模块，或把 desktop-host 改为本仓既有的 bundle 装载路径。此项未修前 desktop-host 无法完整启动。

## 二、本轮实测基线（收尾时复跑）

| 范围 | 结果 |
|---|---|
| `packages/boot/app-boot` | 146/146 ✅ |
| `packages/experimental/expert-team` + `client-ui-expert-team` | 全绿 ✅ |
| `packages/experimental/project-memory` | 145/145 ✅ |
| `packages/experimental/client-ui-project-memory` | 22/22 ✅ |
| `packages/experimental/devframe-profile` | 4/4 ✅ |
| `scripts/desktop-plugin-delivery` + `apps/desktop-host/tests` + `worktree-registry/peer-singleton` | 34/34 ✅ |
| `node_modules/tsx/dist/cli.mjs scripts/verify-client-ui-i18n.ts` | 通过（500 文件）✅ |
| oxlint（上表全部包，不含 apps/desktop 与 desktop-host/src） | 0 错误 ✅ |
| `corepack pnpm install` | 成功 ✅ |

**注意**：本仓 Bash 里 `pnpm` 不在 PATH，须用 `corepack pnpm`；`corepack pnpm exec` 仍会触发依赖自检，跑测试优先沿用 `node node_modules/vitest/vitest.mjs run <paths>`（现也可用 `corepack pnpm exec vitest`，安装链已修复）。

## 三、剩余工作（按优先级，交给下一个 agent）

### P0 — desktop-host 无法启动（接第 9 项遗留）
1. `PluginPackages` 导入失配（`apps/desktop-host/src/index.ts:22,352`）。上游实现在 `packages/boot/app-boot/src/profile-resolution/service.ts`；请核对上游后移植，或改走本仓等价装载路径。
2. **`apps/desktop-host/config/desktop.cordis.patch.yml` 缺失**（`config/` 目录整个不存在），被 `index.ts:98` 与 `apps/desktop/src/core-package-set.ts:19` 引用，宿主启动即失败。上游只读副本 `D:\dsh-upstream-latest\apps\desktop-host/config/desktop.cordis.patch.yml` **存在**，可取回对齐（注意按本仓路径改写内部引用）。
3. desktop-host 剩余 lint：第 9 项修完后复跑（预计 unsafe 系列随类型恢复自动消失）；`apps/desktop-host/tests/devframe-deps.spec.ts` 的 tsconfig 引用问题单独看。

### P1 — apps/desktop（Electron 主进程，未动）
- **lint 约 95 个错误**：`tests/main-startup.spec.ts`(33)、`tests/profile-mcp.spec.ts`(22)、`tests/startup-renderer.spec.ts`(13)、`tests/update-coordinator.spec.ts`(6 个 unsafe-*)、`tests/runtime-tree.spec.ts`(3)、`tests/runtime-file-policy.spec.ts`(1)。多数是 `no-unnecessary-type-assertion` 与 `no-unsafe-*`， Mechanical 可清。
- **`scripts/development-project.ts` 开发机硬编码**：12 处 `D:/dsh-devframe`、4 处 `C:/Users/25313/.dsh/...`、`D:/shadow-trial`，且 `workspaceRoot`/`vaultRoot`/`writeEnabled: true` 全部写死。需改为从 `REPOSITORY_ROOT`/环境变量推导；`vendor/dsh-mobile-pairing/node_modules` 的 junction 写入建议移到一次性 postinstall 或文档步骤。
- **版本号钉错**：同文件 L174 把 18 个包统一钉 `0.1.2-alpha.4`，实际 16 个已是 `0.1.6-alpha.1`；`project-manager.ts` 的 shape 校验不比值。改为读取各包真实 version。
- **未加防护的破坏性操作**：`scripts/prepare-package-set.ts:130` 对任意 `--out` 路径 `rmSync(recursive)`，无归属校验。
- **线协议两份拷贝**：`apps/desktop/src/host-protocol.ts` 与 `apps/desktop-host/src/wire.ts`（魔数/头部/分块/版本逐字相同），建议加一个跨文件一致性测试钉住。
- **重复路径/目标逻辑**：`APP_ROOT`/`REPOSITORY_ROOT` 在 4 个脚本各算一遍；targets 列表出现 4 次；"desktop 版本必须等于 dsh 版本"实现 3 份。可抽一个 `desktop-paths` 模块（可选，非阻断）。

### P2 — 陈旧嵌套副本（未跟踪，建议删除）
三处完整包自拷贝（含 node_modules，体积大，拖慢一切 git/du 操作）：
- `packages/experimental/shadow-router/shadow-router/`
- `packages/experimental/client-ui-shadow-entry/client-ui-shadow-entry/`
- `packages/experimental/client-ui-project-memory/client-ui-project-memory/`
删除前确认无脚本引用它们（`grep -rn 'client-ui-shadow-entry/client-ui-shadow-entry'` 等）。另注意 `packages/experimental/client-ui-project-memory/client-ui-project-memory/` 里有一份**旧版** LibraryCard.tsx 与一个指向不存在 `packages/tsconfig.base.client.json` 的 tsconfig，oxlint 会误报，别被它误导。

### P3 — org 级清理（低优先）
- `expert-team` 8 个死 locale key（`refresh`/`close`/`loading`/`status.error`/`status.unmounted`/`teams`/`experts`/`empty`）；project-memory locale 7 个死 key。
- `receipt.ts` 头注释仍写 "used by tests"，实为生产 receipt store。
- `expert-pack-files.spec.ts` 只验证 package.json 声明的 glob，未验证 tarball 实际内容（Stage 6 报告 O2 已记录）。
- `ExpertTeamCard.tsx` 814 行 / `orchestrate.ts` 631 行 / `project-manager.ts` 619 行的拆分（snapshot 投影在 `orchestrate.ts`、`tools.ts`、`gateway.ts` 三处重复）。

## 四、提交策略（下一步，尚未执行）

用户已确认的顺序是：修质量 → 提交 → 继续开发。本阶段**未做任何 git 操作**（当前仍在 `main` 分支，工作树含约 200 个改动文件 + 约 50 个未跟踪项）。

建议拆分（每笔自绿、随笔带上对应 Agent Note）：
1. 安装链修复（`apps/cli/package.json`）
2. expert-team M3/M4 + no-cross-process-resume（Note 已在树：`.agents/notes/implemented/feature/2026-09-15-expert-team-m3/m4/no-cross-process-resume.*`）
3. expert-center UI + summon（Note：`2026-09-16-expert-center-ui/summon.*`）
4. project-memory 质量修复（本文件第 3/4/5/6 项，注意这是行为决策变更，commit message 写清「devframe-memory 从 workspace 放行改为排除」及理由：README/工具描述/测试三方一致 + 消除隔离绕面）
5. client-ui-project-memory 库页面修复（第 8 项）
6. app-boot `loadProfileDirectory` 移植 + devframe-profile 测试同步（第 7/9 项）
7. 自包含分发改造（20 包，Note：`2026-09-19-devframe-self-contained-distribution.md`）
8. desktop apps（WIP 单独一笔，先完成 P0/P1 再提交）
9. 删除陈旧嵌套副本（P2）

**红线提醒**：当前在 `main` 上，提交前先开分支；push 与开 PR 是对外动作，需用户另行确认。

## 五、环境备注（给下一个 agent）

- `pnpm` 不在 Bash PATH：用 `corepack pnpm`（11.7.0）。`corepack enable` 因无写 `C:\Program Files` 权限会 EPERM，但 `corepack pnpm <cmd>` 本身可用。
- 全量测试很慢（约 6.5 分钟）+ Windows 环境有既有失败面（bash 类套件、subagent spawn 类、exe 构建类），不要用全量失败数判断回归；按上表跑聚焦范围。
- 临时输出文件 `full-suite.txt`、`gen-typert.txt` 是 9-17 遗留的未跟踪根目录文件，鉴定完毕可删。
