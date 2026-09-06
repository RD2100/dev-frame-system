---
description: 项目总控 v1.2 交接定稿（2026-09-06，第三版）：当前状态入口、在途 AT4 保留、P05 全收口与接任者首轮动作。
---

# 项目总控交接 — 2026-09-06（定稿）

[English](dsh-controller-v1.2-handoff-2026-09-06.md) | 中文

## 交接状态：在途链未收口、可交棒但旧链保留接收责任

AT4 故障注入 Worker 仍在运行（与本文档整理零文件依赖，保留执行）。旧总控在本文提交后**停止新派发与主树合并**；AT4 结算接收责任保留至交棒前一刻。V1.3 由外部创建，接管后不得重建、打断或重复派发 AT4。本文是接任总控的**当前状态入口**；历史账本（`.agents/devframe/pluginized-round-registry.md`）按需查阅。

## 已作废结论（以最新用户指令为准）

旧并发上限（2/5）、Provider 退避/独占假设、"常规裁定挂起等授权"、"轮次设置调整"等旧结论**全部作废**。现行规则：并发不设固定上限，按实测 API 吞吐扩大（两条 Provider 名不代表独立额度）；同 owner 不等于串行，按具体文件/接口冲突判断，组长可拆多 Worker 并行（依赖接线最后串行）；现有项目范围内可回滚的开发/测试/配置/验收**已获授权**默认执行；仅当具体操作需要真实凭据（registry 认证、DEEPSEEK_API_KEY）或用户部署根时，标注该操作自身阻塞，其余继续；40 轮检查规则维持原样，8 分钟节奏属外部自动化。

## 主树快照

| 项 | 值 |
| --- | --- |
| 截至 HEAD | `c4ad144d81`（本文提交紧随其后，SHA 以 git log 为准） |
| 用户改动与 stash 保护 | `AGENTS.md`、`docs/working/devframe-qa-2026-09-04.*`、`stash@{0}` 原样保留——不提交、不还原、不 push、不删除；除此之外工作树无未提交改动 |
| 权威门禁基线 | build exit 0（220 artifacts）；experimental+extensions sweep 130 文件 1256P+1S；agent-hierarchy 40/40；gen-cordis-catalog 0；test:docs 15/15；verify-cordis-config 133；verify-package-invariants 39 |

## P05 指纹链（已全收口）

| 波 | 合并 | 证据 |
| --- | --- | --- |
| 引擎 | `4f1df4348a`（`85f6e8cab7` src+`8321c3e0b4` test+`3671385046` docs） | devframe 53/53，新模块 100% 覆盖；build exit 0 |
| 比对面（案 B 裁定落地） | `88668ea890`（`77a6371a7a` src+`bc85310b2c` test+`09b155c4a3` docs） | devframe **58/58**（+5 verify 用例）；build exit 0；controller/events/schemas/journal 零 diff |

设计记录：`.agents/devframe/p22/fprecompute-design.md`（指纹构成、5 错误码族、untracked 不可见=已裁定边界、案 A=案 B 前移使用留后叠）。

## 在途链（唯一保留）：AT4 故障注入

| 项 | 值 |
| --- | --- |
| Worker SessionID | `dc51bc32-92b6-4b51-9bc3-fedabedaad1f`（one-shot subagent） |
| 父组长链 | Worker → L-Foundation `55979618-6bd7-4bc7-badc-8a3b13079158` → 旧总控 `session-724834c2-9ff4-49e5-9b0a-4ce5f68d2c2d` |
| Worktree / 分支 / cwd | `D:\dsh-devframe-p-at4`（组长按三层自建），分支 `p/at4process`，基点 `526e773b23`；会话创建 cwd=`D:\dsh-devframe`，任务工作区=p-at4 |
| Provider / 模型 | JSON 尚未落记录（首轮未完成）——**结算时按 session_projcache JSON 补核**，禁止假设 |
| 产物 | 无提交；工作树 dirty=2（只读调查/早期落盘）；任务=AT4-02/03/06 真实进程注入旅程落 `agent-reliability/tests/`（零模型依赖） |
| 实际调用 | 一次性 subagent 运行中；恢复点=读工作树文件状态续起、不重做已落盘部分 |
| 结算接收方式 | 旧总控保留接收责任至交棒前一刻（亲验提交/vitest/tsc/build/证据→其合并权在停止前有效）；交棒后由 V1.3 按 `send_message` 续组长会话接收，**不得重建、打断或重复派发** |

## Shadow / Memory 四态与具体生产缺口

| 插件 | 源码 | 安装+启用（已证实=隔离实例） | 运行时验证（已证实=真实探针） | 生产可用（具体缺口） |
| --- | --- | --- | --- | --- |
| Shadow（`packages/experimental/shadow-router`） | ✅（含 completeDelivery 停止守卫） | ✅ integration profile 六插件行；bundle 行+manifest 声明 | ✅ 包级 26P+1S；组合级 markShadow/投递旅程/stop 对照/crash-window（`.dsh-integration` 与全新临时根双实测 0） | 宿主组合 markShadow 生产调用点不存在（P23/S4 缝）；生产 authorizedRoots 需真实部署配置（该操作被真实数据根阻塞）；UI 状态集 |
| Memory（`packages/experimental/project-memory`） | ✅ | ✅ 同上 profile 行 | ✅ 三工具面+回执再水化+冷恢复（同上实测） | writeEnabled 生产实例未启用（config 面，可做本地实例）；memory 三工具未入角色允许表（配置面）；真实 Vault 根（被真实数据根阻塞） |

冷恢复复跑（已实测）：新建空临时目录为 `DSH_HOME` → `pnpm dsh plugin --profile integration add @deepseek-ai/dsh-<pkg>` 引导（install 步缺 registry 认证会 exit 1，但配置落盘、探针源码模式解析通过；首次执行记录实际行为）→ 探针 `--phase write`/`--phase verify` 双 0 → 仅删该临时根。**禁止整树删除共享 home 既有 sessions/storages/vault**。证据路径：`.agents/devframe/p22/shadow-delivery-flow-evidence.md`、`s6-evidence.md`、`memory-rehydration-evidence.md`、登记表 integration-3/4、shadowflow、shadowguard 条目。

## 剩余任务与接任者首批可派（经现状核对）

| 任务 | 组长 | 文件域 | 已证实依赖 | 验收 | 冲突处理 |
| --- | --- | --- | --- | --- | --- |
| Windows B 族快照（88F 唯一根） | L-Foundation（patch 行）+L-Verify（语料期望/delta） | `base/cordis.patch.yml` L252-254、minimal preset L36-38、snapshot 语料期望 | 平台参数化技术裁定（已授权）：场景级平台期望配置字段 | test:snapshot lib delta（A/C 族保持 0）+dump | patch 行与语料期望分属两组长不同文件域 |
| Shadow/Memory 本地配置接入 | L-Integration | 本地（非共享）profile 实例+writeEnabled/角色允许表本地实例 | 无（integration 文件域空闲） | dump-config+双相探针（全新临时根）+build | 与其他任务无文件交集 |
| AT4 进程注入/恢复 | L-Foundation | `agent-reliability/tests/` | **在飞保留中（见上）** | 包 vitest+tsc+build | 等其结算，不重复派发 |
| 真实三级任务离线脚手架 | L-Verify | 三级任务 brief+验收脚手架（不依赖 DEEPSEEK_API_KEY 的部分） | 无；真实运行段缺 key 仅阻塞该段 | 脚手架离线段全绿 | profile/e2e 文件域与 L-Integration 任务分文件或串行 |
| P05 残余（required-checks 模型；错审查者①与 snapshotId⇄fingerprint④已闭环） | L-Foundation | devframe 配置 schema+evidence 比对面 | fprecompute 已收口（本案 B 面）；产品配置面设计先行 | 包 vitest+tsc+build+jsdoc | 与 AT4 不同包零冲突；events/schemas 接线最后串行 |

接任者首轮动作：核对主树 HEAD/登记表末条/本文一致 → 向 L-Foundation 会长发送 AT4 续接确认（不重建）→ 并行派 Windows B 族参数化设计与 Shadow/Memory 本地接入（不同组长、零文件冲突）→ 按 fprecompute-design.md 的案 A 叠加路径排 P05 required-checks 设计。

## 交接闸门（已执行到第 2 步）

1. ✅ 在途 P05 链结算亲验并合并（引擎 `4f1df4348a`+比对面 `88668ea890`）。
2. ✅ AT4 当前结果持久化（本节+登记表 `c4ad144d81`）+本文提交。
3. ✅ 旧总控自本文提交起**停止新派发与主树合并**（登记表末条为止），自动目标随交棒暂停。
4. ⏳ V1.3 由**外部协调**创建：独立顶层 Session+独立 Worktree；旧总控不创建子 Agent、不修改父子记录。
5. ⏳ V1.3 接管核对：主树 HEAD、登记表末条、本文一致后取得唯一控制权；不得重建/重复派发 AT4。

## 守恒规则（V1.3 必守）

三层拓扑（总控→组长→Worker，Worker 不创建 Agent）；组长与总控独立 Worktree；总控唯一合并主树；无 idle 空转；SessionID/Agent/Worktree/任务/结果持久化；车道与 Provider 只按持久化 JSON 标注；无静默路由、无不确定调用盲重试；用户未提交项与 stash 全程不动；不 push、不建 PR、不发布、不删除用户文件。

## Dev Note

本文为 2026-09-06 定稿快照，属 docs/working 过期性材料；V1.3 收口 AT4 后更新在途节并自行建立新版本记录。文中未落记录的 Provider 字段须以持久化 JSON 补核后使用。
