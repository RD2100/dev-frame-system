# Agent Note: Agent-Evidence Journal Producer (Production Source)

Status: implemented

English | [中文](2026-09-06-agent-evidence-journal-producer.zh.md)

## Problem

The [completion admission seam](2026-09-06-goal-completion-admission-seam.md) and the [/goal-complete host command](2026-09-06-command-goal-binding-host-command-surface.md) consume `devframe/verification` and `devframe/review` evidence folded into the devframe projection, but no production source emitted those records: tests were the only producers, so a real host could only answer `NO_VERIFICATION_TEXT` / `NO_REVIEW_TEXT` at its completion command. The S4 toolface plan deferred production wiring, and the at105 rejection-matrix record left the residual explicitly to this slice.

## Decision

Two plain classes land in `agent-evidence`. `CheckRunner` executes a required-checks config's command as a real subprocess under the honesty contract: the stored command is re-verified for exact equivalence, outcomes map to a four-state result, output is captured verbatim, config order is deterministic, and a failed check is recorded as failed — never re-executed to hunt a pass. `AgentEvidenceJournal` is constructed with the composition's `DevFrameSessionJournal` and review gate — construction wires `EvidenceReviewGate`, and an unwired gate is a construction failure per the p05harden ruling. At the host's verification- and review-completion moments its two record methods load the configured checks store, run the checks, aggregate, and append through the session log's only schema-validated append path, so the devframe projection folds the records in and `/goal-complete` reads real evidence. The package exports the two classes plus their result types; no Context merge is registered, the devframe package carries zero diff, and the ledger tables stay zero-diff.

## Alternatives considered

**A Context-merged service instead of plain classes.** A merge would spend public catalog surface on a seam whose composition wiring is not landed yet; the plain classes keep the constructor dependency explicit at the composition site.

**Appending events outside `DevFrameSessionJournal`.** The journal is the only schema-validated append path; a second write face would break projection folding and duplicate validation.

**Retrying failed checks inside the runner.** Retry is the honesty contract's opposite: the record must state the real outcome of the configured command.

**Landing the composition wiring now.** Who constructs the producer, `ctx.sessions.flush` timing, and live-role authority belong to the S4 toolface slice.

## Consequences

- Hosts gain real producers for the admission's evidence chain; the no-evidence errors become reachable only when genuinely nothing was produced.
- Composition wiring, bounded output capture, a `timeoutMs` injection point beyond the 600s default, and ledger mirroring of journal evidence remain toolface-slice work.
- The design test matrix's duplicate-findings-id rejection lacks a named case; the path is anchored by the pass-plus-blocking-findings case and the devframe events suite, recorded as debt.
