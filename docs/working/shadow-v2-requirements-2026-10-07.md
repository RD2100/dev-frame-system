---
description: Acceptance baseline for a standalone Shadow plugin on the installed DSH host.
---

# Shadow v2 requirements — 2026-10-07

English | [中文](shadow-v2-requirements-2026-10-07.zh.md)

## Summary

Shadow provides one stable coordination entry for explicitly selected projects. It recovers the responsible session, consults the existing task board and memory, guides a human through code-review decisions, advances authorized work, and reports evidence-linked results. This is a requirements reference and development baseline, not a claim that the plugin is implemented or accepted.

## Table of Contents

- [Scope and authority](#scope-and-authority)
- [Required behavior](#required-behavior)
- [Architecture constraints](#architecture-constraints)
- [Acceptance](#acceptance)
- [Development controls](#development-controls)
- [Dev Note](#dev-note)

## Scope and authority

The deliverable is an independent plugin compatible with the installed DSH host, plus reproducible isolated validation, an installable archive, and maintenance guidance. It is not a new general-purpose development platform. Installation or activation in the daily-use profile and publication are not authorized.

The development lead is the current main session. Independent subagents analyze and review requirements, design, and code; an implementation author cannot approve their own output. Technical development reviews do not require the user to approve every intermediate step. Human decisions required by the running product remain mandatory.

The source checkout is [the DSH development repository](../../README.md); the installed host is `D:\DSH\DSH Desktop\resources\app`. Their dependency versions differ. Compatibility statements must name the tested host and backend versions, rather than infer compatibility from the source checkout.

## Required behavior

| ID | Requirement | Observable result |
|---|---|---|
| R1 | Keep a durable project-to-responsible-session association. | A restart recovers the same association; an existing responsible session is preferred over creating another. |
| R2 | Handle ambiguous candidates, offline or invalid sessions, and rebinding explicitly. | Ambiguity never selects the first arbitrary candidate; failed delivery never silently replaces ownership. |
| R3 | Limit coordination to the selected projects and granted operations. | Listing or opening a project does not authorize task execution or takeover of unrelated projects. |
| R4 | Reuse the existing task board as the authority for tasks, runs, and acceptance. | Shadow consults current tasks and execution records, identifies duplicates, and links actual task and run identifiers. |
| R5 | Keep retried requests safe. | The same request and content does not create or start duplicate work; a reused identifier with different content is rejected. |
| R6 | Read relevant user preferences and project decisions; persist sourced review conclusions. | Records identify their project, request, session, evidence, and whether they represent a human judgment, model suggestion, or verification result. |
| R7 | Isolate project memory and code access. | Project-level records and code outside the selected project's scope are denied by default. Global user preferences are the explicit, separately labeled exception. |
| R8 | Implement the runtime rd-loop: overview, human review of key modules, then summary. | An overview and concrete decision points are visible; necessary human judgments are recorded before dependent work advances. |
| R9 | Preserve human waiting across retries, restart, and Goal continuation. | Waiting is a non-failure state; model output, plugin relays, and automatic continuation cannot manufacture a human decision. |
| R10 | Distinguish transport, review, execution, and acceptance outcomes. | Message delivery is not reported as completed review, completed work, or passed acceptance; results reference the relevant authoritative evidence. |
| R11 | Declare missing or incompatible capabilities. | Each unavailable backend yields an actionable capability/error result; affected operations fail closed while independent read-only work remains usable. |
| R12 | Preserve user tasks and memory when disabled or uninstalled. | Plugin contributions are removed, but existing backend tasks, runs, and memory remain intact. |

## Architecture constraints

The lightweight core depends on four interfaces: `IProjectRouter` owns project identity, responsibility, and routing; `ITaskTracker` adapts existing tasks and runs; `IMemory` adapts scoped memory and provenance; `ICodeReader` uses host-controlled reading and searching. Concrete service names, tool schemas, version mappings, and transport details belong only in adapters.

The first adapters target the installed task-board backend and engram. Their public interfaces and actual mount availability must be verified. Unsupported backend combinations are reported as unsupported, not advertised as universal compatibility.

One plugin may contain the core, entry, persistence for Shadow-owned associations and requests, and current adapters. Separate npm packages are not required. The plugin must not implement another task board, memory database, Teams service, Goal engine, session engine, or filesystem service. Backend-private databases are not an integration API.

Modules have one current responsibility, communicate through explicit typed contracts, and do not access another module's internal state. Ownership of persistence, cancellation, event disposal, and recovery is explicit. Runtime controls that vary by deployment are validated configuration; interface defaults are resolved at their owning boundary.

## Acceptance

| Case | Required isolated evidence |
|---|---|
| A1: Installation | Install the archive into a separate host home/profile through the real DSH launcher, load the plugin, and exercise its entry without altering the daily profile. |
| A2: Complete outcome | User goal → project/responsible session → task and memory lookup → overview → genuine human module judgment → sourced summary or improvement task → authorized execution → actual task/run/acceptance feedback. |
| A3: Isolation | Two projects with distinct owners, code, and memory; prove permitted access plus denial of reads and writes to all other-project records, including unmarked records, and denial of cross-project code access through real executors. |
| A4: Retries | Repeat routing, task creation, execution, and human decision delivery; prove no duplicate task/run or double application. |
| A5: Recovery | Interrupt after persistence and around external effects, then restart; recover associations and human waiting, and reconcile authoritative task/run state. |
| A6: Human boundary | Attempt approval via model tools, relay messages, wrong-project inputs, stale decisions, and Goal continuation; reject them without advancing. Accept a current genuine human decision once. |
| A7: Missing backend | Omit or disable each required backend and reject incompatible versions; display the exact unavailable operations without reporting success. |
| A8: Disable/uninstall | Remove plugin contributions, reach lifecycle quiescence, and verify that backend tasks and memory still exist and can be read independently. |

A source unit test, visible UI, received message, model claim, or skipped check is not substitute evidence for a real-host acceptance case. Evidence names the artifact version/content, host/backend versions, command, result, and coverage limitation. Changed inputs invalidate dependent evidence.

## Development controls

Work proceeds through requirements analysis, high-level design, detailed design, implementation, and testing. Each stage has an independent review and an explicit disposition of findings before dependent work advances. Test design starts with these requirements; tests execute against the implemented behavior.

The lead owns integration and shared build outputs. Subagent write scopes and task dependencies are explicit before concurrent implementation. Existing source changes, daily configuration, and third-party data are preserved. Handover names the entry, supported adapters, lifecycle and recovery responsibilities, reproducible checks, and remaining limitations.

## Dev Note

This working baseline expresses the current user request. Public host-interface analysis and the independent requirements review are still in progress. The final implementation location and runtime integration design are not selected here.
