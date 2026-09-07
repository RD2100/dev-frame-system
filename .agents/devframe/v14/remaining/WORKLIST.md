# V1.4 第二期 · 唯一剩余工作清单（W-1 基线）

单一事实源。每项四态：**源码**（实现存在且最新）/ **profile**（挂入实际启动面）/ **运行**（本机真实运行证据）/ **生产验收**（用户功能口径通过）。
只记录变更：状态翻转或新增证据时更新对应行，禁止整表重抄。

## A 工程缺陷线（负责人：L-Defects）

| ID | 用户功能/项 | 源码 | profile | 运行 | 生产验收 | 证据 | 真实依赖 | 下一步 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A1 | both-mode-turn 快照绿 | **已修**（normalize.ts 栈帧令牌化：帧=录制宿主属性，异常种类+消息钉住；e0c6a0f582 合入 64625d8268） | n/a | **干净树绿**（用户+组长隔离复验）；主树 collection 被用户 85 src/*.js 遮蔽（0 tests） | 干净树口径通过；主树待用户清理后复跑 | a1a2-repro.md+a1 vitest 输出（.agents/devframe/v14-defects/repro/） | 用户 85 文件裁定 | 主树复跑待用户清理 |
| A2 | ptc-turn 快照绿 | **已修**（同 A1 同 commit） | n/a | **干净树绿**（用户+组长隔离复验）；主树同被遮蔽 | 同 A1 | 同上 | 同 A1 | 同 A1 |
| A3 | src/*.js 污染机制查清+防复发 | **已落地**（verify-no-source-js 门禁：local+CI 双挂线、6/6 无效用例 spec；产生机制报告 a3-producer-mechanism.md） | n/a | **主树按设计 fail-loud**（点名 85 用户文件："remove them and fix the producer; never gitignore"） | 门禁防复发生效；85 文件处置待用户 | no-source-js.ts+spec+run-gates 接线+机制报告 | **用户裁定 85 文件** | 用户处置后主树门禁转绿 |
| A4 | 可逆独立候选启动目录（污染排除的候选版本启动方式） | **已交付**（a4-candidate-launch.md：创建/更新/回滚命令+终验退出码 @ ceb4befc59） | 候选树验证 | **全链绿**：install 0+build 0+gate 0+port 3081 LISTENING | **关闭**——候选树即用户可启动本地候选版本（去 --no-open 自动开浏览器） | a4-candidate-launch.md | 无 | A 线关闭；主工作区只记保护状态 |

## B 用户组合交付线（负责人：L-UDeliver）

| ID | 用户功能/项 | 源码 | profile | 运行 | 生产验收 | 证据 | 真实依赖 | 下一步 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B1 | 真实 dsh profile 全链 | **blocked/not_run**（总控最终尝试 chain5 收口：5 步+1 请求+goal 绑定绿，但无 Worker 派发/提交/deliverable；进程全停+证据入册 d6caf6f992） | **shipped 已挂载**（boot/profile/route/缓存/UI 状态≠验收） | S1-S3b/S8-进程级绿证据保留（chain-evidence.md）；S4-S12 未达 | **blocked**——恢复须新证据驱动的新裁定，不再重试 | chain-evidence.md（四轮+边界+chain5 全记录） | C2b 已修（模型面正常） | 无活动；B 组长转 B2/B3 |
| C2b | **HuoshanStreamArgs**——provider 流式 tool-call 参数 delta 累积契约 | **已修+已验证**（02251fac16 合 64dae5eb2a：assembler index 复用冲突丢弃+indexConflicts 诊断面+id 覆写消除+逐字透传契约测试） | n/a | 单测 953/953+tsc 0+build 220 artifacts；**最小真实重放 PASS**（session-f37c4bea：request/header seq=12 huoshan-1/glm-5.3-flash+工具真实返回 4 providers+turn/end seq=166；旧缺陷签名消失） | **通过**（双层根因中流式面已修；input-as-string 属模型侧，重放未见复发） | chain3 fixture+replay 证据 bf198278cc | 无 | **B1 恢复解锁**：重启 12 站链 |
| B2 | Shadow 跨项目投递/隔离进真实用户路径 | 已有（shadow-router；S6 机制 B PASS） | shipped 待挂/待证 | 机制 B 限范围 | 待 shipped 证据 | S6 判定书（隔离域路径+SHADOW_REQUEST_CONFLICT） | B1 | 随 B1 链跑真实跨项目站 |
| B3 | Memory 写/读/冷恢复进真实用户路径 | 已有（project-memory；S7 机制 B PASS） | shipped 待挂/待证 | 机制 B 限范围 | 待 shipped 证据 | S7 判定书（Vault 恰 2 真实 .md） | B1 | 随 B1 链跑真实 Memory 站 |
| B4 | S1 真实凭据重测（隔离 profile） | **PASS**（bb5d514d0f：harness exit 0、7/7 checks） | 隔离 profile | **keyless BLOCKED→真实凭据 PASS 翻转**（请求级 seq=10 huoshan-1/glm-5.3-flash 逐字+wire 响应 seq=49"ok"；凭据零记录） | **通过** | b4 证据+三层证据分列 | 无 | 已关闭 |
| B5 | AT 验收矩阵 36 条逐项对账（AT1×11/AT2×8/AT3×9/AT4×8） | **36 行对账收官**（4886aff6bd：b5-reconciliation.md 69 行） | 部分经 B1 挂载改善 | 矩阵 not_run→已覆盖项链接最新证据（AT2=7 覆盖+1 部分 AT2-05 双存储后端） | 逐条对账完成；未覆盖项按依赖待派 | b5-reconciliation.md | B1 链产物复用 | 未覆盖项小切片随 12 站链产出评估 |

## C 产品与外围线（负责人：L-Product）

| ID | 用户功能/项 | 源码 | profile | 运行 | 生产验收 | 证据 | 真实依赖 | 下一步 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | Agent 树默认折叠/箭头仅下一层/SessionID 直接复制 | **存在**（三重一致：折叠 WorkspaceBrowser.tsx:352-354；箭头 Rows.tsx:678-690+756-776；SessionID 复制 Rows.tsx:43,60-86,89-101+词条 locales.ts:48-50；契约 README.md:40） | client（挂载证据随 C3 补） | **组件级自动化绿**（vitest 3 files/61 tests exit 0） | **技术验收通过**（无新增真用户动作） | c1-agent-tree.md（C 线树）；Worker 673d61fe，provider 请求级实证 seq13/14 | 无 | 已关闭；三种更短复制路径=可选增强，用户要再立独立项 |
| C2 | 显式 @codex/@claude/@cursor 提及 | **已实现并合 main**（d859259b5a：宿主 subagents/providers Remote 面=注册表实况[出域 list() Remote 已追认：只读零行为变更]+独立 client @subagent source+字面 pick 走既有 model-visible user/message 路径+陈留元数据修正；类型收口 ceb4befc59） | client 挂载随 ui-subagent 既有行（cordis.patch.yml:260-261 核实无需改） | **181/181 绿**（137 回归+44 新增含三名用例）；build:lib 0 | 技术验收通过；浏览器实机 e2e 未跑（如实保留） | c2-mentions-impl.md+四 commit | 无 | 关闭（待真机像素路径的浏览器级验证不属本切片口径） |
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
