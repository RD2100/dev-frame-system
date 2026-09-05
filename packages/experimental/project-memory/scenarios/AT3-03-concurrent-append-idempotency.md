---
description: "AT3-03 recorded-session 场景草案：8 路并发同源追加恰一 created、幂等重试、冲突不覆盖与中断写排除上报（memory_append / memory_search / memory_read）。"
kind: "acceptance-scenario-draft"
---

# AT3-03 场景草案：并发追加幂等与中断写

包已在 main 4bc507e332，场景对其当前契约。

映射：`docs/testAndAcceptance.md` Part 3 `AT3-03` / `R3.2`（并发同源追加；幂等重试/冲突不覆盖；中断写被排除并上报）。

## 目标

验证追加路径的排他与幂等：8 路并发追加同一 `sourceRef` 恰好产生一个完整 note（1 `created` + 7 `already_exists`）；匹配内容的重试幂等；同派生路径上内容不同的候选报 `memory_conflict` 且从不改写已存在文件；中断（部分写入）的文件报 `incomplete_note`，原样保留待显式修复，并被排除在自动召回之外。

## 前提（宿主集成）

同 AT3-01 草案：三工具需宿主装配进 profile 后才能录制。并发由录制期在单会话内同时发起 8 个 `memory_append` 调用产生；中断写由宿主装配面按 Part 4 前言的 fault-injection 纪律提供（进程自有文件层 fault + 显式中断点），在派生路径留下半写文件。

## 计划录制布局

`snapshots/session/memory-concurrent-append-idempotency/`：`snapshot.yml`（`profile: headless`，workspace facts 记录 `workspaceId`）；`session.jsonl` 含 8 路并发追加事件、重试/冲突/中断子案事件与宿主回执持久化事件（先于 `created` 结果）；`workspace.expected/` 断言命名空间内文件数恰为各子案声明值。

## Vault 与工作区夹具

服务实例 `workspaceId: ws-concurrent`，`writeEnabled: true`，`userScopeEnabled: false`，临时 Vault，空命名空间起步。三个互不占位的 `sourceRef`：S1（并发 + 幂等 + 冲突）、S2（无回执冲突预置）、S3（中断写）；note id 由 `sha256(namespace\0sourceRef)` 确定性派生，宿主可离线预算 S2/S3 的派生路径。

## 剧本（replay 步骤）

1. 8 路并发：8 个同 `scope: 'project'`、同 `sourceRef: S1`、同 `body`、`kind: 'fact'`、`assertionStatus: 'observed'` 的 `memory_append` 同时发起 → 结果集恰含 1 个 `created` 与 7 个 `already_exists`，全部同一 `noteId` 与同一 `relativePath`；命名空间内恰一个文件，receipt store 内该 id 恰一条回执（各路写入 digest 一致，按 noteId 覆盖合并）。
2. 幂等重试：并发结束后以相同请求再追加一次 → `already_exists`，文件与回执不变（回执路径校验 + `sameNoteContent` 全字段相等；`createdAt` 不参与比较）。
3. 冲突不覆盖：`sourceRef: S1` 不变、`body` 换为另一段合法非凭据形文本追加 → `memory_conflict`，返回同一 `noteId`；既有文件逐字节不变，回执不变。
4. 无回执冲突：宿主在 S2 的派生路径预置一个自洽完整 note（front matter `noteId` 等于派生 id、`bodyDigest` 与 body 一致，无回执）后以 S2 + 不同 body 追加 → 仍 `memory_conflict`（无回执时落回既有文件内容比较，不重建）；验证后移除该预置文件。
5. 中断写：宿主在 S3 派生路径留下半写文件（预置截断文件，或 fault 包装在 flush 中途截断——录制选其一）后以 S3 追加 → 服务在稳定窗口（5 × 50 ms）内不把在途写误报为中断，窗口后报 `incomplete_note`；文件原样保留，不被删除、补全或重建。
6. 中断排除与如实上报：`memory_search` 用命中 S3 body 片段的 query → 该文件被跳过（解析失败即候选排除），hit 只含完整 note；`memory_read` S3 的 id → `incomplete_note` 且 `reason` 说明失败点；同 `sourceRef` 重试 → 仍 `incomplete_note`，等待显式修复。

## 可观察通过标准（对应 AT3-03）

- 至多一个完整 note：8 路并发后文件数恰 1、`created` 恰 1，7 路 `already_exists` 与其同 id 同路径。
- 匹配幂等、冲突不覆盖：步骤 2 返回 `already_exists` 且零变更；步骤 3–4 返回 `memory_conflict` 且文件/回执逐字节不变。
- 中断写被排除并上报：`incomplete_note` 出现在 append 与 read 结果中，文件保留待修复，search 不召回，重试不重建。

## 环境与安全

合成内容；临时 Vault 用后清理；中断 fault 只作用于进程自有临时目录。

## 开放问题

- 回放是顺序重放，8 路并发的输赢位次在录制期定格：断言只绑定 "1 `created` + 7 `already_exists`" 的集合性质，不绑定具体调用位次。
- 宿主 fault 注入面（半写文件构造点）尚未存在，录制前由宿主属主提供；包内行为测试已覆盖同类语义，录制只补 assembled-transcript 证据。
