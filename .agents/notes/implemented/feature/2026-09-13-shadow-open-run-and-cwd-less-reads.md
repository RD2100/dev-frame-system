# Agent Note: The shadow host open records the authorized run, and the read faces admit cwd-less sessions

Status: implemented

English | [中文](2026-09-13-shadow-open-run-and-cwd-less-reads.zh.md)

## Problem

The R2 real-model end-to-end verification (2026-09-12) ran the full shadow loop with a live model and left three product-face gaps that only manual workarounds closed. Opening a project through the panel or the Shadow conversation provisioned a `ready` binding, but nothing ever recorded the binding's authorized open run — `setActiveGoal` is a host-only seam no product face calls — so every host delivery was rejected with `SHADOW_GOAL_NOT_AUTHORIZED` until the verification hand-injected the run into the `shadow_router` storage. The router's `controllerProfile` defaulted to `'devframe'`, a preset id no shipped preset provides, so every provisioned controller session carried an `agentPreset` that fails when a consumer resolves it. And the Shadow conversation session — persisted under `sessions/_no-cwd/` because the designated session records no workspace cwd — could not be loaded from the Web history: the session controller's cold list dropped every cwd-less row and its history face rejected every cwd-less observation with `session/not-found`, even though `cwd` is an optional `SessionHeader` field and the live read face worked.

## Decision

The authorization ruling this round implements: **a human-initiated open through the panel or the Shadow conversation is a human authorization action, and the host bridge records it. The shadow and the model cannot self-authorize — the model-facing tool path keeps its gate, and `setActiveGoal` stays host-only.**

- **`openProjectForHost` records the run** (shadow-router; the contract wording lives in the shadow-routing definition). When the gated open lands `ready` and the binding records no authorized open run, the bridge records one — `host-run-<receiptRevision>` paired with `open-run-<receiptRevision>` — at most once per binding, re-reading the binding inside the operation chain so a stop that raced the open skips instead of authorizing a closed receiver. A repeated open, a replayed request id, and a later explicit host `setActiveGoal` keep or replace the record under the existing goal-switch semantics; the revision the open receipt carries may sit one past the durable one.
- **`controllerProfile` defaults to `'standard'`** — a shipped preset id — so provisioned controller sessions pin a preset that resolves; the README config rows name the new default and a behavior test pins it.
- **A cwd-less Session is a first-class read row** (session-controller). The history source no longer maps a cwd-less observation to `session/not-found`, the cold list no longer drops cwd-less rows, and following a cwd-less source schedules no background promotion, because the generic resume face stays project-scoped (its owner — the Shadow conversation host — resumes the session itself). Search stays project-scoped for now; the session-controller README records that boundary.

## Alternatives considered

**Record the run at the shadow-controller call sites** (the panel Remote and the conversation tool each call `setActiveGoal` after their open). Rejected: two call sites duplicate the recording, and any future host-plane caller silently skips it; the router bridge is the single chokepoint both human surfaces already converge on, which is exactly where the ruling places the recording.

**Re-authorize a fresh run on every host open.** Rejected: a repeated open would re-mint a new `host-run-<newRevision>` each time, bumping the revision without end and orphaning queued deliveries against the previous run; the run is established at most once, and a host `setActiveGoal` remains the only way to switch it.

**Tie the authorized run to the per-project `/devframe-start` goal flow** so the acceptance hash names a real Goal's admission instead of a host label. Deferred as the future tightening path: it needs the per-project goal stack the shadow family does not depend on today. The `host-run-<revision>` label keeps that migration open without pre-committing the router to it.

**Keep cwd-less Sessions invisible outside the Shadow card** (list, history, and search all scoped to a workspace). Rejected: an optional `SessionHeader.cwd` is a first-class durable state, the live face already surfaced such sessions, and the `session/not-found` rejection made the Web history a dead end for a persisted conversation the user owns.

**Ship a `'devframe'` preset** so the old default resolves. Rejected: the preset set is owned by agent-presets and no current consumer provides that persona; the router should default to a preset that exists rather than grow one for a default's sake.

## Consequences

Bought: open followed by send works end to end with no manual storage injection, pinned by the router's host-bridge tests and a two-boot real-Loader composition test that restarts over the same root; provisioned controllers pin a preset that exists; and a persisted Shadow conversation lists and pages from the Web history without scheduling a doomed activation. Cost: the open receipt's `bindingRevision` may predate the durable binding by one (documented on the bridge); a cwd-less session is listed and readable but not resumable or searchable through the generic faces; and the bridge's check-then-record spans two operation-chain segments, so two concurrent first opens of one workspace can record the same run with one extra revision bump — identical values, deliveries unaffected.
