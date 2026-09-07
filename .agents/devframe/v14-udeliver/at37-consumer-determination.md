# AT3-07 消费面与日志契约判定（B 线组长亲定，证据在案）

依据：`packages/experimental/project-memory/scenarios/AT3-07-vault-unavailable-degradation.md` 前提（宿主集成）+ 步骤 6——"警告 vs 失败"分级是**宿主装配面策略**，断言面是**会话日志事件**（录制布局：session.jsonl 含错误事件、警告事件与任务结果事件）；该场景开放问题自认"警告事件具体类型（宿主任务事件词汇）尚未存在"。

## 事实（全仓核实）

1. **任务旅程事件族唯一存在=devframe/***：`packages/experimental/devframe/src/events.ts` L253-276——role-policy/goal-binding/usage/verification/review/lifecycle 六种，声明合并进 SessionEventMap、zod 校验、可冷恢复。**无任何通用 `task/*` 事件**（全 packages grep 零命中）。
2. **memory 侧持久事实唯一=memory/receipt**（project-memory receipt-log；失败 append 不落 receipt——failure.spec L49-58 已证）。任务警告的**生产消费者今天不存在**。
3. **project-controller 任务板**：complete(taskId)/fail(taskId, 三元组) 是完成/失败两个既有权威入口；TaskRecord 无警告字段；板只负责状态/准入/持久化（README 职责）。

## 判定

- **警告的日志契约**：宿主装配层在完成决策点发**恰好一条**会话事件（类型名落位=场景开放问题，录制时绑定；归属包按事件语义定——任务旅程事件归 devframe 族或新的宿主装配事件声明，不由任务板持有可能性），payload 携带 taskId + 逐字 memory 失败码（'MEMORY_UNAVAILABLE'）+ 未保存标记。**永不**为失败保存发成功事件：memory/receipt 仍是保存成功的唯一事实（不重复 memory_saved）。
- **Model-visible ⟺ logged**：memory 工具错误本身已模型可见（tool result 事件在案）；分级决定是宿主决策，以新事件落日志满足录制重放断言（"恰一条警告事件"）。
- **A1/A2/A3 全部复用既有 complete/fail**：A1=宿主发警告事件 + `complete(taskId)`（板面无字段也成立——断言面是日志）；A2=无 receipt + 无成功声明事件（包级已成立）；A3=宿主走既有 `fail()`（三元组强制诚实，板面已支持）。
- **TaskRecord/共享契约扩展：现证据不支持，不动**（遵循总控修正：不改 project-contracts 与 taskRecordSchema）。任务意图（编码 vs memory-only）由宿主装配配置持有，不压成 code|memory 板面二选一；混合交付不丢信息。
- 仅当后续证据证明**任务板冷恢复必须重放警告**（板成为断言面），再提请总控裁定扩展。

## 后台追踪 Worker（补充接线点证据）

| 项 | 值 |
| --- | --- |
| SessionID | 4c7f3b68-cfa5-44db-91f4-92703b3442da（subagent 后台 run_in_background:true） |
| 继承账号 | 如实记录：随我当前路由（h2 / huoshan-2 · glm-5.3-flash）；429 有限退避 |
| worktree | `D:\dsh-udeliver-at37`（branch codex/v14-udeliver-at37，快进至 435a73c17a；只读，全部命令限定该 workdir） |
| 任务书要点 | 只读追踪 ①B2/B3 driver b2b3/b2b3verify 真实调用序 ②生产宿主链「任务开始→可选 recall→代码验收→候选摘要 append」（devframe /devframe-start 旅程 + memory 工具挂载 + receipt 日志）③现存任务结果事件消费者 ④产出=具体消费者+缺失接线点+TaskRecord 是否必须扩展的裁决建议；禁新框架、禁模型测试、零写入零提交 |
| 设计护栏（已入任务书） | 不压成 code|memory 二选一；不重复 memory_saved 事实（receipt 唯一） |
