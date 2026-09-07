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
| B1 | 真实 dsh profile 全链 | **增量更新②（2026-09-07 下午）**：chain5 阻断面维持不重试；**消费链已交付并合并**——engine 恢复（190271fd4f）→适配并发门+恢复接线（58f9fbd6ce）→**正式 consumer（agent_dispatch 工具）+P1 Loader 入口修复（红证明）**→lead 指派落盘波（dcd3eb19c6）→**opt-in overlay 接线（238460f57f：hierarchy+dispatch 两行+manifest+role policy fail-closed）**；真实门禁轮 exit 0（worker 经 deepseek-v4-flash-ga-260731 真实回合+pwsh 工件，service 面+模型驱动派发证据） | opt-in overlay 已接线（候选命令显式 --patch 面）；**原 3080 未激活**（v3 激活前置不变：project_tasks v2→3 域+冷启动 reconcile+独立候选 profile 验证+受控重启） | **已证**：Loader 工具面（红证明）/身份复用/恢复装配/落盘投影/真实模型派发；**未证**：lead review+fingerprint 准入读取/integrate Git 执行/端到端联跑（V1.2 端 consumer 实作中，project-controller 归其独占） | **开放**：候选 profile 完整验证（C 干跑中）；准入 consumer 待 V1.2 交付后我审合并 | chain-evidence+agent-dispatch-integration+dispatch-persisted-evidence+c-verify-evidence §8 | catalog/README/config-catalog 全部收口；构建残渣 360 清理 | V1.2 接管后继续 |
| C2b | **HuoshanStreamArgs**——provider 流式 tool-call 参数 delta 累积契约 | **已修+三证闭环**（2dae9f852e：①chain3 真实片段流逐字嵌入修前复现=非法 JSON/索引拼接/id 抹除 7/7；②同样本现行 assembler 冲突丢弃+indexConflicts(17)+逐字透传；③固定脚本真实探针：huoshan-1 请求级 seq12+并行双调用 4/4 arguments 合法 JSON+turn/end seq819） | n/a | 7/7+真实探针 boot exit 0+请求级路由证据 | **通过——关闭**（assembler 面闭环；残留=模型发射嵌套 input 字符串形状+inspect fail-loud 正确拒绝=独立观察项不属 C2b） | c2b-verification.md+chain3-streamargs-evidence.json | 无 | 关闭；残留观察项另列 |
| C2b-r | 模型嵌套 input 字符串发射形状+工具 fail-loud 拒绝回路 | **排查闭合：无产品改动**（四问只读结论 2385f37a0a 后：契约清楚——input 须满足方法 schema+navigate-first 已文档化+对象要求显式 providers.ts:94；跳过发现=任务书给死参数+模型取舍；schema 经发现返回送达=模型未走该步但自救指令在上下文未被用；字符串=provider 流式原始形态，harness 边界内恒等透传） | n/a | d070abea 逐层 seq 定位（chunks 115/133→block-end 167→派发 168 逐字节拼接） | **一次模型三次不遵循→结案**；可选加固=inspect-registry.ts:232 拒绝诊断附 received-type（~1 行，减少无效重试）登记不执行 | c2b-verification.md+排查结论 | 无 | 结案；加固项可随时按需立片 |
| B2 | Shadow 跨项目投递/隔离进真实用户路径 | **已交付**（c2c0daa308，已合并 eef082a7aa） | shipped overlay | **运行+验收通过**（三要件+总控磁盘实证） | b2b3-evidence.md | AT2-05 双后端参数化→**B 组长补派中**（纯测试改动） | B 组长（huoshan-2 受限，测试为主） | 已闭合；AT2-05 由 B 闭合 |
| B3 | Memory 写/读/冷恢复进真实用户路径 | **已交付**（同 commit，已合并） | shipped overlay | **运行+验收通过**（三要件+磁盘实证） | b2b3-evidence.md | AT3-07 任务联动半边：**监听器片闭合**（a861715995：devframe/task-warning 分级事件+宿主装配监听器+三竞态/形状缺陷修复+6/6+264 回归+tsc host exit 0；判据=显式宿主上下文 declare，mode 面零接触；grade=fail≠实际任务失败验收边界已留档） | B 组长（已闭合） | 闭合 |
| B4 | S1 真实凭据重测（隔离 profile） | **PASS**（bb5d514d0f：harness exit 0、7/7 checks） | 隔离 profile | **keyless BLOCKED→真实凭据 PASS 翻转**（请求级 seq=10 huoshan-1/glm-5.3-flash 逐字+wire 响应 seq=49"ok"；凭据零记录） | **通过** | b4 证据+三层证据分列 | 无 | 已关闭 |
| B5 | AT 验收矩阵 36 条逐项对账（AT1×11/AT2×8/AT3×9/AT4×8） | **36 行对账收官**（4886aff6bd：b5-reconciliation.md 69 行） | 部分经 B1 挂载改善 | 矩阵 not_run→已覆盖项链接最新证据（AT2=7 覆盖+1 部分 AT2-05 双存储后端） | 逐条对账完成；未覆盖项按依赖待派 | b5-reconciliation.md | B1 链产物复用 | 未覆盖项小切片随 12 站链产出评估 |

## C 产品与外围线（负责人：L-Product）

| ID | 用户功能/项 | 源码 | profile | 运行 | 生产验收 | 证据 | 真实依赖 | 下一步 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | Agent 树默认折叠/箭头仅下一层/SessionID 直接复制 | **存在**（三重一致：折叠 WorkspaceBrowser.tsx:352-354；箭头 Rows.tsx:678-690+756-776；SessionID 复制 Rows.tsx:43,60-86,89-101+词条 locales.ts:48-50；契约 README.md:40） | client（挂载证据随 C3 补） | **组件级自动化绿**（vitest 3 files/61 tests exit 0）；**浏览器实证 PASS**（29c9c8e5e6：折叠 aria/chevron 单层/复制剪贴板全过；测试面等待惯用法修正） | **技术+浏览器双验收通过——关闭** | c1-agent-tree.md+c-verify-evidence.md；Worker 673d61fe，seq13/14 | 无 | 关闭；三种更短复制路径=可选增强，用户要再立独立项 |
| C2 | 显式 @codex/@claude/@cursor 提及 | **已实现并合 main**（d859259b5a：宿主 subagents/providers Remote 面=注册表实况[出域 list() Remote 已追认：只读零行为变更]+独立 client @subagent source+字面 pick 走既有 model-visible user/message 路径+陈留元数据修正；类型收口 ceb4befc59） | client 挂载随 ui-subagent 既有行（cordis.patch.yml:260-261 核实无需改） | **181/181 绿**；build:lib 0；**浏览器实证 PASS**（29c9c8e5e6：三名候选+@cl 收窄+pick 落字面，首跑即过） | **技术+浏览器双验收通过——关闭** | c2-mentions-impl.md+c-verify-evidence.md | 无 | 关闭 |
| C3 | 模型切换/侧栏/用量监测 | **存在一致**（模型切换 index.ts:126-179+service.ts:68-111；侧栏 SidebarRoot.tsx:52-186；用量 turn-tail.ts:164-166→TurnUsagePanel.tsx:99-178+StatsLine.tsx:163-209+ContextMeter.tsx:55-167） | **挂载在案**（:197-198/:218-219/:286-288） | **101/101 exit 0**；浏览器实证全过（C3 e2e exit 0：usage pill 挂载+700/500/1200 tok 对话框+Archive+侧栏 RTT+tripwire 干净；修复前 FAIL 留档 §3a） | **技术+浏览器双验收通过——关闭**（用量折叠缺陷已修：normalizeUsage 两桶全无→input+output，单桶 fail-closed 保持；C1/C2 回归净；8da577d4cc） | c3-model-sidebar.md+c-verify-evidence.md | 无 | 关闭 |
| C4 | 手机配对 | 外部包/本仓库零源码（配对守护=外部运行时/APK，诚实标注不可核面） | **已安装启用**（mobile profile 四 bundle，release v1.1.6；包内 version 字段落后 release tag 已记录） | **装配级在案**（~/.dsh/mobile/ 守护密钥对+devices.json 恰 1 台设备，仅记结构） | **待真用户动作**（3 步清单已出） | c4-mobile-pairing.md | 真用户手机操作 | 用户操作清单已列入最终交付 |

## D 独立验证线（负责人：L-LlmVerify）

| ID | 用户功能/项 | 源码 | profile | 运行 | 生产验收 | 证据 | 真实依赖 | 下一步 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | dsh-llm-opencode-go 隔离核验 | **复验闭合**（0.1.20 digest 同旧台账三重互证；旧 ark compat probe seq=12/13 有效不重跑） | 隔离 profile | dump-config exit=0 | **BLOCKED(缺 OPENCODE_API_KEY) 延续**——凭据到位即解 | d-verification.md（c04de6016f） | 外部认证 | 闭合 |
| D2 | dsh-llm-ollama 同上 | **复验闭合**（0.6.17；/v1 归一化无逃生口亲读一致） | 隔离 | 亲读一致 | **BLOCKED(缺 OLLAMA_API_KEY) 延续** | d-verification.md | 外部认证 | 闭合 |
| D3 | dsh-llm-grok 同上 | **复验闭合并推进**（判定对象 0.3.10→0.3.11：digest MATCH、增量 8 文件全在搜索面、认证面同构） | 隔离 profile d3-grok-0311 | dump-config exit=0 | **BLOCKED(xAI 订阅 OAuth 会话) 延续**（grok-oauth.json 不存在） | d-verification.md | 外部 OAuth | 闭合 |
| D4 | dsh-llm-commandcode 同上 | **复验闭合**（0.1.19；端点硬编码+凭据名 lib/index.js:230 亲读一致） | 隔离 | 亲读一致 | **BLOCKED(缺 COMMANDCODE_API_KEY) 延续** | d-verification.md | 外部认证 | 闭合 |
| D5 | dsh-ponytail 同上 | **复验闭合**（0.2.5 latest 未变） | 隔离 | 旧静态+装配证据有效 | **SKIP(Web 真机 headless) 维持** | d-verification.md | 真机环境 | 闭合 |
| D6 | dsh-llm-providers-ui+codex 插件外部包源码/版本/配置核对 | **复验闭合**（事实纠正：workspace:52=minimumReleaseAgeExclude 豁免非 pin；真实声明 ^0.84.2+lock 0.84.2；上游 latest 0.85.1 不在范围内） | n/a | Worker 只读评估（零 install/build） | **维持 0.84.2**（强升必致宿主+四外部插件双实例树；升级触发=外部插件声明 ^0.85 或仅 0.85.x 携必需目录条目） | d6-piai-delta.md+d-verification.md | 无 | 闭合 |

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
- W-3（2026-09-07 晚）：实链缺口立 owner——编排宿主正式运行消费者（dispatch→assigned/developing→Worker 交付+真实 checks→reviewing→recordReview→submit→现有 project_integrate，复用 AgentEvidenceJournal，禁预制造 passed/submitted）派 A2（387b0963）；C2 出测试/证据面设计稿对齐；优先于并发扩张。main@0350415ac8（durable ack f4b32013ed+真实挂载 0350415ac8+devframe-profile 隔离层 aea4e51925）。
- W-4（2026-09-07 晚）：接口裁定（V1.2）——checks/review 消费者复用其 task-consumer/delivery-consumer（./task-consumer、./delivery-consumer、./consumer，含 devframe/task-delivery 最新 delivery 精确引用），A2 不另造；A2 收窄至 host/bootstrap/profile 接线+真实根工作树/锁+startProject+leadRoleLanding+每任务已批准 digest+角色 allowlist+实际 shipped 工具+真实模型/重启验收。main@53884943fe（C harness 双 patch+全链设计稿+zh locale 小修）。
