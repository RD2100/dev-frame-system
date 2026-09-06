---
description: L-Integration Shadow/Memory 本地隔离 profile 配置接入证据：project-memory 本地 writeEnabled 实例、memory 三工具入角色允许表、全新临时根双相探针与 build 门禁。
---

# Memory 本地写启用实例证据（L-Integration 本地配置接入）

- 任务：handoff v1.2「Shadow / Memory 四态与具体生产缺口」中 Memory 行的两个配置面缺口在本地集成实例收口——project-memory 行启用本地 `writeEnabled: true` 实例（本地 vaultRoot，路径明确隔离）、memory 三工具纳入本地实例角色允许表。
- Worktree / 分支 / 基线：`D:\dsh-devframe-p-intlocal` / `p/intlocal` / `fc34223e28`（V1.3 首批四线统一基线；与登记表 integration 批次记录一致）。
- 范围口径：纯配置面（`.agents/devframe/integration/`）+ 探针证据，src 零改动，shipped 默认不变（本 profile 是本地集成实例，非 shipped 栈）。

## 变更清单

| 文件 | 变更 |
| --- | --- |
| `cordis.patch.yml` | project-memory 行 `writeEnabled: false→true`（L148，注释同步 L138-142：写启用本地实例、vaultRoot 为隔离 home 下探针专属目录、user scope 保持关闭）；`roleToolPolicies` 三角色 `inheritedTools` 各加入 `memory_append`/`memory_read`/`memory_search`（controller L52-54、lead L83-85、worker L111-113，保持字母序） |
| `probe-cold-recovery.ts` | `probeMemoryFace` 拆为 `probeMemoryWriteFace`/`probeMemoryVerifyFace`：写相真实写路径走真实分派器（controller 绑定 agent 执行 `memory_append`），lead/worker 角色放行经同一分派器断言，user scope 拒绝面（`MEMORY_SCOPE_FORBIDDEN`）保留；验证相 resume 追加会话 → `agent/created` 钩子折叠重放日志再水化回执 → read `verified: true` → 同源冷重试 `already_exists` |
| `probe-state.json` | write 相重写：新增 `memoryWrite` 记录（noteId / relativePath / sourceRef / appendingSessionId + 十项断言） |
| `memory-local-write-dump.output.txt` | 新证据文件（本次 dump-config 全量输出，448 行） |

## 门禁（组长亲跑，命令与计数）

1. **引导 + dump-config**：全新空临时目录 `%TEMP%\dsh-intlocal-e1` 作 `DSH_HOME` → `pnpm dsh plugin --profile integration add @deepseek-ai/dsh-experimental-project-memory` → install 步 registry 404/无认证 **exit 1**（`ERR_PNPM_FETCH_404`），profile 初始化落盘（`cordis.patch.yml`/`package.json`/`pnpm-workspace.yaml`）= 既有口径预期行为 → `node --import tsx/esm apps/cli/src/bin.ts --profile integration --patch <worktree>\cordis.patch.yml --dump-config` → **exit 0**，448 行。行号引用：`- id: project-memory` 行起 L447，`vaultRoot` L451、**`writeEnabled: true` L452**、`userScopeEnabled: false` L453；`- id: agent-hierarchy` 行起 L345，**memory 三工具入表：controller L363-365、lead L394-396、worker L422-424**。栈形态：无 `integration` 模板 → `dsh plugin add` 以 `DEFAULT_PROFILE_BUNDLES`（dsh-base）初始化，dump 呈 base 层 + 本档案 overlay，base-only。
2. **双相探针**（同一临时根，两次独立进程）：`--phase write` **exit 0**（`WRITE PHASE OK`；`memoryWrite` 十断言全 true——真实写路径断言 = 真实分派器 `memory_append` 回执 `created` + note 文件真实落盘 `devframe-memory/projects/integration/fd4a0cb393…94fc8d.md` + 回执先落 `session-memory-write-w` 会话日志；`memory_search`/`memory_read` 经分派器以 controller 身份命中/verified；lead `memory_read`、worker `memory_search` 经分派器放行；user scope 服务级拒绝面保留）→ `--phase verify` **exit 0**（`RESTORE OK`：`coldReadFound` / `receiptRehydrated`〔resume 持久会话重放日志、对可观察结果轮询等待再水化、read `verified: true`〕/ `dispatcherReadVerified`〔新 controller agent 经真实分派器〕/ `searchHitRestored` / `retryAlreadyExists`〔同源冷重试幂等〕/ `readAbsent` / `userScopeForbidden`；既有 shadow 投递旅程、stop 对照、hierarchy 三断言、绑定行逐字段冷恢复面随本次复跑全绿）。
3. **`pnpm run build`**（工作树全量构建：host face `tsc -b tsconfig.host.json` + tsdown、client face `tsc -b tsconfig.client.json` + tsdown）→ **exit 0**。

## 四态（本任务增量面，只写已证实面）

| 插件 | 源码 | 安装+启用（本地实例） | 运行时验证（真实探针） | 生产可用（缺口保留） |
| --- | --- | --- | --- | --- |
| Memory（`packages/experimental/project-memory`） | ✅（本轮未动） | ✅ 本地 profile 行 `writeEnabled: true` + 隔离 vaultRoot（dump L447-453）；memory 三工具入 controller/lead/worker 角色允许表（dump L363-365/L394-396/L422-424） | ✅ 双相探针全新临时根 0/0：真实分派器写路径落盘、回执落会话日志、冷恢复回执再水化 + `verified: true` 读回、同源重试 `already_exists`、user scope fail-closed | 生产 writeEnabled 实例未启用——真实 Vault 根被真实数据根阻塞；本任务只收口本地实例配置面 |
| Shadow（`packages/experimental/shadow-router`） | ✅（本轮未动） | 无变化（`authorizedRoots` 仍指向隔离 home 下探针专属目录） | ✅ 既有组合面全绿（随本次探针复跑再证：标记/零泄漏/绑定行 write-through/投递旅程/stop 对照/冷恢复逐字段/模型面读回） | markShadow 宿主组合生产调用点不存在（P23/S4 缝）；生产 authorizedRoots 需真实部署配置（被真实数据根阻塞） |

## 缺口登记（范围外，本任务不解决）

- markShadow 宿主组合生产调用点 = P23/S4 缝。
- 生产 authorizedRoots / 真实 Vault 根 = 被真实数据根阻塞。

## F10 合规

探针栈保持 base-only：`dsh plugin add` 引导的临时 home 无 `integration` 模板，即 `DEFAULT_PROFILE_BUNDLES`（dsh-base）单 bundle；探针 `bundlePatches` 只取 dsh-base 层并自带 workspace/worktree-registry 补位行。dump 与探针两个组合中本档案的 project-memory / agent-hierarchy 行均无同 id 重复，未与 shipped headless bundle 行冲突。
