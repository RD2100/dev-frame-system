# v14-accept 验收结算（results）

taskId=v14-accept（独立组合集成验收波）。组长为**有界接替**组长：前任组长 9fa566f7 因
huoshan-1 AccountQuotaExceeded 停止并封存；本组长树 `D:/dsh-devframe-v14-accept2-lead`
（分支 `codex/v14-accept2-lead`）自前任分支尖端创建，**原样继承其场景设计**
（design.md @4fce69f194，S1-S7 定稿）与 findings.md @2893337b37。接替关系，非父子关系，
无伪造归属。本文件为七场景真实执行的结算：逐场景 pass/fail/blocked + 证据路径 +
现状失败清单 + 环境事实 + 逐笔 SHA + Worker 车道实证 + 偏差 + GAP。合并权在总控
session-c1668d60。

## 1. 结论速览

| 场景 | verdict | 退出码 | 检查项 | 证据（lead 树内收档路径） |
|---|---|---|---|---|
| S1 真实任务运行（keyless 钉住） | **BLOCKED**（真实 API 路径） | 3 | 4/4 钉住复现 | `evidence/s1/`（verdict.json, exitcode.txt, stdout.txt, stderr.txt, session-listing.txt, key-probes.json） |
| S2 权限三模式 | **PASS** | 0 | 9/9 | `evidence/s2/`（verdict.json + 每子运行 stderr/stdout/exitcode/launch/events） |
| S3 cwd | **PASS** | 0 | 2/2 | `evidence/s3/`（verdict.json, header.json, session-path.txt, stderr/stdout/exitcode） |
| S4 goal 流转 + /goal-complete 钉住 | **PASS** | 0 | 7/7 | `evidence/s4/`（verdict.json, results.json, session-log.json, events.json） |
| S5 两进程重启续跑 | **PASS**（write 0 / resume 0） | 0/0 | 1/1 + 3/3 | `evidence/s5/`（write.json, resume.json, verdict.json） |
| S6 Shadow 跨项目路由 | **PASS**（warm 5/5；cold 加分项行级全恢复） | 0/0 | 5/5 + bonus | `evidence/s6/`（verdict.json(cold 汇总), routing-log.json, bindings.json, deliveries.json, verdict-copy-cold.json） |
| S7 Memory 冷恢复 | **PASS**（write 0 / read 0） | 0/0 | 1/1 + 4/4 | `evidence/s7/`（write.json, read.json, vault-listing.txt, verdict.json） |

- 判读语义：全部 pass = PASS；真实不可运行面 = BLOCKED（附精确阻塞）；检查项真实失败 = FAIL
  （evidence.mjs 契约：exit 0/2/3/4）。诊断性中间运行收档于 `evidence/_diagnostic/`（见 §5 偏差）。
- **无 key 事实**：根 `.env` 不存在、进程 `DEEPSEEK_API_KEY` 未设置、隔离
  `$DSH_HOME/.credentials.yaml` 不存在（`evidence/s1/key-probes.json` 实测）→ S1 按 design
  记 BLOCKED + 精确原因；S2-S7 免 key 场景照跑并全过。
- 全程无 LLM 触碰：机制 B 经 harness `AcceptanceMockAdapter`（stream 首拉抛
  `ACCEPTANCE_LLM_TOUCHED`）；七场景无一次触发（无该错误出现）。

## 2. 逐场景钉住面复现明细（全部挂在真实运行产物）

- **S1**：exit 1；stderr 末行原文
  `dsh: MISSING_CREDENTIAL: llm-deepseek: no API key for provider route "deepseek-official"; store DEEPSEEK_API_KEY through the credentials service (the web Models page writes it), or export DEEPSEEK_API_KEY in the launching environment`；
  stdout 恰 1 字节 `\n`（见 §5 偏差 D3）；`$DSH_HOME/sessions/` 恰 1 个 session 目录。
- **S2**：`DSH_PERMISSION_MODE` unset/read-only/danger-full-access 三子运行，各自
  `permission/preset`/`sandbox/mode`/`approval/policy` 恰 1 次、值逐一等于
  workspace-write|read-only|danger-full-access × policy ask|ask|never——env→事件值真实因果成立。
- **S3**：header.cwd（realpath+大小写归一）== spawn cwd（目录名含 uuid）；session 目录映射唯一。
- **S4**：`/goal`（无 goal）→ `NO_CURRENT_GOAL_TEXT` 原文；create→`goal/change` operation=create
  + phase active；pause→paused / resume→active；start lane（组合 test-visible `startBinding`）
  后未绑定 `/goal-complete` → `NO_BINDING_TEXT` 原文；绑定后 `/goal-complete` →
  **`NO_VERIFICATION_TEXT` 原文（钉住）**；每次派发 command/run+command/done 按 commandId 配对、
  拒绝后 goal phase 不变；`/goal clear` → `Goal cleared.` + clear 事件。稳定文本逐字导入产品
  src 导出面比对，无私有副本。
- **S5**：write 进程 `/goal` 后真实持久化 3 事件（command/run, goal/change, command/done）；
  resume 进程 `ctx.agents.resume` 冷加载——id/cwd 等值、持久化前缀逐行（seq+type）包含、
  goal projection 恢复 active+objective 等值；`/goal pause` 成功且新事件（seq 4-6）自恢复日志
  末端（seq 3）单调接续。冷加载 boot 自补 1 条 `session/end-seed`（产品事实，见 §5 偏差 D4）。
- **S6**：两真实项目目录 A/B 下 openProject 返回独立 workspaceId+controllerSessionId（canonical
  root=项目根）；sendToProject 每项目 received、投递相互隔离（A2 条/B1 条）；setActiveGoal
  两项目独立 activeGoalId；stopProject/confirmProjectStopped 仅停 A（B 不受影响）；同
  requestId 不同输入重放 → `SHADOW_REQUEST_CONFLICT`。cold 加分项：同 root 新进程绑定行级
  恢复 true + 投递行级恢复 true（design 标注失败不判 FAIL，实际全复现）。
- **S7**：write 进程 append 两 note（project 域 projects/ws-accept + user 域）经
  `memory/receipt` 落真实 session 日志；read 进程 `ctx.agents.resume` +
  `rehydrateMemoryReceipts` 后按 noteId read → found + verified:true + 六字段等值（noteId/
  body/kind/status/source/namespace）；search 两域各恰 1 命中；同 sourceRef 重试 append →
  `already_exists`；Vault 内恰 2 个真实 `.md`
  （`devframe-memory/projects/ws-accept/<id>.md`、`devframe-memory/user/<id>.md`）。

## 3. 现状失败清单（供 compos 落地后复验，非本波阻塞）

1. **生产组合无 AgentEvidenceJournal producer/接线** → 真实宿主 `/goal-complete` 到不了
   admitted 完成链。本波以组合 test-visible start lane（`startBinding`，README 标注
   test-visible）复现到稳定拒绝 `NO_VERIFICATION_TEXT` 并钉住（S4 检查 5）。
2. **`/devframe-resume` 宿主入口缺席**：grep 实证 `packages/**`（shipped profile
   bundles、实验包 src，排除 tests/node_modules）对该命令名**零匹配**（本组长执行，
   2026-09-06，树 d6e3f9d534）。S5 钉住的是 JSONL 冷加载面（SessionStore restore +
   ctx.agents.resume）本身。
3. **shipped profile（headless/devframe）不挂 v14 实验包**：机制 B 场景的命令族/绑定/
   Shadow/Memory 组合全部经真实插件序列 in-process 组合驱动；profile 级 `--patch` 叠加仍是
   唯一真实 profile 级组合通道（findings §4）。
4. **S1 真实 API 路径**：需有 key 环境才能走通；keyless 形态已按 design 钉死为 BLOCKED。

## 4. Worker 车道实证（如实登记）

- 派发：workflow 工具单次 `agent(prompt, {provider:'huoshan-2', model:'glm-5.3-flash'})`，
  meta 记录于 workflow `v14-accept-harness-worker`。
- 事实：Worker 交付了**全部 11 个 harness 文件**（4 lib + 7 场景脚本，内容与 design §1/§2
  逐项对应、与 src 实证接口一致），但 child 在提交/回执前失效——workflow 返回
  `receipt: null`（疑似同额度池中断，与前任组长 huoshan-1 中断同型）。
- **车道实证 gap**：要求"Worker 回执真实请求模型"无法满足（无回执）。派发参数为
  huoshan-2/glm-5.3-flash，但实际请求模型**不能从回执证实**，如实登记为未证实，不声称符合。
- 未重派（守"禁重复派发/多 Worker"）；按 design §3.3 机械修正通道由 lead 逐文件验收后
  代为提交（见 §5）。

## 5. lead 偏差登记（全部机械性、逐条验证非语义回退）

Worker 树 `codex/v14-accept-w1`：交付 commit **d6e3f9d534**（lead 代提交，--no-verify，
staged `git diff --check` exit 0，11/11 node --check + 每文件恰一尾随换行）+ 执行期修正
commit **9b5103f54c**（--no-verify，diff --check exit 0）。

- **D1（交付期）** s4-goal-complete.mjs：4 处相对导入 `../../packages/...` 层级错误（harness
  根到树根 5 级）→ 改 `../../../../../packages/...`。运行验证：S4 PASS。
- **D2（交付期）** s1 判定语义：keyless 且钉住检查未复现时应 FAIL（design §0），原实现一律
  BLOCKED → blocked 仅在 key 存在或钉住复现时给出。
- **D3（执行期）** s1 stdout 检查精化：design "stdout 为空" 按字节不复现——headless runner
  无条件写 `outcome.text + '\n'`（packages/bundle/headless/src/index.ts L206），错误收尾
  stdout 恰 1 字节换行（findings §6 的"stdout 空"为未量化观察）。检查改为"stdout 无任务输出
  （至多 runner 单个尾随换行）"，observed 记录字节级 repr。首跑证据
  `evidence/_diagnostic/s1-first-run-stdout-byte/`；修正后 S1 BLOCKED 4/4。
- **D4（执行期）** s5 事实基准：write 相位原取 flush 前内存快照；resume 冷加载的是持久化
  全量，且冷加载 boot 会自补 1 条 `session/end-seed`（packages/core/session/src/index.ts
  L575-576，resume seed 路径）。改为：write 事实取 flush/dispose 后真实持久化日志；
  身份判据=id/cwd 等值+持久化前缀逐行（seq+type）包含+越前事件如实记录（实测恰
  `session/end-seed` 1 条）；seq 判据以恢复日志末端为基准。中间两跑诊断证据
  `evidence/_diagnostic/s5-run1-pre-fix/`、`s5-run2-pre-fix/`；修正后 S5 PASS。
- **D5（执行期）** s7 fieldEqual 修参：三元判断 `namespace === 'project'` 而调用方传
  `'projects/ws-accept'`，project 侧错拿 userNoteId 比对 → 改为显式传期望 noteId。中间跑
  证据 `evidence/_diagnostic/s7-run1-fieldEqual-bug/`（两条 note 实际 found+verified:true+
  内容等值，仅比较参数错位）；修正后 S7 PASS。
- Worker 原备注的两条偏差沿用：S4 检查 5 前插入 `/goal clear` 中间步（start lane 要求无
  未完成 goal，GOAL_BINDING_ALREADY_RUNNING）；S5/S7 `ctx.agents.resume` 显式传与 write
  相同 agentOptions（design 文本仅列 resumeSessionId）。

## 6. 环境事实

- 宿主：Windows（pwsh，无 bash）；node v24.19.0；pnpm 11.19.0。pre-commit lefthook 宿主
  exit 127（环境事实）→ 全部提交 `--no-verify` + 替代验证收据（staged `git diff --check`
  exit 0 + 每文件恰一尾随换行 + node --check）。
- 隔离：每场景独立 `%TEMP%/dsh-accept-<label>-<uuid>/` 根；`DSH_HOME=<root>/dsh-home`；
  `DSH_TELEMETRY_DISABLED=1`；`DSH_AGENTS_HOME=<cwd>/.agents`；机制 A 子进程 cwd 为场景
  专属临时目录。**真实 `C:/Users/25313/.dsh` 与主树全程零写入**（所有写入面均实测落隔离域）。
- 运行树：Worker 树 `D:/dsh-devframe-v14-accept-w1`（node_modules 已装 + typert 工件已生成，
  前任遗留齐备，lead 复用未重建）；harness 以 `node --import tsx/esm` +
  `TSX_TSCONFIG_PATH=<tree>/tsconfig.json` 运行。
- w1 树创建时已存在（前任被中断前所建，@4fce69f194、干净、无 worker 文件）——按"接续非重做"
  复用；本波未重复 `git worktree add`。

## 7. 逐笔 SHA

| 项 | SHA | 分支/树 |
|---|---|---|
| 前任 findings（继承基线） | `2893337b37` | codex/v14-accept-lead（继承，未触碰） |
| 前任 design（继承定稿） | `4fce69f194` | codex/v14-accept2-lead 起点与本波工作基线 |
| Worker harness 交付（lead 代提交） | `d6e3f9d5346133075b7a0940ce3e997c1ad37d22` | codex/v14-accept-w1 |
| lead 执行期机械修正 | `9b5103f54c` | codex/v14-accept-w1 |
| 本结算文件 | 见本树 codex/v14-accept2-lead 最新提交（git log 本文件） | codex/v14-accept2-lead |

## 8. GAP / 未尽

1. **Worker 车道回执缺失**（§4）：真实请求模型未证实；huoshan-1 车道本波未使用（如实登记）。
2. S1 真实 API 路径需有 key 环境复验（§3.4）；keyless 形态已钉死。
3. 现状失败清单 1-3 待 compos 落地后复验：重跑 `s4-goal-complete.mjs`（期望检查 5 从
   NO_VERIFICATION_TEXT 推进到 admitted 完成链）与 `s5-resume.mjs`（期望生产 /devframe-resume
   入口面另行验收）即可闭合；harness 与判据已就位、可重复执行。
4. 产品事实两则供后续期望面对照（本波如实记录，不判优劣）：headless 错误收尾 stdout 恰 1 字节
   换行（D3）；resume 冷加载自补 1 条 `session/end-seed`（D4）。
5. S6 cold 行级冷恢复为加分项且已复现；其非 design 必检项，回归时按 bonus 记录。
