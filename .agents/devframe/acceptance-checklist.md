# DSH 夜间并行开发组 — 验收清单与组合测试计划

维护组：G5（组合与验收基础设施）。范围：G1–G4 四条线的验收条目、对应测试命令、证据格式与合并顺序建议，以及本机已知环境限制。合并负责人按本清单逐条勾验收；G5 只维护本文件与 `packages/test-support/composition-smoke/`，不实现产品功能。

## 证据格式

每条验收记录为一行 JSON，追加到对应组合并 PR 的描述或合并报告中：

```json
{"item": "G1-2", "command": "pnpm exec vitest run packages/client/ui-workspace", "exit": 0, "tests": ["session row Session-ID menu > opens a dialog showing the full id verbatim"], "commit": "<sha>"}
```

补充规则：GUI 用户可见变更（G1/G2/G3 的表面）除命令证据外，必须附按 `record-browser-gif` 录制的 GIF（来自真实服务器与模式），并确认已含对应的无密钥录制会话快照场景；快照与 Web 期望输出的刷新只由场景属主在本地执行并逐 diff 评审。所有提交以手工门禁 + `git commit --no-verify` 落库，preflight 由本清单的针对性命令承担。

## G1 — SessionID 菜单（会话行操作菜单 → SessionIdDialog）

状态：**已合并**（提交 01eb0d288a）。合并后复验跑 G1 全部条目 + G5 组合冒烟。

| ID | 验收条目 | 对应测试命令 |
|---|---|---|
| G1-1 | 行操作菜单列出“会话 ID”项，且打开菜单不触发会话打开 | `pnpm exec vitest run packages/client/ui-workspace` |
| G1-2 | 对话框以 `sessionId.title` 为 aria 标签，逐字展示完整会话 ID（无截断） | 同上 |
| G1-3 | 两个复制入口（ID 文本、复制按钮）写入完整 ID 并回报成功；宿主拒绝时回报失败且从不见成功 | 同上 |
| G1-4 | 选择切换到其他会话时，已打开的对话框保持该行自己的 ID；关闭后重开显示对应行的 ID | 同上 |
| G1-5 | 新增键在 zh/en 双语字典键集一致 | 同上，以及 G5 组合冒烟 |
| G1-6 | 装配层：会话列表 → 行菜单 → SessionIdDialog 在根组件装配层可用 | `pnpm exec vitest run packages/test-support/composition-smoke` |

证据与快照：G1-1…G1-4 引用 `packages/client/ui-workspace/tests/session-id-dialog.client.spec.tsx` 中的用例名；用户可见变更需 GIF + `snapshots/web/` 对应场景（属主刷新）。

## G2 — Worktree 注册表（Workspace 注册表面）

| ID | 验收条目 | 对应测试命令 |
|---|---|---|
| G2-1 | 注册表命令（create/rename/delete/insertBefore/insertSessionBefore/archiveSession）经 Controller face 验证持久效果 | `pnpm exec vitest run packages/api/workspace-controller packages/client/ui-workspace` |
| G2-2 | 浏览器行与选择状态从注册表快照派生，不复制第二份数据源 | `pnpm exec vitest run packages/client/ui-workspace` |
| G2-3 | 注册/注销证明处置：dispose 贡献纤程后账目清空（HMR 安全） | 同上 |
| G2-4 | 装配层：注册表状态变化反映到组合后的侧栏表面 | `pnpm exec vitest run packages/test-support/composition-smoke` |

证据与快照：命令 + 退出码 + 用例名；改变持久化或 wire 格式时，属主在本地刷新对应期望并评审 diff。

## G3 — Goal 回执（目标回执面）

状态：**已合并**（提交 527269c5bf）。合并后复验跑 G3 全部条目；SDK 投影义务应已在其 PR 内结清。

| ID | 验收条目 | 对应测试命令 |
|---|---|---|
| G3-1 | 回执在会话日志有持久事件；不可忽略事件按 SessionEventMap 的 required-on-read 规则进入日志 | `pnpm exec vitest run packages/goal` |
| G3-2 | 命令入口（command goal）与模型面（tool goal）行为符合各自 Service Consumer 契约 | `pnpm exec vitest run packages/goal packages/client/ui-goal` |
| G3-3 | GUI 目标条呈现回执状态 | `pnpm exec vitest run packages/client/ui-goal apps/web` 中的相关 spec；`pnpm run test:gui` |
| G3-4 | TypeScript 与 Python SDK 投影在同一 PR 内更新（`SessionEventMap` 变更的硬性要求） | `pnpm run test:snapshot`（CI 信号，本机不跑）；Python 侧由 `scripts/snapshots/python-sdk-single-exe/` 的 CI 车道持有 |

证据与快照：命令 + 退出码 + 用例名；SDK 快照场景名记录在合并 PR；本机不执行 `test:snapshot`（见环境限制）。

## G4 — 可靠性（横切验证线）

| ID | 验收条目 | 对应测试命令 |
|---|---|---|
| G4-1 | 新增/改动的测试满足并发与隔离规则（端口、路径、子进程、teardown 所有权） | 按 `dsh-ci-test-reliability` 技能审查；`pnpm run test` |
| G4-2 | 覆盖门禁（per-file 100%）不因新代码回退 | `pnpm run test:coverage`（CI 门禁；本机可选） |
| G4-3 | 契约回归测试覆盖已知故障类（参照 agent-loop 的 contract-regressions 模式） | `pnpm exec vitest run packages/core/agent-loop` |
| G4-4 | 全量单元套件绿（Windows 本机按下方排除表执行） | `pnpm run test` |

## 合并顺序建议（协商项，非硬门禁）

当前进度：G1 已合并（01eb0d288a）、G3 已合并（527269c5bf）；父代理已修复 gen-cordis-catalog 的 profileIdentity partition violation（e247d0d008）。待办：G2 → G4。

1. **G2 先并（待办）**：注册表数据模型是 G1 行表面的宿主（ui-workspace 的 rows 同时承载两者）；并后跑 G2 全部条目 + G5 组合冒烟，并确认已合并的 G1 表面在最终数据模型上仍绿。
2. ~~**G1 次并**~~（已完成）：行菜单与对话框依赖 G2 后的行数据形状；并后立即跑 G1 全部条目 + G5 组合冒烟。
3. ~~**G3 可并行**~~（已完成）：goal 回执面与 G1/G2 的表面不相交；其 SDK 快照义务在各自 PR 内结清。
4. **G4 最后（待办）**：作为横切验证线，在 G1–G3 全部合并后的组合树上跑全量单元与覆盖，输出最终验收报告。

每次合并进组合分支后，跑合并组的针对性命令（上表）+ `pnpm run test:docs`（任何动了 `.agents/`、`docs/`、README 的组合并后必跑）。

## 本机已知环境限制

- **无 npm、无 bash**：本机只有 `pnpm` 与 `pwsh`。依赖 bash 可执行文件的夹具（bash 工具描述、POSIX JSON 转义）无法在本机运行；不要为本机绿灯改夹具。
- **Windows 既有红灯套件（记录为 CI 信号，本机不跑、不修、不刷新任何 `*.expected.md`）**：`pnpm run test:snapshot`、`pnpm run test:web`。两者的绿灯由 Linux CI 车道持有；本机只跑各自属主的单元与期望测试。
- **vitest 的 Windows 排除表**：`vitest.config.ts` 的 `windowsUnsupportedPackages`/`windowsUnsupportedTests`（bash-local、bash-sandbox、tool-bash、hooks/*、terminal-bash、code-runtime-python、sandbox-local、subprocess 部分 spec 等）在本机自动排除，属预期。
- **每组合并后的针对性命令**：G1/G2 → `pnpm exec vitest run packages/client/ui-workspace` + `pnpm exec vitest run packages/test-support/composition-smoke`；G3 → `pnpm exec vitest run packages/goal packages/client/ui-goal`；G4 → `pnpm run test`；全部 → `pnpm run test:docs`。
- **文档门禁**：`pnpm run test:docs` 覆盖 markdown 链接/换行、双语配对、README Model Experience 与 Known Limitations、Agent Note 格式与配对、doc 预算；改动 `.agents/`、`docs/`、任何 README 后必须本机跑绿。
- **提交纪律**：本机提交使用 `git commit --no-verify`（lefthook 钩子依赖的完整门禁在 CI 执行）；`git diff --cached --check` 的尾随换行检查仍需本地保证。
