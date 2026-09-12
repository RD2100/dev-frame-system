# Shadow project router

English | [中文](shadow-router.zh.md)

The shadow-router subsystem is the Shadow-side router of the pluginized agent hierarchy: it routes user intent between independent project roots. It keeps one controller binding per workspace in its own `shadow_router` storage domain, provisions each project's independent controller root session with exact `cwd` metadata, persists every cross-root delivery twice — the sender's `queued` intent and the target-accepted `received` input — with `completed` as a separate durable state, and installs exactly four project tools (`project_open`, `project_send`, `project_status`, `project_stop`) into the one agent scope the host designates as Shadow. Stopping is per-project: other bindings, their controllers, and their queues are untouched. The [package README](../../packages/experimental/shadow-router/README.md) owns the mount configuration and the model experience.

## Service surface

`ctx.shadowRouter` is the router. Its core operations:

- `markShadow` — installs the four project tools into that agent's scope and nothing else; every other scope resolves none of them.
- `openProject`, `sendToProject`, `stopProject`, and `projectStatus` — the same methods the four tools dispatch to: open resolves one authorized existing directory to a workspace and controller root, send delivers one bounded `work`/`note` message and returns a `received` receipt that never claims completion, status reads one project or a bounded page, stop stops exactly one project and reports stopping until the host confirms.
- Host-only seams the model never reaches — `setActiveGoal` authorizes one open run per project, `completeDelivery` settles a received delivery, `confirmProjectStopped` finishes a stop, and `recoverDeliveries` and `reconcileProject` converge interrupted rows on restart.
- Queries — `findBinding`, `listBindings`, and `listDeliveries` answer from the index restored at start.

## Contracts

Every failure returns a structured `SHADOW_*` code on `ShadowRouterError` (stale revision, unknown workspace, unauthorized caller, oversized text, queue full, root missing or unauthorized, roots overlap, profile conflict, goal stale or not authorized, receiver closed, needs attention, project stopped, request conflict, invalid config or request, persistence) — never raw storage errors. Bindings, deliveries, and the replay journal live in the `shadow_router` [storage domain](storage.md) (bindings, deliveries, and requests tables). Provisioning is a per-project state machine (`reserving → provisioning → ready`) that persists each step before acting on it, so a crash at any point leaves a row a later open or host reconcile converges around. `sendToProject` persists the sender intent as `queued` first and then marks the target-accepted input `received`; `completed` is a controller-side fact the host settles separately, and those are the only forward transitions — cancelled queued rows stay visible with a reason. Every open/send/stop stores its normalized input hash and result keyed by the caller's `requestId`, so a retry replays the stored result and the same id with different input fails loud with `SHADOW_REQUEST_CONFLICT`. Configuration is fail-closed: an empty `authorizedRoots` opens nothing, and the config also fixes `controllerProfile`, `maxPendingDeliveries`, `maxMessageChars`, and `statusPageSize`.

## Boundaries

Routing reuses workspace-registry canonical-path facts (the `fs.realpath` canon, alias collapsing, segment-aware overlap checks) from the [workspace](workspace.md) subsystem, but agent-team mailbox member validation is deliberately not reused — a Shadow target is authorized by the binding store, not by [team membership](agent-team.md). The binding records it reads are documented at [session identity bindings](session-identity.md), controller roots are provisioned through the [session](session.md) store, and `setActiveGoal` authorizes against the [goal](goal.md) identity a run is bound to. Forwarding received input into the controller's session log is the host composition's job, so a bare mount receives nothing model-visible.

<!-- BEGIN GENERATED cordis-surface (gen-cordis-catalog.ts) — do not edit between markers -->

<a id="cordis-surface"></a>

## Cordis API

Generated from source by `scripts/gen-cordis-catalog.ts` (verified fresh by `pnpm run verify-cordis-catalog` in doc-sync; regenerate with `pnpm run gen-cordis-catalog`) — the language sides differ only in locale-specific paired document paths. Signature blocks use a `ts cordis-catalog` fence and keep the original source JSDoc; dispatch modes are defined in the [primer](../cordis-primer.md#dispatch-modes), and the framework-inherited `ctx` API lives in [cordis-api/inherited.md](../cordis-api/inherited.md).

<a id="ctxshadowrouter--shadowrouter-abstract-seam"></a>

### `ctx.shadowRouter` — `ShadowRouter` (abstract seam)

Abstract shadow router service. Subclass, implement the abstract methods, and load the subclass as a plugin — it registers as `ctx.shadowRouter` (one implementation per context; loading a second throws, which is cordis' standard duplicate-service behavior).

Implementations must honor these semantics:

- Every routing mutation is serialized on one operation chain and written through to the implementation's durable authority, so the durable rows stay the only record of truth and the in-memory index is a projection.
- sendToProject persists the delivery twice on purpose: first as the sender intent (`queued`), then as the target-accepted input (`received`) — and emits Events['shadow/delivery-received'] at that transition, exactly once per real conversion, after the durable write commits. `completed` stays a separate durable state the controller side settles via completeDelivery.
- Recovery convergence (recoverDeliveries) that lands a queued row on `received` is the same transition and emits the same event, so event-driven consumers do not miss recovered work.

```ts cordis-catalog
/**
 * Designate one live agent as the host's Shadow and install the four
 * project tools — and nothing else — into its scope. The host chooses the
 * profile; workers, leads, and reviewers are never marked, and marking is
 * idempotent.
 * @param agent - The live agent the host designates as Shadow.
 */
abstract markShadow(agent: Agent): void

/**
 * Whether one agent is the designated Shadow.
 * @param agent - The agent to check, or `undefined` when the caller has no attached agent.
 * @returns true when the agent is currently designated as the host's Shadow; the predicate also narrows `agent` to `Agent`.
 */
abstract isShadow(agent: Agent | undefined): agent is Agent

/**
 * Open (or resolve) one project: canonicalize and authorize the root, reuse
 * the workspace registry's identity, and converge the controller binding —
 * reserving a controller session id and persisting the in-creation
 * association before the session exists. Repeated opens deduplicate; a
 * request id replayed with different input conflicts.
 * @param caller - The designated Shadow session.
 * @param request - Existing authorized path and stable request id.
 * @returns the controller association.
 */
abstract openProject(caller: Agent | undefined, request: ProjectOpenRequest): Promise<ProjectOpenResult>

/**
 * Deliver one bounded message to a project's controller. The delivery is
 * persisted twice on purpose: first as the sender intent (`queued`), then as
 * the target-accepted input (`received`). The receipt never claims
 * completion; `completed` is a separate durable state the controller side
 * settles via {@link ShadowRouter.completeDelivery}.
 * @param caller - The designated Shadow session.
 * @param request - Target workspace, asserted revision and work ownership, mode, and text.
 * @returns the delivery receipt.
 */
abstract sendToProject(caller: Agent | undefined, request: ProjectSendRequest): Promise<ProjectSendResult>

/**
 * Stop one project in isolation: close its receiving, cancel its pending
 * deliveries (kept visible, never dropped), and park the binding in
 * `stopping` until the host confirms quiescence via
 * {@link ShadowRouter.confirmProjectStopped}. Other projects are untouched.
 * @param caller - The designated Shadow session.
 * @param request - Target workspace, asserted revision, and stable request id.
 * @returns the stop receipt.
 */
abstract stopProject(caller: Agent | undefined, request: ProjectStopRequest): Promise<ProjectStopResult>

/**
 * Read one project or one bounded page of projects. The read never mutates
 * durable state, never appends a session event, and never wakes a model;
 * every row carries the observation instant, and a `received` receipt is
 * reported verbatim instead of being read as completion.
 * @param caller - The designated Shadow session.
 * @param request - Optional workspace id plus bounded page controls.
 * @returns the observed status.
 */
abstract projectStatus( caller: Agent | undefined, request: { readonly workspaceId?: string; readonly cursor?: number; readonly limit?: number }, ): Promise<ProjectStatusResult>

/**
 * Confirm one `stopping` project quiescent and finish its stop. The host
 * calls this once the project's own work has drained; no model tool does.
 * Already-stopped bindings resolve without writing.
 * @param workspaceId - The project whose stop completes.
 * @returns the stopped binding.
 */
abstract confirmProjectStopped(workspaceId: WorkspaceId): Promise<ShadowBindingRecord>

/**
 * Host-plane open: the same gated flow the `project_open` tool runs, driven
 * by the designated Shadow's authority for host status surfaces (the Web
 * Shadow card). Path canonicalization, authorization, replay, and
 * provisioning are identical to the tool path.
 * @param request - Existing authorized path and stable request id.
 * @returns the controller association.
 */
abstract openProjectForHost(request: ProjectOpenRequest): Promise<ProjectOpenResult>

/**
 * Host-plane delivery: one `work` message to a project's controller through
 * the same delivery channel the `project_send` tool runs, with the binding's
 * current revision and authorized open run supplied by the router itself.
 * @param request - Target workspace, bounded message text, and stable request id.
 * @returns the delivery receipt.
 */
abstract sendToProjectForHost( request: { readonly workspaceId: string; readonly text: string; readonly requestId: string }, ): Promise<ProjectSendResult>

/**
 * Host-plane release: stop the project through the same gated flow the
 * `project_stop` tool runs and confirm quiescence in one step, so the
 * host surface's release closes the project instead of parking it
 * mid-stop. Pending deliveries stay visible as cancelled.
 * @param request - Target workspace and stable request id.
 * @returns the stop receipt; `status` reflects the completed stop.
 */
abstract releaseProjectForHost( request: { readonly workspaceId: string; readonly requestId: string }, ): Promise<ProjectStopResult>

/**
 * Record the workspace's authorized open run. Deliveries may only arrive
 * while the asserted Goal/acceptance association matches this record, which
 * is what keeps a previous Goal's message out of the controller's current
 * Goal. The host (controller side) calls this; no model tool reaches it.
 * @param workspaceId - The project to authorize the run for.
 * @param goalId - The authorized Goal.
 * @param acceptanceHash - The authorized acceptance association.
 * @returns the updated binding.
 */
abstract setActiveGoal(workspaceId: WorkspaceId, goalId: string, acceptanceHash: string): Promise<ShadowBindingRecord>

/**
 * Settle one received delivery as completed. `completed` is a controller
 * side durable fact, distinct from the `received` receipt; the host calls
 * this, and no model tool does. A receiver that is `stopping` or `stopped`
 * cannot settle: the call rejects with `SHADOW_RECEIVER_CLOSED` and the row
 * stays `received`.
 * @param workspaceId - The project the delivery belongs to.
 * @param messageId - The delivery to settle.
 * @returns the updated delivery.
 */
abstract completeDelivery(workspaceId: WorkspaceId, messageId: ShadowMessageId): Promise<ShadowDeliveryRecord>

/**
 * Converge one workspace's queued deliveries after a restart or a Goal
 * switch: a still-authorized delivery becomes `received`; a stale one is
 * cancelled with a visible reason instead of being forwarded to a Goal it
 * was never bound to.
 * @param workspaceId - One project, or omitted for every project.
 * @returns the converged deliveries.
 */
abstract recoverDeliveries(workspaceId?: WorkspaceId): Promise<readonly ShadowDeliveryRecord[]>

/**
 * Converge one workspace's provisioning row around its reserved session id:
 * create the reserved session when it is still missing, complete the bind
 * when the session matches, and park mismatches as `needs_attention`. The
 * host calls this after a restart; `project_open` runs it implicitly.
 * @param workspaceId - The project to converge.
 * @returns the converged binding.
 */
abstract reconcileProject(workspaceId: WorkspaceId): Promise<ShadowBindingRecord>

/**
 * Read one binding from the restored index.
 * @param workspaceId - The project whose binding to read.
 * @returns the binding record, or `undefined` when the workspace has no binding.
 */
abstract findBinding(workspaceId: WorkspaceId): ShadowBindingRecord | undefined

/**
 * Read every binding in stable (createdAt, workspaceId) order.
 * @returns every binding record in the index.
 */
abstract listBindings(): readonly ShadowBindingRecord[]

/**
 * Read every delivery of one project (or all projects), oldest first.
 * @param workspaceId - Limits the result to one project; omit it to read every recorded delivery.
 * @returns the matching delivery records in stable (createdAt, messageId) order.
 */
abstract listDeliveries(workspaceId?: WorkspaceId): readonly ShadowDeliveryRecord[]

/**
 * Read the host-facing aggregate status: the configured Shadow designation,
 * its liveness, the canonical authorized roots, and every binding row. The
 * read is synchronous and side-effect free, and never model-facing — host
 * status surfaces (the Web Shadow card) consume it through the Shadow
 * controller, so it carries no Shadow-caller gate and no page bounds.
 * @returns the aggregate status snapshot.
 */
abstract readStatus(): ShadowRouterStatus
```

Types: [Agent](core.md) · [WorkspaceId](workspace.md)

Source: [`packages/experimental/shadow-routing/src/service.ts`](../../packages/experimental/shadow-routing/src/service.ts)

<a id="shadow-events"></a>

### `shadow/*` events

<a id="shadowdelivery-received--emit"></a>

#### `shadow/delivery-received` — emit

One delivery entered `received` — the durable target-acceptance transition. Observe-only: listeners forward or record the accepted input, but the router's durable rows stay the only authority, and the event never exposes a mutation verb. A listener mounted after the transition (or a process restart) still converges through the provider's recovery and index reads.

```ts cordis-catalog
/**
 * One delivery entered `received` — the durable target-acceptance
 * transition. Observe-only: listeners forward or record the accepted
 * input, but the router's durable rows stay the only authority, and the
 * event never exposes a mutation verb. A listener mounted after the
 * transition (or a process restart) still converges through the
 * provider's recovery and index reads.
 * @param workspaceId - The project the delivery belongs to.
 * @param delivery - The frozen delivery record snapshot as it entered `received`.
 * @mode emit
 */
'shadow/delivery-received'(workspaceId: WorkspaceId, delivery: ShadowDeliveryRecord): void
```

Types: [WorkspaceId](workspace.md)

Source: [`packages/experimental/shadow-routing/src/service.ts`](../../packages/experimental/shadow-routing/src/service.ts)
<!-- END GENERATED cordis-surface -->
