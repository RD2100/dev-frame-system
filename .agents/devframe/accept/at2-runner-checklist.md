# AT2 Shadow 场景草案清单（at2-runner）

状态：draft — 绑定 part2 契约（[docs/detailDesign-part2.zh.md](../../../docs/detailDesign-part2.zh.md)），Shadow 落地后对齐校准。验收项定义见 [docs/testAndAcceptance.md](../../../docs/testAndAcceptance.md#part2)。场景草案位于 [packages/experimental/shadow-router/scenarios/](../../../packages/experimental/shadow-router/scenarios/)，fixture 形态对齐 [snapshots/session/](../../../snapshots/session/)。

| 场景草案 | 覆盖 AT 项 | 前置 | 期望 | 当前状态 |
| --- | --- | --- | --- | --- |
| [AT2-01-open-route-two-projects](../../../packages/experimental/shadow-router/scenarios/AT2-01-open-route-two-projects.md) | `AT2-01` / `R2.1` | 两个不相交已授权项目根 A、B，任务与输出文件可区分 | 两个独立控制器根，worker 各挂正确根下，无嵌套 Team，输出留在目标项目 | draft |
| [AT2-02-forbidden-probes](../../../packages/experimental/shadow-router/scenarios/AT2-02-forbidden-probes.md) | `AT2-02` / `R2.1` | 已打开的控制器 A 及其 worker 会话 | 禁止的 shell/原始会话工具、任意目标会话 ID、未授权根、陈旧 `bindingRevision` 全部在目标变更前失败，拒绝文本无项目内容 | draft |
| [AT2-03-open-dedup-recovery](../../../packages/experimental/shadow-router/scenarios/AT2-03-open-dedup-recovery.md) | `AT2-03` / `R2.2` | 单一已授权根 A，不同 `requestId` 的并发重复 open，预留后、就绪前注入中断 | 收敛到唯一预留/当前控制器；恢复围绕同一会话 ID，无重复写入者、无悄悄替换的根 | draft |
| [AT2-04-alias-overlap](../../../packages/experimental/shadow-router/scenarios/AT2-04-alias-overlap.md) | `AT2-04` / `R2.2` | 根 P 及其大小写变体、junction 别名、物理重叠子根 `P/sub` | 别名解析到同一工作区身份；重叠同时写入被显式拒绝；未支持的别名语义报告为未测试 | draft |
| [AT2-05-delivery-interruption](../../../packages/experimental/shadow-router/scenarios/AT2-05-delivery-interruption.md) | `AT2-05` / `R2.3` | 已打开的 A，固定 `messageId`/`requestId` 的投递，三个中断点，两种受支持存储后端 | 同一 message ID 收敛为一条 accepted 输入；回执恢复不重复模型可见任务；intent→accepted→receipt 各有 flush 边界 | draft |
| [AT2-06-retry-limits-stale-goal](../../../packages/experimental/shadow-router/scenarios/AT2-06-retry-limits-stale-goal.md) | `AT2-06` / `R2.3` | 已打开的 A，控制器从 Goal `goal-a-1` 切到 `goal-a-2`，限额取第 4 部分默认值 | 相同 `requestId`+相同输入去重，不同输入 `request_conflict`，超限/队满接受前拒绝；旧 Goal 绑定永不成为新 Goal 输入且重试限额不重置 | draft |
| [AT2-07-stop-isolation](../../../packages/experimental/shadow-router/scenarios/AT2-07-stop-isolation.md) | `AT2-07` / `R2.4` | A、B 各运行真实 owned job；对 A 连续两次 `project_stop` | A 排空后幂等停止，已接受消息保留为取消/待人工；B 的 job、队列与控制器全程不受影响 | draft |
| [AT2-08-status-readonly](../../../packages/experimental/shadow-router/scenarios/AT2-08-status-readonly.md) | `AT2-08` / `R2.4` | A 被驱动到 idle/queued/received/blocked/completed 五个观察点，另加陈旧观察 | 状态有界、只读、含观察时间，不唤醒模型；`received`/`idle` 不等价于 `completed`，`completed` 只依据第 1 部分完成结果 | draft |
