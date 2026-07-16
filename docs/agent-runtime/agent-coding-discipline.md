# Agent Coding Discipline

Lifecycle state: active operating discipline and planning sidecar

Authority level: agent behavior guidance and governance input. This document is
not stable runtime behavior, not completion evidence, and not a substitute for
tests, artifacts, review decisions, or gate decisions.

Related docs: [Methodology Skills Registry](methodology-skills.md), [Verification Gates](verification-gates.md), [Runtime Invariants](runtime-invariants.md), [Outcome-First Delivery](outcome-first-delivery.md), [Skill Asset Utilization Plan](../status/skill-asset-utilization-plan.md), [Review-First Governance Kernel Implementation Spec](../status/review-first-governance-kernel-implementation-spec.md)

## Purpose

This document consolidates scattered agent coding discipline into one canonical
catalog. It exists so agents, skills, review prompts, and future governance
fixtures can cite stable rule IDs instead of rephrasing the same behavior in
many places.

The catalog is intentionally practical: every rule maps a dishonored behavior to
an honored behavior, a required skill route, a produced artifact, acceptance
evidence, failure state, and first enforcement phase.

## Rule Catalog

| Rule ID | Principle | Dishonored behavior | Honored behavior | Required skill route | Required artifact | Acceptance evidence | Failure state | First enforcement phase |
|---|---|---|---|---|---|---|---|---|
| `agent-discipline-001` | Interface and API truth | Guessing interfaces, commands, schemas, or call shapes | Inspect docs, schemas, symbols, source, or current tool output before changing behavior | CodeGraph or `codebase-recon` practice -> evidence gate | Source citation or inspected-symbol note | Referenced file/schema/symbol and verification command when changed | `blocked` or `insufficient_evidence` | Immediate discipline; Phase 1A negative fixture where applicable |
| `agent-discipline-002` | Requirement alignment | Starting from vague intent or assumed product goals | Frame goal, non-goals, success criteria, and user-visible outcome before implementation | `intent-framing-gate` -> work-type router | Intent/scope note or TaskSpec section | Matching work-type route, artifact, and acceptance evidence | `human_required` for unresolved intent | Immediate discipline; Phase 1A WorkItem fields |
| `agent-discipline-003` | Domain humility | Inventing business rules or policy from model common sense | Cite project docs/rules/evidence or ask the smallest bounded question | context/evidence gate | Context snapshot, doc citation, or bounded question | Evidence links or explicit missing-context reason | `blocked` or `human_required` | Immediate discipline; Phase 1A context artifact rules |
| `agent-discipline-004` | Reuse discipline | Adding redundant mechanisms or hand-rolling mature surfaces | Reuse existing modules, rules, schemas, skills, or record a reuse assessment | reuse assessment -> evidence gate | Reuse note, recon receipt, or scoped design decision | Existing asset citation plus reason for any new surface | `blocked` for missing recon/reuse check | Immediate discipline; Phase 1A non-goal checks |
| `agent-discipline-005` | Verification completeness | Skipping tests, negative cases, or public-surface verification | Run targeted tests/checks or state the exact blocker and residual risk | `tdd` when coding -> `evidence-driven-acceptance` | Test, verifier output, or blocked verification note | Command, exit code, and relevant output | `insufficient_evidence` | Immediate discipline; Phase 1A required negative tests |
| `agent-discipline-006` | Architecture restraint | Broad refactors, new subsystems, or adjacent churn outside the slice | Stay within approved slice and public-surface boundaries | `review-governance-kernel` for Phase 1A -> evidence gate | Diff summary and scope statement | Changed-path list tied to approved work type | `blocked` for scope expansion | Immediate discipline; Phase 1A forbidden top-level object tests |
| `agent-discipline-007` | Honest uncertainty | Pretending certainty when context, evidence, or authority is missing | Mark `blocked`, `insufficient_evidence`, or `human_required` with a concrete reason | review/gate decision | Decision or report section with reason | Missing evidence/context named explicitly | `blocked`, `insufficient_evidence`, or `human_required` | Immediate discipline; Phase 1A decision outcomes |
| `agent-discipline-008` | Iterative delivery | Bulk uncontrolled edits, hidden state changes, or unreviewable batches | Stage work into small slices with verification and rollback clarity | `devprocess` practice -> evidence gate | Plan slice, diff summary, or cleanup inventory | `git diff --check`, relevant tests, and path-specific summary | `blocked` for unsafe or unclear batch | Immediate discipline; cleanup/review workflows |
| `agent-discipline-009` | Outcome primacy | Counting Goal updates, worker starts, polling, or reports as delivery | Tie each batch to a user, product, research, or risk outcome | outcome-first milestone -> evidence gate | Project-local milestone record | Outcome artifact, actual diff, verification, review verdict, or accepted delivery | `insufficient_evidence` | Immediate discipline; orchestration rules |
| `agent-discipline-010` | Risk-proportional verification | Running release-level checks after every low-risk hunk or weakening high-risk gates for speed | Use focused checks per batch and broad checks at the applicable risk or milestone boundary | outcome-first risk profile -> verification gate | Verification profile in milestone or ExecutionReport | Commands and exit codes mapped to declared risk | `blocked` for missing critical/high checks; warning for redundant low-risk governance | Immediate discipline; review rules |
| `agent-discipline-011` | Bounded continuity | Treating the whole project as one endless chain, or stopping after each batch to await master instructions | Continue explicit TaskSpecs to terminal; while the finite Delivery Goal remains active, let the project root select the next eligible milestone; do not invent out-of-scope work | outcome-first Delivery Goal -> milestone -> runner policy | Goal candidate set, milestone decision, and resume pointer | `accepted_done` for the inner milestone plus next project-selected milestone, or a valid Delivery Goal terminal state | `blocked` for fabricated continuation or master micro-management | Immediate discipline; runner/orchestration rules |
| `agent-discipline-012` | Task-selection truth | Inferring a missing feature from dirty candidates, stale Goals, or repeated negative probes | Inspect committed HEAD, tests, backlog, and actual failure before remediation | Recon Gate -> outcome-first selection | Focused HEAD capability note | Cited path/symbol/test plus uncovered gap | `blocked` or already satisfied | Immediate discipline; recon rules |

## Usage Rules

- Cite rule IDs when a methodology skill, review prompt, or handoff needs to
  explain agent discipline.
- Do not copy this table into every skill; link to the rule ID and add
  task-specific evidence requirements only where needed.
- Do not treat compliance with this document as completion evidence.
- Do not add runtime enforcement until review-governance fixtures and gate
  decisions can validate the rule.
- Do not promote local or plugin skill behavior into this catalog without a
  provenance, license, and review decision.

## Phase 1A Integration

During the review-first governance kernel slice, enforce only the discipline
rules that naturally fit existing packet objects:

- missing context blocks readiness;
- run success does not complete a work item;
- report text is not evidence by itself;
- gate pass requires evidence;
- projection status is derived, not invented;
- scope expansion remains blocked unless the governing work item allows it.

Broader rule telemetry, fingerprints, dashboard compliance, or skill promotion
records wait until the kernel can validate evidence and decisions.
