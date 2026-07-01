# Design: Open Orchestration MCP (multi-AI coordination surface)

> Status: design / pre-implementation. Turns the thin DevFrame MCP server
> (read + propose-file-edit) into an OPEN interface that exposes DevFrame's
> EXISTING orchestrator (workflow engine / `/go` dispatch / team runtime / ACP)
> so any AI can coordinate a governed agent team — under a hardened security
> model and a mandatory human gate. Pairs with
> `docs/status/recon-receipt-devframe-mcp-server.md` and the roadmap (M1/M2/M5).

## 1. Goal and non-goals
- **Goal**: an open, standard MCP endpoint where any AI client can (a) observe
  the project and the agent team, (b) PROPOSE governed work (tasks + edits), and
  (c) coordinate with other AIs — while a human approves anything that writes,
  runs executors, or spends tokens.
- **Non-goals**:
  - NOT a file editor. Editing/coding is the executor's job (OpenCode/Codex via
    ACP). The MCP must not become a second CodexPro.
  - NO auto-approve and NO silent execution. The human gate is the boundary.
  - NOT public-by-default. Loopback-only unless explicitly exposed with a token.

## 2. How it composes with the orchestrator we already have
The MCP server must call the EXISTING orchestration code, not reimplement it:

```
Any AI (MCP client)
  → DevFrame Orchestration MCP (this design: tools + scopes + audit)
     → existing orchestrator: workflow_engine / go_dispatch / team_runtime
        → ACP drives OpenCode/Codex (executors) to do the work
           → changes return as a human-gated proposal
              → human approves → applied/committed; every step audited
```

The MCP is the **open remote control for the orchestrator**, not a parallel
path. "Dispatch a task" routes into `/go`/workflow; "team status" reads the
team runtime; "approve" stays human.

## 3. Tool surface (tiered by capability and risk)
Every tool: declared scope, what it touches, gate, audit. Default least-privilege.

### Read tier — no gate, no side effects (scope: `read`)
- `list_projects` — project ids/titles/status (metadata only).
- `get_run_status(runId|latest)` — phase, agents, results of a `/go`/workflow run.
- `get_team_status(projectId?)` — agent registry, task board, event log,
  conflict control, review gates (the team objects).
- `list_pending_gates()` / `list_pending_writebacks()` — what awaits a human.
- `get_diff_preview(runId|requestId)` — the proposed change as a diff (so the AI
  and the human can reason about it). **Metadata/diff by default; raw file
  contents require the higher `read_content` scope.**

### Propose tier — stages a human-gated item, NO side effect until approved (scope: `propose`)
- `propose_task(projectId, goal, constraints?)` — stages a governed `/go`/workflow
  dispatch **proposal**. It does NOT run executors or spend tokens until a human
  approves it (running agents costs money — that is a gated, budgeted action).
- `propose_writeback(projectId, relativePath, contents)` — already built; stages
  a file change, applied only on human approval.
- `post_message(projectId, toRole, summary)` — a coordinator/agent note into the
  team **message bus** (the multi-AI collaboration channel). Low-risk text only.

### Coordinate tier — multi-AI teamwork (scope: `coordinate`)
- `claim_task(taskId)` / `release_task(taskId)` — task-board claim with conflict
  control, so multiple AIs don't collide on the same work.
- `record_review(runId, verdict, notes)` — an AI acting as a *reviewer* posts a
  non-binding verdict; the binding gate is still human.

### Human-only — NEVER exposed as an AI-callable tool
- **approve/reject a gate, apply a write, start spending tokens.** These live in
  the dashboard/editor and require a human. An AI can *request* and *propose*; a
  human *decides*. This is the single most important invariant.

## 4. Authorization model — connect-time human consent (per the owner's decision)
The security boundary is **a human consent prompt at connection time**, not a
pre-shared per-AI secret. Any AI that can speak MCP may knock; the human decides.

**Consent flow:**
1. An AI connects (`initialize`). The server issues an `MCP-Session-Id` (standard
   MCP; even `auth=None` clients echo it back on later requests) and records the
   connection as **pending**, capturing the client's self-reported identity
   (`clientInfo.name`, connector origin).
2. The first tool call from a *pending* connection does NOT return data. Instead
   the server raises a **local authorization prompt on the owner's machine**
   ("An AI client『<name>』wants to connect to DevFrame and read project info.
   [Allow once] [Allow always] [Deny]") and replies to the AI with
   `authorization_pending` (please retry shortly).
3. The human clicks Allow/Deny locally. On **Allow**, the connection becomes
   `authorized` with the **default scope** (read most info, EXCLUDING core
   sensitive — see §4.1). "Allow always" stores a durable grant keyed by the
   client fingerprint so reconnects don't re-prompt; "Allow once" is
   session-scoped. On **Deny**, the connection is blocked.
4. Authorized connections can use read + propose tools within scope. **Approving
   writes / running executors / spending tokens remains a separate, per-action
   human gate** (§3 human-only) — connection consent ≠ write consent.

The prompt surfaces in two places for reliability: an immediate desktop
notification/dialog, and a **pending-connections list** in the RD-Code editor /
dashboard where the owner can review identity and Allow/Deny/Revoke at any time.

### 4.1 What an authorized connection may read (default) vs never
- **Allowed by default (most info):** project list/structure, run + team status,
  task board, event log, review-gate status, diffs/previews, and non-sensitive
  file contents.
- **Core sensitive — never returned by default (even when authorized):** secrets
  and credential stores (`.env*`, key files, token stores), raw browser/session
  profiles, and anything matching configured secret patterns. Access to these,
  if ever needed, is a separate explicit higher grant, not part of default
  consent.
- **Revocation:** the owner can revoke any connection at any time from the
  pending/active connections list; revoked connections immediately lose access.

## 5. Security model (the hard part)
Each risk from the prior analysis with a concrete mitigation:

1. **Reachability vs authorization (two layers).** Authorization is the
   connect-time human consent (§4). But on a PUBLIC tunnel, an open endpoint lets
   random internet scanners trigger consent prompts (popup spam / DoS). So keep a
   thin **reachability gate** in front: a lightweight endpoint token (in a custom
   header — Cloudflare strips `Authorization`) or Cloudflare Access, just to stop
   anonymous internet noise from reaching the consent layer. On loopback / a
   trusted LAN this gate can be off. Net: **endpoint token = "can you knock";
   human consent = "are you allowed in"; per-action gate = "can you change
   things".** Endpoint tokens are rotatable/revocable; never in the URL/query.
2. **Reads leaking project data.** Default scope returns **metadata/diffs only**;
   raw file contents need `read_content`. Redact known secret patterns. Optional
   per-connector project allowlist. Make it explicit which AI vendor sees what.
3. **Approval fatigue.** Default-deny; group proposals; show clear diffs; always
   flag high-risk proposals (delete/deploy/secret/many-files) prominently and
   require a stronger confirm. Rate-limit proposals per connector.
4. **Prompt injection / untrusted AI.** Treat ALL AI-proposed content as
   untrusted. The human gate is the boundary, so an injected instruction can at
   most create a *proposal* a human will see and can reject. Never auto-approve.
   Surface provenance (which connector/AI proposed each item).
5. **Multi-AI attribution & conflicts.** Every proposal, message, and tool call
   is tagged with connector id + AI identity and recorded in the team event log;
   file-level conflict control prevents two AIs clobbering the same target.
6. **Network exposure.** Loopback-only by default; tunnel exposure is an explicit
   opt-in requiring a token; bind 127.0.0.1; document that a tunnel + token is
   not the same as real auth and recommend Cloudflare Access / mTLS for anything
   beyond personal dogfooding. Origin/DNS-rebinding guard where it does not break
   legitimate non-browser clients.
7. **Audit.** Every tool call (connector, tool, argument summary, result,
   timestamp) is appended to a durable audit log (reuse the team event log),
   outside the public repo. This is how "who did what" stays answerable.
8. **Cost/abuse.** Per-connector budget caps; dispatching agents requires human
   approval (or a capped pre-authorized budget); rate limits on all write/propose
   tools.

## 6. Phased plan (each phase = a Recon Receipt slice + tests + reviewer)
- **Phase 0 — authorization + hardening first (before adding power).** Implement
  the connect-time consent flow (§4): pending-connection state keyed by
  `MCP-Session-Id` + client fingerprint, a local Allow/Deny prompt (desktop
  dialog + pending-connections list in the editor/dashboard), durable
  grants/revocation, default scope with core-sensitive exclusion, a thin
  reachability token (custom header) for public exposure, and a tool-call audit
  log. No new orchestration capability yet — just the safe door.
- **Phase 1 — read-tier orchestration tools.** `get_run_status`,
  `get_team_status`, `list_pending_gates`, `get_diff_preview`. Read-only.
- **Phase 2 — propose-tier.** `propose_task` (staged `/go` dispatch; a human
  approves before any token spend) + existing `propose_writeback`.
- **Phase 3 — coordinate-tier.** `post_message`, `claim_task`, `record_review`
  (multi-AI collaboration on real team objects).
- **Phase 4 — broaden.** Any AI may connect (consent is the gate); document
  per-connection review/revocation. (The owner has chosen: open to any AI that
  can call MCP and is explicitly authorized.)

## 7. Decisions — owner's choices recorded
- **Authorization = connect-time human consent popup.** Any AI that can call MCP
  may connect; it only gets access after the owner explicitly Allows it in a
  local prompt. (DECIDED.)
- **Default read scope = most info, excluding core sensitive** (secrets,
  credentials, raw profiles). (DECIDED.)
- **Open to any AI**, gated solely by the consent popup + (for public exposure) a
  thin reachability token to stop anonymous internet spam. (DECIDED.)
- **Still open — task-dispatch cost gate:** dispatching agents spends real money.
  Default (recommended, and assumed unless you say otherwise): a proposed task
  must be **approved by a human before it runs/spends**. Later we can add an
  opt-in per-connection budget with hard caps. Tell me if you want the budget
  option from the start.

## 8. Honest bottom line
The value is real (a vendor-neutral, human-governed, multi-AI orchestration hub),
but it is only worth more than CodexPro if the orchestration + governance are
real, and it is only safe if Phase 0 (token/scope/audit hardening) lands BEFORE
the powerful tools. Recommended order: **harden, then expose orchestration reads,
then proposes, then multi-AI coordination — never auto-approve, never silent
spend.**
