# Agent Note: required-checks 接线与完成 admission

Status: proposed

[English](2026-09-06-required-checks-wiring.md) | 中文

## Problem

AT1-05 的"削弱必需检查"拒绝变体在全树没有任何实现锚点：approved 检查配置仅以不透明的 `acceptanceHash` 存在，没有配置存储可解析它，durable schema 没有任何规则拒绝"记录的 checks 与 approved 集合偏离"的 verification 载荷，也没有 admission 面把"检查齐备"与已落盘的审查授权面、指纹验证面合取。完成声明因此可以在静默删掉或调换某条必需检查的情况下主张成功。设计波（`.agents/devframe/p22/required-checks-design.md`）落了纯面——配置 schema、canonical digest、完成策略评估器——并登记了四个 GAP；本 note 记录收口这些 GAP 的接线波。

## Proposal

在 `packages/experimental/devframe` 内收口四个已登记 GAP：

1. **配置存储与 check-configuration 分量。** `RequiredChecksConfigStore` 接口 + `MemoryRequiredChecksConfigStore` 参考实现按 digest 登记解析后的配置、经 `decodeRequiredChecksConfig` 重装载（未登记的 digest 以 `REQUIRED_CHECKS_CONFIG_NOT_FOUND` fail-loud）；`acceptanceCheckComponent(config)` 命名 acceptanceHash 合成中的 check-configuration 分量——它返回 canonical digest 且绝不宣称 `digest === acceptanceHash`，objective 分量与全合成归宿主波。
2. **durable 覆盖规则。** `devframe/verification` 事件载荷新增自声明覆盖面 `requiredChecks: {config, digest}`；`verificationEventSchema` 在解码时拒绝：声明 digest 与自身 config 不自洽的载荷、声明的 check 未被记录 checks 精确执行（同 checkId 加精确命令三元组）的载荷。真实跑过且失败的必需检查仍作为诚实 failed evidence 解码——passed 判定属 admission 不属 schema。
3. **完成 admission 合取。** controller 域的 `evaluateCompletionAdmission(request)` 按设计钉定的证据链序合取三个已落盘谓词：指纹 match 先（`verifySourceFingerprint` 锚定证据关于哪棵树）、required checks 次（`store.load(digest)` 加 `evaluateRequiredChecks` 锚定跑了什么 versus 批准了什么）、授权审查决定收尾（锚定谁判定；journal 写入门在该记录存在前已强制审查者授权）。violation reason 经既有稳定错误码族路由；结构错误（`SourceFingerprintError`、`RequiredChecksError`）fail-loud 冒泡。评估是显式异步调用——热路径零改动。
4. **README source map。** devframe README 的 source map 双语补 `required-checks.ts` 与 `source-fingerprint.ts` 两行。

## Key design

- **评估序是证据链的一部分。** 指纹先行（最便宜的无效化：树已漂移则后续谓词全部无意义）、检查次之（依赖指纹结论与 stored config）、审查收尾（消费 durable 且经门授权的 pass 决定）。每个拒绝阶段自带证据形态——mismatch 双值、按配置序的逐 check violation、审查的非 pass 决定。
- **品牌边界保持。** `RequiredChecksDigest` 保持独立品牌；接线绝不把它与 `AcceptanceHash` 等同。`acceptanceCheckComponent` 只是分量面，命名使未来宿主波可以组合 `objective + checkComponent` 而无需重新争论身份。
- **schema 与评估器共用同一精确等值实现。** durable 覆盖规则与完成策略都调用 `sameRequiredCheckCommand`，"精确执行"在解码层与 admission 层之间不可能漂移。
- **诚实 failed evidence 保持可解码。** 覆盖规则拒绝的是声明面与执行面的偏离，不是失败本身；真实失败的必需检查作为 failed evidence 入账，只在 admission 处失败。

## Alternatives considered

**schema 只携带 digest（无 config 的自描述）。** 只有 digest 无法在解码时校验内部一致性，durable 载荷不经旁路配置查询就不可审计。自声明 `{config, digest}` 对让 schema 自行校验该主张，载荷自包含。

**本波把 admission 折进 GoalBindingController 生命周期。** 设计的案 A 裁定把生产组装——谁在哪个生命周期点调用 `evaluateCompletionAdmission`、verify 结果在何处入 journal——留给 P23/S4 工具面。本波接进 `start` 或 `resolveResultBinding` 会重新打开设计已登记的热路径边界。

**本波实现持久化 store 后端。** store 接口加 memory 参考实现（`MemoryGoalBindingStore` 先例）是诚实范围；没有消费者就发明 JSONL/SQLite 后端是投机基建。

## Acceptance criteria

- 声明 digest 与 config 不自洽、或声明 check 未被精确执行的 verification 载荷在 `verificationEventSchema` 解码即失败，消息点名 offending check；真实失败但被精确执行的 check 的载荷可解码并读作 failed evidence。
- `evaluateCompletionAdmission` 按 `source-fingerprint`、`required-checks`、`review` 的固定顺序拒绝——指纹坏且 checks 也坏的请求拒绝在指纹阶段——三谓词全过才返回带已验证指纹的 `admitted`；未登记 digest 与 git 失败以结构化错误冒泡。
- `acceptanceCheckComponent` 返回 canonical digest，`RequiredChecksDigest` 品牌与 `AcceptanceHash` 保持区分。
- devframe 套件全绿（含按新语义改写的 durable 组合用例）；包 `tsc -b`、仓库 build、`verify-export-jsdoc`、`verify-translation-pairing`、`gen-cordis-catalog`、`verify-persistence-catalog` 全干净。

## Risks

- 生产组装仍未接线：shipped 运行时尚无任何调用点调 `evaluateCompletionAdmission`——拒绝力当前由用例钉住，P23/S4 工具面落地前产品不可达。
- store 仅有 memory 后端；进程重启丢失已登记配置，在无持久消费者时可接受，出现第一个持久消费者时必须重审。
- 自声明覆盖面使 verification 载荷变大并在每个事件内复制 config；存储契约稳定后，未来波可改为仅按 digest 引用 stored config。
- `acceptanceHash` 的 objective 分量仍无 owner；宿主波组合它之前，两个面在代码与行文中都不得等同。
