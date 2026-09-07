# AT1-11 效率实证基线（准备层）

基准树：codex/v14-udeliver-lead @ 2c965e5a61。数据源：`at11-task-ledger.json`（5 行，全字段 provenance）+ `tools/at11-collect.mjs`（校验脚本，exit 0）。本文只做综合与采样方案，不宣称速率、不捏造对照。

## 1. 可比较基线（3 个已完成真实 Worker 任务 + 2 个 Lead 集成任务）

| 维度 | W1 组合切片 (a9fcb6c5) | W2 双后端切片 (6fa6f883) | W3 AT1-09 旅程 (51ad6b98) | L1 Lead 集成 | L2 Lead 集成 |
|---|---|---|---|---|---|
| 产出 | ba36245196（10 文件 +264/−8） | 4a8c35dafc（6 文件 +153/−103） | 232e6fe825（1 文件 +213/−2） | c469e0863c+6dac3f305d | 6f01fa0d87+78fc5b88a7+047b4f6fb4 |
| 累计模型回复 | 126 | 56 | 23 | unobserved | unobserved |
| 活跃窗口 | spawn≤22:08:25 checkpoint（下界）→ 22:34 终止 | 同左 → 22:34 前完成 | 无本地 spawn 下界 → 最后事件 23:03:42 | 22:38:38–22:48:57 | 仅 git commit 夹逼 |
| Worker 自报验证运行 | 5（套件/三包/tsc/docs/translation） | 3（5 套件/全包/tsc） | 3（本文件/两包） | — | — |
| Lead 验收复跑 | 三包+tsc+test:docs | 三包+tsc | 三包+tsc | 六包+tsc+目录门 | 四包+tsc |
| 返工环 | README 锚点修复 1 次（既有门失败） | EBUSY 世代重构 1 次（断言零改动） | 0 | 合并断言补行 1 次 | 记录更正 2 次 |

诚实边界：(1) 累计回复数≠RPM，本会话无任何分段/速率数据；(2) spawn 时间本地不可观测，W1/W2 仅 22:08:25 checkpoint 下界、W3 无下界——**窗口时长不可计算**，只有"产出锚点+窗口端点观测"可比较；(3) W1 的 126 无 git 佐证（另两个回复数有 commit 消息双源）；(4) Lead 侧 commit 落地时间晚于 Worker 终止时间（验收-提交模式的结构性滞后，属流程成本非任务时长）。

## 2. 下一轮同类任务采样方案

每任务固定采集（模板已由 ledger 行体现）：
- **身份**：taskId / executorSession / route（显式 spawn 参数为准）
- **产出锚**：output commit hash + git author date；files/ins/del（diff --stat）
- **模型活动**：cumulativeModelReplies（provenance=controller-account-log，强制附 "cumulative, not RPM" 注记）
- **窗口**：startBound/endBound——**要求账户侧日志提供 spawn 时间戳**（本轮 5 条 unobserved 缺口之首；补齐后窗口时长才可比较）
- **构建/测试重复**：worker-report 运行次数与 lead-acceptance-log 复跑次数**分列**（并发所有权修正后 Worker 不再跑 tsc/全包，预期下一轮 worker-report 数下降、结构可比）
- **返工环**：报告明示的重构/门失败事件计数
- **验证状态**：exit code 段（进 commit 消息）

采样纪律：同类型任务成组采样（≥3 个）；切片大小按 files/ins/del 分桶比较，不跨桶比时长；窗口时长仅在 spawn 端点可观测后进入比较；每轮复用同版本树基线（merge 后重置）。

## 3. AT1-11 原验收要求的对应关系（用户门控部分不在此层）

原验收：3–5 个真实小任务**配对试用**+用户三态结论（helpful/inconclusive/not_helpful）+继续/简化/停止选择。本基线是前置条件：任务记录字段已定义、可比维度已固定、诚实边界已声明。配对设计（with/without DevFrame 同型任务、干预/用时分开计数、三态结论）需用户单独授权任务选择与执行，本层不替代、不预填任何用户结论。

## 4. 局限声明

- L1/L2（Lead 集成行）无模型活动数据（Lead 会话计量在账户侧，本地不可读）——配对分析时 Lead 行仅作流程成本参考。
- 并发所有权修正（Worker 只跑 focused tests）在 W1-W3 之后生效，W1-W3 的 worker-report 验证次数含 tsc/全包——跨轮比较时按"修正前/后"分代，不混代比较。
- 本文档与 ledger/script 均为准备层产物，不构成 AT1-11 验收证据；验收态 not_run 不变。
