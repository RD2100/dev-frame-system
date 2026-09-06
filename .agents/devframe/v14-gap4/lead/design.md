# v14-gap4 设计书：subagent-continuable 回放绑定契约修复

依据：同目录 `classification.md`（根因链与现场证据）。本波写域=产品源与测试，**零触碰 `snapshots/**`**。

## 一、最小待改文件清单（具名，仅此两文件）

1. `packages/test-support/llm-replay/src/index.ts`
   - `inferStartedSubagents`（:463-479）:470 的模式 `/started subagent ([^\s"'<>]+)/g` 扩为 `/started (?:continuable )?subagent(?:; SessionID)? ([^\s"'<>]+)/g`。
   - 覆盖面：现行 continuable 文本 `started continuable subagent; SessionID <id>`（tool-subagent/src/index.ts:457）与历史文本 `started subagent <id>`；继续**不**匹配 job 文本 `started background subagent job <jobId>`（background 字面阻断了模式前缀，无需额外排除逻辑，但须有单测钉死）。
   - 同步更新 :462 的契约注释：写明两类被接受的产品文本及其来源（tool-subagent 的 start render），以及 job 文本不得绑定的理由（jobId 非会话 id）。保持注释局部，不展开历史。
   - 既有去重守卫（:473 `liveSessionIds.includes(id)`）与槽位顺序语义（:474 首个未绑槽）不动。
2. `packages/test-support/llm-replay/tests/llm-replay.spec.ts`
   - 按既有绑定用例模式（:1213 materializes…、:1250 rejects…、:1277 legacy 文本用例）扩展，新增用例见 §二。
   - 不改既有用例语义；legacy 用例保留（历史措辞继续可绑定，防回归）。

不改：`packages/subagent/**`（产品措辞是文档化特性的锚点）、overlay fixture（fence 定序=夹具确定性）、`snapshots/**`（本波禁区）、README（机制散文未钉具体文本，避免无谓扩散；如 Worker 认为必须同步，须在回执中给出逐字 diff 理由，默认不动）。

## 二、测试矩阵（不依赖 120s 快照套件）

| # | 用例 | 输入（父请求消息中的字符串叶） | 期望 |
| --- | --- | --- | --- |
| R1 | 现行措辞绑定（本波回归主案例） | 工具结果 `started continuable subagent; SessionID <live-child-id>`；脚本条目含 `{{session:2}}` | 条目 materialize 为 live-child-id，不抛 "used before that recorded session bound" |
| R2 | 历史措辞仍绑定 | `started subagent <live-child-id>` | 同 R1（既有用例已覆盖则复用，不重复造） |
| R3 | job 文本不错绑 | `started background subagent job subagent-1` + 含 `{{session:2}}` 的条目 | 保持未绑定 → 走 :448 的 fail-loud 拒绝路径（或直接断言槽位仍为 undefined，按既有用例风格） |
| R4 | 无关文本不绑定 | 任一无启动文本的请求 | 槽位不变，语义同既有用例 |

验收口径：`packages/test-support/llm-replay` 聚焦 vitest 全绿（含 R1-R4）。

## 三、回放行为影响评估（如实）

- **修复本身不改任何已录快照的语义**：llm-replay 的绑定只影响"运行时能否把 `{{session:N}}` 换成正确 live id"，不产生新的模型可见输出；其余 105 个快照场景的绑定路径不变（文本学习只是子会话先于首调绑定时的前置通道，R3 钉死不错绑）。
- **`sdk/subagent-continuable` 场景在修复后的签名变化**：120s 挂起 → 秒级 fail-loud diff（比较点 `normalizeSessionSnapshots`，唯一 delta=classification.md §五所列陈旧面）。这仍是红——**本波门禁据此调整**：该场景必须"快速确定性失败且 diff 面唯一"，不再要求绿（绿被禁区夹具阻断）。
- **完成绿所需的夹具写回=总控配方**（本波不执行）：
  1. 本波修复合并后，keyless：`pnpm run test:snapshot:refresh -t subagent-continuable`（refresh 重放已提交脚本、回写期望输出，写回 §五全部陈旧面）；
  2. 复查 `git diff` 于 `snapshots/sdk/subagent-continuable/`（预期：session.jsonl 文本行、session.1.jsonl request/header 工具描述、两个 sidecar），提交；
  3. `pnpm run test:snapshot -t subagent-continuable` 复跑转绿；全量套件 4 红 → 预期 3 红（image-compaction / both-mode-turn / ptc-turn 维持原归因）。
  - 备选：按 classification.md §五点位手工编辑（逐字：`started subagent {{session:2}}` → `started continuable subagent; SessionID {{session:2}}` 等），效果等价，refresh 更不易漏面。

## 四、key 状况探测记录（不得伪造）

- `DEEPSEEK_API_KEY`：进程环境未设置。
- `D:/dsh-devframe-v14-gap4-lead/.env`、`D:/dsh-devframe/.env`：均不存在。
- 结论：`test:snapshot:record`（需 key）在本宿主 **blocked**；§三配方全程 keyless（replay/refresh 均不读 key），不受阻塞。

## 五、Worker 车道与门禁

- 写域：§一两文件 + `.agents/devframe/v14-gap4/worker/**`（回执与日志）。
- 禁区（零触碰）：`snapshots/**`、`vendor/**`、`packages/experimental/{devframe,agent-evidence,command-goal-binding,shadow-router,project-memory}`、`.agents/devframe/v14/next/**`、主树、其他链 worktree、`D:/dsh-devframe-p-*`。
- 门禁（逐项真实退出码入回执）：
  1. `packages/test-support/llm-replay` 聚焦 vitest 全绿（含 R1-R4）；
  2. 删全部 `*.tsbuildinfo` 后 `pnpm run build` exit 0；
  3. `git diff --check` exit 0；每文件恰一尾随换行；
  4. `pnpm run test:docs` exit 0；
  5. 全量 `pnpm run test:snapshot`：恰 4 failed（image-compaction、both-mode-turn、ptc-turn、subagent-continuable）零新增；其中 subagent-continuable 的新签名=快速失败（场景耗时 ≪120s）且失败面为 session 0 的 tool/result 文本 diff；其余 SDK 子代理场景全绿。
  6. 提交 `--no-verify` + 收据（staged `git diff --cached --check` exit 0、尾随换行核对、触及域零 vendor 路径）。
- 边界：禁创建任何 Agent；禁 push/PR/发布/删除；单 Worker。
