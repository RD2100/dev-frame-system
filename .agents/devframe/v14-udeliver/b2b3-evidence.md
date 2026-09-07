# B2/B3 — Shadow/Memory 真实路径证据（b2b3-evidence）

基线：B1 已由总控定格 blocked/not_run（chain-evidence.md"chain5 收口"节=d6caf6f992；清单 765b20384d）；本文件只收 B2/B3。隔离面：DSH_HOME=`D:\dsh-udeliver-iso\home-b2b3b`（settings+凭据引用），启动目录=`D:\dsh-udeliver-chain2`，overlay=`b2b3-overlay-b.yml`（shadow-router 补丁：authorizedRoots 双根+controllerProfile standard+shadowSessionId 声明式标记；project-memory 补丁：vaultRoot=`D:\dsh-udeliver-iso\vault-b2b3b`+writeEnabled true；driver v2，b2b3/b2b3verify 模式**零模型依赖**——全部为确定性 service/tool 真实面）。代码树=修复版（bf198278cc 已并）。UI-adapter 边界=进程内 sessionController.create+真实 router/service/tool 面，**非浏览器像素路径**。执行纪律：无 ≥60s 等待；每轮 boot 后台 job+单次 25s 检查；失败步当场记录；小步提交（d050a83b22→3dbe7b8cce→6d0d57c81e→b5dafec048→66d64967f3→b92e37ba39）。

## Boot A（写旅程，pwsh-215/216/217/218 四轮收敛）

**Round 1（pwsh-215）**：影子会话声明式标记成功（session-7f0c9a52，standard preset）；**project_open 真实成功**（workspaceId=bcd80c86、controllerSessionId=shadow-fe079f37 路由预留、bindingRevision=1、state=ready、canonicalPath=D:\dsh-udeliver-second）；driver 收养传参缺陷（cwd 归属校验 RemoteError 逐字在案）→appExit(1) 自净（**appExit 优雅退出验证生效**）。

**Round 2（pwsh-216，全新 home-b2b3b）**：project_open 再次真实成功（workspaceId=5e32a516、controllerSessionId=shadow-4d5f0f49、ready）；收养被拒逐字 `cannot prepare session "..." while it is live`——**路由 provisioning 已建活跃 agent**。

**Round 3（pwsh-217）**：活跃 controller agent 经 agents.get 解析成功；**/devframe-start 在第二项目根真实绑定成功**（kind=success，required checks executed for real: 1, passed）；投影取值字段名修正（bindings 数组）。

**Round 4（pwsh-218）＝完整绿**：
| 步骤 | 证据（b2b3b-driver.jsonl） |
| --- | --- |
| project_open | workspaceId=5e32a516-6cc8-4433-a7ea-39fe7ce39393、state=ready（open 去重收敛复用 round3 绑定） |
| /devframe-start 幂等卫兵 | kind=**error**："A goal is already current and not complete. Resume or complete it before using /devframe-start."——**真实产品幂等行为**（round3 已绑定的 goal 未完成，拒绝二次 start） |
| 绑定读取 | goalId=goal-b74ddfb5-fe2b-4039-b8f9-9428142f0638、acceptanceHash=a1afce280c9c…f542、controllerSessionId=shadow-4d5f0f49（round3 真实绑定） |
| setActiveGoal（host 缝，如实标注） | bindingRevision 1→**2**、activeGoalId/activeAcceptanceHash 写入、state=ready |
| **project_send** | messageId=**msg-b2b3a-send-1**、status=**received**（mode=work、真实投递） |
| **project_status** | projects[0] 全行：controllerLive=true、profileKey=standard、bindingRevision=2、state=ready、activeGoalId、deliveries=[msg-b2b3a-send-1 received+receivedAt]、deliveriesTruncated=false |
| **memory_append** | status=**created**、noteId=5ffff47c…2a172、relativePath=devframe-memory/projects/default/5fff….md——**Vault .md 真实落盘**（文件系统列目录在案） |
| **memory_read** | status=**found**、verified=**true**、body/bodyDigest（sha256:8c793e94…）逐字 |
| 退出 | b2b3-boot-complete→appExit(0) 进程自净（job completed exit 0） |

## Boot B（冷恢复读回，pwsh-219，同 home 同 Vault，进程已停→再启动）

| 步骤 | 证据（b2b3c-driver.jsonl） |
| --- | --- |
| 影子会话跨重启复用 | session-7f0c9a52 create-or-adopt（真实 resume 路径，preset 一致无冲突） |
| **project_status 冷恢复** | 绑定行整行恢复：workspaceId/bindingRevision=2/state=ready/**activeGoalId 保留**、**delivery msg-b2b3a-send-1 state=received+receivedAt 保留**；controllerLive=**false**（冷态如实）——Shadow 存储冷恢复 ✓ |
| **memory_search 冷恢复** | 命中原笔记：noteId 全等、excerpt=原文、kind=fact、freshness=**current**、coverageComplete=**true**——Vault 落盘+回执再水化冷恢复 ✓ |
| 退出 | b2b3verify-boot-complete→appExit(0) 自净 |

## 停止后日志 seq 证据（probe-b2b3-logs.mjs，两进程皆停后抽取）

- **影子会话**（--D-dsh-udeliver-chain2--/session-7f0c9a52）：`memory/receipt` **seq=4**（noteId+namespace projects/default+relativePath 全录）——回执先于结果落会话日志（durable，再水化源）。
- **第二根 controller**（--D-dsh-udeliver-second--/shadow-4d5f0f49）：
  - `request/header` **seq=17 provider=huoshan-1 model=glm-5.3-flash**（count=1）——**第二项目根会话内的真实模型请求**；
  - `devframe/goal-binding` **seq=8**：workspaceId、controllerSessionId、goalId=goal-b74ddfb5、goalRevision=2、taskIds=[devframe-goal]、acceptanceHash=…（逐字）；
  - `devframe/verification` **seq=19**（真实必需检查）；`command/run` seq=4,24、`command/done` seq=20,25（round3 成功 start+round4 幂等拒绝两轮命令面）。

## 结论

B2（Shadow：open→goal 绑定→host setActiveGoal→send→status）与 B3（memory_append 写 Vault→read 验证→**重启冷恢复读回**）全部以真实进程链收证：服务/工具面逐字段结果、会话日志 seq、Vault 实体文件三层齐备；两轮 boot 均 appExit 优雅退出（退出码 0）。B2/B3 可计入运行态翻转依据（真实进程+日志响应+重启恢复三要件满足）。运行态验收翻转仍归总控裁定。
