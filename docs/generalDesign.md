---
description: Proposed DSH-native multi-agent development design and delivery scope.
---

# DevFrame on DSH: General Design

English | [中文](generalDesign.zh.md)

## Summary

This is a proposed architecture and behavior baseline, not a frozen implementation plan or an implemented DevFrame product. The immediate scope is to validate a usable single-project workflow on DSH, including safe stop/recovery and the user's operating burden; multi-project coordination and memory remain candidate extensions. The deployment is one trusted user's local process, not a multi-tenant service or a sandbox for hostile code. These documents do not authorize deployment, external writes, or changes to the old governance core.

## Table of Contents

- [Scope and baseline](#scope)
- [System composition](#composition)
- [Document and delivery map](#delivery)
- [Functional reuse](#reuse)
- [Development workflow](#workflow)
- [Constraints and decisions](#constraints)

<a id="scope"></a>

## Scope and baseline

The source baseline is DSH `dsh-v0.1.2-alpha.4`, commit `4e84901e6471b79ec0338099867ebb4606d12bb5`, in the new `dsh-devframe` checkout. The local source, [architecture](architecture.md), and [Agent Teams reference](subsystems/agent-team.md) take precedence over assumptions from the supplied prompt. The old `dev-frame-system` checkout is a read-only source of functional examples, not an implementation base.

| Product requirement | Included outcome | Excluded from this design |
| --- | --- | --- |
| Supervised development | A controller delegates implementation, obtains real test results, and requests independent review. | Autonomous production deployment, push, merge, or credential changes. |
| Multiple projects | Shadow selects a project and routes work to its own controller session. | Nested Teams, arbitrary recursive delegation, or distributed scheduling. |
| Continuity | Native session recovery plus bounded, optional Obsidian memory. | A second transcript store, automatic knowledge certification, or mandatory vector search. |
| Controlled operation | Explicit permissions, cancellation, bounded retries, and observable failures. | A replacement DEV governance kernel or a generic agent-management platform. |

The product reuses DSH's web/terminal interaction and native model-provider configuration. No new desktop application, HTTP gateway, model billing system, or provider-specific agent loop is part of the first implementation.

<a id="composition"></a>

## System composition

Start with one feature plugin and one composition bundle/profile. Keep routing, role policy, and memory as modules in that plugin until a real independent lifecycle justifies a package split. Use the [experimental Team profile](../packages/experimental/agent-team-profile/cordis.patch.yml) as a composition reference, not as a claim that Teams ship in the official release payload.

```text
User
  |
Shadow session (independent root; routing only)
  +---- Project A controller (independent root / native Team Lead)
  |       +---- Worker A   (direct child)
  |       +---- Reviewer A (direct child)
  +---- Project B controller (independent root / native Team Lead)
          +---- Worker B   (direct child)
          +---- Reviewer B (direct child)

All sessions -> DSH session persistence
Project bindings -> DSH workspace/domain persistence
Selected knowledge -> optional Obsidian Markdown notes
```

The diagram describes a candidate expanded product. The first pilot goes directly from the user to one project controller, without Shadow or memory. Cross-root routing is not native Team membership: each project owns a flat Team, and Shadow neither edits project files nor leads a Team containing other Team Leads.

| Responsibility | Reuse | DevFrame addition |
| --- | --- | --- |
| Execution and model calls | [DSH plugins and agent lifecycle](architecture.md). | Role composition and request limits; no core loop fork. |
| Project team | Native roster, durable mailbox, task board, and Team UI. | Controller/worker/reviewer policy and guarded project completion. |
| Multiple projects | Workspace identity, root sessions, and native storage. | One workspace-to-controller binding and durable cross-root delivery. |
| Knowledge | Native runtime logs remain the source of execution history. | Small Markdown recall/read/append operations for reusable knowledge. |

One plugin package is a packaging choice, not a claim of low implementation effort. Distinguish the following work before estimating a slice; [Part 1](detailDesign-part1.md#integration) owns the permission hookup.

| Work | Reuse classification |
| --- | --- |
| Native sessions, Team roster/board, presets, and available UI | Configuration/composition reuse, followed by assembly tests. |
| Role guards and human project commands | Adapters over `tools.guard()`, the scoped command registry, and Goal services; new role/admission logic is still required. |
| Child-role options through Team creation | Required experimental-Team source change; no core-loop fork is planned. |
| Source fingerprints, check execution/evidence, writer ownership, budgets, and recovery | New feature implementation using native storage, tool, and lifecycle primitives; not solved by configuration alone. |
| Cross-root delivery and managed Vault notes | Separate candidate feature work, considered only after the pilot decision. |

<a id="delivery"></a>

## Document and delivery map

Document numbers identify subjects, not mandatory implementation order. Work proceeds through a single-project loop, single-project safe stop/restart, and the [usefulness trial](testAndAcceptance.md#usefulness). Only then does the user decide whether to continue into multi-project work and optional memory. Future sections remain revisable or removable.

| Design area | Owner | Requirements | When it applies |
| --- | --- | --- | --- |
| Single-project team and operation | [Part 1](detailDesign-part1.md) | `R1.1`–`R1.7` | First pilot: a real change, scoped evidence, consecutive tasks, and a usable human entry. |
| Safe stop and recovery | [Part 4](detailDesign-part4.md) | Selected `R4.*` paths | Before the pilot handles ordinary user work; the exact early subset is in the acceptance table. |
| Shadow and multiple projects | [Part 2](detailDesign-part2.md) | `R2.1`–`R2.4` | Candidate extension after the single-project value decision. |
| Obsidian memory | [Part 3](detailDesign-part3.md) | `R3.1`–`R3.4` | Optional extension; absence does not block coding acceptance. |
| Validation and product value | [Tests and acceptance](testAndAcceptance.md) | `AT1-*`–`AT4-*` | Distinguish integration proof, safe operation, and whether the user actually needs less intervention. |

The [single-project user journey](detailDesign-part1.md#user-flow) owns registration, configuration approval, starting, stopping, resuming, and results. There is no separate UI-design document or new planning database.

<a id="reuse"></a>

## Functional reuse

Use the old repository as a behavior-and-test reference after checking that each example is actually implemented. Port the smallest useful behavior into DSH conventions; do not import its controllers, approval hierarchy, or persistent state machine wholesale.

| Old reference, relative to the old checkout | Useful part | Exclude or defer |
| --- | --- | --- |
| `packages/control-plane/control_plane/obsidian_memory.py` and its project-plan tests | Bounded reads, project namespaces, create-only writes, and conflict handling. | Its governance imports, publication workflow, and a second runtime store. |
| `packages/control-plane/control_plane/codegraph_fresh_context.py` | Check index identity/freshness before returning bounded context. | A mandatory CodeGraph service for basic coding tasks. |
| `packages/ai-workflow-hub/src/ai_workflow_hub/context_layer/adapters/paper_pdf_fulltext_segments.py` | Page-aware PDF extraction and content fingerprints when a task needs papers. | Building a research platform before the coding workflow works. |

These old-checkout paths are discovery references, not dependencies or required files in the new repository. A fixture-only adapter is not evidence of a production integration. Browser/cloud coordination, permanent debate teams, and a separate arbiter remain outside the initial delivery.

<a id="workflow"></a>

## Development workflow

Use a small software-development loop: define the user's observable result, select a slice, implement it, exercise the real path, review the same source snapshot, then obtain human acceptance where required. Write an acceptance case before implementing behavior that could falsely report success or lose data.

- Keep purpose and exclusions here; keep tool fields and failure handling in the owning detailed design.
- Give each required behavior an `R*` identifier and at least one `AT*` case; do not create a separate requirement database.
- Change the relevant design and acceptance case together when implementation changes a decision; do not grow parallel status reports.
- Store execution evidence in the existing runtime/artifact location, outside the source checkout; keep only paths and a compact result in the delivery report.
- Record consequential trade-offs in the [proposal note](../.agents/notes/proposed/feature/2026-09-02-devframe-dsh-native-development.md); do not add a document for every routine choice.

Code completion, project acceptance, and publication are separate decisions. No worker or reviewer stages, commits, pushes, deploys, changes global configuration, or grants itself additional access. Any later publication workflow needs its own explicit user authorization.

<a id="constraints"></a>

## Constraints and decisions

The initial choice is a DSH-native workflow with explicit implementation work for role enforcement, task/evidence ownership, and safe lifecycle handling. Models plan and review; code checks identity, permissions, limits, and completion prerequisites. An LLM's claim is not a test result or authorization, and more participating roles are not evidence of greater usefulness.

The [Windows ACL provider](../packages/sandbox/sandbox-windows-acl/README.md) is write-restricted, not complete read/network isolation. In-process trusted plugins also share a process. The first release must describe these limits honestly; hostile repositories, strong cross-project secret isolation, or multiple untrusted users require a separately proven execution environment before admission.

Before a live-model demo, the user selects the model/provider, credentials, a disposable test project, and a spend limit. Before memory writes, the user selects an allowed Vault root and enables append. Before ordinary daily use, the reliability acceptance cases must pass on the actual Windows execution path. None of these choices is inferred from a pasted prompt.

## Dev Note

This design intentionally does not choose a vector database, distributed queue, external gateway, or additional model roles. Reconsider one only after an observed limitation is recorded with a failing acceptance example and a smaller alternative has been evaluated.
