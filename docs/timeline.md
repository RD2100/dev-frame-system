---
description: Compact milestone record for the DSH-native DevFrame pilot.
---

# DevFrame Timeline

English | [中文](timeline.zh.md)

This is a compact milestone index for decisions and verification outcomes. Detailed behavior belongs in the design and acceptance references; add one entry per meaningful milestone instead of copying every runtime event here.

## 2026-09-02 — Permission and Goal startup-order spike

**Status:** `passed` as keyless integration evidence; this is not product acceptance or a release claim.

**Baseline:** DSH commit `4e84901e6471b79ec0338099867ebb4606d12bb5`; the spike ran on `codex/dsh-permission-goal-spike` with disposable, uncommitted changes.

**Evidence:**

- The actual composition booted AgentLoop, Goal, Goal Round Driver, Subagent, Team, Team tools, and JSONL persistence together.
- A child `toolFilter` survived cold resume; the inherited probe was absent, while the scope-local `team_task_update` remained visible and was rejected by the reviewer guard even when a later pre-execute handler allowed it.
- Goal creation was disarmed before binding; the binding event was flushed before explicit resume; the resumed request used the same Goal identity and no unbound model request occurred.
- Command result: 8 test files and 199 tests passed, including 2 focused spike assertions and the native Team, persistence, scope, interception, Goal, and Goal Round Driver regressions.

**Decision:** The native seams are viable for a later implementation. The narrow Team child-composition forwarding change is required by the probe, while the role profile, `/project` workflow, real process-tree stop/recovery, live-model task, and usefulness trial remain unimplemented and unclaimed.

**Record hygiene:** No credentials, model spend, commit, merge, push, or deployment was used. After this documentation pass, remove the spike branch and discard only its disposable probe and source edits; preserve pre-existing user documents and unrelated working-tree files.
