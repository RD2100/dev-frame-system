# Product Maturity Roadmap

Last updated: 2026-06-30.

This document is intentionally critical. It is not a feature wishlist. It is a
product-convergence plan for turning DevFrame from a capable control plane into
a mature tool that heavy software engineers would choose to use every day.

## Brutal Diagnosis

DevFrame is already strong as an engineering substrate:

- release gates are real
- evidence and review boundaries are real
- the CLI, dashboard, bridge, MCP/ACP seams, and customization layer are real

But it is still weak as a daily-use product.

The current project has three identities at once:

1. a coding tool (`devframe code`, `go`)
2. a governance/control plane (`rdgoal`, actions, gates, evidence)
3. a research platform (MCP, ACP, Web AI, T3 bridge, cluster runtime)

That combination is powerful for builders and confusing for heavy users.

The current failure mode is not "missing features". The failure mode is
"insufficient product convergence".

## Non-Negotiable Product Decision

DevFrame must pick one primary product.

Recommended primary product:

- **Primary**: `devframe code`
- **Secondary**: dashboard / action queue / session views
- **Tertiary**: RD-Code / T3 desktop client
- **Experimental**: web-AI orchestration expansion, ACP-default execution,
  paper workflow, deeper multi-agent research surfaces

Reason:

- `devframe code` is the shortest path to a mature product because it already
  looks closest to Codex / Claude Code / OpenCode usage patterns.
- The dashboard is useful, but it behaves like a control console, not a primary
  work surface.
- RD-Code is promising, but it is still a bridge target with product-shape
  uncertainty. It should not be treated as the mainline until the CLI loop is
  excellent.

## What To Stop Doing

These are the highest-value subtractions.

1. Stop treating every capability as first-class in the top-level UX.
2. Stop exposing internal system nouns too early: `packet`, `runtime_dir`,
   `action_id`, `gate`, `bridge bundle`, `provider binding`.
3. Stop presenting dashboard/client/research tracks as if they are equally
   primary.
4. Stop trying to "feel mature" by adding more surfaces before the default path
   is short and obvious.
5. Stop using the README as an architecture catalog. It must become a product
   entry doc.

## Target Product Shape

The mature product should feel like this:

1. open a repo
2. run one command
3. see one clear task session
4. prepare work
5. review or execute
6. inspect the result
7. continue from the same session later

The user should not need to understand the control plane to use the product.
The control plane should exist behind the product.

## Borrow Ruthlessly From Mature Tools

Borrow from Codex / Claude Code / OpenCode:

- one obvious main entrypoint
- short default path
- strong session continuity
- explicit execution boundary
- visible but minimal status model
- advanced capability behind progressive disclosure
- recoverability when a run fails or pauses

Do not copy blindly:

- broad feature menus
- research/demo surfaces in the main help text
- multiple equally-prominent execution models
- architecture-first UX

## Roadmap

### Phase 0: Product Line Surgery

Goal:

- make the product legible in one minute

User-visible outcome:

- a heavy user immediately understands that DevFrame is a governed coding CLI
  with an optional control console

Concrete work:

- make `devframe code` the only mainline product in all top-level docs
- demote or hide second-line commands from primary help surfaces
- rewrite root docs around a single golden path
- clearly label dashboard as "control plane" and RD-Code as "secondary client"
- clearly label experimental capability families

Files/modules to change:

- `README.md`
- `README.zh-CN.md`
- `packages/control-plane/README.md`
- `packages/control-plane/QUICKSTART.md`
- `packages/control-plane/control_plane/cli/_usage.py`

Acceptance gate:

- a new user can answer "what is DevFrame?" in one sentence
- a new user can find the primary command in under 15 seconds
- top-level help no longer reads like a capability dump

Hard rule:

- no new top-level command families before this phase is complete

### Phase 1: Golden Path Compression

Goal:

- make the default daily loop genuinely short

User-visible outcome:

- from repo root to prepared run should feel as direct as Codex / Claude Code /
  OpenCode, not like navigating a framework

Concrete work:

- compress the main happy path to `code`, `code status`, `code execute`
- make session resume the default mental model
- unify terminal output so every run shows the same compact structure
- reduce repeated flags and explanatory noise
- keep advanced knobs available but not foregrounded

Files/modules to change:

- `packages/control-plane/control_plane/cli/_coding.py`
- `packages/control-plane/control_plane/go_dispatch.py`
- `packages/control-plane/control_plane/worker.py`
- `packages/control-plane/control_plane/dispatch_packet.py`
- `packages/control-plane/control_plane/visual_state.py`

Acceptance gate:

- an existing user can prepare a bounded run in under 30 seconds
- 80 percent of common use fits inside `devframe code`, `status`, `execute`
- the terminal summary is scannable without opening docs

Hard rule:

- no new workflow verbs until the main loop feels finished

### Phase 2: Trust and Recovery

Goal:

- make the product feel safe to depend on daily

User-visible outcome:

- users trust that a run can be resumed, inspected, or rejected without losing
  control

Concrete work:

- unify run/session/action status language
- make paused, blocked, failed, approved, and completed states crisp
- ensure every prepared run has a reliable resume surface
- make evidence/report output feel productized, not internal
- ensure failures degrade honestly and point to the next action

Files/modules to change:

- `packages/control-plane/control_plane/dashboard.py`
- `packages/control-plane/control_plane/client_launcher.py`
- `packages/control-plane/control_plane/runtime_digest.py`
- `packages/control-plane/control_plane/team_runtime.py`
- `packages/control-plane/control_plane/workflow_engine.py`

Acceptance gate:

- a user can recover from interruption without reading internal docs
- failure states never require understanding packet internals
- the dashboard adds clarity instead of introducing new nouns

Hard rule:

- no new observability surface unless it directly improves recovery

### Phase 3: Power-User Depth

Goal:

- keep advanced capability, but only after the core product is stable

User-visible outcome:

- advanced users unlock more leverage without making the default path worse

Concrete work:

- expose multi-agent fan-out as an advanced expansion of `devframe code`
- expose model/provider selection as an advanced control, not a starting choice
- expose customization layer through focused UX, not raw category sprawl
- keep ACP and RD-Code progressing behind explicit maturity labels

Files/modules to change:

- `packages/control-plane/control_plane/model_providers.py`
- `packages/control-plane/control_plane/methodology_dispatch.py`
- `packages/control-plane/control_plane/scope_resolver.py`
- `packages/control-plane/control_plane/scoped_store.py`
- `packages/control-plane/control_plane/t3_bridge_bundle.py`
- `packages/control-plane/control_plane/client_manifest.py`

Acceptance gate:

- advanced features do not lengthen the beginner path
- users can ignore them completely and still have a complete product

Hard rule:

- advanced capability must be additive, never mandatory

### Phase 4: Client Mainline Decision

Goal:

- decide whether RD-Code becomes a true primary client or stays secondary

Decision criteria:

- does the CLI product already feel complete without it?
- does the client reduce task friction or merely visualize internals?
- can the client own a real daily loop, not just inspection?

If YES:

- promote RD-Code to a first-class client track
- build a true task/session/review UX
- keep dashboard as operator view

If NO:

- keep RD-Code as a secondary integration shell
- stop spending mainline energy on making it look primary

Hard rule:

- do not let the client strategy stay ambiguous for multiple milestones

## What Gets Frozen Until Mainline Converges

Freeze or sharply demote:

- paper workflow as a top-level product story
- broad web-AI orchestration storytelling in main docs
- additional protocol expansion that does not improve the main coding loop
- more dashboard surfaces that expose system internals
- trying to make CLI and desktop equally primary

## Suggested 90-Day Plan

Days 1-14:

- complete Phase 0
- ship a rewritten top-level story and command surface

Days 15-35:

- complete Phase 1
- tighten `devframe code` into the canonical daily loop

Days 36-60:

- complete Phase 2
- productize recovery, evidence, and status semantics

Days 61-90:

- complete Phase 3
- then make the client-mainline decision in Phase 4

## Success Metrics

The roadmap is working only if these move:

- first successful run from clone to prepared session: under 5 minutes
- repeat run in an existing repo: under 30 seconds
- user can explain the product in one sentence
- primary workflow uses three commands or fewer most of the time
- control-plane terms disappear from default-path docs and output
- ten consecutive real tasks complete without needing internal status docs

## Final Judgment

DevFrame should not try to become "Codex + Claude Code + OpenCode + T3 + MCP
lab" at the same time.

It should become:

- a mature governed coding product first
- a capable control plane second
- a protocol and client research platform third

That ordering is the whole game.
