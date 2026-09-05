---
description: L-Integration 集成线的端到端无钥匙验证证据：装配清单、双进程冷恢复探针、recorded-session 回放，含全部命令与输出摘要。
---

# 集成端到端证据（e2e-evidence）

- 工作树：`D:\dsh-devframe-p-integration`（`p/integration`，基线 `cda26762d7` → main `4bc507e332` → main `e3d4d6ad02`，均为 fast-forward）。
- 隔离 home：`C:\Users\25313\.dsh-integration`（本线专用；生产 home `C:\Users\25313\.dsh` 全程未触碰）。
- 无钥匙声明：本环境未设置 `DEEPSEEK_API_KEY`；以下全部验证走 `DSH_SNAPSHOT=replay` recorded-session 回放与真实服务调用，无任何伪造输出；真实模型调用的唤醒条件见文末。
- 插件面构成：`packages/bundle/base` + `packages/bundle/headless` 两 bundle 层，叠加本线档案 `.agents/devframe/integration/cordis.patch.yml`（8 个 insert 行 + 1 个 id-targeted restate）。
- 第二轮（main `e3d4d6ad02`）：project-memory 三切片（S1 工具装配 / S2 回执落日志 / S3 JSDoc，merge `fb1519cd19`）已具备插件形态，本线以只读装配纳入 profile 并完成组合重验（1–3 节均为重验后结果）。

## 1. 装配验证（dump-config，exit 0）

命令（工作树根执行）：

```powershell
$env:DSH_HOME='C:\Users\25313\.dsh-integration'
pnpm dsh --profile integration --patch D:\dsh-devframe-p-integration\.agents\devframe\integration\cordis.patch.yml --dump-config
```

- 退出码 0，无 "not found" 警告；完整组合树落盘于 [dump-config.output.txt](dump-config.output.txt)（456 行）。
- 装载清单（patch 层段，行号对应 dump 文件）：
  - `workspace` + `worktree-registry`（insert；base 的 tool-worktree 硬注入这两个服务，自定义 profile 无安装态 web-app 层，须显式补齐）
  - `session-identity`（`@deepseek-ai/dsh-experimental-session-identity`）
  - `agent-hierarchy`（含 `roleToolPolicies` 三态 × 26 工具名、`delegationToolNames: [subagent, subagent_fork]`、`leadPluginScopes: {}`）
  - `project-controller`（含 `maxActiveTasks: 2`）
  - `agent-evidence`、`agent-reliability`
  - `project-memory`（第二轮新增，dump 第 460 行：`workspaceId: integration`、`vaultRoot: !!js dshHomePath('integration-vault')`、`writeEnabled: false`、`userScopeEnabled: false`——只读装配）
  - `session-persistence-jsonl` restate（`compression: none`；sessions root 单一编码为 fail-loud 约束，集成线统一未压缩 JSONL）
- 判定：装配级通过。dump-config 只证明组合，不证明激活；激活证据见第 2、3 节。

## 2. 双进程冷恢复探针（重启恢复，exit 0 × 2）

探针：[probe-cold-recovery.ts](probe-cold-recovery.ts)。同一组合（dsh-base + 集成档案层；滤除 headless 应用面因探针不是一次性任务运行），分两次真实进程执行：

```powershell
$env:DSH_HOME='C:\Users\25313\.dsh-integration'
pnpm exec tsx .agents/devframe/integration/probe-cold-recovery.ts --phase write
pnpm exec tsx .agents/devframe/integration/probe-cold-recovery.ts --phase verify
```

write 相（进程 1，exit 0）真实服务调用路径：

| 服务 | 调用 | 结果 |
| --- | --- | --- |
| ctx.agentBindings（session-identity） | `createBoundSession({cwd, role:'controller'})` | 原生 Session `session-1` 创建 + 绑定行落盘 |
| ctx.projectController | `startProject()` → `createTask(task-probe-1)` → `assign(...)` | `admission_open` / 任务 `assigned` |
| ctx.agentEvidence | `recordTaskGoalBinding(...)` + `recordVerification(...)` | 2 条回执落盘 |
| ctx.agentReliability | `openAdmission(...)` + `assertAdmitted(...)` | 准入切断预检通过（进程内态） |
| ctx.agentHierarchy | 挂载即校验（三态守卫安装；load 期无孤儿工具名报错） | 激活成功 |
| ctx.projectMemory + ctx.tools（project-memory，第二轮） | `tools.get('memory_search'/'memory_read'/'memory_append')` 均非 undefined；`search({scope:'project',query:'probe'})` 扫真实 Vault；`read` 缺席 note id → `memory_missing`；`append` 被拒 | 三工具注册 ✅ / 搜索覆盖完整 ✅ / 读路径真实 ✅ / 只读拒绝 ✅（`MEMORY_APPEND_DISABLED`） |

探针重跑前须清 `storages\`、`sessions\`、`integration-vault\` 与 probe-state.json（本轮曾因遗留 storages 得到预期的 `PROJECT_CONTROLLER_TASK_EXISTS`——防重面再次实测，非故障）。

write 相后域表落盘实测（`C:\Users\25313\.dsh-integration\storages\`）：
`agent_evidence.json`、`project_tasks.json`、`session_identity.json`、`workspace.json`；绑定会话 JSONL 落盘于 `sessions\--C-...-probe-*\session-1\session.jsonl`。状态快照：[probe-state.json](probe-state.json)（含 memory 四项断言结果）。

verify 相（进程 2 = 冷重启，exit 0）：

```
RESTORE OK {"sessionId":"session-1","role":"controller","taskState":"assigned","bindings":1,"verifications":1,"memoryToolsRegistered":true,"memorySearchCoverageComplete":true,"memoryReadAbsent":true,"memoryAppendDenied":true}
```

三个持久化域（session_identity / project_tasks / agent_evidence）跨进程逐行恢复一致；project-memory 只读面在冷启动后重新断言全部成立（工具注册 / 搜索覆盖 / 读路径 / 写拒绝）。**恢复失败登记：无。**

## 3. recorded-session 无钥匙回放（真实启动 + 真实工具调用，exit 0）

按 docs/testing.md 快照路线（shipped profiles + `DSH_SNAPSHOT=replay`），复用 `snapshots/session/pwsh-tool-turn` 录制脚本（模型响应回放，工具真执行）：

```powershell
$env:DSH_HOME='C:\Users\25313\.dsh-integration'
$env:DSH_SNAPSHOT='replay'
$env:DSH_SNAPSHOT_FILE='D:\dsh-devframe-p-integration\snapshots\session\pwsh-tool-turn\session.jsonl'
$env:DSH_SNAPSHOT_PROVIDER='deepseek-official'; $env:DSH_SNAPSHOT_MODEL='deepseek-v4-pro'
$env:DSH_PERMISSION_MODE='danger-full-access'; $env:DSH_TELEMETRY_DISABLED='1'
pnpm dsh --profile integration `
  --patch D:\dsh-devframe-p-integration\.agents\devframe\integration\cordis.patch.yml `
  --patch D:\dsh-devframe-p-integration\snapshots\session\text-turn\cordis.yml `
  --patch D:\dsh-devframe-p-integration\snapshots\session\pwsh-tool-turn\cordis.snapshot.yml `
  --patch D:\dsh-devframe-p-integration\snapshots\session\text-turn\model.cordis.yml `
  "Use the pwsh tool to run exactly: [Console]::Out.Write('PWSH_OK'). Then reply with the single word DONE and stop."
```

- 退出码 0；stderr 摘要（完整输出 [e2e-replay.output.txt](e2e-replay.output.txt)）：
  - `dsh: reasoning: The user wants me to run a PowerShell command…`
  - `dsh: reasoning: The command executed successfully and printed "PWSH_OK". …`
  - 最终助手消息：`DONE`
- 持久化会话日志（`sessions\--D-dsh-devframe-p-integration--\session-1cd14fe4-…\session.jsonl`）关键事件：
  - `tool/call` → `{"name":"pwsh","arguments":"{\"command\": \"[Console]::Out.Write('PWSH_OK')\", …}"}`
  - `tool/result` → `{"type":"text","text":"PWSH_OK"},"isError":false`（真实 pwsh 进程执行，非回放文本）
  - `assistant/message`（step 2）→ `DONE`；`turn/end` reason `completed`
- 即：真实 profile 启动 → 八行集成插件装配激活（含 project-memory 只读装配）→ 至少一条工具调用路径（pwsh）全绿，无钥匙。第二轮重验（main `e3d4d6ad02` 组合）同命令同结果（输出逐字节同前：推理两段 + `DONE`，exit 0）。

## 4. 过程中登记的失败（均已定位闭环，非遗留）

| # | 现象 | 根因 | 处置 |
| --- | --- | --- | --- |
| F1 | patch 行 "entry not found" 警告 ×5 | 新增行误写为顶层 id-targeted 替换 | 改为 `- insert:` 块（对齐 agent-team-profile 先例） |
| F2 | `typert-loader: 4 contributor(s) failed … lib/typert.host.js` 缺失 | 聚合构建在 host tsc 阶段失败，tsdown 未运行（见 F5） | `pnpm exec tsdown --env.DSH_BUILD_FACE host` 定向补产（exit 0） |
| F3 | `dsh-tool-worktree pending (workspaceRegistry, worktreeRegistry)` | 该服务仅由安装态归一化追加的 web-app bundle 提供，自定义 profile 不携带 | 档案层显式 insert `workspace` + `worktree-registry` 两行 |
| F4 | `duplicate loader entry id: session-persistence-jsonl` | 对 base 已有行在 insert 块内重复插入 | 移出为顶层 id-targeted restate |
| F5 | 聚合 `pnpm run build` exit 1（host tsc） | **上游债（已处置）**：P02/P06 合并后 host 聚合 tsc 首跑，`agent-hierarchy/tests/guard.spec.ts` 与 `agent-reliability/tests/service.spec.ts` 测试类型错误（branded 类型面）；与登记册"P02 已知风险：host 聚合 tsc 未跑"吻合 | 已通报总控；上游经 p/foundation-fix（`56acefd984`）修复 branded 工厂与 stop 桩，`e3d4d6ad02` 记录 build validation；本线未重跑聚合构建（不在本轮任务面） |
| F6 | `plugin-package-inventory-deepseek: cannot resolve "@deepseek-ai/dsh-llm-replay"` | 回放插件包不在 profile resolver manifest | profile package.json 增补该依赖 + node_modules junction |
| F7 | `session artifact … .jsonl.zstd … compression "none"` fail-loud | 探针默认 zstd 与回放组合 none 混用同一 sessions root | 档案层统一 restate `compression: none`（属 F4 同文件） |

## 5. 真实模型调用（SKIP_AUTH 登记）

- 本环境无 `DEEPSEEK_API_KEY`（`$env:DEEPSEEK_API_KEY` 为空，根目录无 `.env`）。第 3 节的模型轮次为录制回放，工具执行与持久化均为真实路径。
- **唤醒条件（受控凭据）**：在隔离会话环境中注入 `DEEPSEEK_API_KEY`（或等效凭据存储）后，重跑第 3 节同一命令、去掉 `DSH_SNAPSHOT*` 三个环境变量，即可完成真实模型轮次验证；本线未执行、不伪造。
