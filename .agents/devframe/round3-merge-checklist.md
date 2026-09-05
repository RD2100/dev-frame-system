# DevFrame Round-3 合并前验收清单（阶段 C 固化）

G5 产出。本文记录本轮各组合并时**实际执行**的验收证据，并固化为 G5 自身合并前必须重走的可执行清单。合并执行人只有总控；合并一律 `--no-verify` 并手工执行等价门禁。

## 一、五项验收域与本轮实际执行记录

### 1. Clean 树

| 组 | 实际执行 |
| --- | --- |
| G1 | 提交序列完成后工作树 clean；总控阶段 A 核对七个 r3 工作树全 clean |
| G2 | rebase 零冲突后 clean；文档三单元逐提交落库 |
| G3 | 最终报告自报 5 提交、clean |
| G4 | 重启断点续跑后工作树 clean（阶段报告虽未发出，提交完整在树） |
| E1 | 执行 Agent 工作树 `r3-g2-e1` 依赖就绪，交付单提交 `c10127a5f5` |

### 2. 提交完整

- 每组内容提交清单登记于 `.agents/devframe/round3-status-registry.md`；合并提交与内容提交均可 `git log` 实证。
- 每单元提交前执行 `git diff --cached --check`（尾随空白门禁）；合并时零 vendor 暂存核对。
- G3 合并前置类型修复 `e0bac267fa` 由总控按用户指令机械执行并单独提交，未混入组内容。

### 3. 定向测试绿

| 组 | 实际执行的定向命令（均记录实际结果） |
| --- | --- |
| G1 | `vitest run packages/subagent packages/session packages/api/session-controller packages/client/ui-workspace` → 122 文件 / 2304 passed / 2 skipped / 0 failed |
| G2 | `vitest run packages/subagent packages/experimental/devframe` → 804 passed / 2 skipped |
| G3 | `pnpm run test:gui` → 283 文件 / 3930 tests 0 failed |
| G4 | `vitest run packages/workflow/worktree-registry`（21/21 → 30/30 随单元推进）+ `verify-tool-catalog`/`verify-cordis-catalog` 双绿 + `test:docs` 15/15 |
| 合并后 main 复验 | host tsc exit 0；ui-workspace 175/175；workflow+smoke 237/237；subagent 单跑 7/7 |

已知 Windows 红名单（组合跑偶发、单跑复绿，不阻塞）：codex real-product 负载抖动、session-projection-cache flush 超时、claude-code real-product 时序。复确认一律单跑定性。

### 4. 边界合规

总控对每组合并 diff 做只读审核（台账 §七 各条）：

- G1：11 文件 +210/−21，仅身份暴露面，未碰 UI 树/worktree。
- G2：仅 devframe + subagent 测试与文档；策略为 toolFilter.deny + maxDepth 双重强制。
- G3：13 文件 +983/−31，仅 ui-workspace 及其测试/locales。
- G4：workflow 注册表/工具包 + catalog 生成物 + 双语文档；未碰 UI 树。
- E1 交付（+57 行测试）由 G2 组长审核后 cherry-pick，边界为 subagent driver 测试。

### 5. 无伪造状态与 SessionID

- 全部 SessionID 来自 `list_agents`（descendants）/会话存储目录实证（本轮复核：`5e7138d6`/`93a4ed58`/`ca378724`/`143b05d9`/`75f59aff`/`66e9cb16`/`86de844b` 七个会话目录均存在于 `C:\Users\25313\.dsh\sessions\--D-dsh-devframe--\`）。
- 状态迁移（developing→merged 等）均以 main 分支上的 git 提交为准，不凭口头汇报登记。
- 执行 Agent 数量与交付物（E1、probe）逐个核对，无虚构登记项。

## 二、G5 自身合并前可执行清单

1. `git status --porcelain` 为空（clean 树）；`git log --oneline main..r3/g5-quality` 列出全部待并提交。
2. 逐提交 `git diff --cached --check` 干净；改动范围仅 `.agents/devframe/**`（如动 docs/ 则双语配对齐全）。
3. 最终回归绿：host tsc + 四组定向矩阵 + composition-smoke + `test:docs`（实际结果记录于最终报告）。
4. 状态登记表与注册表行一致，且每个 SessionID/提交号可在会话存储/git 历史复核。
5. 总控执行 `--no-verify` 合并 + 等价门禁（diff --check、零 vendor、双语配对如动 docs）。
