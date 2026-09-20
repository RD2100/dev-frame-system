---
description: "AT3-07 recorded-session 场景草案：Vault 未配置/缺失/只读/中途移除的只读退化——编码任务带警告完成、失败保存不报成功、memory-only 任务保持 failed（memory_search / memory_read / memory_append）。"
kind: "acceptance-scenario-draft"
---

# AT3-07 场景草案：Vault 不可用退化

包已在 main 4bc507e332，场景对其当前契约。

映射：`docs/testAndAcceptance.md` Part 3 `AT3-07` / `R3.4`（Vault 停用/只读/移除；编码任务可带警告完成，失败保存不得报成功）。

## 目标

验证 Vault 各不可用形态下的显式退化：未配置/缺失/非目录的 Vault 对搜索/读取稳定 `MEMORY_UNAVAILABLE`，只读配置下追加稳定 `MEMORY_APPEND_DISABLED`；只读 Vault 读路径不受影响而追加稳定写失败（permanent 不重试）；访问中途移除 Vault 产生显式错误而非伪成功；回执 seam 失败时文件保持未确认、无 `created`。宿主侧断言两种任务形态：编码任务带 memory 警告照常完成，memory-only 任务保持 failed/blocked。

## 前提（宿主集成）

同 AT3-01 草案：三工具需宿主装配进 profile。包对一切 Vault 故障抛 `ProjectMemoryError`——"警告 vs 失败"的分级是宿主装配面策略：录制需宿主把 memory 工具错误转为任务警告事件（编码任务）或任务失败事件（memory-only 任务）。只读与中途移除用真实目录操作或宿主文件层 fault 注入（EACCES 形）；回执 seam 失败用可注错的 `MemoryReceiptStore` 包装。

## 计划录制布局

`snapshots/session/memory-vault-unavailable-degradation/`：`snapshot.yml`（`profile: headless`，workspace facts 记录各子案的 spec 形态与 `retry` 覆盖值）；`session.jsonl` 含错误事件、警告事件与任务结果事件；`workspace.expected/` 断言失败子案零文件产生。

## Vault 与工作区夹具

四个服务实例共用 `workspaceId: ws-vaultfail`，`retry` 覆盖为 `maxAttempts: 3, backoffMs: [0, 0]` 保证确定性：A 未配置（`vaultRoot` 缺省）；B 的 `vaultRoot` 分别指向不存在路径与非目录文件；C 正常临时 Vault + 只读/回执 fault；D 正常临时 Vault + 中途移除。

## 剧本（replay 步骤）

1. 未配置：A 实例 `memory_search`/`memory_read`/`memory_append` 各一次 → 前两者 `MEMORY_UNAVAILABLE`，后者 `MEMORY_APPEND_DISABLED`（shipped 默认关闭写入；服务不创建 Vault 根）。
2. 缺失/非目录：B 实例搜索/读取各一次 → `MEMORY_UNAVAILABLE`（stat 失败与非目录两个分支各一次）；若显式开启写入，追加同样在根检查处报告 `MEMORY_UNAVAILABLE`。
3. 只读 Vault：C 实例先追加一条合法 note（`created`），随后把命名空间目录置为拒绝写入（平台能力允许时用真实只读手段，否则宿主 fault 注入 EACCES 形失败）→ 追加第二条立即 `MEMORY_WRITE_FAILED`（permanent 不消耗重试），既有文件与目录内容不变；同期的 `memory_search`/`memory_read` 正常返回既有 note——只读退化只废写路径。
4. 中途移除：D 实例追加一条合法 note 后，宿主删除 Vault 根 → 再次 `memory_search` → `MEMORY_UNAVAILABLE`；`memory_append` → `MEMORY_UNAVAILABLE`（根检查先失败）或 bounded 重试后 `MEMORY_WRITE_FAILED`（根检查竞态窗口内的目录创建失败），以实际序列为准，两者都是显式错误。
5. 回执 seam 失败：C 实例追加合法 note 且宿主 fault 令 `receipts.write` 抛错 → `MEMORY_RECEIPT_FAILED`，无 `created` 返回；note 文件留在磁盘但保持未确认，后续 `memory_read` 该 id → `found` 且 `verified: null`（无回执），不伪称已确认；seam 恢复后同 `sourceRef` 重试 → `already_exists` 并补交回执（文件本就存在，不重建）。
6. 任务形态断言（宿主装配层）：编码任务（正常编码步骤 + 一次失败的记忆追加）→ 任务完成 + 恰一条 memory 警告事件；memory-only 任务（唯一目标是保存记忆）→ 任务结果 failed/blocked，录制品中不存在把失败保存记为成功的任何事件。

## 可观察通过标准（对应 AT3-07）

- 各不可用形态稳定显式：`MEMORY_UNAVAILABLE` / `MEMORY_APPEND_DISABLED` / `MEMORY_WRITE_FAILED` / `MEMORY_RECEIPT_FAILED` 按子案出现，无隐藏回退、无默认目录重建。
- 失败保存不报成功：步骤 4–5 无 `created` 结果、无成功声明事件，文件层面无覆盖或改写。
- 编码任务可带警告完成：步骤 6 编码任务结果为成功且恰含 memory 警告；memory-only 任务保持 failed/blocked。

## 环境与安全

合成内容；只读/移除只作用于录制期临时 Vault；用后清理。

## 开放问题

- "警告 vs 失败"分级事件的具体类型（宿主任务事件词汇）尚未存在，录制时绑定实际事件类型。
- 步骤 4 的错误码在根检查竞态窗口内二选一（`MEMORY_UNAVAILABLE` vs bounded 重试后 `MEMORY_WRITE_FAILED`），断言绑定"显式错误"性质，录制后把实际序列记入 notes。
