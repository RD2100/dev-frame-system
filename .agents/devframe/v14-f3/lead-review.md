# v14-f3 L1 组长审查记录（taskId=v14-f3-proposal）

- 审查对象：L2 Worker 提交 `a573d7609f90d16d4cb8988522ae9fdc57cc6c3c`（分支 codex/v14-f3-w1-semverify，基点 c93b86c43e 未漂移），cherry-pick 入本分支为 `b6895beeec`。
- 审查方式：组长在 D:/dsh-devframe-v14-f3-lead（同一基点）独立亲核下列承重证据，不采信 Worker 转述。

## 独立复核清单

| # | 断言 | 组长亲核 | 结论 |
|---|---|---|---|
| 1 | `NamedEntries.insert` 同名即抛、undo 幂等 | packages/core/scope/src/store.ts:43-54 | 属实 |
| 2 | `ctx.tools.register()` 单一 insert 写路径、`run_code` 保留 | packages/core/tools/src/index.ts:1028-1053（1045-1046） | 属实 |
| 3 | dsh-base 两 shell 行反相平台门控 | packages/bundle/base/cordis.patch.yml:252-258 | 属实 |
| 4 | 行序无加载语义（C 否决论据） | packages/bundle/base/cordis.patch.yml:12-13 | 属实 |
| 5 | headless = dsh-base + dsh-headless | packages/boot/app-boot/src/profile.ts:317-320 | 属实 |
| 6 | 同语料反例"两行都表态" | snapshots/session/pwsh-tool-turn/cordis.snapshot.yml:79-85 | 属实；Worker 标注"83-91 一带"行号偏差约 ±4，以"一带"对冲，实质成立 |
| 7 | patch 装配三层 + completed turn 期望退出码 0 | snapshots/session/headless.snapshot.ts:661-699（666、667-671、696-699） | 属实 |
| 8 | 持久插件 apply→register 链 | packages/shell/tool-pwsh-persistent/src/index.ts:492-512、511、441-442 | 属实 |
| 9 | `evaluate` 注入 `{process:{platform}}` 原语 | packages/bundle/base/tests/base.spec.ts:79-80 | 属实 |
| 10 | 语料 corpus spec 存在且已挂 snapshot 车道 | scripts/session-snapshot-corpus.corpus.ts（9427 字节，引入提交 0033fd4c04）；vitest.snapshot.config.ts:48 | 属实——方案 B 文件清单形状正确（既有文件加用例） |
| 11 | Cordis effect body 立即执行（加载期抛错链） | vendor/cordis/src/fiber.ts:402-410 | 属实 |
| 12 | 重名抛错为测试钉死契约 | packages/core/tools/tests/tools.spec.ts:1984-1996 | 属实（首轮已核） |

复核命中 12/12，无事实错误；1 处行号引用带 ±4 偏差（#6），Worker 已用"一带"表述对冲，不构成事实错误。

## 审查结论

**接受 Worker 三件产出，无需修改。**

- semantics.md：机制链（win32 双活跃行 → 激活期同层同名注册 → `NamedEntries.insert` 抛 → fiber FAILED → `plugin tree failed to load` 非零退出 → 场景红；POSIX 绿因=基座行平台禁用、平台条件式冲突对录制宿主不可见）成立。
- fix-proposal.md：采纳建议（A 场景 composition 补全 + B 语料级守卫成对、C core/tools 替换/幂等否决）与代码事实及 AGENTS.md 纪律（Registrations are effects；Misconfiguration fails loud；行序无加载语义；既有 spec 契约）一致。
- verification-design.md：判别力论证成立——V1（静态语料守卫，任何宿主可跑）对 C 仍红；V2（win32 回放）在 POSIX 无判别力故必须与 V1 成对；C 在 V2 以 header pin 失配形式仍被拒。非 pass-for-all。

## 组长补充意见（供修复波次执行）

1. 方案 A 实施时 `cordis.yml` 与 `cordis.snapshot.yml` 必须同步修改（record/replay 成对），漏改其一会导致录制与回放行为分叉。
2. 方案 B 守卫断言范围限定在"触碰了 shell 行"的 composition，避免过度约束非 shell 场景（Worker 已自我约束，采纳其边界）。
3. A 触碰 `snapshots/**`，按本任务边界（PROPOSAL 不实施、不改快照）本次未实施；其归属为该场景自身（composition owner 规则，headless.snapshot.ts:472-475）。

## 工具行为注记

glob 工具对无通配符精确路径 `scripts/session-snapshot-corpus.corpus.ts` 出现一次假阴性（返回 No files found），以 pwsh `Test-Path`/`Get-ChildItem` 复核为准。存在性核验以文件系统直接探测为准。

reviewedAt：2026-09-06T13:00:38+09:00
