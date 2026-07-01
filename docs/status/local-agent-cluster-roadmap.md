# Local Agent Cluster Roadmap

Where dev-frame-system stands relative to the ultimate goal: a mature,
T3Code-like, governed agent cluster where web AIs become local agents and
multiple agents can be triggered into a collaborative workflow.

Living status doc. Pairs with `docs/agent-runtime/agent-protocol-landscape.md`
(protocol facts) and `docs/agent-runtime/reuse-depth-review-method.md` (review
method). Last updated: 2026-06-26.

## Architecture spine (corrected)

```
DevFrame governance (contracts, evidence, gates, decisions, provider abstraction)
  ├─ ACP  : one client drives many coding agents (Codex/OpenCode/Claude Code) — multi-agent backbone
  ├─ MCP  : each agent/brain reaches tools (model -> tools)
  ├─ Provider abstraction : API / local model / web-shim, one DevFrameSession
  └─ T3Code shell (reuse) : visual client; OpenCode/agents execute; DevFrame governs
```

ACP — not MCP — is the backbone for "trigger multiple agents into a
collaborative workflow". MCP gives each agent its tools. (That a coding agent is
driven via ACP rather than "called as an MCP tool" is a resolved fact; choosing
ACP as DevFrame's backbone, and the build-vs-reuse/depth of that integration,
are still open design decisions — see register D1/D5.)

## Done (verified)

- Governance core: decision engine, dispatch packets, contracts, evidence/gates,
  runtime journal.
- Single-agent execution realized to L2: OpenCode JSONL events parsed into real
  session/token/cost/tool data, verified against real OpenCode 1.17.9.
- Write-set serialization (executor-agnostic concurrency safety, first slice).
- Pluggable model provider: registry + `--model-provider` + unified session;
  deferred web-shim guarded against silent paid execution.
- Opt-in execution isolation (`--isolate`): per-agent git worktree + packet
  rebase + per-agent OpenCode `XDG_DATA_HOME`. Verified against real OpenCode
  1.17.9: parallel agents edit only their own worktree, main tree untouched, no
  `database is locked`. Default OFF and byte-identical.

## Remaining modules (priority-ordered)

### M1. Real multi-agent runtime (team objects: projection -> runtime) — critical path
Team objects (Agent Registry, Task Board, Message Bus, Event Log, Evidence
Store, Review Gate, Conflict Control) were entirely *projected* from parallel
runs. **Slices 1-2 done**: Event Log, Message Bus, Conflict Control, and Review
Gate are now real, recorded runtime facts — `control_plane/team_runtime.py`
records `task_created` / `task_claimed` / `task_result` to a durable
`team-events.jsonl` (outside repo) during `/go` execution, and the read model
derives all four objects real-first from those records (projection fallback;
prepare-only runs stay byte-identical). **Slice 3 done**: Agent Registry, Task
Board, and Evidence Store are now also real recorded objects, derived from the
SAME durable events (a task per (run, agent) with a created→claimed→result
lifecycle; an agent per participant with its latest recorded status; an evidence
ref per result that carried a report path), merged real-first into the read
model (dedupe by id) and surfaced through the MCP `get_team_status` tool. So six
of the seven team objects (Event Log, Message Bus, Conflict Control, Review Gate,
Agent Registry, Task Board, Evidence Store) are now real recorded facts.
Remaining: real agent-to-agent messages, task-claim contention, and a
blackboard/shared memory (genuinely new runtime mechanics, not just derivations).
See `docs/status/recon-receipt-team-runtime.md`. This is the heart of "agent
cluster collaboration" (recon-008).

### M2. ACP integration (multi-agent backbone) — critical path
**Slice 0 (transport seam) + Slice 1 (governed live session) done.**
- Slice 0: `control_plane/acp_client.py` — a real DevFrame-owned Python ACP
  transport (newline-delimited JSON-RPC 2.0 over stdio; reader thread, per-id
  timeout, incoming handlers, clean close; Windows `.CMD`/`.ps1` shim launching).
  Mock-verified.
- Slice 1: `control_plane/acp_session.py` — `GovernedAcpSession` drives a real
  ACP agent and wires governance: a permission policy (allow normal edits, HOLD
  high-risk: delete/deploy/push/secret/external) and `fs/*` handlers confined to
  the session cwd, recording the session lifecycle + permission decisions via the
  M1 team runtime. **Verified live against `opencode acp` (OpenCode 1.17.9):**
  real handshake, real session, the agent actually edited the target file, and
  the session was recorded.
- HONEST status: the governance gate is verified LIVE against OpenCode. With a
  project `opencode.json` of `{"permission":{"edit":"ask","bash":"ask"}}`,
  OpenCode routes `session/request_permission` to our client: a normal edit was
  ALLOWED and applied, and a high-risk delete was HELD — the file was not deleted
  (verified on disk). Without `permission: ask`, OpenCode auto-applies and never
  asks (its own policy). See `docs/status/recon-receipt-acp-backbone.md`.
- Remaining: stream `session/update` tool calls/diffs into the read model (visual
  layer, M6); make `--driver acp` work under `--isolate` (env passthrough); and
  eventually make ACP the default once parity is proven.

### M2.1 ACP as an opt-in executor — done
`--driver acp` on `devframe code`/`go` (and `run_go_dispatch(driver="acp")`)
routes each `/go` agent through a `GovernedAcpSession` instead of the CLI worker:
it drives the agent live, enforces the permission gate + fs confinement,
synthesizes the standard ExecutionReport (status from stop reason, changed files
from `git status`), and records the session via the team runtime. Default is
`driver=command` (byte-identical). Verified hermetically (mock ACP agent) AND
live: a real `/go --driver acp` run against OpenCode 1.17.9 passed, edited the
target file, fired the permission gate (`workflow-permission` recorded), and
recorded the session. See `docs/status/recon-receipt-acp-backbone.md` (slice 2). `--driver acp` also works
under `--isolate` (per-agent worktree + `XDG_DATA_HOME` env passthrough;
verified: the edit lands in the worktree, main tree untouched), and streamed
`session/update` activity surfaces in the read model as a low-noise
`workflow-acp-stream` event.

### M3. Workflow orchestration engine — critical path
**Slice 1 done**: `control_plane/workflow_engine.py` provides a real, recorded
`WorkflowEngine.run_coding_workflow` that drives plan (coordinator) -> execute
(executors) -> review (reviewer), records every phase transition and the
controller's verdict as real team events (reusing the M1 journal), and exposes
`devframe workflow "<goal>"`. The reviewer phase derives a continue/revise/stop
verdict from recorded task results. The workflow can now also drive the execute
phase over **ACP** (opt-in `driver="acp"`, threaded into the prepared run so
`execute_go_run` picks it up; default `command`, byte-identical), recorded in the
start event. See `docs/status/recon-receipt-workflow-engine.md`. Remaining:
consolidate the two existing orchestrators (control-plane rdgoal vs
ai-workflow-hub LangGraph) into one source of truth, **live-verify** the
ACP-driven execute (needs real OpenCode + token spend — human-gated), and use a
real reviewer agent (not just status aggregation). This is the literal "trigger
multiple agents into a collaborative workflow".

### M4. Execution concurrency completion
Worktree isolation + per-worktree OpenCode state (root fix for `database is
locked`) is **done as an opt-in `--isolate` mode** (verified against real
OpenCode 1.17.9). Remaining: make isolation a managed default with diff
review/merge-back of each worktree, optional OpenCode serve/SSE for live
progress (L3), and session resume. Foundation under M1/M2.

### M5. Web AI as a real cluster participant
- **DevFrame MCP server (AI operation surface) — done & self-verified.** DevFrame
  now also *serves* MCP (not just consumes it): `control_plane/mcp_server.py`
  exposes `POST /mcp` (loopback, stdlib JSON-RPC) with read tools
  (`server_config`, `read_project_shell`, `list_pending_writebacks`) and a
  governed `propose_writeback` tool. An AI client can read the project and
  PROPOSE single-file changes; the server **never writes** — applying a proposal
  still needs a human approval via `/api/t3/approval-response`. Verified
  end-to-end with DevFrame's own `mcp_live_probe` (`live_ok`). Independent review
  PASS-WITH-NITS (Origin guard + SSE are documented follow-ups). See
  `docs/status/recon-receipt-devframe-mcp-server.md`. This is the other half of
  the core promise: a web AI as a governed local agent entrypoint that can act,
  not just observe.
- **MCP connect-time consent (open multi-AI gate) — Phase 0 done & verified.**
  Any AI may call the MCP, but a connection can only USE tools after the human
  Allows it locally (Allow once / Allow always / Deny / Revoke). `initialize` +
  `tools/list` are open (discovery); `tools/call` from an unauthorized
  connection returns `authorization_pending` and yields zero project data;
  revoke cuts access immediately and clears the durable grant. Connections are
  reviewable/decidable via loopback endpoints (`GET /api/mcp/connections`,
  `POST /api/mcp/connections/decide`) and a `devframe mcp connections` CLI; every
  connect/decision/tool-call is audited. Core-sensitive data stays out of the
  default read scope. Independent review PASS-WITH-NITS (fingerprint blast radius
  + rate-limit are documented later-phase items). Implements Phase 0 of
  `docs/status/design-orchestration-mcp.md`; see
  `docs/status/recon-receipt-mcp-consent.md`. A desktop popup is a thin
  presentation layer over the existing decision endpoint (follow-on). Remaining:
  Phase 1 read-tier orchestration tools (run/team status), Phase 2 propose-task,
  Phase 3 multi-AI coordination.
  - **Phase 1 done (read-tier orchestration tools):** authorized AI connections
    can call `get_run_status` (a `/go` run's status/agents, metadata only),
    `get_team_status` (agent registry / task board / recent events / review gates
    / conflict control summaries), and `list_pending_gates` (gates awaiting a
    human) — all read-only metadata projected from the visual state, behind the
    same consent gate, no file contents or secrets. So an AI can now *see* the
    governed team, not just the project shell. Full suite 551 passed. Remaining:
    Phase 2 `propose_task` (staged `/go` dispatch, human approves before any
    token spend), Phase 3 multi-AI coordination.
  - **Phase 2 done (propose_task — AI proposes, human approves, no spend):** an
    authorized AI can `propose_task(projectId, goal)` and `list_pending_tasks`;
    proposing stages a task (`control_plane/task_proposals.py`) and runs nothing.
    A human approve/reject goes through the existing `/api/t3/approval-response`
    (`tk-` branch): **approve only promotes the task to a queued intent —
    `ran=False`, `spent_tokens=False`** — and actually running it (which spends
    tokens) stays the existing separate human execution gate (`devframe go …
    --execute` / `/actions/execute` confirm). Independent review PASS-WITH-NITS
    confirmed no path lets propose/approve execute or spend; the `approved`
    status has no auto-consumer. Full suite 561 passed. Remaining: Phase 3
    multi-AI coordination (messages, task claim, conflict control), then the
    careful broadening to multiple AIs.
- **Tier A (local MCP) — live round-trip VERIFIED.** DevFrame's own MCP client
  (`mcp_live_probe` / `devframe web-ai live-check`) completed a real
  Streamable-HTTP JSON-RPC `initialize → tools/list → tools/call(server_config)`
  against a live CodexPro local MCP server at `http://127.0.0.1:8787/mcp`
  (bearer auth), returning `live_ok` and importing a real session into the
  runtime. This is the concrete realization of "a web-AI-facing MCP surface as a
  local agent entrypoint", verified end-to-end (no mock). See
  `docs/status/evidence-web-ai-mcp-live-roundtrip.md`.
- Tier B: ChatGPT Web MCP — **VERIFIED end-to-end over a stable tunnel.**
  ChatGPT connects to a permanent Cloudflare named tunnel
  (`https://mcp.rd2100.uk/mcp`, auth via URL query token → connector
  Authentication: None) reaching the local CodexPro MCP server. ChatGPT ran
  `codexpro_self_test` (9 pass / 3 benign warnings / 0 fail): read git status,
  wrote a workspace probe file, registered 15 tools, safe-bash confirmed. This is
  the core promise realized — a web AI as a governed local agent entrypoint into
  the workspace over a fixed URL. See
  `docs/status/evidence-web-ai-mcp-live-roundtrip.md`.
- Tier A others: DeepSeek/Qwen/Doubao via API or local model (no web MCP needed).
- Tier C: web-only (Doubao/DeepSeek web) as attended external brain via a
  headless background session daemon; not unattended-autonomous by nature.

### M6. Writable editor loop (T3 client)
T3 desktop zero-config launch acceptance; real-time subscription (WS) over poll;
diff review -> human gate -> write-back. Turns the read-only dashboard into an
editor. Depends on M4.
**Entry point added**: `scripts/launch-editor.ps1` + a Desktop shortcut
("DevFrame T3 Editor", created by `scripts/create-editor-shortcut.ps1`) launch the
integrated T3 Code desktop client (at `.devframe-runtime/external/t3code/`, MIT,
outside the public repo) wired to the DevFrame bridge on port 8788. The client
reads DevFrame projects/threads/sessions (read-only today).
**RD-Code fork (rebrand + i18n) started**: the client is rebranded to RD-Code
(display identity; T3 MIT notice retained + `NOTICE.devframe.md`), and real
multi-language support was added via react-i18next (English + 中文) with a
Language switch in Settings → General and first-screen coverage; adding a
language = one catalog file. Verified: changed files typecheck clean; no T3
source vendored into the public repo. See
`docs/status/recon-receipt-t3-rebrand-i18n.md`. Remaining: full string coverage
(incremental), layout/theme differentiation, and the writable diff→gate→write-back
loop (the read side works today).

### M7. Methodology execution + maturity
Enforce `@go read/edit/risky` profile semantics at the executor (read_only really
blocks writes, network really gated); unified forensics/metrics; clean release
workflow.

### M8. RD-Code client completeness (bridge data + write-back) — NEW, client track
The T3-fork client (RD-Code) launches and reads DevFrame projects/threads via the
read-only bridge on :8788. But several settings panels (Source Control discovery,
Archived threads, Providers status, Connections) query backend RPCs the read-only
bridge does NOT implement, so they spin/empty forever. This module makes the
bridge a complete-enough read model for the client:
- **M8.1 Bridge data completeness (A)** — **done (honest outcome).** Investigated
  the four panels (Providers, Source Control, Archived threads, Connections):
  their data sources are WebSocket RPCs the read-only HTTP bridge cannot serve,
  and DevFrame has **no truthful read-only data** to project for provider
  install/auth status, server git discovery, or archived snapshots — inventing it
  would be fake green. So the shipped fix is honest: in bridge mode the panels
  stop spinning and render localized "read-only bridge mode" empty states
  (en + zh-CN `settings.bridge.*`), and the Connections auth-access WS
  subscription is guarded off. No backend change needed (`/api/auth/session`
  already reports read-only scopes). All edits are presentation-only in the fork
  (no client-runtime changes, no T3 source vendored). Verified: changed files
  typecheck clean (only the 3 pre-existing bridge errors remain), `pytest` green
  (483), `verify-public-snapshot.ps1` exit 0, independent review PASS-WITH-NITS.
  See `docs/status/recon-receipt-rdcode-bridge-data.md`.
- **M8.2 Write-back loop** — **slice 1 done (DevFrame-side governed write executor).**
  `control_plane/writeback.py` applies a single proposed file edit into the
  workspace with a hard security contract: writes can never escape the workspace
  root (resolve + relative_to guard), absolute/drive/UNC/`..` paths rejected,
  sensitive components refused (`.git`, `.env*`, key stores, runtime/state dirs,
  `node_modules`) including Windows trailing-dot/space and 8.3 short-name bypass
  hardening, symlink escapes blocked, size-capped, atomic write + honest audit
  record. Default bridge policy stays read-only; write-back is a per-action
  human-gated exception (not a mode flip). 26 unit tests; full suite green;
  independent review PASS-WITH-NITS with the security nits fixed. See
  `docs/status/recon-receipt-rdcode-writeback.md`. Remaining: wire the executor
  behind the existing approval-response/`confirm=execute` gate as a new action
  kind + CLI subcommand (slice 1b), then the client diff-review → approve
  affordance in the RD-Code fork (slice 2). Pairs with M4 worktree
  review/merge-back and M6.
  - **slice 1b done:** `devframe writeback apply --workspace <root> --path <rel>
    --contents-file <f> [--confirm]` is a governed CLI entrypoint — preview-only
    (exit 3) without `--confirm`, applies + writes a `writeback-runs/` audit with
    `--confirm`. `preview_single_file_writeback` / `apply_writeback_with_audit`
    in `writeback.py`; CLI in `cli/_writeback.py`. 33 writeback tests; full suite
    green (one unrelated pre-existing Windows socket flake in
    `test_dashboard_serves_controlled_action_page_and_confirmation_gate`, passes
    3/3 in isolation). Remaining for the HTTP path: surface a write-back proposal
    as a gated `next_action` and route `/api/t3/approval-response` approve to the
    executor (slice 1c), then the RD-Code diff-review UI (slice 2, needs visual
    acceptance).
  - **slice 1c done:** the editor can propose a change over the loopback channel
    (`POST /api/t3/writeback-propose`) which only STAGES it (nothing written); a
    human approval (`POST /api/t3/approval-response` approve) applies it and
    reject discards it. Workspace root is resolved server-side from an explicit
    project id (client paths never trusted), the approval cross-checks the
    proposal thread, a proposal is consumed exactly once, and every applied write
    is audited. Default policy stays read-only; the endpoint + `writeback_apply_file`
    action kind are registered in the launch plan and client manifest. Full suite
    527 passed; independent review PASS-WITH-NITS, both nits fixed. Remaining: the
    RD-Code diff-review → approve UI (slice 2, needs visual acceptance).
- **M8.3 i18n + rebrand finish** — extend Chinese coverage screen-by-screen
  (settings module done), finish RD-Code identity, layout/theme differentiation.

## Critical path summary (current, honest)

Engine track: M1 (real team runtime) **slices 1-2 done**, M2 (ACP) **transport +
governed live session + ACP-as-executor done & live-verified**, M3 (workflow
engine) **slice 1 done**. What remains on the engine critical path: M1's last
team objects (Agent Registry/Task Board/Evidence as recorded, agent-to-agent
messages, claim contention), M3 orchestrator consolidation + ACP-driven execute +
real reviewer agent, and making ACP the default executor.

Client track: the RD-Code editor launches, is rebranded, and the Settings module
is localized, but it is **read-only and several panels have no backing data**
(M8.1) and there is **no write-back** (M8.2).

Not started: M5 (web-AI as cluster participant), M7 (methodology enforcement at
the executor), M4's managed-default isolation + merge-back.

## Suggested next step

**M8.1 (bridge data completeness)** is the approved next module: stop the
read-only client's panels from spinning/empty by extending the DevFrame bridge to
serve real read-only projections (provider status, source control, archived
threads, connections). It is bounded to the bridge/contract layer and the client
read model, and unblocks the editor track without touching the engine critical
path. After M8.1, choose between M8.2 (write-back) and finishing M1/M3 on the
engine side.
