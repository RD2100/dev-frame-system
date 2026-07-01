# Phase 1 Plan: Global Coordinator conversation shell

Status: `ready-for-implementation`
Date: 2026-06-30
Depends on:

- `docs/status/recon-receipt-global-coordinator-conversation-mainline.md`
- `docs/status/cluster-coordinator-design-and-roadmap.md`

## Reader and outcome

Reader:

- planner
- coder worker
- reviewer
- product owner

After reading this document, a fresh reader should be able to answer two
questions:

1. what exactly must change in Phase 1; and
2. what evidence proves Phase 1 is complete.

## Why this phase exists

The current product already has a cluster runtime, team objects, dashboard
monitoring, and a secondary client shell. But the top-level user experience is
still structurally wrong for "总控":

- "总控" behaves like a monitored item, not like a real ongoing conversation;
- a new conversation does not bind to a project early enough;
- the first screen still teaches "start a generic chat" more than "hand a goal
  to the coordinator";
- the lower workbench/input shell is visually unstable enough to weaken trust in
  the product;
- the user still needs to understand too much of the control plane to know what
  to do next.

Phase 1 fixes the **shell and interaction model**, not the entire orchestration
stack.

## Phase 1 objective

Make the Global Coordinator a first-class conversation surface in RD-Code, and
make project-bound goal creation the default path.

This phase succeeds when the user can:

1. open "总控" like a normal conversation;
2. hand the coordinator a new goal while choosing the target project up front;
3. tell the difference between a normal native chat and a coordinator-owned goal
   conversation;
4. use the shell without the current input/workbench layout feeling broken.

## Product laws for this phase

1. "总控" is a conversation, not a panel card.
2. New goal creation must bind to a project before execution semantics matter.
3. Dashboard stays monitoring/config only.
4. Native chat and team conversation are different conversation kinds.
5. The first-run experience must bias toward "send to coordinator" rather than
   "start an unbound generic chat".

## In scope

### 1. Global Coordinator entry becomes a real conversation

The sidebar/top-level navigation must expose "总控" as a first-class
conversation target, with the same interaction dignity as any other thread.

Expected user-visible behavior:

- clicking "总控" opens a conversation shell, not a status card;
- the user can send multiple messages there and see a persistent conversation
  history;
- the page teaches "give the coordinator a goal" rather than "inspect a
  control-plane record".

### 2. New goal flow binds project at creation time

The current new-thread experience is too generic. Phase 1 changes the flow so
that creating a coordinator-owned goal requires project selection.

Expected user-visible behavior:

- when the user starts a coordinator goal, they must choose a project (or
  confirm the current project) before the goal is considered valid;
- the shell makes clear whether the user is opening:
  - a native chat,
  - the global coordinator inbox,
  - or a project-bound goal conversation.

### 3. Conversation kinds become explicit

The client should stop pretending every conversation is the same thing.

Minimum kinds for Phase 1:

- `native_chat`
- `global_coordinator`
- `goal_conversation`

The exact type names may vary in code, but the product distinction must be
visible and durable.

### 4. Workbench/input shell cleanup

The current lower shell has obvious layout and density problems:

- project binding is too implicit or missing during new-goal creation;
- the composer/footer area is too tall and visually heavy;
- the message area and workbench controls do not feel compositionally stable.

Phase 1 does not require perfect design polish, but it does require the shell to
stop feeling broken.

## Out of scope

These are explicitly **not** Phase 1:

- full LangGraph migration;
- replacing OpenCode or ACP;
- full team-runtime maturity;
- complete human escalation policy engine;
- deep dashboard redesign;
- complete agent drill-down redesign;
- multi-project coordination logic beyond the shell entry and project binding.

## Reuse boundary

### Must reuse

- RD-Code / T3Code conversation shell and workbench patterns
- existing DevFrame runtime/read-model projection seams

### Must not hand-roll

- a brand-new chat shell
- a new dashboard-first total control UI
- a second, parallel conversation framework

### DevFrame-owned in this phase

- conversation kind semantics
- project binding rules
- coordinator thread identity
- goal creation contract
- mapping between reused shell UI and DevFrame runtime state

## Implementation slices

### Slice A — Conversation-first entry

Goal:

- "总控" becomes a real conversation entry point.

Work:

- add a dedicated coordinator thread/open path in the client;
- make the current total-control view reachable through conversation shell
  semantics;
- preserve existing monitoring data, but subordinate it to the conversation
  surface.

Acceptance:

- the user can click "总控" and land in a normal conversation shell;
- the shell persists and supports multi-turn interaction.

### Slice B — Project-bound goal creation

Goal:

- new coordinator goals are project-bound from the start.

Work:

- introduce project selection/confirmation into the new-goal flow;
- distinguish "native chat" creation from "coordinator goal" creation;
- make the current project visible and editable at the moment of goal creation.

Acceptance:

- a coordinator-owned goal cannot be created without a project binding;
- the selected project is visible in the created goal conversation.

### Slice C — Conversation-kind distinction

Goal:

- the product visibly differentiates conversation types.

Work:

- add the minimum thread-kind metadata and rendering differences;
- show enough label/state for the user to understand whether they are talking to
  a normal assistant, the global coordinator, or a project goal thread.

Acceptance:

- the distinction is visible in navigation and in the opened conversation
  surface;
- reviewer can confirm that "总控" is no longer just another generic chat.

### Slice D — Shell stabilization

Goal:

- remove the current obviously unstable layout behavior in the bottom workbench.

Work:

- reduce excessive empty height and awkward footer density;
- stabilize project/control strip placement;
- keep the typing surface visually coherent across empty/new/existing threads.

Acceptance:

- the screenshot-class issues that motivated this phase are visibly improved;
- no obviously broken blank strip, oversized footer, or missing project binding
  affordance remains in the main path.

## Verification

Phase 1 is not complete unless all of the following are true.

### Visual acceptance

- "总控" opens as a conversation shell
- new coordinator goal flow shows project binding up front
- footer/workbench shell no longer shows the current broken composition
- reviewer can distinguish native chat vs coordinator goal thread from the UI
  alone

### Behavioral acceptance

- coordinator-owned goal creation records a project association
- opening an existing goal conversation restores the correct conversation kind
- dashboard remains available, but is clearly secondary to the conversation path

### Engineering acceptance

- no new vendored client framework or second shell is introduced
- the reuse boundary remains RD-Code/T3Code shell + DevFrame semantics
- added state fields/objects are covered by targeted tests

## Evidence package expected from implementation

- screenshots or browser-based acceptance for:
  - total-control conversation entry
  - project-bound new-goal flow
  - existing goal conversation
- targeted tests for conversation kind and project binding behavior
- updated doc pointers if labels/flows change

## Automatic work vs human work

### I can continue automatically

- write the implementation brief and slice contracts
- adjust thread kind/object model
- implement coordinator-thread shell behavior
- implement project-bound new-goal flow
- clean up the shell layout and add targeted tests
- run local verification and prepare PR-ready evidence

### You should remain the human gate for

- final naming/product wording if multiple variants feel plausible
- final visual acceptance of whether the shell now feels like the right product
- merge/release/onlining decisions
- any decision that changes the product hierarchy more broadly than this phase

## What Phase 2 starts after this

Once Phase 1 is accepted, the next slice is **not** "more shell polish". The
next slice is:

- a thin LangGraph-backed Project Coordinator seam,
- with DevFrame still owning review, evidence, gates, and runtime projection.

That is where the product stops only looking like a coordinator and starts being
one.
