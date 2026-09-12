# Agent Note: Bounded pluginized Agent topology and dispatch

Status: proposed

English | [中文](2026-09-05-pluginized-agent-topology-and-dispatch.zh.md)

## Problem

The current project plan needs to coordinate many low-coupling capabilities, but a project controller, plugin lead, and leaf worker can be mistaken for different kinds of session or represented only by UI labels. That ambiguity makes SessionID ownership, Worktree ownership, child-agent permissions, recovery, and merge responsibility difficult to verify.

The development program also mixes platform foundations, existing third-party plugins, and later multi-project ideas. Without explicit plugin ownership and bounded creation depth, concurrent work can duplicate installation, overwrite shared files, exhaust provider quotas, or leave a task appearing active without durable evidence.

## Proposal

Define a bounded three-level topology: one first-class Project Controller Session at L0, first-class Plugin Lead Sessions at L1, and non-spawning Leaf Worker Sessions at L2. Controller and Lead use the same Agent and Session mechanism, each has a durable SessionID and independent Worktree, and the parent relation is stored as authorization and presentation metadata.

Allow only the Controller to create Leads and only a Lead to create Workers within its own plugin ID. Enforce the rule at tool dispatch, cold restore, and forged-request paths, with a maximum of two creation edges and no recursive creation.

Split the implementation into independently owned plugin seams for SessionID, hierarchy, Worktree registry, Controller scheduling, evidence, reliability, UI, explicit external-agent routing, provider integration, and optional extensions. Keep one small shared contracts library as the only intentional cross-plugin source dependency.

Make the Controller the only main-tree merge owner. Leads may commit in their Worktrees and request review; QA validates one fixed composition candidate before exact paths are promoted.

## Alternatives considered

**A flat controller with internal labels:** Rejected because labels do not create independent SessionIDs, Worktree ownership, or enforceable lead permissions.

**Unbounded recursive Agent creation:** Rejected because it makes quotas, ownership, recovery, and termination unbounded and permits leaf workers to create work outside their responsibility.

**A weaker special session class for Plugin Leads:** Rejected because the user needs Leads to create Workers and resume independently; making them first-class sessions preserves one identity and lifecycle model.

**One monolithic orchestration plugin:** Rejected because it couples unrelated provider, UI, mobile, reliability, and project features and prevents independent Agent ownership and safe concurrency.

## Acceptance criteria

The runtime can create one Controller, multiple first-class Leads, and bounded Workers with unique durable SessionIDs, exact parent records, and one Worktree binding per Agent.

Creation attempts from a Worker, creation of a Lead by a Lead, depth overflow, duplicate ownership, forged parent data, and ambiguous Worktree paths fail closed in live and cold-restored paths.

The Web UI renders the same records as a collapsed Controller → Lead → Worker tree, expands one level per arrow action, and copies a complete SessionID directly without a dialog.

The Controller can schedule independent plugins concurrently, serialize shared contracts/profile/main-tree integration, recover from restart and rate limits, and merge only reviewed exact paths.

The five requested ready-made repositories are validated by one isolated validation Lead, with authentication/quota skips reported honestly and no production-profile contamination.

## Risks

The topology adds durable registry and event fields, so event ownership, session-log recovery, and schema evolution must be planned before broad plugin work.

The bounded depth intentionally gives up arbitrary delegation; a future deeper workflow requires a new reviewed design rather than silently increasing the limit.

Independent plugins still compete for shared provider quotas and profile files; the Controller must keep concurrency and integration queues explicit.

Third-party compatibility, authentication, quota, and licensing remain external risks and cannot be converted into green evidence by local profile loading alone.
