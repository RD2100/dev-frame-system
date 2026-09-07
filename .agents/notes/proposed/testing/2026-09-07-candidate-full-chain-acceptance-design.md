# Agent Note: Candidate full-chain dispatch acceptance design

Status: proposed

## Problem

Every seam of the candidate dispatch journey is proven by its own suite — the dispatch engine and its `agent_dispatch` consumer (unit + real-Loader composition specs), the durable task ack (log-fold + restart proofs), the lead-assignment landing wave (cold-restore fold), the reviewer gate (`AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED` matrix), the DevFrame evidence journal, and the project-controller task machine (`planned → assigned → developing → reviewing → submitted → integrated`). What no suite proves is the **journey on one real candidate deployment**: one controller session dispatches one lead, the lead dispatches **two independent Worker tasks onto two separate worktrees running concurrently**, each Worker delivers through real required checks, the lead reviews independently, tasks are submitted, the controller integrates through the controller-only merge gate, and a controlled restart re-derives every durable fact. V1.2 named the gap: without a formal running consumer the product cannot close this loop on its own. That consumer is A2's assignment (agent_dispatch → `assigned`/`developing` → Worker delivery with real checks → `reviewing` → independent lead `recordReview` → `submit` → existing `integrate`, reusing `AgentEvidenceJournal`, never pre-minting `passed`/`submitted` records, not rewriting the controller or Git gate). This note designs the **test and evidence face** that will accept that consumer's delivery; it implements nothing.

Two constraints shape the design. First, the acceptance-scope boundary recorded in `c-verify-evidence.md` §8: the opt-in overlays ride explicit candidate commands, never the default 3080 bundle, and a scaffold `composeEntries` scenario must never masquerade as shipped-overlay verification. Second, the worklist's three-layer evidence discipline: only the actual-response layer proves a provider; preset or self-reported state proves nothing.

## Proposal

### Deployment face

The chain boots through the candidate command the harness already proves (`apps/cli/tests/cordis-example-overlay.e2e.ts`): the real source CLI with explicit root-level `--patch`es over an isolated harness home — the example overlay (pinned 3081 webserver + tool-cordis) plus the private DevFrame profile layer (`packages/experimental/devframe-profile/cordis.patch.yml`, the six-row hierarchy stack). A third **loop-closure overlay** (a test fixture yml, never a default change) closes the configuration the shipped overlays deliberately leave open:

- It **replaces** the `agent-hierarchy` row's whole config (patch semantics): controller and lead keep the shipped inherited surface plus `agent_dispatch`; **worker `inheritedTools` = the minimal actionable set** — platform shell (`pwsh`/`bash` via the platform seam) plus `read`, `write`, `edit`, `glob`, `grep`. Enough to implement a file-delivery task; no dispatch tool (invisible via restrict anyway), no web, goal, or worktree tools.
- It preallocates the lead identity: the controller dispatches the lead naming `childId: 'candidate-fullchain-lead'`, and the same overlay sets `leadPluginScopes: { 'candidate-fullchain-lead': ['candidate-fullchain'] }` — the approved scope every Worker dispatch must name.
- It inserts/patches the **project-controller row** (owner: A2's consumer brings the model-facing moves; the overlay only guarantees the service is mounted with `requestBudget: 4` and `maxActiveTasks: 2`, the machine-neutral defaults the concurrency window relies on).
- It registers the **approved required-checks checklist** (file store) whose digest the evidence requests carry; checks stay machine-neutral (`git diff --check` in the task worktree, an artifact-existence probe) so the real subprocess execution face runs everywhere.

### Model face: wire-level replay, zero real credentials

The model turns (controller, lead, two Workers) are **scripted at the wire boundary**: the harness runs a local replay server speaking the provider wire protocol, and the isolated home's provider route points at it. Everything else is real — the CLI process, the composition, worktrees and git, journals, the task machine, locks, restart. This keeps the acceptance deterministic, credential-free, and CI-able, and it satisfies model-visible⟺logged trivially (replayed turns produce ordinary session events). One **authorized real-model round** (one 总控 notification = one round, credentials extracted from refs into process env only) later replays the same scenario against a real provider as the 运行-layer evidence; its cross-check bounds wire-shape drift.

### Scenario and evidence windows

Each step lists the observable face the assertions read (session log events, domain tables, file artifacts):

1. **Boot**: readiness line on 3081; `pluginInventory/list` shows all rows from both patches active (existing harness face).
2. **Controller turn**: worktree creation ×2 (distinct branches), `agent_dispatch` of the preallocated lead. Evidence: worktree rows registered under the workspace; the durable agent binding (role `lead`, parent = controller); the **`devframe/role-policy` landing event** appended by `devframe-lead-role-landing` (fold re-derives the lead assignment on cold restore); `agent/created` publication.
3. **Lead turn**: `agent_dispatch` ×2 — two distinct `taskId`s, two worktrees, `pluginId: 'candidate-fullchain'`. Evidence: two child sessions with recorded parent/role/task/plugin; **each worktree's single-writer lock held by its child**; briefings queued strictly after publication; acks `briefed` → `claimed`.
4. **Concurrency window** (the V1.2-named proof): the two Workers' claiming turns genuinely overlap. Evidence from the logs, never from sleeps: with claim instant `c_i` and terminal `turn/end` instant `t_i` per Worker, assert `max(c_A, c_B) < min(t_A, t_B)`. Supporting faces: `project_tasks` shows both tasks `developing` simultaneously (`maxActiveTasks: 2` admits exactly this); the request-budget global reaches ≥ 2 charged requests with serialized durable charges (two receipts, no lost update).
5. **Worker delivery + real checks**: each Worker turn completes its file artifact in its own worktree; the consumer moves `developing → reviewing` backed by `AgentEvidenceJournal.recordVerification` — the **real subprocess execution** of the approved checklist, results appended as one `devframe/verification` event (status passed, executed checks recorded). Evidence: artifact bytes on disk in each worktree; verification events bound to the correct `GoalResultBinding`/`snapshotId`; dispatch acks read `terminal` with `completed: true` and `durable: true`.
6. **Independent lead review**: `recordReview` appends one `devframe/review` (decision pass) — the reviewer gate cross-authorizes through the projection directory against the landed lead authority, with no role self-report field in play. Evidence: review event's `reviewerSessionId` = the lead session; the fold keeps exactly one review per reviewed task.
7. **Submit → integrate**: consumer moves `reviewing → submitted`; the controller (and only the controller — the binding lookup refuses others) mints the merge marker via `requestMainTreeMerge`, and `integrate` consumes it: task `integrated`. Evidence: `project_tasks` row states; the consumed marker replayed → `PROJECT_CONTROLLER_MARKER_INVALID`; a lead mint attempt → the controller-only refusal.
8. **Controlled restart**: after step 6 (before integrate), SIGTERM the CLI mid-quiescence and relaunch the same command/home. Evidence: `project_tasks` restored verbatim; the DevFrame projection folds identically from the restored log (landed lead assignment, verification, review all present, zero diff against the pre-restart fold); `taskAck` re-derived from child logs still reads `terminal/completed/durable`; worktree locks recover or rebind cleanly. Integration then completes on the restarted process.

### Gates and failure assertions

Each named denial is asserted exactly once with its stable code, proving the gates did not merely stay untripped: `DISPATCH_WORKTREE_UNREGISTERED` (foreign worktree id), `DISPATCH_HIERARCHY_DENIED` (lead dispatching outside the approved scope), worker invisibility of `agent_dispatch` (tool absent, not merely denied), landing before policy (fail-loud), review by a Worker session → `AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED` with zero events appended, forged or replayed marker → `PROJECT_CONTROLLER_MARKER_INVALID`, illegal transition (e.g. `submit` from `assigned`) → `PROJECT_CONTROLLER_ILLEGAL_TRANSITION`, and the degraded-ack face (`durable: false` + `degraded: true` when no flush barrier participates) pinned in a dedicated probe.

### Real vs preset criteria

| Face | Real (proven by) | Scripted (allowed) | Forbidden |
| --- | --- | --- | --- |
| Process & composition | real CLI subprocess, real Loader boot | — | scaffold `composeEntries` substitute |
| Model turns | session events they produce | wire-replay responses | claims of provider identity without the actual-response layer |
| Worktrees & locks | real git worktrees, registry rows, single-writer binds | — | mocked lock state |
| Evidence & state machine | real journals, real subprocess checks, real `project_tasks` table | — | pre-minted `passed`/`submitted`/`integrated` records |
| Concurrency | log-derived wall-clock windows + budget charges | — | sleep-ordered serialization |
| Restart | real SIGTERM + relaunch, restored fold | — | in-memory resume claims |
| 运行-layer round | one authorized real-provider round | — | treating the replay run as provider evidence |

SDK-preset lead/worker sessions (scaffolded identities, scripted turns mounted in-process) remain valid unit evidence for their own suites and are **not** acceptable stand-ins for steps 2–8; the candidate chain's children must carry durable bindings created through the real dispatch entry.

## Alternatives considered

- **Real-model-only full chain.** Every turn driven by a live provider. Rejected as the primary gate: nondeterministic, credential-consuming, and not CI-able; kept as the single authorized 运行 round whose only job is cross-checking the wire shape.
- **In-process scaffold scenario (§8 style).** Reuses the web lane's fixture machinery. Rejected: the boundary explicitly forbids scaffold verification of the shipped overlays — `composeEntries` never loads the example bundle, and preset-mounted children would masquerade as dispatched ones.
- **Prompted-model tool chains without scripted responses** (let real models decide every tool call). Rejected even for the authorized round: the acceptance needs exact tool-call ordering (two dispatches, one review, one mint) to be reproducible; the real round may vary its prose but the scenario pins its tool calls via the briefing prompts.
- **Driving the state machine through direct service calls from the test process** instead of the model-facing consumer. Rejected: it would bypass the very consumer whose acceptance this face exists for; the test drives only the wire faces (HTTP RPC + the replayed model turns), same as a real client.

## Acceptance criteria

The design is accepted for implementation when a single vitest run — boot to restart — exits 0 with: all patch rows mounted; the two-Worker overlap window satisfied from log timestamps; both verification events carrying real executed-check results; the lead review authorized and folded; both tasks `integrated` after marker consumption; the post-restart fold byte-identical on durable facts; every named denial asserted with its stable code; and the degraded-ack probe pinned. The real-provider round separately exits 0 and its actual-response layer is recorded in the worklist's three-layer format. Nothing in the run pre-mints a terminal state, and the run's own wording never claims default-3080 activation.

## Risks

- **New fixture surface**: the wire-level replay server does not exist yet (the web lane replays in-process); it is the one genuinely new piece, and its protocol coverage must match the real provider's streaming shape — bounded by the authorized real round's cross-check.
- **Overlap-window flakiness**: wall-clock windows can shrink on loaded hosts. The window derives from durable log timestamps (never sleeps), and the scenario schedules the second dispatch inside the first Worker's long-running turn, giving a wide window; a CI rerun policy handles residual flake.
- **Restart-point choice**: SIGTERM mid-turn could trip the flush-barrier degraded face and muddy the restart diff. The scenario restarts at a scripted quiesce point (between turns), and the degraded face is covered by its own dedicated probe rather than the happy path.
- **Vocabulary drift**: the consumer owner (A2) may rename moves or states before landing; the design pins only the `TaskState` union and stable error codes from `project-contracts`/`project-controller`, and implementation must recheck every named surface against the landed consumer.
- **Ownership boundary**: this note proposes only the test/evidence face. The running consumer (A2), the controller/Git gate (V1.2), and the shipped overlays' single-write authority (总控) remain theirs; the loop-closure overlay is a test fixture and must not leak into any shipped default.
