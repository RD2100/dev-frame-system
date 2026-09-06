# p23 离线验收证据

环境：worktree `D:\dsh-devframe-p-3level`，分支 `p/3level`，基线 `fc34223e28`（`git rev-parse HEAD` 核验一致，工作树 0 脏文件）。说明：`git grep` 命中时退出码 0、未命中时退出码 1，一律如实记录；每条命令的退出码与时间戳在同一次调用内回显采集。

| # | 命令原文 | 退出码 | 时间戳 | 结果 |
|---|---|---|---|---|
| 1 | `git grep -l "三级任务"` | 0 | 2026-09-06T10:06:50.0142725+09:00 | 1 命中（docs/working/dsh-controller-v1.2-handoff-2026-09-06.zh.md）——派单预期"零命中"不成立，照实记录 |
| 2 | `git grep -li "three-level"` | 0 | 2026-09-06T10:06:50.5791079+09:00 | 4 命中（.agents/notes/implemented/simplification/2026-07-29-shared-base-config-overlays.md；docs/working/dsh-controller-v1.2-handoff-2026-09-06.md；packages/client/ui-directory-picker-browse/tests/directory-browser.client.spec.tsx；packages/session/session-telemetry-otel/src/index.ts）——同上 |
| 3 | `pwsh -File .agents\devframe\p23\run-offline-acceptance.ps1` | 0 | 2026-09-06T10:08:16.9422995+09:00 | OFFLINE ACCEPTANCE: ALL GREEN（第 1 次运行；当时 evidence 尚未生成，runner 按"允许"放行；已打印"真实模型运行段被阻塞（缺 DEEPSEEK_API_KEY）"提示） |
| 4 | `pwsh -File .agents\devframe\p23\run-offline-acceptance.ps1` | 0 | 2026-09-06T10:08:40.6811024+09:00 | OFFLINE ACCEPTANCE: ALL GREEN（第 2 次运行；evidence 已存在后复跑，四件套齐，"检查时已存在，允许"分支通过；阻塞提示同上） |

缺口：①真实模型运行段被阻塞（缺 DEEPSEEK_API_KEY，未执行 `pnpm dsh --profile headless`，不虚构结果）；②锚点 grep 实测非零命中（1 与 4），与派单预期"零命中"不符，已如实记录待组长/总控复核。
