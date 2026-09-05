---
description: "AT3-06 recorded-session 场景草案：推断偏好不自动转 confirmed、同源重标冲突、矛盾 note 并存召回、陈旧可见与授权 supersession 保留旧 note（memory_append / memory_search / memory_read）。"
kind: "acceptance-scenario-draft"
---

# AT3-06 场景草案：信任晋升与矛盾并存

包已在 main 4bc507e332，场景对其当前契约。

映射：`docs/testAndAcceptance.md` Part 3 `AT3-06` / `R3.3`（推断偏好不自动转 confirmed；冲突/陈旧可见；授权 supersession 保留旧 note）。

## 目标

验证信任标签的晋升规则与召回中的矛盾处理：`inferred` 偏好入库后没有任何路径把它变成 `confirmed`（无更新工具、缺 `humanConfirmation` 被拒、同源重标报 `memory_conflict`）；内容矛盾的 note 并存召回、各带标签，服务不做消解；旧 snapshot 的观察以 `potentially_stale` 可见；显式授权 supersession 建新 note、旧 note 文件保留且仅从自动召回排除。

## 前提（宿主集成）

同 AT3-01 草案：三工具需宿主装配进 profile。confirmed 用户偏好的 `humanConfirmation` 由宿主指向真实确认事件引用；`currentSnapshot` 由宿主 spec 提供。

## 计划录制布局

`snapshots/session/memory-trust-promotion-contradiction/`：`snapshot.yml`（`profile: headless`，workspace facts 记录 `workspaceId` 与 `currentSnapshot`）；`session.jsonl` 含全部追加/搜索/读取事件；`workspace.expected/` 与 Vault 断言：被 supersede 的旧 note 文件仍在且逐字节未变。

## Vault 与工作区夹具

服务实例 `workspaceId: ws-trust`，`writeEnabled: true`，`userScopeEnabled: true`（用户偏好子案需要），`currentSnapshot: snap-002`，临时 Vault。

## 剧本（replay 步骤）

1. 推断偏好入库：`scope: 'user'`、`kind: 'preference'`、`assertionStatus: 'inferred'`、稳定 `sourceRef: S1` → `created`；`memory_read` 与 `memory_search` 的结果均 `status: 'inferred'` 原样携带。
2. 晋升探测 A（缺人确认）：同 S1 换 `assertionStatus: 'confirmed'`、无 `humanConfirmation` → `MEMORY_INVALID_REQUEST`（该检查先于 id 派生与文件访问）。
3. 晋升探测 B（同源重标）：同 S1、`confirmed` + 合法 `humanConfirmation` → 同一派生 noteId 上既有 note 的 status 不同 → `memory_conflict`，文件不变；`confirmed` 没有被原地写进旧 note。
4. 合法 confirmed 偏好：新 `sourceRef: S2`、`confirmed` + `humanConfirmation` → `created` 为新 note；旧 inferred note 原样保留，两条偏好并存可召回。
5. 矛盾并存：追加两条 body 相互矛盾、`sourceRef` 不同的 fact note → `memory_search` 同一 query 返回两条 hit，各带自己的 `status`/`source`/`createdAt`/`freshness`，无消解、无去重。
6. 陈旧可见：一条 fact 以 `snapshot: snap-001` 追加 → hit 的 `freshness: 'potentially_stale'`（与 `currentSnapshot: snap-002` 不同）；以 `snapshot: snap-002` 追加对照 note → `freshness: 'current'`。
7. 授权 supersession：新 `sourceRef: S3` 追加更正 fact、`supersedes` 指向步骤 5 其中一条的 noteId → `created`；`memory_search` 原 query 只返回更正 note，被 supersede 的 note 从自动召回排除；旧文件逐字节保留，`memory_read` 旧 id 仍 `found`（read 不做召回过滤）。
8. supersession 边界：`supersedes` 等于自身派生 id → `MEMORY_INVALID_NOTE`；跨命名空间探测——project 命名空间的追加 `supersedes` 指向 user note id → 新 note 照常 `created`，user note 不受任何影响（superseded 集合按命名空间局部生效）。

## 可观察通过标准（对应 AT3-06）

- 无自动晋升：步骤 1–3 后旧 note 的 status 全程 `inferred`，confirmed 只经 S2 的人类确认路径出现，无任何原地改写事件。
- 矛盾与陈旧可见：两条矛盾 note 同 query 并存召回且标签齐全；旧 snapshot note 明确 `potentially_stale`，对照 note `current`。
- 授权 supersession 保留旧 note：更正 note `created`，旧文件零改动且 read 仍可达，仅自动召回排除；自指与跨命名空间探测被拒或不生效。

## 环境与安全

合成内容；临时 Vault 用后清理。

## 开放问题

- `currentSnapshot` 不提供时全部带 snapshot 的 note 为 `potentially_stale`；属主可改为无 snapshot 录制并把断言统一为 `potentially_stale`，二选一并记录在 snapshot.yml。
- 跨命名空间 supersession 的"不生效"是命名空间局部扫描的自然结果（被指 id 不在本命名空间文件集合内），无专门拒绝码；若属主认为需要显式拒绝，走包契约 PR，不混入本录制。
