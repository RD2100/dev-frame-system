# Agent Note: agent-reliability 的截止限定准入

Status: proposed

[English](2026-09-06-at406-deadline-admission-seam.md) | 中文

## 问题

AT4 交付登记了 GAP AT4-06：短截止过期必须关闭准入并取消有界工作，但 agent-reliability 的 src 没有截止实现缝。树中唯一的截止时刻是 DevFrame stop 的内部宽限界，并未接入准入；anchor-matrix 也注明"无用例，归 P06"。因此派发代际可能无限运行：前置步骤只检查准入关闭与身份，本应在某一时刻结束的窗口会永远放行工作。

## 提案

`openAdmission` 新增可选第二参数，即 `AdmissionCutoff` 请求 `{ deadline }`——一个 epoch 毫秒时刻。打开即整体换代，身份与截止同时替换；不传 cutoff 即清除上一代际的截止。非有限截止在打开处以 `AGENT_RELIABILITY_ADMISSION_DEADLINE_INVALID` 明确失败，且先于任何状态变更，被拒绝的打开不会触碰当前代际。截止已过的代际可以正常打开；它的第一次前置步骤调用即报告窗口已死。

`assertAdmitted` 依次检查：准入关闭（`AGENT_RELIABILITY_ADMISSION_CLOSED`）、截止——当 `Date.now() >= deadline` 时以 `AGENT_RELIABILITY_ADMISSION_DEADLINE_CLOSED`（"admission deadline has passed; dispatch rejected"）拒绝——然后身份（`AGENT_RELIABILITY_IDENTITY_MISMATCH`）。截止时刻本身含端点。顺序是有意的：截止已过是对窗口的陈述，不是对身份的陈述，因此先于身份检查，三种拒绝保持可区分。恢复唯显式重开新代际。`admissionState` 保留存储的两值 `'closed' | 'open'` 联合；截止由前置步骤（唯一派发闸门）强制执行，新增的 `admissionCutoff` getter 报告当前代际存储的时刻。

两项内容明确留待裁定，本提案均不认领：(1) 截止的时间源是前置步骤经 `Date.now()` 读取的墙钟 epoch；单调时长是备选。(2) 已通过前置步骤的在途工作不会在截止时刻被自动取消——AT4-06 的有界取消半边待控制器语义裁定；本缝只切断尚未开始的工作。

## 备选方案

**到期时用定时器急切翻转准入状态。** 落选：它把定时器放进服务，使存储态在调用之间变成时间相关，而前置步骤已是唯一派发闸门——第二个强制执行点可能与它不一致。

**在 `ReliabilityAdmission` 联合里加第三个 `deadline_closed` 值。** 落选：外部消费方按两值联合做模式匹配，错误码已经能区分派发死于何因，联合类型会把同一路由信息复制给每个消费方。

**以单调时长替代墙钟时刻。** 留待裁定，不做静默选择：时长会改变 API 形状（打开时锚定 vs 检查时刻）与钟跳风险画像。

**在打开处拒绝已过去的截止。** 落选：它需要在打开处读钟并与调用方的时钟竞争，而"打开即已死"的窗口是合法状态，由前置步骤在第一次派发时报告。

## 验收标准

- 新用例文件的八个用例全绿（`tests/at4-06-admission-deadline-closed.spec.ts`）：含端点的截止时刻、三种可区分拒绝、非有限守卫不触碰代际、存储态与前置步骤强制执行分离的钉死、重开恢复、无截止回归守卫、对账重试组合、失败刷写后 `ADMISSION_CLOSED` 优先。
- 既有包套件零回归，`tsc -b packages/experimental/agent-reliability` 干净。
- README（中英）与 JSDoc 契约共同描述本缝：`openAdmission` 的 cutoff、`admissionCutoff` getter、两个新错误码、存储态与前置步骤的分离。

## 风险

墙钟跳变：宿主时钟变化会提前或推迟关闭/延长窗口。这对进程内准入可接受——窗口限定的是一个进程的派发代际，不是跨进程契约——但与单调时长备选一并标记待裁定。存储态/生效态的分离可能困扰只读 `admissionState` 而不运行前置步骤的宿主；该分离已在 getter 上记载并有测试钉死。AT4-06 的有界取消半边仍未收口：已通过前置步骤的工作不会被截止取消，其语义待控制器裁定。
