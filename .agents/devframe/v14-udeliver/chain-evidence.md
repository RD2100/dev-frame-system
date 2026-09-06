# B1 — 12 站真实链本轮收口证据（按总控裁定：失败证据收口，禁止盲重试）

日期：2026-09-07。隔离面：DSH_HOME=`D:\dsh-udeliver-iso\{chain,chain2,chain3,chain4}-home`（settings+凭据引用），启动目录=`D:\dsh-udeliver-chain`（branch codex/v14-udeliver-chain @ 2380aae9a3），overlay=`D:\dsh-udeliver-iso\overlay.yml`（port 3490、shadow authorizedRoots、memory vault）。驱动=`harness/chain-driver.ts`（UI-adapter 边界=进程内 sessionController.create + ctx.commands.execute，**非浏览器像素路径**，逐站如实标注）。

## 判定（引用总控裁定）

**provider 流式 args 缺陷，非链缺陷。** huoshan-1/glm-5.3-flash 流式 tool-call args 碎片损坏（tool-call-chunks 内 `\\\"` 双重转义、`"list","Service"` 碎裂、引号错位→JSON 不可解析→`"input" must be an object` 拒绝×N→仅 1 次模型请求无自愈）。链驱动/组合/goal 绑定/任务投递本身全绿——S1-S3 站证据有效保留。恢复路径（流式 args 契约缺陷修复+最小真实重放）已登记总控清单，B 线不得自行开工。

## 四轮 boot 记录（driver JSONL 实录，逐轮要点）

| 轮 | 配置 | driver 证据 | 结果 |
| --- | --- | --- | --- |
| boot1 | headless+shipped+driver(agents.create 面) | `chain-driver.jsonl`：driver-applied→agent-created→start-result **success**（真实检查 1 项 passed）→flag-written；随后 fail-loud | 总控真实请求 seq=14 huoshan-1/glm-5.3-flash；tool-cordis pending `dynamicCordisRunner,cordisInspect`→`1 entry did not activate`（shipped overlay 原生宿主=web 的实证，已入 boot-evidence.md） |
| boot1b | web+overlay+driver(收紧行动任务书) | `chain2-driver.jsonl`：同上四事件全绿 | 总控工具面只有 memory/cordis（裸 agents.create 绕过 preset），探索不派工，手动停止 |
| boot1c | web+overlay+driver(单动作任务书) | `chain3-driver.jsonl`：同上四事件全绿 | 同工具面缺陷；总控以 cordis_define/cordis_run 自建 scout；**provider 流式 args 损坏在此轮日志定案**（见下节样本）；手动停止 |
| boot1d | web+overlay+driver(**sessionController.create+agentPreset standard**) | `chain4-driver.jsonl`：composition-ready→agent-created(**agentPreset:"standard"**)→start-result success→flag-written | 总控全工具面（pwsh/get_goal/todo_write/glob/read 实用），自建分支尝试+读设计文档推进产出；受 provider args 缺陷损伤，交付物未落；按裁定停止 |

四轮 /devframe-start 全过（`kind:"success"`，"required checks executed for real: 1, verification status: passed"=git diff --check 真实子进程）。

## chain3 根因日志引用（provider 流式 args 损坏样本）

会话：`D:\dsh-udeliver-iso\chain3-home\sessions\--D-dsh-udeliver-chain--\session-87444f2d-771e-4530-9d29-bedc0ce11c3d\session.jsonl.zstd`

- tool-call-chunks 碎片样本：seq0=1082 / 2365 / 2416 / 4046（`\\\"` 双重转义与 token 碎裂，总控判定引用）。
- 本组亲读受损 args→拒绝回路（seq=4270-4273）：`cordis_inspect_query` args=`{"input":"{\"service\": \"goals\"}","method":"listService",...}` → tool/result isError `"Error: Host Cordis inspect Service.listService rejected input: \"input\" must be an object"`；同 step 内并列 call 的 method/`"list","Service"` 碎裂。
- 结构性放大：仅 1 个 request/header（seq=14）对应全部受损轮次——args 解析失败未触发模型自愈重请求。

## 已证站清单（S1-S3 保留，boot1d 为准）

| 站 | 状态 | 证据 |
| --- | --- | --- |
| S0 隔离面准备 | ✅ | 四套隔离 home+凭据引用；启动目录=链工作树；overlay 端口/授权/vault |
| S1 boot+四包挂载 | ✅ | boot1d driver JSONL `agent-created agentPreset:"standard"`；boot 探针（boot-evidence.md）：3491 LISTENING ~4s、四包在列、152 行零重复 |
| S2 总控真实调用 | ✅ | boot1d request/header **seq=16 provider=huoshan-1 model=glm-5.3-flash**（逐字）；chain3 同证 seq=14 |
| S3 /devframe-start 目标绑定 | ✅ | command/run seq=3（devframe-start+objective 逐字）；goal/change seq=4 create+seq=5 resume（goal-a2919dea）；devframe/goal-binding seq=7（controllerSessionId+goalId）；devframe/verification seq=18（verificationId 986df254，真实检查 passed） |
| S3b 任务投递 | ✅ | driver `followup(createUserMessage)` 真实 user 消息；总控回合开启并真实用工具（todo/pwsh/read/glob） |
| S4 组长 subagent | ⛔ 阻塞 | 模型未派工：三轮工具面缺陷+一轮 provider args 损伤；已证组合面无阻断（standard preset 下工具可用） |
| S5 Worker workflow 显式 huoshan-2 | ⛔ 阻塞 | 产品内未达；**车道机制证据由 B 线四个 harness 级 workflow dispatch 补位**（receipts.md ③层：request/header seq=13 provider=huoshan-2/model=glm-5.3-flash ×4） |
| S6 产出+独立审查 / S7 合并 | ⛔ 阻塞 | deliverable/hello.md 未落（总控尝试分支 codex/v14-b1-w1 未成；工作树仅余 .chain-scout-state.json/.goal-bound.flag 两个探针残留） |
| S8 停止 | ✅（进程级） | harness job 系统对 pwsh-213（boot1d node 进程）发停止请求→确认受理；复核 port3490-listening=False、chain4 node 进程不存在。进程内 drain 式 stop 未及驱动（S8 语义级待恢复轮） |
| S9 重启 / S10 /devframe-resume | ⛔ 阻塞 | 依赖 S6/S7 产出后的有物可复会话；resume 事务面已在 driver 就绪（sessionController create-or-adopt） |
| S11 Shadow 站 / S12 Memory 站 | ⛔ 阻塞 | overlay 已配置（authorizedRoots 双根、vaultRoot+writeEnabled）；待链恢复后驱动 |

## 停止命令与退出码（收口动作 a）

```
job_kill(pwsh-213, reason="总控裁定 B1 本轮失败证据收口：停止 boot1d（port 3490）…")
→ 请求受理；6 秒后复核：Test-NetConnection 127.0.0.1:3490 → TcpTestSucceeded=False；Get-Process node (CommandLine match chain4-home) → 无
```

（Windows 强杀语义：无信号标记，按 harness 约定记为终止而非命令失败；stdout/stderr 尾部为空，无错误输出。）

## 移交清单

- 证据文件（本树已提交）：boot-evidence.md（四轮集成发现）、b4-evidence.md、b5-reconciliation.md、worker/receipts.md（③层已实证）。
- 隔离目录（未提交，保留待恢复轮复用）：`D:\dsh-udeliver-iso\{chain,chain2,chain3,chain4}-home`、`out\chain*-driver.jsonl`、`out\probe-*.mjs`、overlay/driver-patch-*.yml。
- 恢复前置（总控清单所有，B 线不自行开工）：huoshan 流式 args 契约缺陷立项→录播 chunk 解析器对照→修复→最小真实重放（一次请求+单工具调用）→重启 12 站链。

## 总控补遗（监督新增诊断，2026-09-07 收口时点）

- **pkg-4 running ≠ 成功**：`cordis_inspect_self` 显示 host handlers 为空、chain_scout 未暴露——define 后的 package 内容受损（与流式 args 损坏同根因面：cordis_define 的 source 参数经同一损坏通道），运行态标签不能替代 handler 实存；模型在相同诊断上循环，deliverable/hello.md 始终未产生。
- **双根因面并列登记**（C2b 修复需两者都覆盖）：①流式 args 碎片损坏（seq 1082/2365/2416/4046）；②模型把 `input` 序列化为字符串（seq 4270-4273）——工具 fail-loud 拒绝正确，属模型侧行为；harness 侧修复面=①，②在重放验证中观察。
- **附带缺陷登记**：boot1 实证 tool-cordis 在 shipped overlay（web 宿主）`1 entry did not activate`（dynamicCordisRunner,cordisInspect pending）——另立清单项，不阻塞 C2b。
- B1 状态：**未完成/异常退出**；恢复路径唯一（C2b 修复→最小重放→重启链）。
