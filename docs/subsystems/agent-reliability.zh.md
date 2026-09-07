# 代理可靠性服务

[English](agent-reliability.md) | 中文

代理可靠性子系统把 agent（智能体）工作在各 seam 处所需的防御式模式实践收拢为一个 Cordis 服务：DevFrame 进程树停止暴露为一次串行调用——先关闭准入、只取消已知后代、flush 后才释放写入者；一个派发 pre-step，拒绝每个工作绑定与当前获准身份不匹配的操作；不确定调用调解——先探测外部状态、最多重试一次、且只在探测证明效果不存在之后重试；以及 flush 屏障——flush 失败时关闭准入并保留写入权。[包 README](../../packages/experimental/agent-reliability/README.zh.md) 负责挂载配置与模型体验。

## 服务面

`ctx.agentReliability` 是可靠性服务。核心操作：

- `openAdmission`、`closeAdmission`、`assertAdmitted` — 接线派发 pre-step；准入按派发代次为恰好一个工作绑定身份打开，不匹配或陈旧的绑定在任何模型或工具工作运行前被拒绝。
- `reconcileUncertainCall` — 探测先检查外部状态；重试至多运行一次且只在探测返回 `absent` 之后运行，`confirmed` 仅凭探测结算，`still_uncertain` 不重发、原样返回未解决。
- `flushBarrier` — flush 失败立即关闭准入并报告 `writerRetained: true`；释放写入权是宿主的动作。
- `stopProject` — DevFrame 进程树停止经本服务原样再导出。

## 约定要点

pre-step 拒绝在 `AgentReliabilityError` 上携带两个可区分的稳定代码——`AGENT_RELIABILITY_ADMISSION_CLOSED` 与 `AGENT_RELIABILITY_IDENTITY_MISMATCH`——因此派发接线能区分「从未准入」与「错误代次」。准入是初始关闭的进程本地状态；重启会丢失获准身份，宿主显式重新打开准入之前每个 pre-step 都拒绝。调解器在调用之间不持有状态并信任其探测；本服务不新增自己的持久停止状态，任何值都不会到达模型请求，因此不新增会话事件。

## 子系统边界

底层实践由[防御式模式](../defensive-patterns.zh.md)负责，停止契约在 [devframe 包](../../packages/experimental/devframe/README.zh.md) 中只有一份实现、一处测试归属。[项目任务控制器](project-controller.zh.md) 把它的派发/记录两分建立在同一个准入状态之上，获准身份正是 [goal](goal.zh.md) 子系统持久化的 goal 绑定身份。本服务不注入任何服务，也从不阻塞激活。

<!-- BEGIN GENERATED cordis-surface (gen-cordis-catalog.ts) — do not edit between markers -->

<a id="cordis-surface"></a>

## Cordis API

Generated from source by `scripts/gen-cordis-catalog.ts` (verified fresh by `pnpm run verify-cordis-catalog` in doc-sync; regenerate with `pnpm run gen-cordis-catalog`) — the language sides differ only in locale-specific paired document paths. Signature blocks use a `ts cordis-catalog` fence and keep the original source JSDoc; dispatch modes are defined in the [primer](../cordis-primer.zh.md#dispatch-modes), and the framework-inherited `ctx` API lives in [cordis-api/inherited.md](../cordis-api/inherited.md).

<a id="ctxagentreliability--agentreliability"></a>

### `ctx.agentReliability` — `AgentReliability`

The agent reliability service: stop productization, admission cutoff, reconciliation, flush barrier.

```ts cordis-catalog
/**
 * Open dispatch admission for exactly one work binding identity. Opening
 * replaces the whole generation — the identity AND the cutoff: passing no
 * `cutoff` clears a previous generation's deadline. A generation whose
 * deadline is already past opens fine; its first pre-step call rejects.
 * @param identity - The work binding every pre-step will require.
 * @param cutoff - Optional deadline bound for this generation, a wall-clock
 * epoch millisecond instant the pre-step reads via `Date.now()`. Supplying
 * `cutoff.stop` also schedules the native stop protocol. Reopen or explicit
 * closure disarms an untriggered timer; service disposal awaits a triggered stop.
 * @throws {@link AgentReliabilityError} with code
 * `AGENT_RELIABILITY_ADMISSION_DEADLINE_INVALID` when `cutoff.deadline`
 * is defined but not a finite epoch millisecond instant; nothing is
 * mutated in that case, or when the stop grace is invalid. Throws
 * `AGENT_RELIABILITY_STOP_IN_PROGRESS` if the old stop still owns cleanup;
 * reopening is allowed only after its result settles.
 */
openAdmission(identity: GoalBindingIdentity, cutoff?: AdmissionCutoff): void

/** Close dispatch admission; the identity is kept so stop flows can report it. */
closeAdmission(): void

/**
 * The dispatch pre-step: reject any operation whose work binding does not
 * match the currently admitted identity. Call this before dispatching
 * model or tool work; a rejection means the work never starts.
 * @param identity - Work binding carried by the proposed operation.
 * @throws {@link AgentReliabilityError} with code
 * `AGENT_RELIABILITY_ADMISSION_CLOSED` when admission is closed,
 * `AGENT_RELIABILITY_ADMISSION_DEADLINE_CLOSED` when the current
 * generation's cutoff instant has passed, or
 * `AGENT_RELIABILITY_IDENTITY_MISMATCH` when another identity is admitted.
 * The checks run in that order: a passed deadline is a statement about the
 * window, not the identity, so it precedes the identity check.
 */
assertAdmitted(identity: GoalBindingIdentity): void

/**
 * Reconcile one uncertain call: probe external state first, and retry the
 * original call at most once and only after the probe proved the effect
 * absent. There is no blind-retry path by construction.
 * @param plan - The operation identity, its external-state probe, and its retry.
 * @returns the reconciliation outcome; `unresolved` leaves the decision to the caller.
 */
async reconcileUncertainCall<R>(plan: UncertainCallPlan<R>): Promise<ReconciledOutcome<R>>

/**
 * Run one flush barrier: on success the barrier reports a flushed log; on
 * failure it closes admission and retains write ownership — the writer is
 * never released on top of an unflushed log.
 * @param flush - Flush all participating Session state through native persistence.
 * @returns the barrier outcome with the failure, when one occurred.
 */
async flushBarrier(flush: () => Promise<void>): Promise<FlushBarrierResult>

/**
 * Run one serialized process-tree stop: close admission, cancel only known
 * descendants, flush, and release the writer only after confirmed cleanup.
 * The host serializes calls for the same writer and retains unresolved
 * identities across restart.
 * @param options - Native live handles and the owning project's durable state adapter.
 * @returns `stopped` only after confirmed cleanup and flush; otherwise retained ownership.
 */
async stopProject(options: StopProjectOptions): Promise<StopResult>
```

Source: [`packages/experimental/agent-reliability/src/service.ts`](../../packages/experimental/agent-reliability/src/service.ts)
<!-- END GENERATED cordis-surface -->
