# Verification Gates -- RD2100 Agent Runtime v2

> Batch B1, 2026-05-27
> Defines finding severity and evidence semantics. Delivery intensity is chosen
> from the normative
> [`OUTCOME_FIRST_DELIVERY_POLICY.md`](../../packages/agent-acceptance/policies/OUTCOME_FIRST_DELIVERY_POLICY.md),
> not from one fixed verification cycle.

P0-P3 classify the consequence of a finding. They are not four mandatory tool
runs for every change. A task first selects a delivery profile from blast
radius, reversibility, and evidence criticality; it then applies the relevant
gates without weakening any P0/P1 hard stop.

## Gate Hierarchy

```
                      +------------------+
                      |   P0: Security   |  <-- Must pass. Failure = BLOCKED.
                      +--------+---------+
                               |
                      +--------v---------+
                      |   P1: Correctness |  <-- Must pass. Failure = FAILED.
                      +--------+---------+
                               |
                      +--------v---------+
                      |   P2: Quality    |  <-- Should pass. Failure = WARNING.
                      +--------+---------+
                               |
                      +--------v---------+
                      |   P3: Completeness|  <-- Nice to pass. Failure = INFO.
                      +------------------+
```

## Gate Definitions

### P0: Security Gate

| Check | Tool/Method | Pass Condition |
|-------|-------------|----------------|
| No secrets in output | `security-checklist` (PII protection) | No keys, tokens, passwords in code or logs |
| No command injection | Manual review of bash arguments | All user input sanitized or hardcoded |
| No path traversal | Manual review of file paths | All paths within project root |
| Thread safety | `security-checklist` (thread safety) | No unsynchronized shared state |
| Input validation | `security-checklist` (input validation) | All external inputs validated |
| Encryption | `security-checklist` (encryption) | Sensitive data encrypted at rest/in transit |

Gate result: PASS -> continue. FAIL -> **BLOCKED, must not deliver**.

### P1: Correctness Gate

| Check | Tool/Method | Pass Condition |
|-------|-------------|----------------|
| Build evidence | Reviewer-approved validation command or blocked_by_env record | Exit code 0 when approved and run, otherwise explicitly blocked/skipped |
| Test evidence | Reviewer-approved validation command or blocked_by_env record | Existing checks green when approved and run, otherwise explicitly blocked/skipped |
| No regression | Before/after comparison from approved evidence | Same or fewer failures when evidence exists |
| Exit code contract | Check agent-acceptance exit codes | 0=PASS, 1=BLOCKED, 2=FAILED |

Gate result: PASS -> continue. FAIL -> **FAILED, must fix before delivery**.

### P2: Quality Gate

| Check | Tool/Method | Pass Condition |
|-------|-------------|----------------|
| Code review | `ai-code-review` (P2 level) | No code quality issues |
| Lint | `claude-lint-fix` | No lint errors |
| Performance | `performance-lint` (5 anti-patterns) | No main-thread IO, no N+1, no leak |
| Code style | Match existing project style | Consistent with surrounding code |
| No dead code | Manual review | No unused variables, imports, functions |

Gate result: PASS -> continue. FAIL -> **WARNING, should fix but may proceed with justification**.

### P3: Completeness Gate

| Check | Tool/Method | Pass Condition |
|-------|-------------|----------------|
| Documentation | `claude-md-docs` | New features documented |
| Changelog | `changelog-generator` | Changes logged |
| Test coverage | Manual review | New code has corresponding tests |
| Error handling | `security-checklist` (error handling) | Errors handled, not swallowed |

Gate result: PASS -> continue. FAIL -> **INFO, not blocking**.

## Delivery Profiles

The policy profiles remain the machine-facing vocabulary. The L0-L3 labels are
only concise operating lanes for humans; they do not create another schema.

| Lane | Policy profile | Typical work | Required verification | Review |
|------|----------------|--------------|-----------------------|--------|
| L0 | `read_only`, or docs-only `low` | Inventory, explanation, narrow docs correction | Citations, links, parsing, or focused static checks | Root review; no code reviewer |
| L1 | `low` | Local P2/P3 behavior, selectors, pure reducers, narrow diagnostics | Focused checks and a real path when behavior changes; broader checks wait for the containing milestone | Root review unless a stricter rule applies |
| L2 | `medium` | Multi-file product flow, shared UI/business behavior, non-destructive config | Focused tests plus affected integration or build; one broad regression at the milestone or PR boundary | One batch review; independent review only when repository policy requires it |
| L3 | `high`, `critical` | P0/P1, auth, concurrency, shared contracts, release, production, credentials, destructive work | Real-path regression plus affected integration and relevant broad/full verification | Independent review required; `critical` also keeps its explicit human gate |

Recon triggers in `rules/recon.md`, exact Git ownership in `rules/git.md`, and
human gates remain applicable in every lane. A low lane removes duplicate
ceremony; it never downgrades a high-severity finding.

## Gate Selection

1. Declare one policy profile before selecting tests or review.
2. Identify relevant P0-P3 findings from the actual scope. Any applicable P0
   or P1 failure remains blocking.
3. Run the profile's focused evidence first. Run broad or full checks once at
   the containing milestone, PR, release, or L3 boundary.
4. Use the profile's review requirement. Do not dispatch an independent
   reviewer merely to satisfy a low-risk ritual.
5. Record explicit PASS, FAIL, WARNING, BLOCKED, or justified SKIPPED results
   only at the natural batch or milestone boundary.

## Agent-Acceptance Gate Mapping

The agent-acceptance workqueues map to these gates:

| WorkQueue | Gates Covered | Tier |
|-----------|:---:|:---:|
| `local-quality.queue.json` | P2 (Quality) | Tier 1 |
| `docs-quality.queue.json` | P3 (Completeness) | Tier 1 |
| `recovery-regression.queue.json` | P1 (Correctness) | Tier 1 |
| `cleanup-dryrun.queue.json` | P2 (Quality) | Tier 1 |
| `release-readiness.queue.json` | P1 + P2 + P3 | Tier 2 |

## Gate Bypass Policy

| Scenario | Allowed? | Requirement |
|----------|:---:|-------------|
| P0 failure | NO | Never bypass security gate |
| P1 failure with known flaky test | YES | Document the flaky test, link to issue |
| P3 info only | N/A | Not a gate, informational only |
| Emergency hotfix | YES (P1 only) | Human approval + post-fix gate run |
