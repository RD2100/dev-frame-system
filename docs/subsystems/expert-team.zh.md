# 专家团队

[English](expert-team.md) | 中文

专家团队子系统在角色数据包之上运行带人工关口的专家流水线：数据包的 `team.yml` 声明阶段、专家角色、依赖、产物与人工关口，编排器按声明顺序经代理注册表派生的角色化子代理执行各阶段。每个阶段专家以回复正文作为产物并附围栏 JSON 结果对象；运行时是唯一写入者——按声明的产物名与包的 JSON Schema 校验结果、原子写入正文，契约失败时在同一会话内有界重试。带关口的阶段让运行停车，直到人类决定到来：批准推进流水线，驳回把产物连同评审者批注退回同一会话作为修订指引。产物落在 `<artifactsDir>/<runId>/` 下的文件中，绝不作为内容回到提示词。[包 README](../../packages/experimental/expert-team/README.zh.md) 拥有挂载配置、包契约与模型体验。

## 服务面

`ctx.expertTeam` 是五个模型工具派发经过的编排器：`listTeams` 服务 `expert_team_list`，`startRun` 与 `getRun` 服务 `expert_team_run` 与 `expert_team_status`，`approve` 为 `expert_team_approve` 记录人工关口决定，`consult` 在任何运行之外回答 `consult_expert`。同一次运行上的并发决定经每次运行的串行门序列化。

## 契约

每个失败都在 `ExpertTeamError` 上携带稳定 `EXPERT_TEAM_*` 代码：挂载时代码（`EXPERT_TEAM_CONFIG_INVALID`、`EXPERT_TEAM_CATALOG_INVALID`、`EXPERT_TEAM_EXPERT_INVALID`、`EXPERT_TEAM_EXPERT_MISSING`、`EXPERT_TEAM_SKILL_MISSING`、`EXPERT_TEAM_SCHEMA_MISSING`、`EXPERT_TEAM_PHASE_CYCLE`）使加载失败，运行时代码（`EXPERT_TEAM_TEAM_MISSING`、`EXPERT_TEAM_TOOL_MISSING`、`EXPERT_TEAM_MODEL_MISSING`、`EXPERT_TEAM_RUN_UNKNOWN`、`EXPERT_TEAM_GATE_PENDING`、`EXPERT_TEAM_RESULT_INVALID`、`EXPERT_TEAM_MODE_UNSUPPORTED`）浮现在工具结果上。运行与阶段状态沿 `pending` → `running` →（`gate-pending`）→ `done` 或 `failed` 推进，关口停车时运行状态报告 `waiting-approval`。失败阶段没有可下传的已接受产物，因此批准被拒绝，而驳回把它作为引导式修订重新打开。

## 边界

五个工具经 loader 插件进入[工具](tools.zh.md)注册表，阶段子代理经代理注册表的 scoped-create 面派生而不是 [agent-hierarchy](agent-hierarchy.zh.md) 派发引擎——阶段会话是有界的角色，不是角色绑定的 worker。运行状态在每个提交点镜像到 `<artifactsDir>/<runId>/run-state.json`，但运行不跨进程恢复。把产物记入 project-memory 委托给数据包的工具允许清单；编排器自身从不调用记忆。

<!-- BEGIN GENERATED cordis-surface (gen-cordis-catalog.ts) — do not edit between markers -->

<a id="cordis-surface"></a>

## Cordis API

Generated from source by `scripts/gen-cordis-catalog.ts` (verified fresh by `pnpm run verify-cordis-catalog` in doc-sync; regenerate with `pnpm run gen-cordis-catalog`) — the language sides differ only in locale-specific paired document paths. Signature blocks use a `ts cordis-catalog` fence and keep the original source JSDoc; dispatch modes are defined in the [primer](../cordis-primer.zh.md#dispatch-modes), and the framework-inherited `ctx` API lives in [cordis-api/inherited.md](../cordis-api/inherited.md).

<a id="ctxexpertteam--teamorchestrator"></a>

### `ctx.expertTeam` — `TeamOrchestrator`

Orchestrates expert-team runs over the mounted catalog. One instance per mounted plugin, published as `ctx.expertTeam`; the model tools are its only consumers.

```ts cordis-catalog
/**
 * List every mounted team, in pack configuration order.
 * @returns the team views shaped for `expert_team_list`, in configuration order.
 */
listTeams(): readonly ExpertTeamView[]

/**
 * Start one run over a mounted pipeline team: mint the run id, create the
 * run directory, and execute phases to the first park point (a gate, a
 * terminal failure, or completion). Every phase expert's tool allowlist is
 * proven mounted before anything is created, so a pack naming an unmounted
 * tool fails without leaving a run behind.
 * @param teamId - Mounted team id.
 * @param input - Free-form run request text (for example, the research topic).
 * @returns the run snapshot at its first park point.
 * @throws {@link ExpertTeamError} with code `EXPERT_TEAM_TEAM_MISSING`
 *   when the team is not mounted, `EXPERT_TEAM_MODE_UNSUPPORTED` when the
 *   team is not a pipeline, or `EXPERT_TEAM_TOOL_MISSING` when a phase
 *   expert names an unmounted tool.
 */
async startRun(teamId: string, input: string): Promise<TeamRun>

/**
 * Read one run's snapshot; serves `expert_team_status` after a run parks.
 * @param runId - Raw run id as the model supplied it.
 * @returns the frozen run snapshot.
 * @throws {@link ExpertTeamError} with code `EXPERT_TEAM_RUN_UNKNOWN` when
 *   the id is malformed or not a live run of this process.
 */
getRun(runId: string): TeamRun

/**
 * Record the human gate decision on a run's single parked phase and resume.
 * An approval marks the gated phase done and executes the remaining
 * pipeline to the next park point; a rejection re-drives the phase session
 * with the reviewer's comment before parking again. The whole span is
 * serialized against concurrent decisions.
 * @param runId - Raw run id as the model supplied it.
 * @param decision - The recorded decision.
 * @param comment - Optional reviewer comment; a rejection comment is the
 *   revision guidance the phase expert receives.
 * @returns the run snapshot after the decision took effect.
 * @throws {@link ExpertTeamError} with code `EXPERT_TEAM_RUN_UNKNOWN` when
 *   the run is not live, or `EXPERT_TEAM_GATE_PENDING` when no gate awaits
 *   a decision or an approval targets a failed phase. An infrastructure
 *   failure while re-driving the phase (agent derivation, model selection,
 *   session creation) settles the run failed and propagates.
 */
async approve(runId: string, decision: GateDecision, comment?: string | undefined): Promise<TeamRun>

/**
 * Consult one expert outside any pipeline: a single bounded turn with the
 * expert persona and allowlist, no artifacts, no run state.
 * @param teamId - Mounted team id.
 * @param expertId - Expert id within the team's pack.
 * @param question - The caller's question.
 * @returns the answer text and its truncation flag.
 * @throws {@link ExpertTeamError} with `EXPERT_TEAM_TEAM_MISSING` /
 *   `EXPERT_TEAM_EXPERT_MISSING` codes from the catalog lookups.
 */
async consult(teamId: string, expertId: string, question: string): Promise<{ readonly answer: string; readonly truncated: boolean }>

/** Dispose every derived agent session this orchestrator still owns. */
async dispose(): Promise<void>
```

Types: [ExpertTeamView](../../packages/experimental/expert-team/README.zh.md) · [GateDecision](../../packages/experimental/expert-team/README.zh.md) · [TeamRun](../../packages/experimental/expert-team/README.zh.md)

Source: [`packages/experimental/expert-team/src/orchestrate.ts`](../../packages/experimental/expert-team/src/orchestrate.ts)
<!-- END GENERATED cordis-surface -->
