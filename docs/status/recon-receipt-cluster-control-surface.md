# Recon Receipt — RD-Code cluster control surface (@-mention)

Status: ACCEPTED to proceed in governed slices.
Domain: multi-agent surface + client agent UI (mature capability area → recon
gate required by `rules/recon.md`; reuse assessment required by
`rules/open-source-reuse.md`).
Date: 2026-06-28.

## Goal

Let a user drive the local agent cluster from inside the RD-Code editor by
`@`-mentioning a cluster target in the chat composer — e.g. `@coordinator`
(团队主控) to hand a goal to the orchestration coordinator, or `@<agent>` to aim a
goal at a specific worker role — instead of only the `devframe` CLI + dashboard.

## Reuse assessment (open-source-reuse.md)

- **Composer `@`-mention UI:** REUSE T3Code's existing composer mention/command
  infrastructure (`apps/web/src/components/chat/ChatComposer.tsx` +
  `ComposerCommandMenu.tsx`, the same surface that already powers `@file`
  mentions via `useComposerPathSearch`). We add a new mention *source* (cluster
  targets) rather than building a new popup/menu. No new UI framework.
- **Proposal + human gate:** REUSE the existing human-gated task proposal store
  (`control_plane/task_proposals.py`, which already carries an optional
  `target` field) and the existing `/api/t3/approval-response` `tk-` branch.
  Proposing stages only; approval promotes to a queued intent; running (token
  spend) stays the separate existing execution gate. No new gate mechanic.
- **Transport:** REUSE the existing loopback `/api/t3/*` endpoint pattern in
  `dashboard.py` (loopback + origin guarded) and the client manifest / launch
  plan discovery surface. No new server.
- **Team/agent data:** REUSE `team_runtime.build_team_runtime_view` for recorded
  agents; fall back to a documented default role roster so `@` is useful before
  any run exists.

Conclusion: this is an additive composition of existing DevFrame + T3 surfaces;
no hand-rolled client/runtime/agent-UI layer.

## Safety contract

- AI/editor may only PROPOSE a cluster task; nothing runs and no tokens are
  spent on propose or approve. Running stays the existing human execution gate.
- New loopback endpoints are loopback-IP + loopback-origin gated (same as
  writeback-propose).
- Target is validated server-side against the enumerated cluster targets; the
  editor's claimed target is never trusted blindly.

## Slices

- **Slice 1 (this turn, engine/public-repo, fully tested):**
  `control_plane/cluster_control.py` — enumerate cluster targets (coordinator +
  recorded agents + default roster) and `propose_cluster_task` (reuses
  `stage_task_proposal`, staging only). Loopback endpoints
  `GET /api/t3/cluster-targets` and `POST /api/t3/cluster-dispatch`. Registered
  in the client manifest/launch plan for editor discovery.
- **Slice 2 (RD-Code fork UI, needs visual acceptance):** composer `@` mention
  source listing cluster targets, inserting a mention chip, and on submit POSTing
  to `/api/t3/cluster-dispatch`; pending cluster tasks + approve affordance.
