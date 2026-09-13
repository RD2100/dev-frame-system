# Shadow 低耦合改造 — Round 2 任务注册表

总控：本会话。用户决定（2026-09-12）：对 Shadow 插件家族做低耦合处理，不必等"第二个使用者"触发条件（此为所有者对仓库 "require a current owner and need" 规则的显式豁免，记录在案）。

## 目标架构（对准 Round 1 识别的成色差异 1、2）

1. **词汇与契约出族**：新建 Service Definition 包 `packages/experimental/shadow-routing/`（npm `@deepseek-ai/dsh-experimental-shadow-routing`）：ctx 键 `shadowRouter` 的声明与抽象服务类（现 ShadowRouter 全部公开面）、全部词汇（品牌 id、binding/delivery 记录、错误码、投递状态机词汇）迁入。形态以 dsh-subprocess / dsh-shell 为模板（抽象类 + 词汇，无实现、无工具、无存储）。消费者（shadow-bridge、shadow-controller）只准依赖本定义包，禁止再 import shadow-router 实现包。
2. **投递事件化**：定义包声明 `shadow/delivery-received` 能力事件（typed event，declaration merging + @mode JSDoc + payload @param；观察型 emit，携带 workspaceId 与投递记录快照）。Provider 在投递进入 `received` 时 emit——含 `recoverDeliveries` 收敛出 received 的路径（否则桥会漏恢复的工作）。
3. **Provider 化**：`shadow-router` 变为纯 Provider：实现抽象类、在定义键上注册、emit 事件；不再被家族其他包 import。工具（project_* 四件）留在 router（Consumer 角色）。
4. **桥事件化**：shadow-bridge 从"主轮询"改为"事件驱动 + 启动对账 + 低频安全网轮询"：挂载时与 loader 结算后各做一次全量对账（补事件前/错过事件的工作），此后以 `shadow/delivery-received` 触发转发；`intervalMs` 语义降级为安全网节奏（README/Note 更新说明）。
5. **profile 层不动**：devframe-profile / shadow-loop 示例行不变（provider 包名未变）；家族 fail-closed 语义由 Cordis inject 语义自然承载。

## 边界

- 不改 agent-loop、SessionEventMap、SDK 投影（插件路径铁律）。
- 交付后流程沿用既定工作流：实现 agent → 独立审阅 agent → 全门禁绿 → 总控提交（--no-verify + 等价门禁）。
- 单 pnpm 进程纪律；禁止 git 写操作（提交由总控执行）。

## 任务

| 任务 | Owner | 所有权 |
| --- | --- | --- |
| R2-A 定义包 + Provider 迁移 + 事件发射 | seam-impl | 新包 shadow-routing/** + shadow-router/** + tsconfig×2 登记 |
| R2-B 桥事件化 + 控制器依赖切换 | bridge-impl | shadow-bridge/** + shadow-controller 的 import 面 |

R2-B 在 R2-A 落地后派发。

## 收口（2026-09-12）

- R2-A ✅：定义包 18 抽象方法 + 全部词汇 + 事件声明；router 纯 Provider（emit 于 send/recover 两路径，replay/冷恢复不 emit）；六项验收 + 目录/图表门禁全绿。
- R2-B ✅：桥事件化（事件主通道 + 启动双对账 + 安全网；串行链恰好一次）；家族 src/ 对实现包 import 零匹配；135 测试 + 六项验收绿。
- 独立审阅 ✅（BLOCK×2 已修复复验）：Note 消费者段落改为已实现事实（双语对称 + sidecar 重录）；event-producer-consumer/module-graph 再生成 + pair 重录。恰好一次链、emit 覆盖、接缝纯度、处置 LIFO、插件路径底线、秘密扫描全部 PASS。
- 已记录的 HEAD 既有问题（非本轮，待后续）：config-catalog zh 侧滞后（约 2 节）；router config 校验分支覆盖 89%；constraints 门禁（root package.json experimental 依赖 + 两包 files 清单）；7 个既有测试失败（subagent provider pre-abort ×5、worker 时序、tool-catalog 规格）。

## 真实模型端到端验证（2026-09-12，:3080 实机）

- **全链路两次跑通**（glm-5.3 真模型，huoshan-2/1）：人→影子对话→shadow_open_project（绑定 ready、controller 会话自动供给）→shadow_message_controller（投递两写 received）→**桥转发**（[Shadow delivery …] 固定头部进入 controller 会话）→controller 真实执行（探索/读/跑测试/修 slugify/重跑）→独立复核 `node --test` 2/2 绿、测试文件未被改动。
- **重启恢复路径验证**：第二轮投递在服务停机期间保持 received，controller 后上线后由桥安全网（60s）补投——恰好一次标记防重生效。
- **现场抓到并修复的真 bug**：影子会话无 cwd → persona 模板 `{{cwd}}` 严格插值抛错 → 影子任何模型调用静默失败。修复：shadowSetup 注册 scoped `cwd` 变量（诚实值），29/29 测试绿。
- **验证期人工解锁（=Round 3 缺口的现场证据）**：授权运行手工注入 shadow_router 存储（setActiveGoal 无产品面）；controllerProfile 默认 'devframe' 指向不存在 preset + 投影缓存陈旧（改 standard + 删 projcache 行）；devframe-profile 层级工具名单与实际部署不符（restate 收敛为最小面）。
- 外部干扰：huoshan-2/1 账号先后 429 限流（第一轮被迫断续）；第二轮在 huoshan-2 配额恢复后跑通。
- 遗留：完成结算（received→completed）未接 goal 回执；影子会话历史加载 session/not-found（_no-cwd 语料缺口）；干净丝滑的完整跑（无 429 中断）待配额稳定。
