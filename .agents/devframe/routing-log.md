# 双 Provider 路由日志（routing-log）

**并发校正（用户指令 2026-09-05 23:17 后）**：持久化投影显示 23:17 左右 huoshan-2 有 L-Memory+两短切片共 3 活动 > 登记上限 2。对账结论：两个"短切片"=lane2 场景对（约 23:16 已结算返回，投影快照晚于结算）；L-Memory 实际车道**当时未经证实**。诚实修正：可续导 subagent 的车道归属不可由总控控制也不可观测（subagent 工具无 provider 参数），先前"组长继承 huoshan-1"的断言撤回；**唯一已证实的请求级绑定=workflow agent() 的显式 provider 参数**。修正后记账规则：限额按"全部在飞会话总数"合并记账（huoshan-1=5、huoshan-2=2 的分账仅在 workflow 显式绑定内可执行），总控在无法归因车道时按保守总数 ≤5 记账。23:17 后已停止新建派发至对账完成；当前在飞（按结算通知核对）=L-Shadow 1 条。

用户授权（2026-09-05）：huoshan-1 / huoshan-2 常态同时承担不同任务；glm-5.3-flash；显式按任务绑定 Provider；每路按实际限额做有界并发与退避；不借重试吸收超额；不重放结果不确定的调用。

## 路由接缝事实（已验证）
- 可续导派发工具（subagent）无 provider 参数——子组长继承主会话车道（huoshan-1），在跑任务不打断。
- workflow 工具的 agent() 支持 `provider`/`model` 请求级覆盖——**本会话唯一可用请求级路由接缝**，已实测生效（见探针行）。
- 局限：workflow 的 agent 为一次性完成型（不可 send_message 续导），故长任务仍在 huoshan-1 车道的可续导组长上；第二路承接短切片（场景准备/验收探测/独立校验）。

## 有界并发
| 路由 | 当前并发上限 | 依据 |
|---|---|---|
| huoshan-1 | 5（总控+5 可续导组长） | 本轮既有 4a 容量表实践，未见降级 |
| huoshan-2 | 2（起步保守） | 两 Provider 名称不必然独立上游限额，按证据放宽 |

## 记录（task / session / provider / model / start / end / result）
| 任务 | 会话 | provider | model | 开始 | 结束 | 结果 |
|---|---|---|---|---|---|---|
| dual-lane-probe lane1 | workflow:probe-lane1 | huoshan-1 | glm-5.3-flash | 2026-09-05T22:28:03+09:00 (T0，屏障内并发) | 22:28:19.9017637+09:00（agent 自取） | 成功：`LANE1-OK` 真实请求+真实 pwsh 时间戳 |
| dual-lane-probe lane2 | workflow:probe-lane2 | huoshan-2 | glm-5.3-flash | 2026-09-05T22:28:03+09:00 (T0，同一 parallel 屏障) | 22:28:17.2933324+09:00（agent 自取） | 成功：`LANE2-OK` 真实请求+真实 pwsh 时间戳 |
| （脚本墙钟 T1=22:28:46.3254605+09:00；两 agent 时间戳均落于 [T0,T1] 且同屏障执行=时间重叠证据） |
| lane2-scenario AT2 草案 | workflow:at2-scenario-prep | huoshan-2 | glm-5.3-flash | ~22:29（探针后同回合派发，墙钟括号） | ~22:36（脚本返回） | 成功：commit `000145d089`（p/accept，9 文件 +446，8 场景草案+runner 清单） |
| lane2-scenario AT3 草案 | workflow:at3-scenario-prep | huoshan-2 | glm-5.3-flash | ~22:29（与 AT2 同一 parallel 屏障=第二路真实并发） | ~22:36 | 成功：commit `560ccb21b0`（p/accept，5 文件 +269，4 场景草案+checklist，逐条核对 main 包契约） |
| lane2-at3-rest 补齐五篇 | workflow:at3-scenarios-rest | huoshan-2 | glm-5.3-flash | 22:43:51（T0'） | ~22:52（脚本返回） | 成功：commit `175afd9ac9`（p/accept，6 文件 +259/−6，AT3 九篇全 drafted） |
| lane2-jsdoc-debt P00 清零 | workflow:jsdoc-debt-fix | huoshan-2 | glm-5.3-flash | 22:43:51（与上同屏障=第二路双任务并发） | ~22:52 | 成功：commit `53ed44b4`（p/debt，2 文件 +36/−7，devframe 15→0，devframe vitest 33/33；发现 project-memory 尚有 19 处→排队 S3 给 L-Memory） |
| lane2-hier-ctrl 场景草案 | workflow:hier-ctrl-scenarios | huoshan-2 | glm-5.3-flash | ~22:55 | ~23:05 | 成功：commit `1b5289e9b3`（p/accept，7 文件 +371，AT2B-01..06：P02 三拒面/深度双保险/scope fail-closed + P04 九态/三元组/合并门，拒绝文本逐字符锚定 src） |
| lane2-p01p05p06 场景草案 | workflow:p01-p05-p06-scenarios | huoshan-2 | glm-5.3-flash | ~23:08 | ~23:15 | 成功：commit `f525584af2`（p/accept，7 文件 +368，AT2C-01..06：P01 cwd/冷恢复 + P05 证据链/byTask + P06 准入切断/不确定调用） |
| lane2-s4 工具面设计 | workflow:s4-toolface-plan | huoshan-2 | glm-5.3-flash | ~23:08（与上同屏障） | ~23:15 | 成功：commit `a073307d`（p/accept，s4-toolface-plan.md 149 行：P01 提示节/P02 拒绝词表/P04 六工具+/project 命令/P05 零写一读/P06 结构化拒绝；命名冲突表；P23 新切片建议） |

## 排队/补位规则
- 第二路空位由完成事件触发补位；新短切片优先入第二路。
- 主树合并、验收判定、可续导长任务仍在 huoshan-1/总控。
