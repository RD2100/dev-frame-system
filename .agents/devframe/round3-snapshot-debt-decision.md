# DevFrame Round-3 快照夹具债务决策与操作指引

G5 产出。决策：**三选一中的选项 1 —— CI（POSIX）上 keyless `DSH_SNAPSHOT=refresh` 再生**，辅以选项 2 作为个别场景的后备；否决选项 3（长期记红）。

## 一、债务盘点（实际测量，基线 main `8e188c3d36`）

- `snapshots/` 入库文件 655 个（含 acp/sdk/session/web 四子树 + AGENTS.md）。
- 与身份文案相关：43 个文件含旧「agent id」族文案；6 个文件的期望产物仍带旧字段 `subagentId`（例：`snapshots/session/ptc-turn/system-prompt.expected.md` L470/L481 `subagentId: string;`）。
- 源码现状：G1 已将工具结果身份字段更名 `sessionId`（`packages/subagent/tool-subagent/src/index.ts` L438/L457/L529），系统提示词内的 schema 文案随之改变 → 期望产物落后于实现，`test:snapshot` 在 CI 上预期红。
- 本地 Windows 不跑 `test:snapshot`（POSIX 夹具约定）；该信号归 CI 所有。

## 二、决策依据（选项 1）

`vitest.snapshot.config.ts` 顶部契约原文：「Replay is the keyless default… `refresh` replays committed scripts and updates current expected outputs. Replay/refresh never load `.env`; only record reads a key from the environment or root `.env`.」

即：refresh 走已录制会话脚本重放当前管线并再生期望产物，**无需 API key**；债务成因是「有意的输出变更」（G1 身份更名），与 refresh 的设计用途（intentional output change 后再生期望）精确匹配。重录（record）仅在重放无法忠实再生时才必要。选项 3 会让 CI 长期红灯，违背「CI 拥有该信号」的立场，且 refresh 成本极低，无理由容忍。

## 三、操作指引（选项 1 主路径）

1. 在 POSIX 环境（Linux CI runner 或维护者 macOS/Linux 本机）检出含 G1 更名的分支。
2. 运行 `pnpm run test:snapshot:refresh`（等价 `DSH_SNAPSHOT=refresh vitest run --config vitest.snapshot.config.ts`；并发可用 `DSH_SNAPSHOT_MAX_CONCURRENCY` 调节）。
3. 审查再生 diff：预期仅身份文案/字段名变化（`subagentId` → `sessionId`、agent id 文案对齐）；若出现无关大面积漂移，先停下排查管线回归，不得盲目提交。
4. 以单一提交落库再生夹具，提交信息引用 G1 身份更名（合并提交 `1c24e8e49f`）作为变更动因。
5. 复跑 `pnpm run test:snapshot`（keyless replay）确认全绿，随后 CI 恢复绿灯。

### 后备（选项 2，仅限个别场景）

若个别场景 refresh 后仍失败（录制脚本无法忠实再生当前输出），仅对这些场景用 `pnpm run test:snapshot:record`（需 `DEEPSEEK_API_KEY`，POSIX）重录；不要整库重录。

## 四、CI 义务说明（过渡期）

- 本决策随 G5 收口报告交总控登记为**合并后 CI 义务**；在选项 1 执行落地前，CI `test:snapshot` 保持已知红，不作为任何合并门禁。
- `test:web` 同理仅记录为 CI 信号（其 refresh 路径 `pnpm run test:web:refresh` 需先 build，同样 POSIX 执行）。
- 本地 Windows 一律不跑这两个信号；红名单复确认按单跑定性。
