# Agent Note: DSH-native DevFrame development workflow

Status: proposed

English | [中文](2026-09-02-devframe-dsh-native-development.zh.md)

## Problem

The requested product needs supervised multi-agent development, cross-project coordination, and reusable memory. DSH already supplies sessions, tools, persistence, and experimental Teams, while the old DevFrame checkout mixes useful functions with a governance core the user explicitly does not want to carry forward.

## Proposal

Compose a single DSH feature plugin and profile around native flat Teams. Keep Shadow as an independent routing session, give each project its own controller root, and add only role enforcement, checked completion, cross-root delivery, and optional Markdown memory.

The requested [general design](../../../../docs/generalDesign.md), its four linked detailed parts, and the [acceptance reference](../../../../docs/testAndAcceptance.md) own the proposed behavior and delivery sequence. This note owns the trade-offs, not another implementation plan. No existing DSH decision is superseded and no runtime implementation is asserted by this documentation change.

## Alternatives considered

**Reuse the old DEV governance core.** This conflicts with the user's explicit scope and imports approval/state machinery unrelated to the first useful coding workflow. Only small functional behaviors and their tests are reference material.

**Build a new orchestrator and gateway first.** This duplicates native session, roster, mailbox, and task responsibilities. It is deferred until a demonstrated multi-process or external-client requirement needs a separate transport.

**Express every restriction in prompts.** Prompts can describe role behavior but cannot enforce tool permissions, real process termination, idempotent delivery, or snapshot-bound acceptance. A small deterministic policy implementation is necessary.

## Acceptance criteria

First validate the single-project scope selected by the [acceptance reference](../../../../docs/testAndAcceptance.md): role guards, Goal/task/evidence ownership, safe stop/recovery, and the human workflow. Then measure 3–5 real tasks against direct single-agent use and record the user's value decision. Multi-project and memory sections are candidate extensions, not a frozen backlog; expanding them requires a separate decision.

## Risks

Experimental Teams require pinned composition and child-option forwarding; `tools.restrict()` does not restrict scope-local Team registrations, so native monotonic guards are also required. One package still contains real work in fingerprints, writer ownership, recovery, and budgets. Windows/in-process constraints do not provide hostile-code isolation. Useful operation and reduced human intervention remain unproven until the trial; passing technical checks alone does not justify more roles or features. Cross-root delivery does not make arbitrary external effects exactly once. Recovery and rollback must retain compatible required-event readers and cannot resume old work without human authorization.
