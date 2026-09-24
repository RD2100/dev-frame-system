---
description: Desktop 插件接入、专家中心、技能与 MCP、Obsidian 资料库和定时任务的开发与交接记录。
---

# DSH Desktop 产品开发与交接

[English](desktop-product-delivery.md) | 中文

## Summary

本文记录本次开发的范围、分工、验收和进度。后续 agent（智能体）从任务表继续工作，先核对文件与实际验证结果。文档由总控唯一写入；worker 每完成一项提供变更路径、检查结果和待解决问题，由总控即时更新。

## Table of Contents

- [目标与需求](#requirements)
- [事实与复用](#baseline)
- [开发任务](#tasks)
- [协作与验收](#delivery)
- [进度记录](#progress)
- [Dev Note](#dev-note)

## 目标与需求 <a id="requirements"></a>

用户需要在官方 Desktop 使用专家团、影子和 Obsidian 记忆，并通过完整页面管理能力。截图是交互参考，不证明 DSH 已有对应功能。

| 范围 | 预期操作 | 验收 |
| --- | --- | --- |
| 专家与专家团 | 搜索、分类、卡片详情、召唤、示例问题、输入框已选标签 | 召唤绑定真实会话与执行；显示运行结果；影子入口保留 |
| 技能与 MCP | 分页签浏览、搜索、安装状态、启停；连接器添加、编辑、测试、移除 | 复用官方运行时，实际加载和调用；凭据不出现在响应与日志 |
| 资料库与记忆 | 最近访问、本地产物、我的资料、搜索、预览、选择 Vault、复制绝对路径、引用到对话 | Markdown 以 Vault 为文件真源；记忆与原始资料区分；修改冲突明确提示 |
| 定时任务 | 模板、新建、暂停、立即运行、运行记录 | 重启恢复定义；记录成功、失败和取消；重复触发受控 |
| Desktop 插件 | 独立安装、禁用、版本检查 | 使用编译产物；无源码目录依赖；兼容升级保留配置和插件版本 |

共享资料和团队空间属于后续多人协作能力；本地单用户版本不能用空壳按钮声称已经支持。影子是独立入口，专家中心位于其上方。

## 事实与复用 <a id="baseline"></a>

开发仓库为 D:\dsh-devframe，官方对照副本为 D:\dsh-upstream-latest，已下载提交为 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720，版本 0.1.6-alpha.1。副本依赖安装和 headless 帮助命令通过，不代表 Desktop 或定制插件运行验证通过。

[官方 Desktop](https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/apps/desktop/README.md)提供插件管理器；已检查源码的安装入口限定 npm 仓库包，使用精确版本且不接受本地目录和 file: 包。公开发布需要另行授权。开发模式接入与正式安装验收分开记录。

[现有组合包](../../packages/experimental/devframe-profile/README.zh.md)面向源码 checkout。private: true 不妨碍所有本地打包方式，workspace:^ 也可在打包时转换；实际缺口是完整可分发依赖、宿主 peer 约束、编译资源、路径解耦和新版 API 兼容证据。不能只凭这些标志断言必须重写所有 manifest。

| 需求 | 复用候选 | 决策 |
| --- | --- | --- |
| 技能运行 | [官方 Skill](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/skill) | 复用已有发现与加载 |
| MCP 运行 | [官方 MCP](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/mcp) | 复用连接与资源服务 |
| 管理界面 | [skill-mcp-panel](https://github.com/Fishquito7/dsh-skill-mcp-panel) | 候选，先审计 Desktop 传输与配置所有权；未安装 |
| 插件市场 | [dsh-market](https://github.com/dsh-market/dsh-market) | 候选，不与官方安装器重复拥有配置 |
| 记忆 | [dsh-mnemon](https://github.com/omdsh-dev/dsh-mnemon) | 参考分层；现有 project-memory 保持单一写入者，未经评估不并装 |
| 定时任务 | [dsh-automation](https://github.com/titanwings/dsh-automation) | 对照官方 schedule；jobs-local 的进程内后台任务不等于持久定时调度 |

## 开发任务 <a id="tasks"></a>

以下是用户批准的开发范围，不是已实现功能清单。并发按写入目录隔离；共享 manifest、profile、生成文件与集成构建由总控串行安排。

| ID | 工作包 | 依赖 | 状态 | 负责人 |
| --- | --- | --- | --- | --- |
| D0 | 需求、依据、任务与交接文档 | 无 | 文档格式检查通过 | 总控 |
| D1 | 插件依赖与 Desktop 可安装产物检查、隔离打包路径 | D0 | 已完成：依赖闭包与打包路径验收 | Luna max / Kierkegaard / 01a0aa94-f848-7891-ab1d-e033c0cb0e23 |
| D2 | 专家中心交互缺口与可运行召唤流程 | D0 | 已完成：专家中心召唤与审批流程验收 | Luna max / Dewey / 01a0aa94-f920-77a1-bb92-b1c915752a86 |
| D3 | Obsidian 资料库基础：文件列表、读取、搜索与路径状态 | D0 | 已完成：资料库 Host 服务、工具与页面接线验收 | Luna max / Pascal / 01a0aa94-fa61-7022-847f-8a441dd750b2 |
| D4 | 技能/MCP 管理与定时任务的现有能力核对、适配方案 | D0 | 已完成：Skill/MCP/定时任务复用审计 | Luna max / Archimedes / 01a0aa94-fb9a-7df3-b32b-04f8b0adfc1c |
| D5 | Desktop 集成、构建、真实加载与升级兼容验收 | D1–D4 | Host 启动和 Electron 页面已复核；模型驱动的影子看板流程受提供方计费阻塞 | Luna max / Parfit / 01a0aa96-62e5-75d0-a94b-6f88bcb2ff8b |
| D6 | 资料库页面与 Memory Remote：目录、预览、搜索、路径和引用 | D3 | 已实现并挂载；Electron 资料库与 Memory 页面可读取；修改与完整 e2e 证据仍有限 | 待分配 Luna max |
| D7 | 技能与连接器管理页面、官方服务接入 | D4 | 只读目录页已完成；安装、启停与 MCP 增删改测需要管理后端 | 待分配 Luna max |
| D8 | 定时任务模板、持久化运行记录与重启恢复 | D4 | Schedule 工具、模板、暂停/恢复/立即运行/历史、结果回执、投影和只读任务中心已挂载；页面变更控件与冷重启 e2e 仍待做 | 待分配 Luna max |

## 协作与验收 <a id="delivery"></a>

总控负责派发、进度与审核；worker 使用 gpt-5.6-luna，reasoning_effort=max，不再派生 worker。每个 worker 记录自身 ID、工作根、变更前基线、独占路径和检查结果，不回退已有改动。

共享工作区构建由总控唯一调度；worker 可以运行经核对不写共享构建目录的定向测试。源码新增完成后先审核，再集成和运行相应验证。修改后的证据必须对应实际文件版本。状态区分待派发、开发中、待审核、需修复、已验收、受阻。

每个阶段报告变更文件、测试命令和退出结果、缺失验证、下一步。仅源码检查或单元测试通过，不能标为 Desktop 可用；最终需要独立运行时加载、按钮执行、持久化、重启和兼容性测试。真实模型调用遵守现有授权，未运行就明确记录。

## 进度记录 <a id="progress"></a>

- 2026-09-16：需求与源码证据汇总完成；确认当前开发仓库有大量既有修改，按独占目录保护。
- 2026-09-16：已确认 Luna max 可用；开始首轮四个互不重叠的工作包，尚无本轮代码验收结果。
- 2026-09-16：D0 文档已通过 `verify-translation-pairing`、`verify-md-links` 和 `verify-md-wrap`；代码与 Desktop 集成验证仍待 worker 返回。
- 2026-09-16：中英文配对检查通过；增加 D5 隔离集成 worker。D5 独占官方旁侧副本构建输出；当前仓库共享构建仍由总控调度。专家和影子已使用 Remote，是否兼容 Desktop 需加载验证，不能预设必须重写传输。
- 2026-09-17：D4 完成。官方 Skill/MCP 后端可直接复用；`dsh-schedule` 属会话级持久化、无 Cron 支持；MCP 完全没有图形管理 UI，D7 必须自研。报告：`scripts/desktop-capability-audit/d4-skill-mcp-schedule-audit.md`。
- 2026-09-17：D3 完成。Obsidian 资料库只读服务已实现（`library.ts`）：listLibraryFiles / readLibraryFile / searchLibrary / getLibraryStatus，25 个单测全通过，全套 97 项零回退，lint/JSDoc 通过。`plugin.ts` 工具注册待总控串行处理。
- 2026-09-17：D1 完成。DevFrame 插件依赖闭包分析：14 个 workspace 包全不在 desktop-host，需全部打包；`zod`/`ajv`/`js-yaml` 外部包缺失；expert-pack 路径硬编码 `process.cwd()` 在 Desktop 启动必崩（最高优先级修复）；workspaceRoot cwd 需 Desktop overlay；react/schemastery/dsh-llm asar 可达性待验证。报告：`scripts/desktop-plugin-delivery/d1-dependency-closure-report.md`。
- 2026-09-17：D2 完成。专家召唤约束审查：召唤按钮不触发 `expert_team_run`（假召唤）；`ExpertTeamGateway` 缺少写操作 Remote 方法（前置依赖）；`waiting-approval` 无 UI 审批入口。修复顺序：Gateway 写操作 → 召唤触发运行 → 审批节点 UI，预计 2.5 天。报告：`scripts/desktop-capability-audit/d2-expert-summon-constraint-audit.md`。
- 2026-09-17：接替恢复完成（只读核对，不自动采信文档“完成”）。实测：D1/D2/D4 均为审计报告完成、修复/实现未做；D3 `library.ts` 已实现，25 项 library 单测与全套 97 项实测通过（EXITCODE=0），plugin 工具接线未做；D5 staging 目录 `D:\dsh-upstream-latest\.desktop-devframe-staging` 未创建、集成未开始；官方旁侧副本 HEAD=0d1f500 且工作树洁净。下一步按 D2 报告顺序开始实现：Gateway 写操作 → 召唤触发运行 → 审批节点 UI。
- 2026-09-17：D2 实现完成并验收。Gateway 新增 `startRun`/`consult`/`approve`/`getRun` 四个 @Remote 写/读方法；`ExpertTeamCardFace` 与 mount.ts 接线；详情视图区分「启动流水线」（startRun）与「召唤专家（咨询模式）」（consult），绕过草稿预填路径并内联展示咨询结果；等待审批的运行行可展开读取关口问题（getRun）并记录通过/驳回与可选批注（approve）。验证：gateway.spec 6 项 + orchestrate 16 项（含 Remote 方法集断言更新）+ client-ui 卡片 11 项 + selection 3 项全部通过；expert-team 全套 96 项、tsc -b 双包、oxlint 双包 0 错误。中英 README 已同步更新（不再声称“只读 Remote / 不直接启动编排”）。
- 2026-09-17：D1 overlay 落地。产出 `scripts/desktop-plugin-delivery/desktop.devframe.cordis.patch.yml`（覆盖 workspaceRoot、checks[0].cwd、expert-team packs 三条启动路径，令牌未替换时加载 fail-loud；`dshHomePath` 注入已在 desktop-host `runDesktopHost` 流程核实可用）；验证测试 `overlay-apply.spec.ts` 3 项通过，oxlint 0 错误；D1 报告追加第 7 节落地记录与 D5 输入清单。D5 尚未开始（staging 目录未建、集成未做）。
- 2026-09-17：D3 接线完成。总控决策：library 按记忆工具既有模式注册为模型工具（与 D6 的 UI Remote 分离，同 expert-team 模式）。新增 `src/library-tools.ts`（`library_status`/`library_list`/`library_read`/`library_search`，绑定 vaultRoot，未配置时 status 诚实报 UNAVAILABLE、其余 MEMORY_UNAVAILABLE fail-closed），plugin.ts 注册。验证：project-memory 全套 100/100（新增 plugin.spec 3 项分派测试：status/list/read/search 端到端、穿越读 MEMORY_PATH_REJECTED、未配置 fail-closed），tsc 0、oxlint 0；中英 README 同步（工具数 3→7）。
- 2026-09-17：D5 验收通过。staging profile（bundles `[dsh-base, dsh-web-app, dsh-experimental-devframe-profile]`，overlay 注入 packs/workspaceRoot/artifactsDir）经官方 desktop-host `runDesktopHost` 装载，全部行激活，并在桌面传输上应答一次 Remote。开发仓库兼容修复：typert generator 输出记忆化惰性 schema 工厂 + `schema`/`create` 双字段 strict codec（官方 0.1.6 loader 的 `requireStrictCodec` 强制要求 `create`；generator lib 重建、host bundle 全量重生成）；agent-dispatch 在宿主缺少 `TOOL_AGENT_DISPATCH` 时回退仓库 2850 的 prompt section 序位；staging profile patch（部署层）补 `@deepseek-ai/dsh-worktree-registry`——官方 0.1.6 的 bundle 不含该包；开发仓库 web-app bundle 自带，故 devframe-profile 层不得重复该行（重复会让真实 web 服务以 `duplicate loader entry id: worktree-registry` 启动失败，已将该行移至部署层）；cordis-catalog LINK_MAP 补充 gateway 新增签名涉及的 6 个类型并重生成 `api-catalog.ts`。官方旁侧副本实测：`--dump-config` 组合通过；unary RPC `/api/expertTeam/view` 返回完整快照（2 团队 / 15 专家），HTTP 200，帧序列 start/data/end 干净；重启后 manifest 文件不变且响应指纹一致；版本报告 dsh 0.1.6-alpha.1、DevFrame 插件 0.1.2-alpha.4；不含 devframe-profile 的 profile 无任何 DevFrame 行（禁用语义）。生成器套件全绿：schema-emitter 65/65、type-model 43/43（快照刷新）、cordis-catalog 3/3；tool-catalog 期望同步（接线后的 project-controller 暴露 4 个 `project_*` 工具）；DevFrame 域 660 项通过（2 项 loader 超时抖动重跑即绿）；oxlint 0 错误、tsc -b 0。脚本：`.desktop-devframe-staging/verify-load.mts`、`verify-restart.mts`。全仓 `vitest run` 另暴露既有的范围外漂移（docs 子系统 README 索引行、packed-session fixture 迁移、sdk-minimal allowlist），本次交付未触碰。
- 2026-09-17：D5 跟进（web 可用性）。桌面入口整合为单一「DSH」图标，点击打开 DevFrame web 工作台（`apps/cli web` + devframe-profile patch + 部署 overlay；服务在 `127.0.0.1:3080`）。启动暴露：先前加进 devframe-profile patch 的 worktree-registry 行与开发仓库 web-app bundle 的行重复，导致真实 web 启动失败（`duplicate loader entry id: worktree-registry`）。修复：将该行移至 staging profile patch（部署层——官方 0.1.6 的 bundle 确实缺该包、staging 需要；devframe-profile 层保持干净）。staging 复验全绿（verify-load run13：boot OK、无 pending、RPC 200、2 团队 / 15 专家）；web 服务重启后 `status=running`，界面 HTTP 200 可访问。
- 2026-09-24：当前源码与定向证据表明 D1–D4 已完成：依赖与打包、专家中心召唤、资料库基础、Skill/MCP/定时任务审计均已有实现或已接受的审计依据；下方已对账表格中陈旧的“开发中”状态。
- 2026-09-24：已在 DevFrame overlay profile 上复核 D5 Host 启动和真实 Electron 页面。专家、Memory、Agent Team 与影子页面可加载；提供方计费问题阻塞模型驱动的影子规划和看板审批证据。
- 2026-09-24：D6 Host Remote 与只读资料库页面已经实现并挂载；Electron 资料库与 Memory 页面可读取当前投影。
- 2026-09-24：D7 已交付带搜索和刷新的只读 Skill/连接器目录。官方服务没有安装、启停或 MCP 增删改测 Remote，因此这些动作明确延期到管理后端。
- 2026-09-24：D8 已交付会话级 Schedule overlay、8 个模型工具、模板、暂停/恢复/立即运行/历史、成功/失败/取消结果回执、可重启投影和只读任务中心。浏览器变更控件与冷重启 Electron 证据仍延期。

## Dev Note

本文是本次开发的动态工作记录；结束后归档交接，稳定的使用说明归入对应包文档。此前聊天关于记忆未启用、定时任务已具备和源码标志的概括需要实际配置与运行证据核对，不能作为新实现的事实依据。
- 2026-09-18：D8 客户端交付——远程（手机配对）已在桌面端可用。移动配对插件原先等待不存在的 webServer，现改为等待 connection，并把远程路由注册到 connection.fetch；运行客户端已验证设置页 Quick Tunnel、二维码与状态接口，用户可从 DSH → 设置 → 远程扫码配对。
- 2026-09-18：桌面端影子入口已修复。客户端工作区注册、指定会话工作区、无 BOM 的 workspace.json，以及新建会话 cwd 均已对齐；运行验证表明点击影子后进入指定会话、输入框可用，模型供应商余额问题仍属于用户侧配置。

- 2026-09-18：影子侧栏图标位置已修复。footer actions 改为换行布局，已构建的 renderer CSS 同步更新；运行验证表明按钮位于侧栏底部，点击后影子状态为 online，输入框可用。一次启动时曾出现 host request pipe 不可用，需按日志与锁文件排查。
- 2026-09-18：影子入口打开新对话的问题已修复。无 cwd 的指定会话可由 shadow-agent 按 designatedCwd 单向补写并迁移；失败时 Router 与 UI 显示缺少工作区并拒绝打开。相关 403 项测试、typecheck 与 lint 均通过；用户需重启桌面客户端使 Host 执行补写。
