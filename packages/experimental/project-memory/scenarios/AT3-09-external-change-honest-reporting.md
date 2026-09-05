---
description: "AT3-09 recorded-session 场景草案：外部改/伪造/删/移后的 memory_changed / memory_missing 如实上报、内联 digest 不替代会话回执、仅显式确认更正产生新 note（memory_append / memory_search / memory_read）。"
kind: "acceptance-scenario-draft"
---

# AT3-09 场景草案：外部变更如实上报

包已在 main 4bc507e332，场景对其当前契约。

映射：`docs/testAndAcceptance.md` Part 3 `AT3-09` / `R3.2`（外部改/移/删后的变更与缺失如实上报；内联 digest 不替代会话回执；仅显式确认更正产生新 note）。

## 目标

验证服务对外部改动的诚实性：回执确认的 note 被外部编辑或伪造后，read 报 `memory_changed`（展示并标注、不静默召回）、search 排除、原追加重试报 `memory_changed` 不重建；改名/移动/删除后报 `memory_missing`，不跨路径追索、不自动导入；伪造的内联 `bodyDigest` 不能替代会话回执；只有显式确认的更正（新 `sourceRef`）才产生新 note。

## 前提（宿主集成）

同 AT3-01 草案：三工具需宿主装配进 profile。外部改动由宿主在 Vault 内直接操作文件（编辑/改名/删除/移动）——这些操作不是服务 API 的一部分；回执接会话日志，重启后仍可回答 `memory_changed` / `memory_missing`。

## 计划录制布局

`snapshots/session/memory-external-change-honest-reporting/`：`snapshot.yml`（`profile: headless`，workspace facts 记录 `workspaceId`）；`session.jsonl` 含追加、外部改动（宿主操作事件）、read/search 结果事件；`workspace.expected/` 与 Vault 断言：被改/被移文件原样保留、无重建文件。

## Vault 与工作区夹具

服务实例 `workspaceId: ws-honest`，`writeEnabled: true`，`userScopeEnabled: true`，临时 Vault。夹具 note：N1（project fact，`observed`，回执确认）、N2（user 偏好，`confirmed` + `humanConfirmation`，供更正子案）；外部编辑用合法 prose，不用凭据形。

## 剧本（replay 步骤）

1. 建底：追加 N1、N2 → 各 `created`，回执入会话日志；`memory_read` 双双 `found` 且 `verified: true`。
2. 改 body：外部改 N1 的 body（front matter 不动）→ `memory_read` N1 → `memory_changed` 且携带解析出的 note（文件仍可解析）；`memory_search` 原 query → N1 不再出现（召回排除）；以 N1 原请求 `memory_append` 重试 → `memory_changed`（回执在、整文件 digest 与回执不符），文件保持被改状态，不重建、不还原。
3. 伪造内联 digest：外部改 N1 body 并同步改 front matter `bodyDigest` 使文件自洽 → `memory_read` 仍 `memory_changed`（整文件 digest ≠ 会话回执 digest）；自洽的内联 digest 不产生 `found`，更不产生 `verified: true`。
4. 改元数据：外部把 N2 front matter 的 `status` 改为其它合法值（保持文件自洽）→ `memory_read` N2 → `memory_changed`；回执不变——标签提升不能经文件编辑达成。
5. 移动/改名：外部把 N1 文件移出 Vault（录制期临时目录）→ `memory_read` N1 → `memory_missing`；N1 原请求 `memory_append` 重试 → `memory_missing`（回执在、记录路径无文件），不重建；新位置文件原样（无追索、无自动导入回原路径）。
6. 删除：外部删除 N2 文件 → `memory_read` N2 → `memory_missing`；`memory_search` → 无 hit；N2 原请求追加 → `memory_missing` 不重建（confirmed 偏好也不经重试复活）。
7. 显式更正：新 `sourceRef: S3` 追加更正 fact、`supersedes` 指向 N1 → `created`；再以新 `sourceRef: S4` + `humanConfirmation` 追加更正偏好（N2 已删，旧文件保持删除状态）→ `created`；自动召回只出更正 note，N1/N2 的旧文件与被改状态零改动——这是唯一产生新 note 的路径，且偏好更正要求显式确认字段。

## 可观察通过标准（对应 AT3-09）

- 变更与缺失如实上报且不重建：`memory_changed`（改/伪造/元数据）与 `memory_missing`（移/删）按子案出现；每个原请求重试只回 `memory_changed` / `memory_missing`，命名空间文件数不变、无自动导入。
- 内联 digest 不替代会话回执：自洽伪造文件仍 `memory_changed`；`verified: true` 仅出现在整文件与回执一致的读取。
- 仅显式确认更正产生新 note：步骤 7 之前零新 note；更正走新 `sourceRef`（偏好需 `humanConfirmation`），旧文件与其被改状态零改动。

## 环境与安全

外部编辑用合成 prose；移动目标为录制期临时目录；用后清理。

## 开放问题

- 外部改动如何进入录制（宿主工具事件 vs 录制期脚本步骤）及回放时的重放纪律，取决于装配面的录制约定，录制前定案。
- `memory_changed` 携带的 note 展示的是被改内容（含伪造元数据）；包契约只保证标注与排除召回，宿主展示策略是否额外降权由宿主属主定。
