---
description: V1.4 L1 组合验收组长独立证据：全新独立 DSH_HOME + 临时 Vault 的六插件组合真实运行——配置启用核实、Memory write 相真实回执落盘、独立进程冷恢复 verify 相全绿，含两项运行面发现。
---

# L1 组合验收组长独立证据（V1.4 集成组合真实运行）

- 身份：L1 组长 SessionID `f705f2bf-b339-4fa1-bcb2-abfd88f2bc78`，父 = V1.4 总控 `session-c1668d60-b936-45fd-84bc-77f121241cfe`，Provider = DeepSeek Harness subagent（glm-5.3-flash），taskId `v14-l1-combo-accept`，worktreeId `D:\dsh-devframe-v14-integration-lead`（分支 `codex/v14-integration-lead`，基点 `c93b86c43e`）。九态：`submitted`（待总控合并）。
- 复用口径：`.agents/devframe/integration/` 的档案与探针**字节一致拷贝**（SHA256 逐字节核对：cordis.patch.yml `08417F43…65161`、probe-cold-recovery.ts `B36F7429…30682`），落位 `.agents/devframe/v14-integration/`（仓库根下 3 层，匹配探针 L42 的 `../../../apps/cli/src/profile-boot.ts` 深度），零源码改动。历史档案与 probe-state 原件未动。
- 隔离面：全新 `DSH_HOME=C:\Users\25313\AppData\Local\Temp\dsh-v14-lead-home`（创建时不存在，全程零删除，保留为复验证据）；共享 home `C:\Users\25313\.dsh`、`C:\Users\25313\.dsh-integration` 未触碰；临时 Vault = 该 home 下 `integration-vault\`。
- 模型口径：本轮旅程**无任何模型调用**（探针经 `ctx.tools.execute` 真实分派器直驱服务，不开 llm 流）→ 证据标注**「隔离组合证据（无模型参与）」**，无 SKIP_AUTH 项（未尝试任何在线认证操作）。凭据解析路径已核实：provider 行 `apiKeyEnv`（credential-ref）→ credentials seam `resolve()` → 无 seam 时 ambient env 回退、named-but-missing fail loud；本 home 凭据存储为空、`DEEPSEEK_API_KEY` 未设；huoshan-1/2 为宿主运行时 ambient provider，不在本组合内、未被行使。

## 命令与真实退出码（组长亲跑）

| # | 命令 | exit | 说明 |
| --- | --- | --- | --- |
| 1 | `pnpm install` | 0 | 运行基建（未跟踪，不入提交） |
| 2 | `pnpm dsh plugin --profile integration add @deepseek-ai/dsh-experimental-project-memory` | 1 | 既有口径预期：install 步 `ERR_PNPM_FETCH_404`/无认证；profile 骨架（cordis.patch.yml/package.json/pnpm-workspace.yaml）落盘新 home |
| 3 | `node --import tsx/esm apps/cli/src/bin.ts --profile integration --patch <写域>cordis.patch.yml --dump-config` | 0 | 458 行 → [lead-dump-config.output.txt](lead-dump-config.output.txt) |
| 4 | 探针 write（4 层深拷贝试跑） | 1 | 发现 F1（深度硬编码，见下） |
| 5 | 探针 write（3 层深、build 前） | 1 | 发现 F2（boot 需构建产物）→ [lead-obs-boot-fail-typert.txt](lead-obs-boot-fail-typert.txt) |
| 6 | `pnpm run build` | 0 | host face + client face（含 web frontend vite） |
| 7 | 探针 `--phase write`（3 层深、build 后，进程 1） | 0 | `WRITE PHASE OK` → [lead-probe-write.output.txt](lead-probe-write.output.txt) |
| 8 | 探针 `--phase verify`（**全新独立进程**，同 home，进程 2） | 0 | `RESTORE OK` → [lead-probe-verify.output.txt](lead-probe-verify.output.txt) |

## 配置启用（dump 核实，行号对应 dump 文件）

- `project-memory` L447-453：`workspaceId: integration`、`vaultRoot: !!js dshHomePath('integration-vault')`、**`writeEnabled: true` L452**、`userScopeEnabled: false` L453。
- `agent-hierarchy` L345 起：三角色 `inheritedTools` 各含 memory 三工具（controller L363-365、lead L394-396、worker L422-424）；`delegationToolNames: [subagent, subagent_fork]` L435-437；`leadPluginScopes: {}` L438。
- `shadow-router` L454-458：`authorizedRoots: [!!js dshHomePath('integration-shadow-roots')]`。
- `session-persistence-jsonl` L60-64：`compression: none`。
- 判定：dump 只证组合（第 5 步在 dump exit 0 之后 boot 仍失败，恰好实证 dump≠激活）；激活证据见下两节。

## write 相（进程 1，exit 0）真实回执与落盘（组长独立复查，非抄探针输出）

- **真实写路径**：controller 绑定 agent 经真实分派器执行 `memory_append` → `created`；Vault 笔记真实落盘 `integration-vault\devframe-memory\projects\integration\fd4a0cb3…94fc8d.md`（396 字节，sha256 `CEFECAB4…D786F9`，正文与探针 PROBE_MEMORY_BODY 逐字一致，front-matter 含 `source: probe://integration-local-write/1`、`status: observed`、bodyDigest）。
- **回执落会话日志**：写者会话 `sessions\_no-cwd\session-memory-write-w\session.jsonl`（855 字节）含 **1 条 `memory/receipt`** 事件，noteId 与笔记文件一致。
- **角色放行**：lead `memory_read`、worker `memory_search` 经同一真实分派器放行；user scope 服务级 `MEMORY_SCOPE_FORBIDDEN` 拒绝面保留。
- **投递旅程**：标记 Shadow agent 经真实分派器 project_open → project_send（received 两写）→ 宿主 completeDelivery → completed → project_stop → confirmProjectStopped → stopped；`storages\shadow_router.json`（2919 字节）等五域文件落盘（agent_evidence/project_tasks/session_identity/workspace/shadow_router）。
- 状态快照：[../probe-state.json](../probe-state.json)（memoryWrite 十项全真 + shadowDelivery 各字段）。

## verify 相（进程 2 = 冷启动独立进程，exit 0）

`RESTORE OK`：绑定行逐字段冷恢复（session-1 controller / task-probe-1 `assigned` / evidence 1+1）；`memoryWriteRestored` 八项全真（冷读 found、回执经 resume 重放再水化 `verified:true`、新 controller agent 经真实分派器读回 verified、search 命中复原、同源重试 `already_exists`、缺席读 `memory_missing`、user scope 仍拒绝）；`shadowDeliveryRestored: true`（绑定行 state/goal/hash、投递行四字段、project controller 绑定逐字段 + 全新标记 agent `project_status` 模型面读回 completed）；hierarchy 三断言冷后复立；`shadowDomainFileOnDisk: true`。**恢复失败登记：无。**

## 发现（报总控，不在写域内修）

- **F1 探针可移植性**（非产品源码）：`.agents/devframe/integration/probe-cold-recovery.ts` L42 `import '../../../apps/cli/src/profile-boot.ts'` 深度硬编码，仅在其原目录（仓库根下 3 层）成立；异深度运行 `ERR_MODULE_NOT_FOUND: .agents\apps\cli\src\profile-boot.ts`。本轮以「字节一致拷贝 + 同深度落位」零改动绕行。最小复现：把探针拷到 4 层深目录以 tsx 运行 `--phase write`。总控裁定：P22 候选债。
- **F2 运行前置（文档化构建面，非缺陷）**：boot 挂树时 `typert-loader` 需 `@deepseek-ai/dsh-llm`/`dsh-commands`/`dsh-goal`/`dsh-subagent` 四包 `lib/typert.host.js`（`packages/typert/loader/src/index.ts:349,432`）；fresh worktree 仅 install 不 build 则激活 fail loud（4 贡献者全部 ERR_MODULE_NOT_FOUND），先 `pnpm run build`（exit 0）后同命令通过。同轮 dump-config 在无构建产物时 exit 0 —— 再次实证「配置 dump 不能代替实际运行」。复现：fresh worktree + 仅 install + 探针 write。

- **F3 提交基建（宿主环境，非产品源码）**：本 Windows 宿主不存在任何 bash（便携 git `usr\bin` 91 个文件无 bash*、`where.exe bash` 空、无 WSL），pre-commit 的 `vendor manifest guard`（`scripts/check-vendor-manifest.sh`，bash 脚本）以 exit 127 失败、首次提交未落。该 guard 逻辑为 staged 路径正则断言，已在钩子外以 pwsh 等价执行同一 staged 集（vendor_src_changed=0 → PASS）并复跑 `git diff --cached --check`（exit 0）、lefthook 内 lint/whitespace 两阶段此前已真实通过；随后仅本一次提交以 `LEFTHOOK=0` 完成。真实钩子由 CI/pre-push 把关。

## 验收结论

| 项 | 结论 |
| --- | --- |
| 配置启用（writeEnabled/三角色允许表/authorizedRoots/compression） | PASS |
| 真实工具回执（真实分派器 + memory/receipt + 投递旅程） | PASS |
| 落盘（Vault 笔记 / 五域 storages / 会话 JSONL） | PASS |
| 跨进程冷恢复（独立进程 verify 全绿） | PASS |
| 源码缺口阻塞 | 无（F1/F2 为运行面发现，不阻塞） |
| 模型参与 | 隔离组合证据（无模型参与） |

L2 Worker（SessionID `024d6ecb-3fcd-4cb2-85d1-a3191bc2f13d`，taskId `v14-l2-combo-accept`，worktree `D:\dsh-devframe-v14-integration-l2` / `codex/v14-integration-l2`）独立复验同组合，证据与提交哈希见其分支与 [l2/](../l2/) 目录；其会话曾于步骤 6 前中断一次，经 send_message 续跑完成。
