# Cluster Coordinator — Design & Roadmap (aligned)

Status: design locked with the product owner (2026-06-28). This is the agreed
target for the in-editor agent cluster and the phased plan to reach it. Pairs
with `docs/status/local-agent-cluster-roadmap.md` (engine state) and
`docs/status/recon-receipt-cluster-control-surface.md` (recon gate).

## Target design

Two-tier coordination, with the conversation as the live operating surface.

- **Global Coordinator (总体主控) — singleton.** One persistent local
  coordinator. Reached from a dedicated entry under Search in the sidebar
  ("总控"). Every `&goal` is received by the Global Coordinator, which spawns a
  per-goal **Project Coordinator** and coordinates across all of them. Its entry
  opens a single overview/inbox conversation: progress of every goal thread, a
  rollup of everything awaiting a human decision, and a place to give it a new
  goal or set escalation policy.
- **Project Coordinator (项目级主控) — one per goal.** Approximately today's
  `/rdgoal` / workflow engine run. Plans the goal, dispatches subtasks to member
  agents, and drives to completion under project norms (`rules/`, control-plane
  contracts). With refinement in the `&` command it follows the instruction;
  without it, it autonomously picks the best path and keeps going until the goal
  is met.
- **Member agents (编码agentN).** The executors (OpenCode etc.) driven over ACP
  with the governance/permission gate.

### One goal = one conversation (with an ID)

- `&goal` (with optional refinement) creates one **goal conversation**. Each
  conversation has a short unique **ID** (e.g. `g-7a3f9c`) shown by the title and
  copyable; coordinators and the user use the ID to reference/locate a
  conversation (e.g. `&g-7a3f9c add one more requirement`).
- A goal conversation is a **"team conversation"**: its content is the live
  DevFrame coordinator+member collaboration stream. This is a distinct kind from
  a normal **native chat** (you talking to a single local AI). Normal chats are
  unchanged.

### The conversation is the live surface

- Real-time streaming into the goal conversation, e.g.
  `主控 @编码agent1 发布任务` → `编码agent1 执行…` → `编码agent1 → @主控 完成`.
- Clicking a member agent drills into that agent's detail: its thinking, tool
  calls, and execution process (its session/`session/update` stream).

### Human-gate model

- The **dashboard is monitoring only** — never the place to approve.
- A human-issued `&goal` is the human's authorization. Confirmation, when needed,
  is a **one-click inline confirm in the conversation** (B), never a dashboard
  trip.
- The **Global Coordinator runs on a human escalation policy** (Phase D): the
  human pre-configures "only ask me in cases X; otherwise decide autonomously;
  defer deferrable decisions; pre-write dev docs so prerequisites are prepared up
  front for full auto." Goal: keep the human only on the most core decisions.

### Concurrency

- **No fixed cap.** Run as many concurrent goal conversations / project
  coordinators as the machine allows — this is a real requirement. (Resource
  pressure is handled by scheduling/backpressure, not an artificial limit.)

## Current building blocks (honest)

- `/rdgoal` + `workflow_engine` (plan→execute→review): the Project Coordinator
  embryo, single goal/run.
- `team_runtime`: 6 of 7 team objects are real recorded facts; missing real
  agent-to-agent messages and task-claim contention.
- ACP executor (`acp_session` / `--driver acp`): drives OpenCode live with the
  permission gate.
- `&` composer trigger + `/api/t3/cluster-targets` + `/api/t3/cluster-run`
  (inline-confirm → start a project-coordinator run; no dashboard approval).
- Dashboard = monitoring only.
- **Immediate blocker:** OpenCode health check times out (execution backbone
  down) — any real run is blocked until fixed.

Biggest gaps to the target: (1) the singleton Global Coordinator (persistent,
cross-project, policy-driven); (2) real-time team stream into the editor
conversation; (3) per-agent drill-down; (4) the human escalation policy engine;
(5) goal-conversation IDs and the two-kinds-of-conversation split.

## Phased plan (each phase independently verifiable)

- **Phase 0 — Fix the execution backend.** Resolve the OpenCode health-check
  timeout so real runs are possible. (Until then, phases can be validated in
  dry-run.)
- **Phase A — `&goal` runs one goal end-to-end (single Project Coordinator).**
  Inline-confirm (B) → start a Project Coordinator run (reuse the workflow
  engine: plan→execute→review). Key events (plan, task dispatch, agent results,
  review verdict) stream back as messages into the goal conversation. Goal
  conversations get IDs; goal conversation vs native chat split lands here.
- **Phase B — Real-time multi-agent stream + agent drill-down.** Team events
  render live as conversation messages (`主控 @编码agent1 发布任务` /
  `编码agent1 → @主控 完成`); add real agent-to-agent messages + task claim.
  Clicking an agent opens its detail (thinking / tool calls / execution).
  - **Status (2026-06-29): in progress.** Per-agent coordinator↔agent messages
    already record into the team message_bus during execute (`record_task_created`
    / `record_result`) and stream into the goal detail view (2s poll). Added the
    **agent drill-down**: the goal detail now lists each agent as a clickable
    card, and `GET /api/t3/cluster-run-agent` returns one agent's execution view
    (status, changed files, verification, tokens/cost, tool calls, the Markdown
    ExecutionReport). Also hardened: orphaned runs (control plane restarted
    mid-run) are reconciled to `interrupted` instead of a frozen `running`.
    Remaining: agent-to-agent messages + explicit task-claim events, and finer
    live token/thinking streaming via ACP `session/update`.
- **Phase C — Refined instructions + norm-bound autonomy.** With instruction:
  follow it. Without: the coordinator autonomously picks the best path under
  `rules/` and project norms and keeps going until done. Enforce methodology at
  the executor (read-only truly blocks writes, network truly gated).
  - **Status (2026-06-29): first slice landed (goal triage).** `&<target> <goal>`
    now classifies the goal (`goal_triage.classify_goal`): a conversational goal
    (greeting / capability question, e.g. "你好" / "你能做什么") is answered
    directly by the coordinator with no agents and no token spend (run recorded
    as `answered` with the reply surfaced as a coordinator message); an
    actionable development goal dispatches the workflow as before. The classifier
    is conservative — when in doubt it runs the goal. Remaining: instruction
    extraction/grounding and true executor-side methodology enforcement.
- **Phase D — Global Coordinator (cross-project) + human escalation policy.**
  Persistent singleton Global Coordinator receives every `&goal`, spawns Project
  Coordinators, runs **unbounded concurrency**, and coordinates across them. The
  escalation policy engine governs when to ask the human vs decide / defer /
  rely on pre-written dev docs. The "总控" sidebar entry opens its overview/inbox.
- **Phase E — Maturity.** Managed-default per-agent worktree isolation with
  automatic diff review/merge-back, cancel/resume, metrics, release flow.

### Defaults (not separately re-confirmed)

- "Goal achieved" is declared by the coordinator + review phase; the human can
  interrupt/correct in the conversation at any time.
- Goal conversations keep a human-readable title (generated from the goal); the
  ID is only for locating/addressing.
- Start (Phases A–C): each `&goal` needs one inline (B) confirm before a real,
  token-spending run. Policy-driven full autonomy (Global Coordinator decides
  without per-goal confirm) arrives in Phase D.

## Execution order

`0 → A → B → C → D → E`, starting with Phase 0 (fix OpenCode).

## Customization layer (the "visual, customizable" moat)

Audit (2026-06-29): the framework's customizable units — skills, methodology
permission profiles, rules, the agent roster, provider/agent defaults, run
params — are today authored in text / Python / CLI; only RD-Code's inherited T3
settings (providers, connections, …) are visually editable, and the DevFrame
dashboard is read-only. To make customization the moat, every unit follows one
pattern: **machine-readable config (first-class object) → control plane reads it
and overrides the hardcoded default → RD-Code edits it visually.**

Rollout (each slice independently verifiable):
1. **Agent roster — DONE (backend + visual editor).** `schemas/cluster_roster.schema.json`
   + `cluster_control.load_cluster_roster/save_cluster_roster` (stored at
   `<runtime>/cluster-roster.json`); `list_cluster_targets` uses the configured
   roster when present, else the hardcoded default; a malformed file safely
   falls back. Endpoints `GET/POST /api/t3/cluster-roster` (loopback + origin
   gated). RD-Code "团队" editor in the coordinator pane adds/edits/removes agents
   and saves. This is the reference pattern for the units below.
2. **Methodology binding — DONE (custom skills resolve + governed runs show it).**
   `resolve_methodology(requirement, runtime_dir=...)` is now runtime-aware and
   merges user-created custom skills (`<runtime>/skills.json`) into the trigger
   map with the same enriched shape as built-ins; `run_go_dispatch` passes its
   runtime dir so a custom skill's `@trigger` governs the executor packet just
   like a built-in. `start_cluster_run` resolves and records the governing
   methodology on the run; the goal detail shows a methodology badge
   (read-only / network / red-green) and the coordinator declares it in the
   timeline. Remaining: turn the executor's read-only/network traits into true
   sandbox enforcement (today they are conveyed as packet constraints, same as
   built-in).
3. **Rules — DONE (machine-readable + visual editor).** `rules_config.py` parses
   the built-in prose `rules/*.md` (`## RULE <id>:` + `- **Field**:` blocks) into
   structured read-only records (`list_builtin_rules`), and adds a custom store
   at `<runtime>/rules.json` (`load_custom_rules` / `save_custom_rules` /
   `list_all_rules`, custom overrides built-in by id). New
   `schemas/custom_rules.schema.json`; endpoints `GET/POST /api/t3/rules`
   (loopback + origin gated), registered in the manifest (`Rule` object type
   added to the manifest schema). RD-Code "规则" editor in the coordinator pane
   lists read-only built-ins and creates/edits custom rules (id, priority P0-P4,
   rule text, trigger, verification). Remaining: a runtime enforcement engine
   that checks actions against the now-machine-readable rule set.
4. **Skills — DONE (backend + visual editor).** A skill is now a complete,
   machine-readable, editable unit (identity + behavior profile). New
   `schemas/custom_skills.schema.json` + `custom_skills.py`
   (`load_custom_skills` / `save_custom_skills` / `list_all_skills`, stored at
   `<runtime>/skills.json`); built-in repo skills stay read-only, custom skills
   override by id and carry their own read-only / network / red-green traits and
   instructions. Endpoints `GET/POST /api/t3/skills` (loopback + origin gated),
   registered in the manifest (`Skill` object type added to the manifest schema).
   RD-Code "技能" editor in the coordinator pane creates/edits custom skills
   visually. (Binding a custom skill into an actual run is the methodology-binding
   work in slice 2.)
5. Run defaults (agents / model / methodology) → per-project visual config.
