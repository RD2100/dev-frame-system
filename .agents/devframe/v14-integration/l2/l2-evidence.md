# V1.4 六插件集成组合 L2 验收证据（taskId: v14-l2-combo-accept）

- Worker SessionID: `024d6ecb-3fcd-4cb2-85d1-a3191bc2f13d`；父 Agent（L1 组长）: `f705f2bf-b339-4fa1-bcb2-abfd88f2bc78`；Provider: DeepSeek Harness 内置 subagent（模型 glm-5.3-flash）
- worktreeId: `D:\dsh-devframe-v14-integration-l2`（分支 `codex/v14-integration-l2`，基点 c93b86c43e）；唯一写域 `.agents/devframe/v14-integration/**`
- 证据性质：**隔离组合证据（无模型参与）** —— 探针 boot 基座组合（过滤 headless app 面），只驱动真实工具/真实分派器/落盘域；全程零 LLM 请求、零凭据解析，不冒充真实模型旅程。
- 环境：node v24.19.0、pnpm 11.19.0、Windows；独立全新 `DSH_HOME=C:\Users\25313\AppData\Local\Temp\dsh-v14-l2-home`（开工时不存在，由引导命令创建，全程原样保留供总控复验）。

## 一、验收结论表

| 验收项 | 结论 | 证据 |
| --- | --- | --- |
| 配置启用（dump-config exit 0，六插件行逐项核验） | PASS | 证据一（L59-L458 行号核验） |
| 真实工具回执（write 相 exit 0 + WRITE PHASE OK，真实分派器 memory/receipt） | PASS | 证据二 + 证据四 |
| 落盘（vault 笔记 / storages 五文件 / probe-state 全真） | PASS | 证据四（独立复核，非抄探针输出） |
| 跨进程冷恢复（verify 相全新独立进程 exit 0 + RESTORE OK） | PASS | 证据三 |
| 在线认证项 | 无此类项（SKIP_AUTH 集为空，逐项核实凭据解析路径后确认本轮零在线认证项） | — |

九态任务状态：**completed**。

## 二、命令与真实退出码

| # | 命令 | 退出码 | 说明 |
| --- | --- | --- | --- |
| 1 | `pnpm install`（worktree 根） | 0 | Done in 23.8s；两条 bin WARN 为未构建产物所致 |
| 2 | 拷贝 cordis.patch.yml / probe-cold-recovery.ts 至 `.agents/devframe/v14-integration/` + 两侧 sha256 | 0 | yml `08417F43…`、ts `B36F7429…` 原件=拷贝件，字节一致复用 |
| 3 | `Test-Path …\dsh-v14-l2-home`（全新性核验） | — | False（不存在）；总控纠正①后删除类指令作废，本轮从未删除任何文件 |
| 4 | `pnpm dsh plugin --profile integration add @deepseek-ai/dsh-experimental-project-memory` | 1 | 既有口径预期：ERR_PNPM_FETCH_404；骨架三文件落盘（217B/208B/61B），不计门禁失败 |
| 5 | 4 层深位置探针复现（`…\l2\probe-cold-recovery.ts --phase write`） | 1 | 观察项 F1：ERR_MODULE_NOT_FOUND，导入期失败零副作用，stderr 留证 |
| 6 | `pnpm run build`（worktree 根） | 0 | typert-loader 前置（dsh-llm/dsh-commands/dsh-goal/dsh-subagent 的 lib/typert.host.js）；220 client 产物；不入提交 |
| 7 | `node --import tsx/esm apps/cli/src/bin.ts --profile integration --patch <写域拷贝> --dump-config` | 0 | 证据一落盘 14186B |
| 8 | `pnpm exec tsx .agents/devframe/v14-integration/probe-cold-recovery.ts --phase write`（进程 1） | 0 | 证据二；stdout 含 `WRITE PHASE OK`；stderr 0B |
| 9 | `pnpm exec tsx .agents/devframe/v14-integration/probe-cold-recovery.ts --phase verify`（进程 2 = 全新独立 pwsh 进程，同一 home） | 0 | 证据三；stdout 含 `RESTORE OK`；stderr 0B |
| 10 | 独立落盘核实（vault/会话日志/storages/probe-state 解析） | 0 | 结果见第四节 |
| 11 | `git add .agents/devframe/v14-integration/` + `git diff --cached --check` + commit | 0 | 提交前 status 仅写域未跟踪目录；提交哈希见 l2-run-manifest.json `commit` 字段与本节下方补记 |

## 三、关键输出摘录

证据一（dump-config，`l2/l2-dump-config.output.txt`，exit 0）行号核验：

- L59 挂载行 `# == @deepseek-ai/dsh-base, patched by …\v14-integration\cordis.patch.yml`
- L60-L64 session-persistence-jsonl restate：`compression: none`（L64）
- L343 session-identity；L345-L438 agent-hierarchy：controller `memory_append/memory_read/memory_search`（L363-365）、lead（L394-396）、worker（L422-424）；`delegationToolNames: [subagent, subagent_fork]`（L435-437）；`leadPluginScopes: {}`（L438）
- L439-L442 project-controller（maxActiveTasks: 2）；L443 agent-evidence；L445 agent-reliability
- L447-L453 project-memory：`workspaceId: integration`（L450）、`vaultRoot: !!js dshHomePath('integration-vault')`（L451）、`writeEnabled: true`（L452）、`userScopeEnabled: false`（L453）
- L454-L458 shadow-router：`authorizedRoots: [!!js dshHomePath('integration-shadow-roots')]`（L457-458）

证据二（write 相 stdout 首行，`l2/l2-probe-write.output.txt`）：

```
WRITE PHASE OK {"sessionId":"session-1","bindingRole":"controller","lifecycleState":"admission_open","taskState":"assigned","sessionLogExists":true,"memoryWrite":{"noteId":"fd4a0cb3932478ae5a57fd5a84c1ce442c52d7ede4a50b5b552ab1e07994fc8d",…十布尔全 true…},"shadowToolsScopeIsolated":true,"shadowCallerForbidden":true,…,"shadowDelivery":{"workspaceId":"59bd63d1-eeeb-444a-abb5-897dc48c4a62",…,"goalId":"probe-goal-w","acceptanceHash":"probe-hash-w"}}
```

证据三（verify 相 stdout 末行，`l2/l2-probe-verify.output.txt`）：

```
RESTORE OK {"sessionId":"session-1","role":"controller","taskState":"assigned","bindings":1,"verifications":1,"memoryWriteRestored":{…八布尔全 true…},"shadowToolsScopeIsolated":true,"shadowCallerForbidden":true,"shadowDomainFileOnDisk":true,"hierarchyControllerReadAllowed":true,"hierarchyLeadDelegationDenied":true,"hierarchyUnboundControlledDenied":true,"shadowCompMarkedScopeSeesTools":true,"shadowCompUnmarkedScopeClean":true,"shadowCompBindingRowPersisted":true,"shadowDeliveryRestored":true}
```

## 四、磁盘回执清单（独立复核）

1. **Vault 笔记**：`<home>\integration-vault\devframe-memory\projects\integration\fd4a0cb3932478ae5a57fd5a84c1ce442c52d7ede4a50b5b552ab1e07994fc8d.md` 存在，396 字节，sha256 `4301D24E8035A9F74B7A765F9F4A6E247CEABBFCE19B890458101D9DFBEAB48A`；正文与探针 PROBE_MEMORY_BODY 逐字一致（bodyMatch=True）；frontmatter `source: probe://integration-local-write/1`。
2. **writeEnabled 真实写路径回执**：`<home>\sessions\_no-cwd\session-memory-write-w\session.jsonl` 共 6 行，L5 为 `type:memory/receipt` 事件（noteId、relativePath、digest、recordedAt）；grep noteId 命中 1 行、source_ref 字面量命中 0 行（按设计回执记 digest 而非 source_ref，后者存于笔记 frontmatter，已在盘核实）；回执 digest `sha256:4301d24e…` 与笔记文件实测 sha256 跨证一致。
3. **storages 五文件**：`session_identity.json` 2696B、`project_tasks.json` 458B、`agent_evidence.json` 1076B、`workspace.json` 593B、`shadow_router.json` 2915B，全部存在。
4. **probe-state.json**（写域拷贝件，1504B）：memoryWrite 十布尔断言 10/10 全 true；shadowDelivery 七字段（workspaceId/controllerSessionId/messageId/receivedAt/completedAt/goalId/acceptanceHash）全在册；sessionLogExists=true。
5. **shadow roots**：`<home>\integration-shadow-roots\delivery-project-w` 存在；writer/hier/shadow 各探针会话目录在 sessions 树齐全。

## 五、观察项（非缺口）

- **F1 探针放置深度敏感性**：probe-cold-recovery.ts 第 42 行 `import '../../../apps/cli/src/profile-boot.ts'` 只在仓库根下 3 层成立；组长先实测踩到 4 层深 ERR_MODULE_NOT_FOUND（解析到 `.agents\apps\cli\src\profile-boot.ts`），本 Worker 随后首手复现（exit 1，stderr 完整留证 `l2/l2-depth-sensitivity-repro.txt`）。处置：字节一致拷贝上移至 `.agents/devframe/v14-integration/`（3 层）运行，探针未改一字。定性：探针观察项，非产品源码缺口。
- **O2 shadow_router 介质文件时序**：write 相 `shadowDomainFileOnDisk=false`、verify 相 `true`，与探针头部「空域首次写穿透才发布介质文件」的文档一致。
- **O3 回执编码**：`memory/receipt` 事件记录 noteId/digest/relativePath，source_ref 存于笔记 frontmatter；digest 与盘上笔记 sha256 跨证一致。

## 六、缺口小节

无（源码缺口列表为空；全部命令与断言按预期通过）。

## 七、SKIP_AUTH 与模型口径

记 SKIP_AUTH 前逐项核实凭据解析路径：dump-config、write 相、verify 相均无模型调用，亦不读 settings.yaml provider apiKeyEnv 或 DSH 凭据存储；本轮验收项中不存在在线认证项，SKIP_AUTH 集为空。`DEEPSEEK_API_KEY` 缺失对全部步骤零影响；huoshan-1/huoshan-2 不在本轮范围、未被触发。

## 八、总控纠正应用与边界声明

- 纠偏①（拷贝 3 层深）、纠偏②（pnpm run build 前置）已应用；总控纠正①②③④（禁删、异常只记录、模型口径）已应用并记录于 l2-run-manifest.json `correctionsApplied`。
- 未触碰 `D:\dsh-devframe-v14-integration-lead`：本会话全部命令与文件操作仅涉及 `D:\dsh-devframe-v14-integration-l2`、`C:\Users\25313\AppData\Local\Temp\dsh-v14-l2-home` 与 `%TEMP%` 临时目录；组长树 `controller-write-probe.txt` 消失与本 Worker 无关。
- 复验指引：DSH_HOME 已原样保留（`C:\Users\25313\AppData\Local\Temp\dsh-v14-l2-home`）；如需重跑，清空动作（home 内 storages\sessions\integration-vault\ 与写域 probe-state.json）由复验方自行执行，本 Worker 不做任何删除。
