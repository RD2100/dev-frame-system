---
description: 项目总控 v1.2 交接快照（2026-09-06）：主树状态、双插件四态、在途链与剩余任务边界。
---

# 项目总控交接 — 2026-09-06

[English](dsh-controller-v1.2-handoff-2026-09-06.md) | 中文

## 交接状态：交接准备中

旧总控仍持有唯一合并权与新派发权，直至本文"交接闸门"条件全部满足。在途链收口后由旧总控更新本文"在途链"节的最终 SHA 与验收结果，然后停新派发、停合并，交棒才生效。接任者激活前不得宣称已完成交接。

## 已作废结论（以最新用户指令为准）

登记表（`.agents/devframe/pluginized-round-registry.md`）开头部分存在过时状态与并发限制表述，以下结论**作废**：

- "并发上限 2/5 条"——用户已明确授权：并行数量不设固定上限，按文件所有者、冲突风险与实测 API 容量调度，可常态超过 5。
- "huoshan-1 退避/huoshan-2 独占"之类的车道假设——huoshan-1/2 均可常态承接不同任务；车道归属只能由会话持久化 JSON 证实，禁止按假设标注。
- "常规裁定需挂起等用户授权"——用户已授权：与主线一致、可验证且可回滚的开发/测试/集成/配置/验收裁定默认直接执行。仍需明确授权的只剩：W4 真实任务、生产部署面决策、对外发布。
- "40 轮检查规则调整/8 分钟节奏为项目参数"——40 轮规则维持原样；8 分钟节奏属外部检查自动化，非 DSH 项目配置。

## 主树快照

| 项 | 值 |
| --- | --- |
| 快照时间 | 2026-09-06 08:30 前后（本机时区） |
| HEAD | `c1d9da130e`（交接文档提交前，登记表为准） |
| 工作树 | 干净；用户未提交文件保持原样不动 |
| 受保护项 | `AGENTS.md`、`docs/working/devframe-qa-2026-09-04.*`、`stash@{0}`（用户恢复快照）——不提交、不还原、不 push |
| 权威门禁基线 | build exit 0（220 artifacts）；experimental+extensions sweep 130 文件 1256P+1S；agent-hierarchy 40/40；gen-cordis-catalog 0；test:docs 15/15；verify-cordis-config 133；verify-package-invariants 39；快照抽样唯一红=B 族已知根（见下） |

## 双插件四态与最短证据路径

四态口径：源码就绪 / profile 安装+启用 / 运行时验证（组合级）/ 生产可用。Shadow 与 Memory 均属必交范围，前三态已达成，生产可用为部署决策面（非代码缺口）。

| 插件 | 源码 | 安装+启用 | 运行时验证 | 生产可用 | 最短证据路径 |
| --- | --- | --- | --- | --- | --- |
| Shadow（`packages/experimental/shadow-router`） | ✅（含 completeDelivery 停止守卫） | ✅（bundle 行+manifest 声明） | ✅（包级 26P+1S；组合级 markShadow/投递旅程/stop 对照/crash-window 全链） | =部署决策（真实授权根+宿主标记策略） | `.agents/devframe/p22/shadow-delivery-flow-evidence.md`、`s6-evidence.md`、登记表 integration-3/4、shadowflow、shadowguard 条目 |
| Memory（`packages/experimental/project-memory`） | ✅ | ✅（集成 profile 行） | ✅（组合级三工具面+回执再水化 agent 侧+冷恢复） | =部署决策（writeEnabled+角色允许表） | `.agents/devframe/p22/memory-rehydration-evidence.md`、登记表 integration-1/2 条目 |

组合级复跑命令：设 `DSH_HOME=C:\Users\25313\.dsh-integration`，整树清盘 `sessions/storages/integration-vault` 后 `pnpm exec tsx .agents/devframe/integration/probe-cold-recovery.ts --phase write` 再 `--phase verify`，期望双 0。

## 在途链（交接时唯一）

| 项 | 值 |
| --- | --- |
| 任务 | `p/fprecompute`：sourceFingerprint 重算引擎（AT1-05 变体 5 src 波），设计先行+裁定请求 |
| 组长 SessionID | `55979618-6bd7-4bc7-badc-8a3b13079158`（L-Foundation） |
| Worker | 组长自派一次性前台 subagent（SessionID 以组长会话记录为准，接任者向组长索要，不得假设） |
| Worktree / 分支 / 基点 | `D:\dsh-devframe-p-foundation`，分支 `p/fprecompute`，基点 `526e773b23` |
| Provider | 以会话持久化 JSON 为准（本会话已核对的 L-Foundation 历史路由=huoshan-2；当前 Worker 未复核——接任者核对 JSON 后再标注，禁止假设） |
| 产物状态 | 交接时无提交；工作树已落 `packages/experimental/devframe/src/source-fingerprint.ts` 与 `tests/source-fingerprint.spec.ts`（实施中，文件秒级新鲜） |
| 恢复点 | 若组长会话中断：读工作树文件状态续起（设计文档→引擎+用例→门禁），不重做已落盘部分 |
| 验收门禁 | 涉及包 vitest+包 tsc+`pnpm run build`+verify-export-jsdoc+`git diff --cached --check`+commit --no-verify（src/test/docs 分提交） |
| 裁定请求项 | 引擎进 StartGoalRequest 绑定流程还是独立 verify 面——旧总控批复前只落计算引擎与用例，比对面不动 |

## 剩余任务（文件域/依赖/验收/并行性）

| 任务 | 文件域 | 依赖 | 验收 | 可并行 |
| --- | --- | --- | --- | --- |
| fprecompute 比对面 | `devframe/src`（StartGoalRequest/resolveResultBinding 邻域） | 旧总控批复裁定请求 | 同上门禁+真实 git fixture 用例 | 否（同链） |
| required-checks 模型（产品+src） | devframe 配置面+evidence 比对面 | fprecompute 收口（同 owner 串行）+设计文档先行 | host build 口径+正反用例 | 否（同 owner） |
| P05 残余缺口②③ | `agent-evidence`/`devframe` | ①④已闭环（p05harden `3a18ca5d61`）；②③设计先行 | 同上 | 与①④无冲突时可并行派其他 owner |
| P23/S4 生产组合接线 | EvidenceReviewerDirectory 生产实现→project_review | P23 波启动 | 组合级探针扩展 | 待 P23 |
| AT1-03/AT4 真实旅程 | agent-reliability/hierarchy 测试 | 模型/进程注入波授权 | 包 vitest+host build | 进程注入面（AT4-02/03/06）无模型依赖，可先派 |
| B 族快照红（88F 唯一根） | `base/cordis.patch.yml` L252-254+minimal preset L36-38 | 产品裁定三案（参数化/win32 skip/取消门控） | test:snapshot lib 模式 delta | 待裁定 |
| W4 真实任务+AT1-11 | 全仓 | 用户明确授权 | 按任务书 | 待授权 |
| 部署决策面 | cordis.yml 部署实例 | 用户部署波 | 组合探针+dump | 待授权 |

首批执行建议：等 fprecompute 结算并收口 → 同 owner 串行派 required-checks 设计先行；同时可向 L-Hierarchy 或 L-Verify 派 AT4 进程注入面设计（不同 owner、零文件冲突）。

## 交接闸门

1. 在途链交付 → 旧总控亲验（真实提交/产物/门禁/会话 JSON）→ 合并主树 → 更新本文"在途链"节为最终 SHA 与验收结果。
2. 旧总控停止一切新派发与合并（登记表补最后一条）。
3. 接任者核对：主树 HEAD、登记表末条、本文四态与在途节——三者一致后取得唯一控制权。
4. 跨会话无法安全接收旧子链结果时：旧总控先收口再交棒，不阻塞 Worker；接任者不得重建、打断或重复派发在飞链。
5. 用户未提交文件与 stash 在交接全过程保持不动；不 push、不建 PR、不发布、不删除。

## 守恒规则（接任者必守）

三层拓扑（总控→组长→Worker，Worker 不创建 Agent）；组长与总控独立 Worktree；总控唯一合并主树；无 idle 空转；SessionID/Agent/Worktree/任务/结果持久化；车道与 Provider 只按持久化 JSON 标注，无静默路由、无不确定调用的盲重试（同命令单次重试限于瞬时类失败并如实披露）。

## Dev Note

本文为 2026-09-06 交接快照，属 docs/working 过期性材料；接任者收口在途链后应更新本文并在新总控稳定后归档。文中未标注"已核对"的 Provider/SessionID 字段须以持久化记录复核后使用。
