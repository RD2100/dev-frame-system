---
description: P05 required-checks 完成策略设计（AT1-05 变体"削弱必需检查"的依据面）：required 清单声明与身份（canonical digest）、纯函数比对面与判别联合 verdict、错误码族、与 DevFrameReviewGate + verifySourceFingerprint 的完成合取序与证据链、拒绝层分解与串行波 GAP 登记（p/p05checks @ 本波）。
---

# P05 required-checks 完成策略设计（配置 schema + 比对面波）

- 基点：`p/p05checks` @ `fc34223e28`（=worktree HEAD）。范围：`packages/experimental/devframe/src/required-checks.ts`（新）、`src/index.ts`（出口一行）、`tests/required-checks.spec.ts`（新，34 例）、本文档。**零 diff**：`controller/goal-binding.ts`、`events.ts`、`session-journal.ts`、`shared/types.ts`、`packages/experimental/agent-evidence/**`、`packages/experimental/agent-reliability/**`（本波禁区逐条未触碰）。
- 权威断言面：[anchor-matrix AT1-05](anchor-matrix.md)（"削弱必需检查"行：全树无 required-checks 模型；approved 检查配置仅以不透明 acceptanceHash 存在，无配置存储与完成策略比对）、[at105-rejection-matrix.spec.ts 头部对照表](../../../packages/experimental/agent-evidence/tests/at105-rejection-matrix.spec.ts)（"削弱必需检查 = GAP，归产品波 + P05 src 波"）、[testAndAcceptance.md AT1-05/R1.3](../../../docs/testAndAcceptance.md)（"required checks cannot be silently weakened"）。本波交付该变体的**依据面**：一个可从完成/审查域调用的纯比对面——给定 approved 配置与真实执行结果集，产出可审计的判别联合 verdict。存储与接线归串行波（见 GAP 节）。
- 放置理由：与 fprecompute-design.md、p05harden-design.md 同目录（`.agents/devframe/p22/`）——同系列设计先例、同一审计链（anchor-matrix 引用面都在此）、同一读者（总控/组长）；不放包内 `docs/`：devframe 包 README 受 doc-budget 门约束且本波无使用面文档义务（README 未随 fprecompute 更新的先例见"残余"节）。

## 模型：required 清单的声明与身份

**声明**。一条 required check = 稳定 `checkId` + 精确命令三元组（`executable`、`arguments`（argv 有序）、`cwd` 绝对目录）。配置 = `{ version: 1, checks: [...] }`，checks 非空且 checkId 唯一（zod strict，schema 即 `requiredChecksConfigSchema`）。checkId 与 durable 证据面 `DevFrameCheckResult.checkId` 同词表；命令三元组与 `DevFrameCheckResult` 的 executable/arguments/cwd 同构——**配置与证据的每个字段一一对应，比对无需任何映射层**。

**身份**。配置的规范身份 = `requiredChecksDigest(config)` → 品牌串 `dsh-required-checks-v1-<sha256 hex>`：

1. 每条 check 序列化为**固定字段序**的 JSON 记录（checkId, executable, arguments 数组原序, cwd）——不依赖对象 key 插入序，跨进程/跨构造方式逐字节确定；
2. 记录串按字典序排序（checkId 唯一由 schema 钉死，全序无歧义）——**清单语义是集合**：仅调换声明顺序的两个配置同 digest；
3. 外层 JSON 再固定序包裹 `{ version, checks: [records...] }` 过 sha256；前缀 `dsh-required-checks-v1` 与指纹引擎的 `dsh-source-fp-v1` 同代际约定，换代即变值。

argv **数组原序**参与身份（argv 顺序是命令语义的一部分），数组**元素**不排序。身份不覆盖语义等价归一（路径大小写、PATH 解析、`pnpm` vs `npx`）——见"放弃的替代案"。

**与 acceptanceHash 的关系（裁定边界）**：`AcceptanceHash` 的既有语义是"user-approved objective and check configuration"的稳定哈希。本 digest 是其中 **check-configuration 分量的规范输入**；objective 分量与最终合成（objective + digest → acceptanceHash）属宿主组合面，本波不实现、不宣称 `requiredChecksDigest(config) === binding.acceptanceHash`。独立品牌 `RequiredChecksDigest`（不复用 `AcceptanceHash`）正是为了在类型层阻止这一混淆。串行波把配置**存储**（digest → config 的可解析登记）接上后，"binding.acceptanceHash 解析到一份 digest 参与合成的 stored config"才成为可执行断言——该存储面登记为 GAP。

## 完成策略（比对面语义）

`evaluateRequiredChecks(config, executed): RequiredChecksVerdict`，`executed` 类型即 durable `DevFrameCheckResult[]`（type-only 自 events.ts，编译期钉死与 durable 载荷的形状兼容）。一条 required check 被满足，当且仅当 executed 中存在一条结果同时满足：

1. `checkId` 相等；且
2. 命令**精确相等**（executable、argv 逐元素原序、cwd——零归一化）；且
3. 真实 `status === 'passed'`（skipped/failed/timed_out/cancelled/unknown 一律不算，与 events.ts 聚合规则"passed 需全部 passed"同词表）。

策略裁定（各附理由）：

- **命令零归一化**（镜像 `verifySourceFingerprint` 的品牌串等值先例）：削弱攻击的形态就是"同 checkId 换轻量命令"；任何"看起来等价就放行"的归一化（路径 resolve、去重 flag、前缀匹配）都是给攻击留等价类。authority 恒为 approved 配置侧。
- **配置外执行面忽略**：config 声明的是**必须项**不是**允许项**；额外探索性检查不构成削弱（削弱 = 必需项缺失/被改/未过）。
- **同 checkId 多条执行**：存在任一"命令精确匹配"的执行即以它为准（多臂中选 match 臂）；全部偏离 → COMMAND_MISMATCH 且 `executed` 侧**全列**（证据侧完整呈现，执行序）。durable schema 已拒绝重复 checkId（events.ts verificationEventSchema refine），该纯面政策只为函数全定义性；用例同时钉住两层口径（见用例节）。

## 错误码族与 verdict 形态

`RequiredChecksError extends Error`（message+code，对齐 `GoalBindingError`/`SourceFingerprintError`/`AgentEvidenceError` 形态），族码 `RequiredChecksErrorCode`：

| 码 | 触发 | 层 |
| --- | --- | --- |
| `REQUIRED_CHECKS_INVALID_CONFIG` | 配置未过 `requiredChecksConfigSchema`（zod issues 全量聚合进 message，cause 携带原 ZodError） | 解析边界（`decodeRequiredChecksConfig`，形态对齐 `decodeDevFramePayload` 的 durable 入口风格） |
| `REQUIRED_CHECKS_MISSING` | required checkId 无任何执行结果 | 完成策略（verdict 数据，非 throw） |
| `REQUIRED_CHECKS_COMMAND_MISMATCH` | checkId 有执行但命令偏离配置 | 同上 |
| `REQUIRED_CHECKS_NOT_PASSED` | 命令精确执行但 status 非 passed | 同上 |

**政策拒绝是数据不是异常**：拒绝面 = `RequiredChecksVerdict` 判别联合（`kind: 'satisfied' | 'unsatisfied'`，形态对齐 `VerifyVerdict` 的 match/mismatch 先例）。`unsatisfied` 臂按**配置序**携带逐 check violation（`reason` 即上述族码，兼作未来 admission 的路由判别）；COMMAND_MISMATCH 臂**双值呈现**——`configured`（approved 权威侧）vs `executed`（真实证据侧，全列）——直接复刻 fprecompute 裁定里 mismatch 臂"记录主张 vs 可信侧全摘要"的可审计性原则。两臂都携带 `digest`：verdict 自描述"哪份配置被评估"，未来 completion 记录可单独入账。理由：一次拒绝常含多条违规（多缺一项、一项被改），throw 只能携带首个；证据链要求全量可入账。

## 拒绝层分解（何时何层）

| 层 | 面 | 状态 |
| --- | --- | --- |
| durable 事件 schema（伪造成功/错快照） | `verificationEventSchema` superRefine（passed 聚合规则、snapshotId 交叉） | 已落盘（既有），本波零 diff；**不含** required-checks 覆盖规则（GAP，见下） |
| journal 写入门（错审查者） | `DevFrameReviewGate` 构造器强制 + `AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED` | 已落盘（缺口①），零 diff |
| 配置解析边界 | `decodeRequiredChecksConfig` → `REQUIRED_CHECKS_INVALID_CONFIG` | **本波落盘** |
| 完成策略比对 | `evaluateRequiredChecks` verdict | **本波落盘**（纯面，显式调用，不进热路径——与指纹引擎同一边界纪律） |
| 完成 admission 合取 | controller/宿主组合三谓词 | **未落盘**（GAP，串行波；本波不虚构任何拒绝路径） |

诚实钉子：本波用例**真实演示**"schema-valid 但被削弱的 verification 载荷能通过 durable schema 解码、被比对面拒绝"——这正是 GAP 的可执行表述：durable schema 尚无覆盖规则，拒绝力在比对面，二者接线归串行波。

## 与 ReviewGate + verifySourceFingerprint 的组合（合取序与证据链）

完成 admission（未来层）= 三个已落盘纯谓词的**合取**，缺一即拒：

```
admit(completion) ⟺ 检查齐备 ∧ 审查通过 ∧ 指纹 match
  检查齐备 = evaluateRequiredChecks(storedConfig, verification.checks).kind === 'satisfied'   （本波）
  审查通过 = review.decision === 'pass'，且 reviewer 经 DevFrameReviewGate/EvidenceReviewGate 授权  （缺口①已落盘）
  指纹 match = verifySourceFingerprint(worktreePath, binding.sourceFingerprint).kind === 'match' （案 B 已落盘）
```

**合取序论证**（作为纯谓词可交换；作为**证据链**有固定评估序，供未来 admission 采纳）：

1. **指纹 match 先行**：它锚定"证据关于哪棵树"。树已漂移时 checks/review 内容再完整也无意义——最早最便宜的无效化（三次只读 git 子进程，显式调用，与热路径边界登记②一致）；mismatch 双值证据链（记录主张 vs 现算全摘要）已由案 B 交付。
2. **检查齐备次之**：它锚定"在该树上真实跑了什么 vs 批准了什么"，输入依赖 fingerprint match 的结论（比较才有意义）与 stored config（经 acceptanceHash 身份解析——存储面 GAP）。
3. **审查通过收尾**：它锚定"谁判定"。journal 写入门已在事件落日志前强制授权（缺口①），admission 只消费其通过决定。

三臂各自的拒绝证据（指纹 mismatch 双值 / required-checks violation 逐条双值 / review findings）形态同构：**记录主张 vs 可信侧**，可独立入账、可审计。合取面本身零新谓词——全部由已落盘面组合，串行波只做接线。

## 配置 schema 面（zod 形态）

- zod v4、`.strict()`、`superRefine`/`refine`、`as z.ZodType<T>` 钉声明接口——逐条对齐 events.ts 既有用法。
- `trimmedString` 原语在模块内**本地镜像**（events.ts 的同名原语是模块私有的且 events.ts 本波冻结；不可导出复用，重复 3 行是冻结边界的最小代价，JSDoc 注明镜像关系）。
- **argv 元素不做 trimmed 约束**（`z.array(z.string())`，对齐 durable checkResultSchema 的 argv 面）：削弱防御在精确等值，不在字符串卫生（真实 CLI 接受空串 argv）；checkId/executable/cwd 是标识符/路径，取 trimmedString。
- 解析入口 `decodeRequiredChecksConfig(unknown)`：untrusted durable 边界（未来配置存储的读取入口），zod 失败聚合为 `REQUIRED_CHECKS_INVALID_CONFIG`。typed 同进程调用面直接传 validated 接口，不再重复校验（仓库"信任 typed 边界"规则）。

## 用例规约（34 例全部落盘并通过）

- 解析边界（14）：合法配置原样通过；argv 空串元素合法（钉卫生豁免）；rejection message 命名 offending path（`checks.0.checkId`）；参数化 11 个拒绝形状（空清单、重复 id、空白 id、空 executable、未 trim cwd、错版本、顶层/检查级未知键、非串 argv、非对象根、缺 checks）逐个断言 `REQUIRED_CHECKS_INVALID_CONFIG`。
- digest（4）：确定性；**清单序无关 + key 插入序无关**（规范化算法的可执行论证）；`dsh-required-checks-v1-<64hex>` 形状；7 种语义突变（改名/换 executable/换 argv 元素/换 argv 序/换 cwd/删项/加项）逐一变值。
- verdict（14）：全齐 satisfied（乱序执行）；配置外执行忽略；MISSING；COMMAND_MISMATCH 双侧呈现（多候选全列）；executable/cwd 两削弱向量参数化；5 个非 passed 状态参数化钉"仅 passed 计数"；多违规按配置序累积；重复 checkId 全定义性边界（注释钉 durable 层禁止重复的分工）；reject 臂携带 digest。
- durable 组合（2）：真实载荷过 `decodeDevFramePayload('devframe/verification')` 解码后 `decoded.checks` 直接进比对面（编译期钉死 `DevFrameCheckResult[]` 形状兼容）→ satisfied；**schema-valid 削弱载荷**（改命令 + 缺项，全 passed）解码成功（断言 `checks` 长度=2，把"durable schema 无覆盖规则"钉成可执行事实）后 verdict = COMMAND_MISMATCH + MISSING。

## GAP/未尽清单（串行波，fail-loud 登记）

1. **配置存储**：digest → config 的持久登记与 acceptanceHash 合成（objective 分量 + 本 digest）无实现面；`decodeRequiredChecksConfig` 即为其读取入口预留。
2. **durable schema 自描述**：`devframe/verification` 不携带覆盖声明、schema 无覆盖规则（本波 events.ts/schemas/journal 接线冻结，属串行波；削弱载荷过 schema 的用例即为该 GAP 的可执行钉子）。
3. **完成 admission 接线**：三谓词合取的宿主/controller 组合面未落盘；admission 的错误路由（violation reason → 稳定码）设计已备（族码即路由面），实现待波。
4. **README source map 行**：`src/required-checks.ts`（及先波 `src/source-fingerprint.ts`，同样缺席）未入 devframe README Source map——先例：fprecompute 波未更新 README；本波保持最小面并在此登记，待使用面稳定（admission 接线波）一并补双语 README 与 i18n 配对重录。

## 放弃的替代案（一行各记）

- verdict 改 throw：一次拒绝可含多条违规，异常只载首个，丢证据链（mismatch 臂双值先例同源）。
- digest 复用 `AcceptanceHash` 品牌：与"objective+checks 全合成"语义混同，品牌存在的意义即阻止该混淆。
- 配置进 `devframe/verification` 事件自描述：events.ts 本波冻结，journal/schema 接线归串行波。
- cwd/executable 归一化（resolve 绝对路径、PATH 查找）：制造"等价类"攻击面与平台相关行为，违背权威侧精确语义。
- argv 前缀/集合匹配：任何容忍度都是削弱攻击的重新入口。
- digest 序列化依赖输入对象 key 序：跨进程身份不确定（构造序即输出序）。
- 比对面收 `unknown` 自行解析：typed 同进程边界信任 TS，解析属 schema 面单一职责。

## 残余

- POSIX/大清单（数千条 required checks）digest 性能未压测（O(n log n) 排序 + 单次 sha256，量级无虞）；无平台敏感面（JSON/sha256/字符串序跨平台确定——JS 字符串比较按 UTF-16 码元，同一模块实现下跨平台一致）。
- 本波环境：Windows（win32）本地跑 vitest/tsc/build 全绿；无 429/上游限额事件；无禁区触碰。
