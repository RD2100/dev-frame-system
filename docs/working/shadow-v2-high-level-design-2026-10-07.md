---
title: Shadow v2 high-level design
kind: reference
---

# Shadow v2 high-level design

This design defines one independent Shadow plugin for the installed DSH runtime. It is not a new task board, memory store, agent engine, or generic development-process platform. The [requirements baseline](shadow-v2-requirements-2026-10-07.md) owns product scope and acceptance.

## Architecture and ownership

Ship one private plugin package containing a lightweight application core, a stable human entry, and replaceable DSH adapters. Separate modules by responsibility, not one npm package per interface. The host owns sessions, model execution, tools, permissions, task executions, and backend data. Shadow owns project-to-owner bindings, request state, human-decision state, effect journals, and evidence references.

Dependency direction is entry → application core → four contracts ← adapters. The core cannot import Cordis, DSH, a task-board SDK, an Engram SDK, HTTP routes, or native file operations. Only the composition root creates adapters and exposes entry handlers. Each request carries a selected project context; there is no mutable global current-project variable.

| Component | Responsibility | Excluded responsibility |
| --- | --- | --- |
| Entry and composition root | Human interface, capability discovery, validated configuration, lifetime and adapter construction | Business state transitions and backend truth |
| Application core | Authorized coordination, request transitions, rd-loop sequencing and evidence reconciliation | Model loops, backend schemas, filesystem execution |
| IProjectRouter | Project identity, owner candidates, binding validation, route receipts and session observation | Task acceptance or automatic takeover |
| ITaskTracker | Project-scoped task queries, authorized creation/run, execution and verification evidence | Declaring acceptance from a column move or final reply |
| IMemory | Scoped preference/decision recall and source-linked persistence | Treating model advice as a human decision |
| ICodeReader | Bounded, read-only code discovery and reading within approved roots | Editing, shell access, full-disk search or credential reads |
| Shadow durable state | Atomic bindings, requests, decisions, effect intents and evidence pointers | Copies of authoritative task or memory databases |

## Stable entry and project routing

The entry resolves a named project and a persisted owner binding before routing. An existing binding is revalidated against project identity, the session's recorded working directory, existence and availability. Multiple eligible candidates return an explicit selection state. Offline, missing, mismatched and superseded owners remain distinguishable. Rebinding is an explicit authorized operation and preserves the prior association for audit.

The router uses public workspace/session services when mounted. Installing a package does not prove its service is available. New-session creation occurs only when the current request authorizes it; an attach failure may leave a created session and must be reconciled by identity instead of retried blindly. The backend's request-ID duplicate handling is preserved. A route receipt means accepted delivery, not completed review, completed work, durable feedback, or acceptance.

## Request and rd-loop lifecycle

The request lifecycle distinguishes received, resolving, overview, waiting-human, module-review, summary, executing, observing, completed, failed and indeterminate. These are coordination states, not a replacement for the host Goal or task execution lifecycle. A completed coordination request still reports task execution and acceptance as separate facts.

Persist the request identity, normalized-input hash, selected project, owner binding revision and authorized operations before any external effect. A repeated identity with the same input returns the existing state; a changed input is a conflict. Independent requests may run concurrently only when their ownership does not overlap; mutations of one binding or one request are serialized.

rd-loop produces a code-based overview, then stops before decisions that require human judgment. A valid human decision selects the next module or an explicitly permitted summary path. The summary records the actual judgment, the model recommendation and verification results as different source classes. Creating or running an improvement task requires a recorded authorization covering that project and operation.

## Human-decision boundary

The current host provides question correlation and ordinary connection authentication but no discovered public, unforgeable human-decision receipt. Neither source.kind=user, initiator text, Origin, a normal API cookie, a model reply, a peer message nor Goal continuation is a human authorization proof. Shadow must not use those values alone to leave waiting-human.

The entry owns a private decision-verification capability; it is not a fifth backend contract and is never exposed as a model approval tool. The proposed first secure provider verifies a user-presence and user-verification-required WebAuthn assertion from a pre-enrolled, authorized credential. A maintained verifier handles the protocol. Exact supported origin/RP configuration and credential bootstrap are detailed-design obligations; an IP-only origin or absent verified enrollment cannot silently select a weaker mode.

Each challenge binds project ID, owner/binding revision, request ID, decision ID, artifact revision/hash, allowed action and expiry. Verification and one-use consumption are committed atomically before applying the transition. Stale, replayed, mismatched, model-authored and relay-authored inputs do not approve. Missing verification support leaves a visible waiting-human/capability-missing state; no automatic round, timeout or restart approves it.

The trust boundary excludes an attacker controlling the host process, OS, registered authenticator or its approved enrollment. It does not assume that models lack ordinary terminal or HTTP tools. Real human verification is required for the final runtime walkthrough. A virtual authenticator is valid protocol-test evidence only, not evidence of a real human judgment.

## Task-board adapter and effect recovery

The initial adapter targets the public 0.4.5 task-board surface against installed DSH 0.2.0-rc.2. Its extension face supports query/create/integration/events but does not expose run. A run therefore uses the existing complete tool-execution pipeline or the documented HTTP action surface with host-authorized transport; never setStatus, a fabricated service, private ledger access or a direct tool-definition invocation.

All adapter operations enforce selected workspace ownership before returning records or issuing effects. Permission confirmation remains the host's responsibility and is never fabricated by Shadow. Authorization to coordinate does not raise a task's permission preset.

Write a durable effect intent before create/run/route/memory-write. Record the provider request identity and resulting task/execution/session IDs after reconciliation. A transport timeout or crash can leave the effect indeterminate: first query backend records and retained request receipts. Finite backend deduplication/history is not an indefinite exactly-once guarantee. If an effect cannot be proved absent or identified, retain indeterminate and do not automatically resend. An explicit retry is a new authorized operation, not a hidden repeat.

Observe settlement events, then obtain the complete public execution/verification record. Dedupe observations by backend execution identity and cursor. Host verification=passed is an acceptance fact; succeeded, manual done, disabled/skipped verification, UI echoes and final model claims are not. Capture necessary evidence before finite backend history expires without creating a competing task-status ledger.

## Memory adapter and provenance

The initial adapter uses Engram 0.7.15 public tools/HTTP. Project identity is established before a query or write, not assigned by the process working directory. The adapter must not invent a ctx.engram service, a new-save HTTP endpoint, or arbitrary backend provenance fields.

Engram shares storage across normalized git origins, including worktrees. A shared origin is not proof that two Shadow projects are authorized to share records. Where backend scope cannot be proved equivalent to the selected project, the adapter must restrict the query at the public execution boundary to explicitly project-attributed records or report project-scope-ambiguous. Fetching other-project records and filtering afterwards does not satisfy isolation. Legacy records of uncertain ownership are not silently imported.

Use an actual bound project execution context for public saves and a Shadow-owned source record linking memory ID to project/request/session/task/execution, artifact revision and human-decision receipt when applicable. Backend sourceSessionId alone does not carry the full chain. User judgment, model advice and verification findings remain distinguishable. Global user preferences are an explicit scope exception, not permission to read other project decisions.

## Code-reader adapter

Code reads and searches pass through the host's public filesystem/tool policy boundary. Native-root canonicalization and symlink/junction handling must deny an escape before content access; lexical prefixes or cwd alone are insufficient. The adapter excludes configured sensitive paths and credential files, bounds result count/bytes/time and propagates cancellation. The first provider may explicitly support only local native workspaces rather than claim all filesystem providers.

The host filesystem service does not provide glob/grep; existing search tools use subprocesses and include hidden/ignored files. The adapter must enforce equivalent root and sensitive-path constraints for that execution path, or offer a bounded traversal through the controlled filesystem service. Lack of a safe path is capability-missing, not a reason to search the machine.

## Persistence, restart and disposal

Use a versioned Shadow-owned storage domain for atomic state snapshots. Commit durable changes before publishing UI/events. Store opaque backend identities, revisions, cursors, bounded evidence and authorization links, not copies of the third-party databases. Persist waiting-human and indeterminate effects so a cold restart continues observation instead of recreating work or approving decisions.

Model-visible coordination messages and tool results use standard host session events and persistence barriers. Prefer reconstructable standard log data over a private projection required to open an old session after uninstall. An accepted send and an in-memory stream are insufficient evidence of durable delivery; flush and cold reopen are part of verification.

Disposal unregisters entry hooks and observers, cancels/settles owned operations and closes owned storage. It does not delete host tasks, sessions or memories. User task deletion and memory forgetting remain separately available. Installation, disable, uninstall and restart must be tested against isolated state, without changing the daily profile.

## Installed-host compatibility and verification

The supported first target is installed Desktop 2.0.17's DSH 0.2.0-rc.2 and Cordis 4.0.4, not the working tree's 0.1.6-alpha.1. Bundle metadata and DSH peers must match the actual runtime; no compatibility exemption substitutes for testing. Feature discovery happens in adapters and distinguishes installed artifact, mounted capability and executed result.

The primary real-composition environment uses the installed dsh launcher with a distinct custom web profile, explicit independent home/state/log/task-ledger/Engram dbDir/modelCacheDir, two unrelated project fixtures and a separate port. prepareProfile and dump-config can write configuration; neither targets the daily profile. DSH_HOME alone does not isolate Engram or Desktop's Electron userData/single-instance lock.

A custom-web walkthrough proves the actual installed runtime, not the entire Desktop shell. Desktop validation requires a demonstrably isolated userData/lock arrangement or a separate OS/VM; absence of that evidence stays an explicit limitation. Paid model calls, embedding downloads and publication are not silently triggered by keyless validation.

## Phase exit and maintenance handoff

Requirements review is complete; this document is a proposed high-level design pending independent review. Proceed to detailed design only after blocking findings are closed. Detailed design must pin the four contract types, challenge/enrollment verifier, adapter execution context, reconciliation rules, storage schema, supported entry/origin and fixture commands before implementation.

Maintain one authoritative development/evidence record with leader and worker identities, current artifact hashes, independent reviews, actual commands/results and remaining limits. Final delivery contains the installable plugin, adapter/permission documentation, scoped source and test evidence, cold-restart and removal instructions, and a ZIP separating deliverables from internal review records. File presence, source tests or a successful build are not the requirements' final acceptance.
