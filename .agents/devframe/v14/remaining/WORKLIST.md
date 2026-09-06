# V1.4 第二期 · 唯一剩余工作清单（W-1 基线）

单一事实源。每项四态：**源码**（实现存在且最新）/ **profile**（挂入实际启动面）/ **运行**（本机真实运行证据）/ **生产验收**（用户功能口径通过）。
只记录变更：状态翻转或新增证据时更新对应行，禁止整表重抄。

## A 工程缺陷线（负责人：L-Defects）

| ID | 用户功能/项 | 源码 | profile | 运行 | 生产验收 | 证据 | 真实依赖 | 下一步 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A1 | both-mode-turn 快照绿 | 待修 | n/a | 红（5418ms） | 待 A1 绿 | 先存归因：录制树根 `dsh-devframe-p-battery` 路径嵌入期望栈（干净树复验 2 红在案） | 无 | 复现→定位嵌入机制→最小修复→场景绿 |
| A2 | ptc-turn 快照绿 | 待修 | n/a | 红（4288ms） | 待 A2 绿 | 同 A1 同因 | A1 同机制 | 与 A1 同波处理 |
| A3 | src/*.js 污染机制查清+防复发 | 调查中 | n/a | 复现证据在案 | 待防复发落地 | 85 文件清单（09-06 11:34 时戳、untracked 未 ignore、overlap=85 用户文件）；vite 扩展序 .js 先于 .ts 遮蔽源码；清缓存揭开；wave 树全绿对照 | 无 | 干净 worktree 复现产生机制→防复发方案（不动用户 376 文件、不 gitignore 掩盖） |
| A4 | 可逆独立启动目录（污染排除的候选版本启动方式） | 待设计 | 待接 | 未验 | 待 C 线联验 | 依赖 A3 结论 | A3 | 启动目录方案→文档化→与 C 线联验 |

## B 用户组合交付线（负责人：L-UDeliver）

| ID | 用户功能/项 | 源码 | profile | 运行 | 生产验收 | 证据 | 真实依赖 | 下一步 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B1 | 真实 dsh profile 全链：启动→总控→组长→Worker（真实 huoshan 调用）→产出→审查→合并→停止重启恢复 | **收口已合并 main**（b6971bfb6c：cordis.yml 四包挂载 fail-closed 缺省+apps/cli 依赖+command-goal-binding tsconfig path+设计/回执 10 文件；verify-cordis-config 133 files+build exit 0 双树复现） | **shipped 已挂载**（安全机器中立缺省，部署经 --patch overlay 收窄） | 机制 B 已证；shipped 真实链 12 站待跑 | 待 B1 全链 | B 收口 commit+设计文档 lead/design.md | 无（凭据已授权） | B4 huoshan 显式重测→dump-config 装配探针→真实链逐站 |
| B2 | Shadow 跨项目投递/隔离进真实用户路径 | 已有（shadow-router；S6 机制 B PASS） | shipped 待挂/待证 | 机制 B 限范围 | 待 shipped 证据 | S6 判定书（隔离域路径+SHADOW_REQUEST_CONFLICT） | B1 | 随 B1 链跑真实跨项目站 |
| B3 | Memory 写/读/冷恢复进真实用户路径 | 已有（project-memory；S7 机制 B PASS） | shipped 待挂/待证 | 机制 B 限范围 | 待 shipped 证据 | S7 判定书（Vault 恰 2 真实 .md） | B1 | 随 B1 链跑真实 Memory 站 |
| B4 | S1 真实凭据重测（隔离 profile） | 已有（harness s1 脚本 d0c2c455c2） | 隔离 profile | 先前 keyless BLOCKED——**勘误：该隔离测试缺的是 deepseek-official 凭据，非 huoshan 失败；huoshan 账号可用** | 待 huoshan 显式路由重测 | s1 key-probes.json 4/4 钉住 | B1 前置可独立 | huoshan 显式路由重跑（凭据不输出不提交） |
| B5 | AT 验收矩阵 36 条逐项对账（AT1×11/AT2×8/AT3×9/AT4×8） | 待对账 | 部分待证 | 矩阵文件仍声明 not_run 且含多项旧缺口 | 待逐条对账（不得把 S2-S7 通过提升为全范围验收） | `.agents/devframe/p22/anchor-matrix.md`（36 条 not_run+旧缺口）+ `docs/testAndAcceptance.zh.md`（每项精确证据要求） | B1 真实链产物可复用链接 | B 组长逐条对最新测试/真实组合产物：已被后续交付覆盖的复用并链接；未覆盖的按依赖派小切片；**AT1-11 真实任务效用在内**；huoshan 显式路由可推进真实任务 |

## C 产品与外围线（负责人：L-Product）

| ID | 用户功能/项 | 源码 | profile | 运行 | 生产验收 | 证据 | 真实依赖 | 下一步 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | Agent 树默认折叠/箭头仅下一层/SessionID 直接复制 | **存在**（三重一致：折叠 WorkspaceBrowser.tsx:352-354；箭头 Rows.tsx:678-690+756-776；SessionID 复制 Rows.tsx:43,60-86,89-101+词条 locales.ts:48-50；契约 README.md:40） | client（挂载证据随 C3 补） | **组件级自动化绿**（vitest 3 files/61 tests exit 0） | **技术验收通过**（无新增真用户动作） | c1-agent-tree.md（C 线树）；Worker 673d61fe，provider 请求级实证 seq13/14 | 无 | 已关闭；三种更短复制路径=可选增强，用户要再立独立项 |
| C2 | 显式 @codex @claude @cursor 提及 | **缺失（唯一真实缺口）**：@ 触发管线存在且 137/137 绿（detect.ts:48-76、grammar.ts:26-35、roster 唯一入口 service.ts:49）；现存 @ source 仅 reference/cordis；ui-subagent @ source 已于 ad3632f122 退役；@codex/@claude/@cursor 全 packages 零命中 | client | 触发管线运行绿 | 缺失——实现后另立切片验收 | c2-mentions.md（零命中证据+git -S 考古）；修复设计=宿主侧 roster 契约（ctx.subagents provider 目录 RPC）+薄 client @ source | 总控已裁定：C 组长单写者实现（client 半部+宿主半部写域扩展授权） | C 组长派实现切片+回归测试 |
| C3 | 模型切换/侧栏/用量监测 | **存在一致**（模型切换 index.ts:126-179+service.ts:68-111；侧栏 SidebarRoot.tsx:52-186；用量 turn-tail.ts:164-166→TurnUsagePanel.tsx:99-178+StatsLine.tsx:163-209+ContextMeter.tsx:55-167） | **挂载在案**（:197-198/:218-219/:286-288） | **101/101 exit 0** | **技术验收通过**（无新增用户动作） | c3-model-sidebar.md | 无 | 已关闭 |
| C4 | 手机配对 | 外部包/本仓库零源码（配对守护=外部运行时/APK，诚实标注不可核面） | **已安装启用**（mobile profile 四 bundle，release v1.1.6；包内 version 字段落后 release tag 已记录） | **装配级在案**（~/.dsh/mobile/ 守护密钥对+devices.json 恰 1 台设备，仅记结构） | **待真用户动作**（3 步清单已出） | c4-mobile-pairing.md | 真用户手机操作 | 用户操作清单已列入最终交付 |

## D 独立验证线（负责人：L-LlmVerify）

| ID | 用户功能/项 | 源码 | profile | 运行 | 生产验收 | 证据 | 真实依赖 | 下一步 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | dsh-llm-opencode-go 隔离核验 | 待核验 | 隔离 profile | 未验 | skip≠pass | 无 | 外部认证（缺则只阻塞本项） | 实际外部包源码/版本/配置核对+隔离运行 |
| D2 | dsh-llm-ollama 同上 | 待核验 | 隔离 | 未验 | 同上 | 无 | 本机 ollama 可用性 | 同上 |
| D3 | dsh-llm-grok 同上 | 待核验 | 隔离 | 未验 | 同上 | 无 | 外部认证 | 同上 |
| D4 | dsh-llm-commandcode 同上 | 待核验 | 隔离 | 未验 | 同上 | 无 | 外部认证 | 同上 |
| D5 | dsh-ponytail 同上 | 待核验 | 隔离 | 未验 | 同上 | 无 | 待查 | 同上 |
| D6 | dsh-llm-providers-ui+codex 插件外部包源码/版本/配置核对 | 待核验 | n/a | 未验 | 待核对报告 | 无 | 无 | 外部包同名目录≠本仓库源码不存在——按实际包管理清单核对 |

备注：Astra=可选 Provider 兼容分支，不锁开发模型，不建任务不耗主线（用户接受现有 glm 路线）。

## 车道与并发纪律（各组长执行）

- **三层证据纪律（W-3 起）**：每个任务/Worker 在结算表分列三层证据——**请求参数**（派发时显式 provider/model）、**宿主标签**（会话选择配置）、**实际响应**（会话日志 request/header+request/context 的逐字载荷）；只有"实际响应"层可判 provider 实证，自报 unknown/缺日志一律记"未证实"，不得提升。D 线只读包证据与 B 线真实本机探针在结算表分类标注。
- Worker 一律 workflow 显式 `{provider, model:'glm-5.3-flash'}`；每任务记录实际请求 provider/model 及结果，标签≠成功证明。
- 每账号起步 2 条实质 Worker；独立任务充分且响应稳定再增；组长汇报错峰，避免全员同时查账。
- 共享契约/manifest/profile（尤其 shipped cordis.yml）唯一写入者=B 线组长串行收口；其余线只读引用。
- 同提交同环境同命令的通过结果复用；修改/失败/新风险才重跑；集成后组合验证一次。
- 等待须写明对象+唤醒条件；不做空转轮询。

## 变更日志（只记变更）

- W-1（本文件建立）：基线如上。main@381f3dbc10，旧六链+两追加波已并，脏 376 保护。
- W-2：用户补充核验发现合入——新增 B5（AT 矩阵 36 条对账，anchor-matrix.md not_run+旧缺口 vs docs/testAndAcceptance.zh.md 精确证据要求）；B4 勘误（S1 原失败=deepseek-official 缺凭据，非 huoshan 失败；huoshan 显式路由可推进真实任务）。
