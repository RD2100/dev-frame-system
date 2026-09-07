# AT4-06 host stop adapter 接线方案（组长草稿，待总控审后实施）

状态：方案+验收草稿；未实施、未派发。c0c8844bec（Gap#1/#2）冻结独立审查中，本方案全部落**新文件面**，不改冻结快照内文件。

## 0. 所有权清单（先行核查结论）

| 面 | 属主 | 本方案动作 |
| --- | --- | --- |
| agent-reliability stopProject primitive / deadline 委托 / STOP_IN_PROGRESS | V1.2（main f81a5cd9f6 系） | **只调用不修改**；类型经 devframe/reliability 与 ctx.agentReliability 服务面解析 |
| project-controller commit/delivery consumer（d3b 在写） | A2/d3b | **零触碰** |
| command-goal-binding src/{composition,command,config}.ts + 新 spec | 组长 | 接线落点（唯一写面） |
| devframe controller goal-binding | 组长 | **预计零改动**（controller.stop 既有；链在组合层包裹） |
| profile/cordis.yml 启用 wiring | 总控单写 | 本方案只加 validated Config 字段，不碰部署文件 |
| writer 释放真实产品面 | **尚不存在**（grep 证实全树仅 stop.ts 选项槽） | 宿主供给缝：config 挂钩；真实面归 A2/Consumer 定稿后接入 |

## 1. 命令面（/devframe-stop 升级，签名不变）

现行为：stopBoundGoal → controller.stop（stop_requested 持久化+落日志+native disarm+admission 关）→ 返回。**缺** drain/quiescence/writer。

升级（同一命令，签名与参数解析不变）：

```
/devframe-stop
  1. controller.stop(...)                     // 既有：stop_requested + disarm + admission 关
  2. resolve 停止链适配器（§3）               // ctx.agentReliability 未挂载 → 稳定结构错误（不静默降级）
  3. await agentReliability.stopProject(options)   // 真实链：closeAdmission→身份→goals→jobs kill/wait(有界)→processes→flush→releaseWriter
  4. result.status === 'stopped'
       → 落 quiescence_confirmed、stopped 两条 lifecycle 词汇记录（landGoalBinding 形状）+ store 对账
       → renderStopChainStoppedText()
     result.status === 'needs_attention'
       → 绑定停在 stop_requested（不推进）；返回 NEEDS_ATTENTION 文本附 remaining 清单；writer 保持保留
  5. stopProject 抛（结构性）→ 原样传播为 dispatch 失败；绑定 stop_requested；writer 保留
```

重复 stop：第二次 /devframe-stop → 既有 STOP_ALREADY_PENDING_TEXT（stop_requested 不可再停）；stopped 后 → 稳定数据错误零新记录（Gap#2 幂等再观察兜重放收敛）。

## 2. Config 面（config.ts，无硬编码）

- `stopGraceMs?: number` — 有界 drain 上限，传入 StopProjectOptions.graceMs；载入时校验正有限（参照 stop.ts 对 graceMs 的既有校验）；缺省文档化默认 2000（部署可改 cordis.yml，符合"可选字段+文档化默认=可配置"）。
- `releaseWriter?: () => void` — 宿主 writer 释放挂钩（同步、owner 校验、抛错=保留）。**缺省=链如实报 needs_attention 且 writer 保留**（失败安全方向：不虚报释放）。真实面由 A2/Consumer 定稿后经 cordis.yml 注入。

## 3. 适配器解析（停时从 ctx 解析，显式）

| StopProjectOptions 槽 | 解析 | 缺失语义 |
| --- | --- | --- |
| agents | `[invocation.agent]` | — |
| registry | `ctx.agents`（get） | 未挂载=已知身份校验按 registry 语义处理 |
| goals | `{ disarm: () => ctx.goals.disarm(agent), pause: (ref) => ctx.goals.pause(agent, ref) }` | — |
| jobs | `ctx.jobs`（list/kill/wait） | jobs 插件未挂载=诚实空适配器（list=>[]；kill/wait 抛=不被调用）——"无 jobs 可排干"是事实非默认 |
| processes | 宿主进程捕获面（可选 ctx 服务） | 未挂载=诚实空（组合层自身不捕获进程） |
| closeAdmission | `controller.closeAdmission()`（幂等） | — |
| record | 观测写入 session 日志（诊断流） | — |
| flush | `() => ctx.sessions.flush(session)`（真实持久化刷盘） | — |
| releaseWriter | config 挂钩（§2） | 缺省=抛 → stopProject 保留 writer → needs_attention |

## 4. 失败语义（全部失败安全方向）

| 失败点 | 绑定 | writer | 返回面 |
| --- | --- | --- | --- |
| controller.stop 数据拒绝（STOP_ALREADY_PENDING 等） | 不变 | 不涉及 | 稳定数据错误 |
| agentReliability 未挂载 | stop_requested | 不涉及 | 稳定结构错误（不降级） |
| drain 未确认（job/进程超 grace） | stop_requested | 保留（stopProject 保证不调 releaseWriter） | needs_attention 文本+remaining |
| flush 失败 | stop_requested | 保留 | needs_attention |
| releaseWriter 挂钩抛/缺省 | stop_requested | 保留 | needs_attention |
| 结构异常传播 | stop_requested | 保留 | dispatch 失败（原样） |

## 5. 与既有语义的衔接

- **STOP_IN_PROGRESS**（V1.2 service 语义）：drain 在 controller.enqueue 内序列化；进行中新 start → START_GOAL_RUNNING（goal 存在未完成）；新 stop → STOP_ALREADY_PENDING；本链不调 openAdmission（无 reopen 面，V1.2 的 STOP_IN_PROGRESS reopen 拒绝不经我链）。
- **Gap#2 幂等再观察**：可靠性 flow 若在命令车道后重录 stop_requested，折叠收敛（c0c8844bec 已修）——链的 record 流不触发重复记录闩锁。
- **预算保留**：链不触碰 budget；stopped→冷重启→resume→续充 attempt 2 → 折叠 [1,2]（既有 usage 桥接 + Gap#1 代际折叠）。

## 6. 验收用例草稿（实施时落 tests/stop-chain-composition.spec.ts，新文件面）

全部**真实链**（真实 stopProject+真实子进程/真实 flush；无假 timer；无 canned StopResult）：

1. **有序真实停止**：goal 活跃+真实心跳子进程（at4-03 同型 spawn）→ /devframe-stop → 断言：子进程在 releaseWriter 时刻已死（停后探测 pid 消失）；回调次序 closeAdmission→record(stop_requested)→jobs/processes drain→flush→releaseWriter；StopResult={stopped,remaining:[]}；绑定落 quiescence_confirmed→stopped 两条词汇记录；成功文本。
2. **needs_attention+writer 保留**：一个 grace 内不结算的真实 job → result needs_attention；releaseWriter **未被调用**（顺序记录断言）；绑定停留 stop_requested；命令返回含 remaining 的文本。
3. **预算跨真实停止+冷重启保留**：start→usage 1→/devframe-stop（真实链到 stopped）→flush→冷重启→resume→续充 attempt 2 → 折叠 [1,2] 干净、from-zero 1 拒。
4. **重复 stop 幂等**：stopped 后二次 /devframe-stop → 稳定数据错误、零新记录；日志重放收敛（Gap#2）。
5. **drain 中拒绝新启动**：flush 挂起（deferred 门控真实 promise）期间 /devframe-start → START_GOAL_RUNNING 稳定文本；flush 门释放后链完成。
6. **writer 挂钩缺省=失败安全**：不配 releaseWriter → needs_attention+writer 保留+具名 remaining（不虚报释放）。
7. **回归**：/devframe-stop 现有词汇面用例（stop-abandon-composition.spec）保持全绿——链升级不破坏既有序列断言（record 流与 lifecycle 落点的兼容性在实施时核对，若词汇用例的顺序断言需更新，逐条如实登记理由）。

## 7. 实施顺序（审后）

1. config.ts：stopGraceMs + releaseWriter 挂钩（含校验+JSDoc）。
2. composition.ts：停止链升级（§1 序列+§3 解析+§4 语义）+新文本常量（command.ts）。
3. tests/stop-chain-composition.spec.ts：§6 七用例（真实链）。
4. 阶梯验证：新 spec+stop-abandon+start-resume+start-interruption+devframe goal-binding/events+agent-reliability 全套；独立审查→总控唯一合并。
