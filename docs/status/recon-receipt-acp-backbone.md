# Recon Receipt: ACP backbone transport seam (M2)

> Governs write-capable work on the multi-agent driver/backbone (ACP), a mature
> capability domain, per `rules/recon.md` recon-001/003/005/008/009,
> `rules/open-source-reuse.md` reuse-000/001/002, and
> `docs/agent-runtime/reuse-depth-review-method.md`. Pairs with
> `docs/agent-runtime/agent-protocol-landscape.md` and the roadmap (M2).

## Target
- user_goal: Uniformly drive many coding agents (OpenCode/Gemini/Claude
  Code/Codex) over one standard protocol so the cluster has a real multi-agent
  backbone instead of one-shot CLI subprocess + JSONL parsing.
- target_repo_or_kb: `<repo-root>` (control-plane package).
- current_slice_goal: Slice 0 (transport seam) — a real, tested ACP transport
  client: launch an agent subprocess and speak newline-delimited JSON-RPC 2.0
  over stdio (requests/responses/notifications, streaming `session/update`).
  Verified against a mock ACP agent. Honestly scoped: this is the transport +
  handshake seam, NOT yet a live OpenCode/Gemini driver and NOT yet wrapped in
  DevFrame governance (those are the next slices).
- requested_outcome: `control_plane/acp_client.py` with an `AcpConnection`
  (request/notify/handlers + reader thread) and ACP helpers (initialize /
  session-new / prompt); hermetic test against a mock agent; no live agent, no
  tokens; full gates green.
- date: 2026-06-26
- planner_agent_id: kiro
- approval: Human owner authorized priority-ordered progression with full
  automation and a final comprehensive independent review.

## Resource Map
- packages_apps_modules: `packages/control-plane/control_plane`
- related: `go_dispatch.py` (current CLI-subprocess executor — the thing ACP
  will eventually replace as the live driver), `worker.py` (subprocess shape).
- external protocol: Agent Client Protocol — newline-delimited JSON-RPC 2.0 over
  stdio (verified: agentclientprotocol.com/protocol/transports — "Messages are
  delimited by newlines and MUST NOT contain embedded newlines").
- reuse candidate (reference only, not vendored): T3Code `packages/effect-acp`
  (TypeScript ACP client) — DevFrame is Python, so we reuse the *protocol shape*,
  not the code. The official Rust/TS libraries are not Python; a thin Python
  transport over stdlib `subprocess`/`threading`/`json` is the right seam.

## Core Concepts
- transport: NDJSON JSON-RPC 2.0 over a child process's stdin/stdout.
- handshake: client `initialize` -> agent capabilities; client `session/new`
  -> sessionId; client `session/prompt` -> stop reason, with agent
  `session/update` notifications streamed during the turn.
- client-handled methods (future): `fs/read_text_file`, `fs/write_text_file`,
  `session/request_permission` — DevFrame's governance seam (gates) lives here.

## Capability Matrix
- ACP transport client (Python)
  - location: none today.
  - maturity: absent.
  - reusable_as_is: official libs are Rust/TS, not Python -> not directly
    reusable in this package.
  - decision: build a thin Python transport over stdlib (no new dependency).
- live agent driving + governance wrapping
  - location: none.
  - decision: DEFER to next slices (needs a live ACP agent + permission/gate
    integration). This slice is transport only.

## Reuse Candidate List
- candidate: official ACP Rust crate / TS library
  - source: github.com/zed-industries/agent-client-protocol
  - exact_scope_to_reuse: the protocol shape and method names only.
  - blocking_constraints: language mismatch (this package is Python); adding a
    Rust/Node runtime dependency is heavier than a stdlib NDJSON transport.
  - decision: REUSE the protocol definition; BUILD a minimal Python transport.
- candidate: T3Code `packages/effect-acp`
  - decision: reference for session-UI patterns in a later visual slice (M6);
    not used for this Python transport seam.

## Exception Memo (recon-005: hand-writing a mature capability domain)
Hand-writing a Python ACP transport is justified: (1) no maintained Python ACP
client exists in this package's stack; (2) the official implementations are
Rust/TS and would force a foreign runtime into a Python control plane; (3) the
transport is small and well-specified (NDJSON JSON-RPC 2.0); (4) DevFrame must
own the governance seam (permission/fs handlers map to gates) per reuse-002, so
a thin owned transport is preferable to a heavy adapter. Scope is limited to a
spike-level transport with a mock-verified handshake; live driving is deferred.

## Integration Risk Table
- risk: claiming a working multi-agent ACP driver when only transport exists.
  - type: unknown/ux | severity: high
  - mitigation: this slice is explicitly labeled "transport seam"; tests use a
    MOCK agent; the roadmap and receipt state live driving is deferred. No
    fake-green.
- risk: blocking reads / deadlock on subprocess stdio.
  - type: performance | severity: medium
  - mitigation: a dedicated reader thread dispatches messages; requests use a
    per-id event + timeout; `close()` terminates the process. Covered by the
    mock test (handshake + prompt + streamed notification + timeout path).
- risk: embedded newlines corrupting framing.
  - type: correctness | severity: medium
  - mitigation: serialize with `json.dumps` (no embedded newlines) + a single
    trailing `\n`; reader splits on lines. Asserted by the test.
- risk: new dependency creep.
  - type: maintenance | severity: low
  - mitigation: stdlib only (`subprocess`, `threading`, `json`).

## Build-vs-Buy Decision
- must_reuse: the ACP protocol definition + method names; stdlib transport
  primitives.
- must_build_new: `control_plane/acp_client.py` (thin Python NDJSON JSON-RPC
  transport + ACP handshake helpers).
- rationale: no Python ACP client in-stack; the transport is small and must stay
  DevFrame-owned to host the governance seam.

## Unknowns / Questions
- Which live agent to drive first (OpenCode ACP mode vs Gemini CLI ACP) — decide
  in the next slice with a real agent available.
- How `session/request_permission` maps onto DevFrame gates — next slice.

## Recommended Next Slice (this receipt unlocks)
- smallest_safe_increment: `AcpConnection` (request/notify/incoming-handler +
  reader thread + timeout/close) and `initialize`/`new_session`/`prompt`
  helpers; hermetic test against a mock ACP agent script.
- worker_type_needed: planner-implemented spike adopted after the final
  comprehensive independent review (recon-004).
- files_in_scope: `control_plane/acp_client.py` (new), tests.
- files_out_of_scope: go_dispatch rewrite, live agent driving, governance/gate
  mapping, T3 session UI.
- evidence_required_for_completion: hermetic mock-agent test (handshake, prompt
  round-trip, streamed notification dispatch, request timeout, clean close);
  full `python -m pytest -q` green; verify scripts green; final review.

## Deferred (require updated receipt)
- Stream tool calls/diffs into the read model in real time (visual layer, M6).

---

# Slice 2: ACP as an opt-in /go executor (governed DevFrameSession)

> Unlocks the deferred "replace go_dispatch's CLI-subprocess executor with the
> ACP driver" — but as an OPT-IN driver, default OFF (byte-identical), not a
> forced swap. Date: 2026-06-26. planner_agent_id: kiro. approval: human owner
> approved continuing 1->2.

## Scope
- Add a `driver` choice to `/go` execution: `command` (today's CLI worker,
  default) or `acp` (route each agent through a `GovernedAcpSession`).
- When `driver=acp`: for each agent, run a governed ACP session in the agent's
  working directory using the packet's objective as the prompt, then synthesize
  the standard `ExecutionReport.md` (status from the session stop reason + held
  count; changed files from `git status` in the cwd) and ingest it through the
  existing `DispatchPacketStore`, so all downstream status/event/read-model
  handling is unchanged.
- Default `driver=command` is byte-identical to today. The ACP path is selected
  explicitly via `--driver acp`.

## Design principle
- The ACP driver is an alternative EXECUTOR behind the same dispatch contract; it
  does not change scheduling (write-set serialization), isolation, or the team
  recording. Governance (permission gate, fs confinement) comes for free from
  `GovernedAcpSession`.

## Integration Risk Table (slice 2)
- risk: changing the default execution path.
  - severity: high | mitigation: `driver` defaults to `command`; the ACP branch
    is only taken when explicitly selected. Full pytest gates it.
- risk: ACP driver can't be tested without tokens.
  - severity: medium | mitigation: the acp command is injectable; a hermetic
    test drives a MOCK ACP agent that edits a file + ends the turn, producing a
    real ExecutionReport and `passed` status. No OpenCode in tests.
- risk: combining `--isolate` (worktree + XDG_DATA_HOME) with `--driver acp`.
  - severity: medium | mitigation: this slice supports `driver=acp` with the
    default (non-isolated) cwd path; the isolate+acp combination is recorded as a
    follow-up (env passthrough to the ACP subprocess) and not claimed here.

## Evidence required
- hermetic mock-agent /go test (driver=acp produces an ExecutionReport, passed
  status, changed files, team recording); full pytest green; verify scripts
  green; independent review.

## Deferred (slice 3+)
- Make `driver=acp` work under `--isolate` (XDG_DATA_HOME passthrough), stream
  `session/update` into the read model, and eventually consider making ACP the
  default once parity is proven.

---

# Slice 1: governed live ACP session (verified against OpenCode 1.17.9)

> Unlocks the live-driving + governance-seam half deferred above. Date:
> 2026-06-26. planner_agent_id: kiro. approval: human owner approved the default
> plan (drive OpenCode, real-token smoke allowed, high-risk operations held).

## Verified facts (real `opencode acp`, not assumed)
- `opencode acp` starts a real ACP server over stdio. Our `AcpConnection`
  completed a real handshake: `initialize` -> `{protocolVersion: 1,
  agentCapabilities: {...}, authMethods: [...], agentInfo: {name: OpenCode,
  version: 1.17.9}}`; `session/new` -> a real `sessionId` (`ses_...`). No model
  call, no tokens for the handshake.
- On Windows `opencode` is a `.CMD` shim; `AcpConnection.spawn` now resolves via
  PATH and routes `.cmd`/`.bat`/`.ps1` through their interpreter.

## Slice scope
- A governed ACP session driver (`control_plane/acp_session.py`) that:
  1. spawns `opencode acp`, initializes, opens a session;
  2. handles agent-initiated `session/request_permission` via a DevFrame policy
     (default: allow normal file edits; HOLD/reject high-risk operations —
     delete, deploy, push, secret/credential, external side effect);
  3. handles `fs/read_text_file` / `fs/write_text_file` against disk within the
     session cwd, so writes pass through the governance seam;
  4. consumes the `session/update` stream and records the session lifecycle
     (started, permission decisions, result) through the M1 `TeamRuntime`.
- Default gating policy matches the project safety baseline (high-risk requires
  human; normal edits proceed). Recorded, not silent.

## Integration Risk Table (slice 1)
- risk: claiming a full executor replacement.
  - severity: high | mitigation: this slice drives a session and enforces the
    gate seam; it does NOT yet replace go_dispatch as the default executor (still
    deferred). Honestly scoped in code + roadmap.
- risk: permission policy auto-approves something dangerous.
  - severity: high | mitigation: default holds high-risk operations and records
    the decision; policy is a pure, unit-tested function.
- risk: real-token smoke cost.
  - severity: low | mitigation: temp git repo outside the repo, cheap model,
    minimal prompt; hermetic mock test carries the behavioral coverage.

## Evidence required
- hermetic mock-agent test (permission allow + hold, fs read/write, recording);
  one real `opencode acp` smoke (drives a real edit through the fs/gate seam,
  records the session); full `pytest` green; verify scripts green; independent
  review.

## Slice 1 result (verified)
- Hermetic: `tests/test_acp_session.py` (6 passed) — pure policy (allow normal,
  HOLD high-risk, conservative on unknown options), and a mock-agent end-to-end
  proving normal permission allowed, high-risk held, fs write confined to cwd and
  applied through the seam, and the session + permission decisions recorded.
- Real-token smoke (`opencode acp`, OpenCode 1.17.9, temp git repo, authorized):
  the live agent completed the turn (`stopReason=end_turn`) and **actually edited
  the target file**; the session was recorded as `workflow-acp-session`.
- **Live gate verified (both paths).** OpenCode only routes
  `session/request_permission` to the client when its permission config requires
  it. With a project-local `opencode.json` of
  `{"permission": {"edit": "ask", "bash": "ask"}}`:
  - Normal edit: OpenCode asked, our policy ALLOWED (selected option `once`), the
    edit applied, and the decision was recorded (`workflow-permission`:
    "Permission allowed: normal operation allowed by default baseline").
  - High-risk delete ("rm keep.md"): OpenCode asked, our policy HELD it, the
    decision was recorded ("high-risk operation held for human approval"), and
    **the file was NOT deleted** (verified on disk). The safety baseline blocked
    a destructive op against the real agent.
- Resolution of the earlier caveat: the gate now fires end-to-end against the
  real agent. The prerequisite is documented above (OpenCode's `permission: ask`
  config); without it OpenCode auto-applies and never asks, which is an OpenCode
  policy choice, not a DevFrame gap.
