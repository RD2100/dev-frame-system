# v14-gap4 分类账本：sdk/subagent-continuable 120s 超时的根因分类

- 组长树：`D:/dsh-devframe-v14-gap4-lead`，分支 `codex/v14-gap4-lead` @ `24bb18fe4f`（干净基点，本文件为其首个提交）。
- 判别问题：产品挂起（死等/teardown 缺失/子会话永不 settle）还是环境伪影（宿主慢 120s 不够）？
- **判定：产品链缺陷（真实功能回归），非环境伪影。** 卡点已定位到具体 await 与 file:line，并有超时现场（temp 目录残留）逐字节佐证。

## 一、复现记录（真实退出码）

| # | 树 | 命令 | 退出码 | 签名 |
| --- | --- | --- | --- | --- |
| 1 | 本树 | `pnpm run test:snapshot -t subagent-continuable` | 1 | `Test timed out in 120000ms`（实测 120013ms，`snapshots/sdk/sdk.snapshot.ts:858`，卡在运行本身、比较之前） |
| 2 | batteryfix 树（历史证据） | 同上 | 1 | 同签名（120017ms，`.agents/devframe/v14-batteryfix/lead/repro/repro-subagent-continuable.log`） |

确定性：结算基线 + batteryfix 重放 ×2 + 本波 ×1，签名一致。前置：本树新鲜 `pnpm install`（exit 0，20.9s）；keyless replay（宿主无 `DEEPSEEK_API_KEY`、无 `.env`，已探测）。

## 二、卡点链条（哪一步、哪个 await、哪条路径，file:line）

回放驱动（`snapshots/sdk/sdk.snapshot.ts`）：`runScenario` 对父夹具逐 turn 驱动；turn 2 无 prompt（`turnActions` 对无 `user/message` 的 turn 产出 `content === undefined` 的 action），测试在 `waitForRootEvent(... event.type === 'turn/end' && turn === 2)`（sdk.snapshot.ts:654-660）上死等——**这是挂住的 await**。turn 2 只能由子会话 Activation settle 后的 `subagent-settled` 通知唤醒（`packages/subagent/subagent/src/continuation.ts:319-322` 通知措辞与夹具一致）。

超时现场（vitest 超时后测试协程永不 settle，`runScenario` 的 finally 不完成，temp 目录残留）：`%TEMP%\sdk-snapshot-subagent-continuable-afQws1`。

1. **产品侧起点（已落地的有意变更）**：continuable 后台启动的工具结果文本由 `started subagent <id>` 改为 `started continuable subagent; SessionID <id>`（`packages/subagent/tool-subagent/src/index.ts:457`；commit `1ed2c783d4`，Agent Note `.agents/notes/implemented/feature/2026-09-05-subagent-sessionid-explicit.md`，其第 28 行明确"recorded fixtures stay red until refreshed"）。现场父日志 tool/result 实测文本：`started continuable subagent; SessionID d97f7c64-…`。
2. **失效的耦合契约**：llm-replay 以"稳定的工具结果文本"学习后台子会话 id——`inferStartedSubagents`（`packages/test-support/llm-replay/src/index.ts:463-479`）的正则 `/started subagent ([^\s"'<>]+)/g`（:470）不认识新措辞 → `liveSessionIds[1]`（子脚本槽）不绑定。
3. **fail-loud 抛错点**：父 turn 1 step 2 的脚本条目（`send_message` args 含 `{{session:2}}`）经 `materializeSessionTokens`（llm-replay/src/index.ts:441-459，抛错在 :448）→ 抛 `llm-replay: session token {{session:2}} was used before that recorded session bound` → 父 turn 1 以 error 收尾（现场日志 `turn/end reason error`）。
4. **fence 死锁（挂起的直接机制）**：SDK 场景复用 composition `subagent-durability-failure`（owner=`snapshots/session/subagent-published-run-failure`，SDK 回放经 `authoredPatches` 加载 overlay，现场 `.snapshot-patches/1-cordis.snapshot.yml` 证实）。overlay 的 `agent/pre-step` 钩子（`packages/test-support/session-snapshot/tests/fixtures/subagent-durability-failure.ts:109-117`）把子会话步骤压在 `followupsAccepted`（需 3 次子收件箱插入）之后；父 turn 1 在 step 2 即 error，两条 follow-up 永未发送 → 子收件箱仅 1 次插入 → fence 永不释放。**现场子日志冻结在 `turn/start` + 认领 splice、零 `step/start`**——子会话一步未跑，永不 settle。
5. **终局**：子不 settle → 无 `subagent-settled` 通知 → 父 turn 2 永不开始 → 死等 `turn/end` 2 → vitest `testTimeout: 120_000`（`vitest.snapshot.config.ts:62`）触发，测试超时（sdk.snapshot.ts:858）。

## 三、环境伪影排除判据（具体）

- 确定性 ×4 同签名（含 120013/120017ms 两个独立实测），非慢宿主波动。
- 卡点不是"慢"而是"永不来"：现场父日志已走完 turn 1（error 收尾）、子日志冻结于 fence 前零步——机制驱动的停滞，非进度缓慢；若为宿主慢，事件流会在 120s 内持续推进而非冻结。
- 同宿主同窗口内其余 SDK 子代理场景（subagent-list-agents / subagent-send-message / subagent-continuable-inheritance，win32 变体）全绿——宿主/环境变量共性面被排除。

## 四、产品源所有者与修复方向（file:line）

- **所有者（本波可修）**：`packages/test-support/llm-replay/src/index.ts:463-479` `inferStartedSubagents` —— 其"稳定工具结果文本"契约被 `1ed2c783d4` 的措辞更名单方面破坏。这是挂点本身（绑定机制），不是症状（超时）。
- 最小修复：模式扩为同时接受现行 continuable 措辞（`started continuable subagent; SessionID <id>`）与历史措辞（`started subagent <id>`），**不得**把 job 启动文本（`started background subagent job <jobId>`）绑进会话槽位（jobId 非会话 id，会错绑 `{{session:N}}`）。建议模式：`/started (?:continuable )?subagent(?:; SessionID)? ([^\s"'<>]+)/g`，并保留既有去重守卫。回归单测落在 `packages/test-support/llm-replay/tests/llm-replay.spec.ts`（该文件 :1213/:1250/:1277 已有同类绑定用例，按既有模式扩展），不依赖 120s 快照套件。
- **不修产品措辞**：回退 `1ed2c783d4` 文本会同时打绿着的三场景（其 win32 变体夹具钉住新措辞）、工具单测与文档化特性——数学上与"零新增失败"互斥。
- **不修 fence**：overlay 死锁只在 turn 提前 error 的病态路径显现；其定序正是 authored 夹具钉住的确定性（通知到达于空闲父），拆除即引入新漂移。

## 五、夹具陈旧面（本波禁区，交总控配方）

Agent Note :28 自证夹具陈旧为已知状态。本场景（`snapshots/sdk/subagent-continuable/`，无 win32 变体，基座夹具全平台生效）陈旧点：

1. `session.jsonl:21` tool/result 文本（旧 `started subagent {{session:2}}`）。
2. `session.1.jsonl` request/header 内 `send_message`/`interrupt_agent`/`list_agents` 描述（旧 "agent id" 措辞；现行产品文本见 `packages/subagent/tool-subagent-control/src/index.ts:31,80`、`list-agents.ts:95`）。
3. `tool-schemas.1.expected.json`（同上描述面）；`system-prompt.1.expected.md` 如含同面文本则同批。

**完成配方（keyless）**：llm-replay 修复落地后 `pnpm run test:snapshot:refresh -t subagent-continuable` 一次写回全部陈旧面（refresh 重放已提交脚本并回写期望输出，无需 key）→ replay 转绿。备选：按上述点位手工编辑。`test:snapshot:record` 需 key，宿主无 key（env 未设、lead/主树均无 `.env`）→ record 路径 blocked，本配方不依赖它。旁证：三个姊妹场景的 win32 变体即 BatteryFix 波同法 harvest，与现行产品文本一致而转绿。

同族遗留（本波外，报总控）：三姊妹场景的 POSIX 基座夹具同钉旧措辞，POSIX 宿主上预期同因踩坑（本宿主 win32 不触发，不计入本波门禁口径）。

## 六、对 BatteryFix 分类账本的更正

`.agents/devframe/v14-batteryfix/lead/classification.md` §二 GAP-4 称"win32 子代理 durability/恢复机制重放路径阻塞"——方向正确但未触达机制：阻塞不在 durability/恢复路径（子会话的 `sandbox/mode`/`approval/policy` source=delegation 继承面与夹具一致，健康），而在父侧 llm-replay 文本绑定失效 + overlay fence 死锁。本文件为准。

## 七、结论

功能回归为真，判定**产品链缺陷**：修 `packages/test-support/llm-replay/src/index.ts:470` 的绑定契约（本波，Worker 车道）；快照场景转绿还需一步夹具写回（禁区，交总控 keyless refresh 配方）。修复后预期签名变化：120s 挂起 → 秒级 fail-loud diff（唯一 delta=上述陈旧面），直至总控执行 refresh 收口。
