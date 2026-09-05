---
description: "AT3（Obsidian memory，AT3-01…09）验收执行清单：场景草案索引、证据格式与执行纪律。"
kind: "acceptance-scenario-draft"
---

# AT3 runner checklist（project-memory 验收执行清单）

包已在 main 4bc507e332，场景对其当前契约：`packages/experimental/project-memory` 三工具（`memory_search` / `memory_read` / `memory_append`）已合并进 main（merge 4b6a9fe9c1，HEAD 4bc507e332 验证）。本清单服务 `docs/testAndAcceptance.md` Part 3 的执行者：录制/回放前逐项对表，跑完逐项落证据。

## 场景草案索引

草案位于 `packages/experimental/project-memory/scenarios/`（包内草案；正式录制归 `snapshots/session/` 属主）。状态：**drafted** = 场景草案已写；**待起草** = 无草案，执行前先补草案。

| ID | 要求摘要 | 状态 | 草案 |
|---|---|---|---|
| AT3-01 / R3.1 | 授权追加 + 新会话召回带 provenance；他项目 note 不可见；原生日志记录到达模型的上下文（双工作区隔离） | drafted | [AT3-01-workspace-isolation.md](../../../packages/experimental/project-memory/scenarios/AT3-01-workspace-isolation.md) |
| AT3-02 / R3.1 | 中英混排超字节/条数/候选上限；输出不破字符；截断与部分覆盖显式 | drafted | [AT3-02-byte-limit-truncation.md](../../../packages/experimental/project-memory/scenarios/AT3-02-byte-limit-truncation.md) |
| AT3-03 / R3.2 | 并发同源追加；幂等重试/冲突不覆盖；中断写被排除并上报 | 待起草 | — |
| AT3-04 / R3.2 | 穿越探测、越权命名空间 id、symlink/reparse 逃逸；不支持的安全创建使 append 停用而非 shell 回退 | 待起草 | — |
| AT3-05 / R3.3 | note 内嵌指令仍为带标签数据；运行时策略不变；越权操作被拒 | drafted | [AT3-05-trust-label-carry.md](../../../packages/experimental/project-memory/scenarios/AT3-05-trust-label-carry.md) |
| AT3-06 / R3.3 | 推断偏好不自动转 confirmed；冲突/陈旧可见；授权 supersession 保留旧 note | 待起草 | — |
| AT3-07 / R3.4 | Vault 停用/只读/移除；编码任务可带警告完成，失败保存不得报成功 | 待起草 | — |
| AT3-08 / R3.4 | 畸形与凭据形 fixture 拒绝且不落原文明文；重试停在配置上界；稳定可恢复候选引用 | drafted | [AT3-08-secret-screening-rejection.md](../../../packages/experimental/project-memory/scenarios/AT3-08-secret-screening-rejection.md) |
| AT3-09 / R3.2 | 外部改/移/删后的变更与缺失如实上报；内联 digest 不替代会话回执；仅显式确认更正产生新 note | 待起草 | — |

## 执行流程（每个 AT3-0x 一轮）

1. 读对应草案（上表）与 `docs/testAndAcceptance.md` 原条目；草案与原条目冲突时以原条目为准并回改草案。
2. 确认宿主装配面就绪（三工具进 `ctx.tools`、回执接会话日志、召回注入走会话事件）；未就绪时该条目记 `blocked`，不降级为包内单测替代。
3. 授权临时 Vault：AT3-* 属 delivery 表的 Optional memory extension，须用户明确选择 memory 后才执行；Vault 用临时目录，用后清理。
4. 回放：`pnpm run test:snapshot -t <scenario>`（keyless）；录制/刷新期望只由场景属主本地执行并逐 diff 评审（record 需 key）。
5. 落证据（格式见下）并更新本表状态：`passed` / `failed` / `blocked` / `skipped` + 一行原因。

## 证据格式

每条验收记录一行 JSON，追加进 AT3 合并 PR 描述或运行报告（对齐 `.agents/devframe/acceptance-checklist.md` 的证据约定）：

```json
{"item": "AT3-02", "command": "pnpm run test:snapshot -t memory-byte-limit-truncation", "exit": 0, "scenarios": ["memory-byte-limit-truncation"], "commit": "<sha>", "notes": "limits 覆盖值见 snapshot.yml"}
```

## 纪律与红线

- 全部凭据形输入为合成 fixture；任何真实秘密不入 Vault、不入录制、不入错误断言。
- 只跑条目需要的场景，不整跑全库套件；期望输出刷新归属主，评审每个 diff。
- 部分子案通过不折算整条通过；failed/blocked/skipped 的必需条目阻止相应 delivery 声明。
- 红线（hard stop）：权限逃逸、错项目写入、假完成、用户数据丢失/被覆盖、存活的失控写入进程。
- 场景工作不改 `packages/experimental/project-memory/src/`；契约缺口走包的行为测试与修复 PR，不混进验收提交。
- 运行报告字段按 testAndAcceptance.md Delivery and evidence：源提交 + 脏输入快照、profile/policy 版本、平台与存储 provider、模型身份证据或其缺失、验收 ID、精确命令/步骤、退出码、产物路径、评审人、结果、已知缺口。

## 已知开放问题（录制前定案）

- Vault 期望树不属于 `workspace.expected/`：宿主装配面需提供 Vault 比较或独立断言（各草案"开放问题"节）。
- 瞬态故障注入点（AT3-08 步骤 5）依赖宿主文件层 fault 包装，尚未存在。
- 多 `workspaceId` 的录制形态（多次启动 vs 单会话多实例）待宿主装配面定型。
