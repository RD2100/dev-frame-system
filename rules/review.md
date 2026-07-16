# Review Rules -- RD2100 Agent Runtime v2

> Domain: review, evidence, and reporting
> Phase 0-5: P0/P1 active; P2-P4 within approved task scope

---

## RULE review-001: No Fake Green

- **Priority**: P0 (Hard Stop)
- **Trigger**: Reporting task or gate results
- **Scope**: All phases
- **Rule**: Never report FAILED or BLOCKED as PASS. If a check fails, report it as failed. If a check cannot run, report it as BLOCKED. "Fake green" (disguising failure as success) is a hard stop.
- **Verification**: Exit code matches reported status for every task.
- **Conflict Handling**: Known flaky tests may be reported as BLOCKED with a reference to the flaky-test issue. They must not be reported as PASS.

---

## RULE review-002: Execution Report Must Follow Template

- **Priority**: P2 (Evidence)
- **Trigger**: Completing any batch or non-trivial task
- **Scope**: All phases
- **Rule**: Execution reports must include: batch identifier, status, pre/post git diff, file list, constraint compliance table, forbidden action check, and blocking issues (if any).
- **Verification**: Report contains all required sections.
- **Conflict Handling**: If a section is not applicable (e.g., no blocking issues), explicitly state "None" rather than omitting.

---

## RULE review-003: Reviewer Index for Delegated Work

- **Priority**: P2 (Evidence)
- **Trigger**: Completing delegated code work
- **Scope**: All phases
- **Rule**: Final reports for delegated code work must include a Reviewer Index: a list of files changed, line ranges, and what to check. P0/P1 fixes must include a real-path test or probe, not only logic-fragment checks.
- **Verification**: Reviewer Index present with actionable file/line references.
- **Conflict Handling**: If a real-path test is impossible (e.g., requires unavailable hardware), note the limitation and suggest an alternative verification.

---

## RULE review-004: Evidence Chain

- **Priority**: P2 (Evidence)
- **Trigger**: Making any consequential claim
- **Scope**: All phases
- **Rule**: Claims must form a chain back to observable evidence. "X is configured" -> "file Y contains Z at line N" -> `Read` output showing line N. Each claim in a report must be traceable to a command output or file read.
- **Verification**: For each claim, ask "how do we know?" Answer must reference a verifiable observation.
- **Conflict Handling**: If direct evidence cannot be collected, state the claim as "unverified" with confidence level.

---

## RULE review-005: Gate Results Must Be Explicit

- **Priority**: P1 (Scope Control)
- **Trigger**: Running verification gates
- **Scope**: All phases
- **Rule**: Every gate check must produce an explicit result: PASS, FAIL, WARNING, BLOCKED, or SKIPPED. Implicit or assumed gate results are not acceptable. Skipped gates must include a reason.
- **Verification**: GateResult records have explicit status fields.
- **Conflict Handling**: If a gate tool is unavailable, report the gate as BLOCKED, not SKIPPED.

---

## RULE review-006: Pre/Post Status Required

- **Priority**: P2 (Evidence)
- **Trigger**: Any task that may modify files
- **Scope**: Phase 0-5
- **Rule**: Run `git status --short` before and after the task. Include both in the ExecutionReport. The diff between pre and post must only show approved changes.
- **Verification**: Pre and post status are included in report, diff is clean.
- **Conflict Handling**: If git is unavailable, use `ls -R` with timestamps as fallback.

---

## RULE review-007: Verification Must Be Risk-Proportional

- **Priority**: P1 (Scope Control)
- **Trigger**: Selecting verification for a code, config, docs, or research batch
- **Scope**: All phases
- **Rule**: Match verification to blast radius and evidence criticality. Low-
  risk local changes use static or focused checks and share a broad check at
  the containing milestone. Medium-risk work adds affected integration or build
  checks. P0/P1, production, security, concurrency, and formal experiment
  entry paths require a relevant real-path regression and milestone-level broad
  verification.
- **Verification**: ExecutionReport names the risk profile and separates
  per-batch commands from milestone commands.
- **Conflict Handling**: A stricter repository, release, or safety gate wins.
  Governance budget never downgrades a critical or high-risk check.

---

## RULE review-008: Review Requires an Explicit Verdict

- **Priority**: P1 (Scope Control)
- **Trigger**: Counting a reviewer run as review evidence
- **Scope**: All phases
- **Rule**: Reading the diff or restating test output is not a review. Valid
  review evidence contains reviewer identity, reviewed inputs, explicit
  verdict, findings, and unresolved P0/P1 count. Replace an empty reviewer at
  most once. Critical and high-risk work remains blocked without independent
  review; lower-risk fallback is allowed only when project policy explicitly
  authorizes and labels it.
- **Verification**: Review artifact has a parseable verdict and findings list;
  executor and reviewer identities satisfy the selected review profile.
- **Conflict Handling**: Missing or invalid verdict is BLOCKED, never PASS.

---

## RULE review-009: Control Events Are Not Outcome Evidence

- **Priority**: P2 (Evidence)
- **Trigger**: Reporting progress or deciding that a stalled project advanced
- **Scope**: All phases
- **Rule**: Goal refreshes, source reads, hashes, provider probes, worker
  starts, PID polls, and unchanged status reports are control events. They may
  support an audit, but they do not prove delivery progress without a milestone
  artifact, actual diff, verification result, review verdict, or accepted
  delivery.
- **Verification**: Each progress claim references at least one outcome artifact
  defined by the active milestone.
- **Conflict Handling**: Report control-only turns as unchanged status, not
  business progress.
