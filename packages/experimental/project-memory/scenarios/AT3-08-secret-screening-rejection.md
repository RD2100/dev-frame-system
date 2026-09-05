---
description: "AT3-08 recorded-session 场景草案：秘密筛查拒绝（规则名不回显内容）、畸形 note 拒绝与瞬态重试耗尽（memory_append）。"
kind: "acceptance-scenario-draft"
---

# AT3-08 场景草案：秘密筛查拒绝

包已在 main 4bc507e332，场景对其当前契约。

映射：`docs/testAndAcceptance.md` Part 3 `AT3-08` / `R3.4`（畸形/敏感内容拒绝且不落原文明文；重试停在配置上界；留下稳定的可恢复候选引用）。

## 目标

验证追加路径的内容门槛与有界重试：已知凭据形 fixture 逐条被筛查规则以 `MEMORY_CONTENT_REJECTED` 拒绝且错误只含规则 id；畸形 note 以 `MEMORY_INVALID_NOTE` / `MEMORY_NOTE_TOO_LARGE` 拒绝；瞬态失败按 `MemoryRetryPolicy` 耗尽后稳定报 `MEMORY_WRITE_FAILED`，故障清除后同 `sourceRef` 重试命中同一 noteId。

## 前提（宿主集成）

同 AT3-01 草案。瞬态故障注入由宿主装配面提供（进程自有的文件层 fault，符合 testAndAcceptance Part 4 前言的 fault-injection 纪律）；重试 backoff 通过 `resolveMemorySpec` 的 `retry` 覆盖为 `maxAttempts: 3, backoffMs: [0, 0]`，使录制确定性且不引入 1s/3s 等待——文档默认值 `[1000, 3000]` 的时序由包行为测试持有，录制只断言尝试次数。

## 计划录制布局

`snapshots/session/memory-secret-screening-rejection/`：`snapshot.yml`（`profile: headless`，workspace facts 记录 `workspaceId` 与 `retry` 覆盖值）；`session.jsonl` 含全部被拒/耗尽/恢复的追加事件；`workspace.expected/` 断言被拒 note 零文件、成功重试恰好一个文件。

## Vault 与工作区夹具

服务实例 `workspaceId: ws-screen`，`writeEnabled: true`，`userScopeEnabled: false`，`retry` 如上覆盖；空命名空间起步（被拒内容不得建目录以外的任何文件——目录可由首次合法追加按需创建，故夹具先以一条合法 note 建立命名空间）。

## 剧本（replay 步骤）

1. 建底：追加一条合法 note（`created`），使命名空间目录存在，后续被拒子案可断言"目录内容无变化"。
2. 凭据形 fixture 逐条追加，全部 `MEMORY_CONTENT_REJECTED`，期望规则 id 逐一为：`private-key-block`（`-----BEGIN RSA PRIVATE KEY-----`）、`deepseek-api-key`（`DEEPSEEK_API_KEY=sk-…` / `sk-` 长 token）、`aws-access-key`（`AKIA` + 16 位）、`github-token`（`ghp_` + ≥20 位）、`slack-token`（`xoxb-…`）、`bearer-token`（`Bearer ` + ≥20 位）、`credential-assignment`（`password = "…"` 形）、`environment-dump`（≥8 行 `KEY=value`）、`control-characters`（含 U+0007）。错误消息只含 `matched rule "<id>"`；所有 fixture 明文不得出现在任何错误、事件或日志行。
3. 顺序边界：一条既超 8 KiB 又含凭据形的 body → `MEMORY_NOTE_TOO_LARGE`（字节判定先于筛查）。
4. 畸形子案：空体/全空白体 → `MEMORY_INVALID_NOTE`；`sourceRef` 空串、含 NUL、超 512 字节 → `MEMORY_INVALID_NOTE`；`supersedes` 等于自身派生 id → `MEMORY_INVALID_NOTE`；`noteId` 非法（大写 hex、`../x`）在 read 路径 → `MEMORY_INVALID_NOTE_ID`。
5. 重试耗尽：宿主 fault 注入使 note create 连续瞬态失败 → 第 3 次尝试后稳定 `MEMORY_WRITE_FAILED`，事件序列恰含 3 次尝试（backoff 为 0）。permanent 故障（EACCES 形）→ 立即 `MEMORY_WRITE_FAILED`，不重试。
6. 恢复引用：fault 清除后以同一 `sourceRef` 重试步骤 5 的追加 → `created`，`noteId` 与派生规则一致（同一 namespace+sourceRef 必得同一 id），即"稳定的可恢复候选引用"；Vault 中该 note 恰一个文件。

## 可观察通过标准（对应 AT3-08）

- 无效/敏感内容被拒且零落盘：步骤 2–4 的每次拒绝后命名空间文件数与步骤 1 相同。
- 不落原文明文：错误消息与 `session.jsonl` 全文不含任何 fixture 凭据串，只含规则 id 与字节数。
- 重试停在配置上界：尝试次数 = `maxAttempts`，permanent 不消耗重试；恢复后引用稳定、恰好一文件。

## 环境与安全

全部凭据形 fixture 为合成形状（明显假值）；不使用真实凭据；临时 Vault 用后清理。

## 开放问题

- fault 注入面在宿主装配层的具体形态（可注入的文件层包装点）尚不存在，录制前由宿主属主提供；包内行为测试已覆盖同类语义，录制只补 assembled-transcript 证据。
- `unpaired-surrogate` 规则无法以 UTF-8 夹具提交（孤立代理对不可编码），留包行为测试持有，录制不含该子案。
