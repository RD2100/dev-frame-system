# DevFrame Round-3 统一状态登记表（阶段 C 收口版）

G5（调度、状态、合并与质量）产出。七态机：`planned → developing → blocked | review → committed → merged → completed`。
登记基线：main `8e188c3d36`（G4 合并 `749795ba98` + 台账 `8af629b0da`/`c836328632`/`e0bac267fa`/`0795aede41` 等已含）。
身份约定：host 会话 id 带 `session-` 前缀，spawn 工具创建的子会话 id 为裸 UUID；本表按实际返回值原样记录，不添加或去除前缀。

## 一、五功能组登记

| 组 | 组长 Agent | 组长 SessionID | Worktree（分支） | 状态 | 内容提交 | main 合并提交 | 合并时定向验证（实际执行） |
| --- | --- | --- | --- | --- | --- | --- | --- |
| G1 Session 与 Agent 身份 | DSH-G1-SessionIdentity-Lead | `5e7138d6-9e6a-4442-9f7a-b32c55bcb46a` | `D:\dsh-devframe-r3-g1`（`r3/g1-session-identity`） | merged → completed | `c13413559a`、`e25594a317`、`3784ead820` | `1c24e8e49f` | 定向矩阵 122 文件 / 2304 passed / 2 skipped / 0 failed（首次组合跑 1 failed 为 codex real-product 负载抖动，单跑复绿）；test:docs 15/15 |
| G2 Agent 层级与权限 | DSH-G2-Hierarchy-Lead（后继） | `93a4ed58-73f1-481a-8f1d-d1e74e5b7128` | `D:\dsh-devframe-r3-g2`（`r3/g2-hierarchy`） | merged → completed | `dea960b656`、`c64497a257`（策略两提交 rebase 重放）、`d4e1f049a3`、`1905eb7ba1`、`82a404a6f4`、`9c473dd98c`（E1 审核后 cherry-pick） | `4a9aed6e08`；E1 锚定 `6ba3e5f824` | `vitest run packages/subagent packages/experimental/devframe` 804 passed / 2 skipped（G2 自报）；总控零错误退出矩阵 + test:docs 15/15 |
| G3 项目 Agent 树和界面 | DSH-G3-AgentTree-Lead | `143b05d9-5e57-4b55-a203-cee99e94443e` | `D:\dsh-devframe-r3-g3`（`r3/g3-agent-tree-ui`） | merged → completed | `62acd6178c`、`251e8c3b03`、`48c1318d25`、`ca55368235`、`081abb678e` | `a34ed08401`（前置类型修复 `e0bac267fa`） | 自报 test:gui 283 文件 / 3930 tests 0 failed；main 合并后 ui-workspace 175/175 |
| G4 Worktree 产品化与环境可靠性 | DSH-G4-Worktree-Lead | `75f59aff-d25c-4b16-a4fd-7d9a65bb3e0f` | `D:\dsh-devframe-r3-g4`（`r3/g4-worktree`） | merged → completed | `9e33c1be43`、`35953a37e0`、`3a8781c186`、`665bd6ab74`、`e519f56fab`、`b8a5f4a565` | `749795ba98`（零冲突） | workflow 测试零错误退出；tool-catalog + cordis-catalog 双绿；docs 15/15；main 合并后 host tsc exit 0、workflow+smoke 237/237 |
| G5 调度、状态、合并与质量 | DSH-G5-Quality-Lead | `533a3416-4956-4f4f-b5b3-d14e36ec0d0d` | `D:\dsh-devframe-r3-g5`（`r3/g5-quality`） | committed（总控合并后转 merged → completed） | 收口文档七单元：`d97464815d`、`b46f29be8a`、`49a9d89c53`、`e38f64831c`、`f12f7193d9`、`efb9dedab3`、`4d71d1e0a9` | 待总控执行 | 最终回归在 main `8e188c3d36` 执行：host tsc exit 0；四组矩阵 96 文件 / 1608 passed / 2 skipped / 0 failed；composition-smoke 5/5；test:docs 1 红（G3 pairing 遗留，见 round3-final-report.md 未完成项 #1） |

G2 前任组长 `ca378724-8de0-4c17-94e0-05aa828c1366`：三次异常终止（上下文耗尽型），会话保留于存储，状态记 terminated（非七态活跃态，留痕备查），成果由后继 `93a4ed58` 全量继承，零损失。

## 二、执行 Agent 登记

| Agent | SessionID | 深度 | Worktree | 状态 | 交付 | 归宿 |
| --- | --- | --- | --- | --- | --- | --- |
| E1（G2 执行 Agent） | `66e9cb16-d533-4361-ae11-50a01541e67e` | 2 | `D:\dsh-devframe-r3-g2-e1` | completed | `c10127a5f5`（subagent-in-process-driver.spec.ts +57 行执行器级拒绝锚定） | G2 后继审核通过 → cherry-pick `9c473dd98c` → main 经 `6ba3e5f824` 并入 |
| Spawn capability probe | `86de844b-1748-4637-9238-c1b8f2b121f8` | 3 | —（无代码交付） | completed | 活体证据：depth 3 存活 = 默认无 toolFilter 时执行 Agent 可建子 Agent（策略缺口实证，支撑 G2 双重强制设计） | 证据被 G2 设计消费；会话 ready 保留 |

本轮执行 Agent 全量登记为上述 2 个；G3/G4 组长按事件驱动纪律未派执行 Agent，G5 为纯验证+文档组不派执行 Agent。无长时无理由 idle 会话。

## 三、状态机核对结论

1. 五组状态全部收敛：G1–G4 merged（main 实证：各合并提交在 main 历史中），G5 developing（本阶段唯一活跃组）。
2. 两个执行 Agent 均completed，交付物全部经组长审核后入库，无游离工作。
3. 唯一异常记录：G2 前任组长三次异常终止，按监督规程后继接管，工作树成果零丢失（台账 §七 2026-09-05 各条）。
4. 本表与 `.agents/devframe/round3-plan.md` §二 同步维护；冲突时以本表（阶段 C 收口版）为准并回写注册表。
