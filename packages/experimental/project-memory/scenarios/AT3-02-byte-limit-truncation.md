---
description: "AT3-02 recorded-session 场景草案：UTF-8 字节上限、结果/候选截断与整码点裁切（memory_search / memory_read / memory_append）。"
kind: "acceptance-scenario-draft"
---

# AT3-02 场景草案：字节上限与截断

包已在 main 4bc507e332，场景对其当前契约。

映射：`docs/testAndAcceptance.md` Part 3 `AT3-02` / `R3.1`（中英混排 note 超限；输出不破字符；截断显式）。

## 目标

验证全部有界上限按 UTF-8 字节计数生效：单 note 体 8 KiB、返回总量 16 KiB、结果 10 条、候选 200 个、query 2 KiB、excerpt 256 字节；截断与部分覆盖显式上报；CJK/代理对只在整码点裁切。

## 前提（宿主集成）

同 AT3-01 草案：三工具需宿主装配进 profile 后才能录制。上限通过 `resolveMemorySpec` 的 `limits` 覆盖显式注入（宿主边界职责，无隐藏回退）。

## 计划录制布局

`snapshots/session/memory-byte-limit-truncation/`：`snapshot.yml`（`profile: headless`，workspace facts 记录 `workspaceId` 与收紧后的 `limits`）；`session.jsonl` 含预置 Vault 上的全部工具事件；`workspace.expected/` 只覆盖项目工作区。

## Vault 与工作区夹具

服务实例 `workspaceId: ws-utf8`，`writeEnabled: true`，`limits` 用文档默认值，仅两个子案收紧：`maxReturnBytes: 2048`（字节预算子案）；重复步骤用默认 16 KiB 的实例不必另录——预算子案单列一次搜索即可。预置 `devframe-memory/projects/ws-utf8/`（完整可解析 note 文件，回执一并预置或以 `verified: null` 读取）：

- `a-hit-01.md` … `a-hit-12.md`：12 条命中同一 query 的中文+ASCII 混排 note，体 ~1.5–2 KiB（保证 12 > 结果上限 10，且排序在候选窗口前段）。
- `a-budget-01.md` … `a-budget-05.md`：同 query 命中、excerpt 达满宽（256 字节）且 `source` 较长，使单条 hit 的 `JSON.stringify` 序列化字节足够大，在收紧的 `maxReturnBytes: 2048` 下第 3–4 条即触顶。
- `z-filler-01.md` … `z-filler-193.md`：不命中 query 的完整 note，使候选总数 205 > 200，且 `z-filler-193.md` 的体含一个独立短语，排序落在 200 候选窗口之外。
- `cjk-deep.md`：匹配点位于体深处（>600 UTF-16 码元）的中文 note，供 excerpt 裁切验证；另含一段 4 字节 UTF-8（emoji）与代理对文本，验证对齐。
- 上限边界：`exact-8k.md` 通过工具追加体长恰 8192 字节的 note（`>` 判定，恰在限内应成功）。

## 剧本（replay 步骤）

1. `memory_search`（query 命中 `a-hit-*`，默认 limit）→ 命中 12 条中只返回前 10（确定性文件名序），`truncated: true`，`coverageComplete: false`（205 > 200）。
2. 收紧实例重复同一 query → 返回不足 10 条即在 2048 字节预算内触顶，`truncated: true`；`usedBytes` 语义由结果总字节体现（逐 hit JSON 计入）。
3. `memory_search`（query 只命中 `z-filler-193`）→ `hits: []`、`truncated: false`、`coverageComplete: false`：缺失不得读作"任何地方都无此知识"。
4. `memory_append` 体 9 KiB（混排，且内嵌一段凭据形文本）→ `MEMORY_NOTE_TOO_LARGE`（字节判定先于筛查；消息只报字节数，不回显内容），命名空间文件数不变。
5. `memory_search` query 为 700 个中文字符（2100 字节 > 2 KiB）→ `MEMORY_QUERY_TOO_LARGE`；空 query → `MEMORY_INVALID_REQUEST`；`limit: 0` 与 `limit: 11` → `MEMORY_INVALID_REQUEST`（区间检查在扫描前）。
6. `memory_read` `cjk-deep` 的 id → `found`：完整 body 与夹具逐字一致（read 不做 excerpt），`verified` 如有回执为 `true`。hit 的 `excerpt` ≤ 256 字节（含 `…` 标记），裁切边标 `…`，且重编码后无 U+FFFD、无孤立代理对、4 字节字符不被拆开。

## 可观察通过标准（对应 AT3-02）

- 输出停在配置的字节/条数内：结果数 ≤ 10、逐 hit JSON 合计 ≤ 预算、excerpt ≤ 256 字节，全部可从录制结果直接断言。
- 截断显式：`truncated`（结果上限或字节预算）与 `coverageComplete: false`（候选上限）分别出现并按上述子案各触发一次。
- 无破字符：所有 excerpt 与 body 在录制夹具中 UTF-8 有效，CJK 与代理对字符完整。

## 环境与安全

第 4 步内嵌凭据形文本只用于验证字节判定先于筛查，属合成文本；不使用真实凭据。

## 开放问题

- 205 个候选文件的 Vault 夹具较大；若录制产物体积不可接受，属主可改为收紧 `maxCandidateFiles`（例如 5）用 6 个文件达成同一断言，`snapshot.yml` 记录收紧值。
- 回执预置方式（预置回执 vs `verified: null`）影响 read 断言分支，录制前定案。
