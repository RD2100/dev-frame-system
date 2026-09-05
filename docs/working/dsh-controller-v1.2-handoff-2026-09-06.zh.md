---
description: 项目总控 v1.2 交接快照（2026-09-06，第二版）：主树状态、双插件四态、在途链、接任者首批任务与授权边界。
---

# 项目总控交接 — 2026-09-06

[English](dsh-controller-v1.2-handoff-2026-09-06.md) | 中文

## 交接状态：交接准备中（在途链未收口）

本文是接任总控的**当前状态入口**；历史账本（`.agents/devframe/pluginized-round-registry.md`）按需查阅。旧总控仍持有唯一合并权与新派发权，直至"交接闸门"全部满足；接任者激活前不得宣称已完成交接。

## 已作废结论（以最新用户指令为准）

登记表开头段的早期状态与限制表述已作废，作废清单与依据见本文各节；要点：

- 并发无固定 2/5 上限：按文件所有者、冲突风险与实测 API 吞吐调度，同 owner 组长可按具体文件域拆多个 Worker 并行（设计/独立实现/测试准备提前并行，真正依赖的接线最后串行）。
- huoshan-1/2 常态双车道按实测容量承接；两条 Provider 名不代表独立额度；车道归属只由会话持久化 JSON 证实。
- 用户已授权：现有项目范围内可回滚的开发/配置/测试/技术裁定，包括使用现有 Provider 做隔离本地小任务验收。**未授权**：对外发布、push/PR、删除用户文件。具体缺失凭据（registry 认证、DEEPSEEK_API_KEY）或未知用户数据根只阻塞其对应操作，其余工作继续。
- 40 轮检查规则维持原样；8 分钟节奏属外部检查自动化，非 DSH 项目配置；不再讨论轮次修改。

## 主树快照

| 项 | 值 |
| --- | --- |
| 快照时间 | 2026-09-06（第二版，本机时区） |
| HEAD | `ffd9837e7b`（交接文档第一版提交；以登记表末条为准） |
| 工作树 | 除用户未提交项外无我的改动；用户未提交项原样保留、不提交不还原：`AGENTS.md`、`docs/working/devframe-qa-2026-09-04.*`、`stash@{0}` |
| 权威门禁基线 | build exit 0（220 artifacts）；experimental+extensions sweep 130 文件 1256P+1S；agent-hierarchy 40/40；gen-cordis-catalog 0；test:docs 15/15；verify-cordis-config 133；verify-package-invariants 39；快照抽样唯一红=B 族已知根（见剩余任务） |

## 双插件四态与最短证据路径

四态口径：源码就绪 / profile 安装+启用 / 运行时验证（组合级）/ 生产可用。Shadow 与 Memory 均属必交范围。**只写已证实面**：安装与运行时验证的✅对应隔离本地 profile 实例与真实探针（已实测）；生产可用列写具体缺口，不笼统归为部署选择。

| 插件 | 源码 | 安装+启用（已证实） | 运行时验证（已证实） | 生产可用（具体缺口） | 最短证据路径 |
| --- | --- | --- | --- | --- | --- |
| Shadow（`packages/experimental/shadow-router`） | ✅（含 completeDelivery 停止守卫） | ✅ 隔离实例（integration profile 六插件行；bundle 行+manifest 声明） | ✅ 包级 26P+1S；组合级 markShadow/投递旅程/stop 对照/crash-window 全链（`.dsh-integration` 与全新临时根均实测双 0） | 缺口：宿主组合 markShadow 生产调用点不存在（P23/S4 缝）；生产 authorizedRoots 依赖真实部署配置（被真实数据根阻塞）；UI 状态集 | `.agents/devframe/p22/shadow-delivery-flow-evidence.md`、`s6-evidence.md`、登记表 integration-3/4、shadowflow、shadowguard 条目 |
| Memory（`packages/experimental/project-memory`） | ✅ | ✅ 隔离实例（同上 profile 行） | ✅ 组合级三工具面+回执再水化 agent 侧+冷恢复（同上探针实测） | 缺口：writeEnabled 生产实例未启用（config 面，已授权可做本地实例）；memory 三工具未入角色允许表（配置面）；真实 Vault 根依赖生产配置（被真实数据根阻塞） | `.agents/devframe/p22/memory-rehydration-evidence.md`、登记表 integration-1/2 条目 |

组合级冷恢复复跑（本会话已实测的全新临时根路径）：新建空临时目录设为 `DSH_HOME` → 按各插件 fail-loud 提示执行 `pnpm dsh plugin --profile integration add @deepseek-ai/dsh-<pkg>` 引导（本会话六条 add 的 install 步因 registry 认证缺失 exit 1，但插件行与 profile 配置已落，探针以源码模式解析全部通过——接任者首次执行时记录实际行为）→ `pnpm exec tsx .agents/devframe/integration/probe-cold-recovery.ts --phase write` 再 `--phase verify`，期望双 0 → 用后仅删除该临时根。**禁止整树删除共享 home 内既有 sessions/storages/vault**。

## 在途链（交接时唯一，证据已核）

| 项 | 值（已核证据） |
| --- | --- |
| 任务 | `p/fprecompute`：sourceFingerprint 重算引擎（AT1-05 变体 5 src 波），设计先行+裁定请求 |
| 组长 SessionID | `55979618-6bd7-4bc7-badc-8a3b13079158`（L-Foundation；其父=总控会话 `session-724834c2-9ff4-49e5-9b0a-4ce5f68d2c2d`） |
| Worker SessionID | `00e07e03-f59a-49ca-84d6-018655769a55`（one-shot subagent，label "Build fingerprint recompute engine"） |
| 父链 | Worker `00e07e03…` → L-Foundation `55979618…` → 总控 `session-724834c2…` |
| cwd / Worktree / 分支 | `D:\dsh-devframe-p-foundation`（Worker 任务书内声明的工作区），分支 `p/fprecompute`，基点 `526e773b23` |
| Provider / 模型 | **huoshan-2 / glm-5.3-flash**（已核：`C:\Users\25313\.dsh\storages\session_projcache\sessions\00e07e03-f59a-49ca-84d6-018655769a55.json` 的 modelSelection.lastUsed） |
| 产物状态（据同一 JSON todos） | 设计文档/引擎模块/测试 spec 已写盘；门禁（包 vitest+tsc+build+jsdoc）进行中；三提交+终报未完成 |
| 恢复点 | 组长会话中断时：读工作树文件状态与该 JSON todos 续起，不重做已落盘部分 |
| 验收门禁 | 涉及包 vitest+包 tsc+`pnpm run build`+verify-export-jsdoc+`git diff --cached --check`+正常 commit（走仓库钩子） |
| 裁定请求项 | 引擎进 StartGoalRequest 绑定流程还是独立 verify 面——旧总控批复前只落计算引擎与用例，比对面不动 |

## 接任者首批可派任务（经现状核对，非凑数）

同 owner 判定不成立串行：按具体文件/接口冲突判断；同 owner 组长可拆多 Worker，按文件域并行，依赖接线最后串行。

| 任务 | 组长 | 文件域 | 依赖 | 验收 | 冲突处理 |
| --- | --- | --- | --- | --- | --- |
| P05 后续（required-checks 模型+比对面接线） | L-Foundation | `devframe/src`（配置 schema 与 resolveResultBinding 邻域）、`agent-evidence`（比对） | fprecompute 收口；裁定请求批复后接线 | 包 vitest+tsc+build+jsdoc | 设计与测试准备可与 fprecompute 并行（不同文件）；events/schemas 接线最后串行 |
| Windows 快照平台问题（B 族 88F 唯一根） | L-Foundation（patch 行）+L-Verify（delta 验证） | `base/cordis.patch.yml` L252-254、minimal preset L36-38、snapshot 语料期望面 | 平台参数化技术裁定（已授权范围）：语料场景级平台期望配置字段，反硬编码 tunables 规约 | test:snapshot lib 模式 delta（A/C 族保持 0，B 族收口）+dump | patch 行归 L-Foundation、语料期望归 L-Verify，两侧不同文件域 |
| Shadow/Memory 本地配置接入 | L-Integration | 本地（非共享）profile 实例配置+writeEnabled/角色允许表本地实例 | 无（integration 文件域该组长独占，当前空闲） | dump-config+双相探针（全新临时根）+build | 与 AT4/三级验收任务无文件交集，可并行 |
| AT4 故障恢复（AT4-02/03/06 进程注入旅程） | L-Foundation 第二 Worker | `packages/experimental/agent-reliability/tests/`（独立文件域） | 无模型依赖（真实进程树）；dsh-ci-test-reliability 隔离规约硬执行 | 包 vitest+tsc+build | 与 P05（devframe/evidence）不同包，零冲突 |
| 真实三级任务验收准备 | L-Verify | 三级任务 brief+验收脚手架（不依赖 DEEPSEEK_API_KEY 的部分） | 无；真实运行段缺 key 时仅自动阻塞该操作 | 脚手架离线段全绿+任务书评审 | profile/e2e 文件域与 L-Integration 的本地接入任务分文件或串行 |

## 交接闸门

1. 在途链交付 → 旧总控亲验（真实提交/产物/门禁/会话 JSON）→ 合并主树 → 更新本文"在途链"节为最终 SHA 与验收结果。
2. 旧总控停止一切新派发与合并（登记表补最后一条），并将自动目标置为暂停。
3. 接任者由**外部协调**创建：独立顶层 Session+独立 Worktree；旧总控不将其创建为子 Agent、不修改父子记录。
4. 接任者核对：主树 HEAD、登记表末条、本文四态/在途/首批任务节——一致后取得唯一控制权。
5. 跨会话无法安全接收旧子链结果时：旧总控先收口再交棒，不阻塞 Worker；接任者不得重建、打断或重复派发在飞链。
6. 用户未提交项与 stash 全程保持不动；不 push、不建 PR、不发布、不删除用户文件。

## 守恒规则（接任者必守）

三层拓扑（总控→组长→Worker，Worker 不创建 Agent）；组长与总控独立 Worktree；总控唯一合并主树；无 idle 空转；SessionID/Agent/Worktree/任务/结果持久化；车道与 Provider 只按持久化 JSON 标注（两条 Provider 名不代表独立额度）；无静默路由、无不确定调用的盲重试（同命令单次重试限于瞬时类失败并如实披露）。

## Dev Note

本文为 2026-09-06 交接快照第二版，属 docs/working 过期性材料；接任者收口在途链后更新在途节并在新总控稳定后归档。文中 Provider/SessionID 均已按持久化记录核对；新出现的字段沿用同一核对纪律。
