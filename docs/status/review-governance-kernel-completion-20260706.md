# Review-Governance Kernel Completion Status

> Status: 2026-07-07 (updated)
> Author: executor-agent (Claude Code)
> Authority: external GPT review through P3-1; local GPT-equivalent subagent
> review and local execution evidence for P3-2

## Summary

The review-governance kernel authority boundary work has progressed through
P3-2. Phase P1 and P2 phases all passed external GPT review. P3-1 passed.
P3-2 is code-complete after internal audit fixes (58 tests pass) and passed a
2026-07-07 local GPT-equivalent subagent review. A 2026-07-07 local hardening
pass also fixed cross-validator whitespace and document-authority divergence
issues. Commit `2725227d` landed P3-2 and the related public/release gate
hardening. Follow-up commit `bd73d6bc` synchronized the post-commit status and
received local GPT-equivalent branch-level review PASS plus a full local release
gate PASS at that checked state. The repository is still not release-ready until
PR/CI and publication evidence exist.

## Phase Completion Ledger

| Phase | Module | Tests | GPT Rounds | Final Verdict |
|-------|--------|-------|------------|---------------|
| P1-2 | skill_usage_validator | 32 | 5 | PASS |
| P1-4 | continuation_validator | 37 | 2 | PASS |
| P2-1 | review_feedback_validator | 34 | 2 | PASS |
| P2-2 | policy_escalation_validator | 56 | 2 | PASS |
| P2-3 | browser_transport_validator | 35 | 2 | PASS |
| P3-1 | paper_workspace_validator | 50 | 3 | PASS |
| **P3-2** | **graph_projection_validator** | **58** | **1 local GPT-equivalent** | **PASS (local review)** |

## P3-2: Graph Projection - Local GPT-Equivalent Review PASS

### Files
- `packages/control-plane/control_plane/graph_projection_validator.py`
- `packages/control-plane/tests/test_graph_projection_validator.py`

### 58 tests pass, covering:
1. **Forbidden operations (14 tests)**: build_ui, init_graph_db, broad_extraction, writeback,
   graph_driven_code_change, export_canvas, add_node, add_edge, annotate blocked;
   project/query/seed_context allowed; unknown operation rejected; all-forbidden-listed
2. **Inferred edges != source truth (6 tests)**: inferred+truth rejected, inferred only ok,
   cited+truth ok, dangling source/target rejected for source-truth cited edges,
   multiple inferred collected
3. **Annotations != decisions (3 tests)**: annotated+promoted rejected, annotated only ok,
   cited+promoted ok
4. **Context seed authority (9 tests)**: non-authority rejected, inferred not authoritative,
   human_decided/external_reviewed ok, needs cited incoming edge, inferred edge not enough,
   missing cited source rejected, non-authority cited source rejected, authoritative sources list
5. **Node shape (6 tests)**: missing id, whitespace id, missing type, invalid type,
   missing authority, invalid authority
6. **Edge shape (6 tests)**: missing id/source/target/type, invalid type,
   cited edge needs citation_source
7. **Projection (12 tests)**: empty payload, by_node_type, by_authority, authority_seeded_count,
   authority_seeded_count requires authoritative cited incoming source chain,
   by_edge_type, inferred_truth_edges counted, dangling source-truth cited edges excluded,
   shape-invalid excluded, read-only, operation_count
8. **Good path (2 tests)**: minimal valid graph, full valid projection

### Design pattern
- `validate_graph_projection()` + `derive_graph_projection()` share helpers
- `_is_valid_graph_node_shape()` / `_is_valid_graph_edge_shape()` - structural
- `_check_graph_boundary_rules()` - boundary rules
- `derive` uses shape helpers plus the same authoritative cited incoming source-chain
  helper for context-seed authority counting
- All string fields `.strip()` for whitespace bypass prevention

### Internal audit fixes before GPT submission

Read-only audit found four P1/P2 gaps before external GPT submission:

1. Context seed authority could be invented by citing a missing source node or a
   non-authority source node.
2. Mutation-like operations `add_node`, `add_edge`, and `annotate` were known but
   not forbidden in the first read-only graph slice.
3. `derive_graph_projection()` counted authoritative seed nodes without requiring
   the cited incoming source-chain that validation required.
4. Source-truth cited edges could carry authority through dangling source or
   target node references.

All four are fixed in the local P3-2 files and covered by tests. P3-2 passed
local GPT-equivalent subagent review on 2026-07-07, with no P0/P1/P2 findings.

## Local Review Status

P3-2 was reviewed by a delegated local subagent running the same GPT-family
model class instead of using the browser/CDP external submission path. The
review covered `graph_projection_validator.py`,
`test_graph_projection_validator.py`, this status document, and adjacent
validator patterns. Verdict: PASS; no P0/P1/P2 findings.

## Cross-Validator Hardening (2026-07-07)

A follow-up read-only audit found local P1 issues outside the already submitted
P3-2 graph slice:

1. Whitespace-only required IDs/refs could be accepted or counted by five
   validator projections.
2. `derive_authority()` could mark a document authoritative when
   `validate_promotion()` would reject it for missing or blank `content_hash`.

Local fixes completed:

- `skill_usage_validator`: required values and adoption evidence refs now use a
  strip-aware required-value guard in validate and derive paths.
- `asset_utilization_validator`: base-invalid records, including blank
  required IDs/refs, no longer count as utilized or adopted.
- `continuation_validator`: blank IDs/refs no longer count toward active
  continuation projection.
- `review_feedback_validator`: blank review/adoption IDs and evidence refs no
  longer count as adopted feedback.
- `mcp_utilization_validator`: blank required IDs/refs no longer count as
  valid utilized/adopted MCP usage.
- `document_authority`: `derive_authority()` and `validate_promotion()` now
  share the same nonblank `content_hash` gate before `authoritative`.

Main-thread verification:

- targeted hardening suite -> 248 passed;
- `packages/control-plane/tests/test_public_snapshot.py` -> 23 passed in the
  current 2026-07-07 rerun;
- `scripts/verify-public-snapshot.ps1` -> PASS;
- `git diff --check` -> PASS with line-ending warnings only;
- `packages/control-plane/tests` -> 1387 passed, 1 skipped.

## Public Gate And Semantic Hardening (2026-07-07)

A second local audit found that several checks were implemented but not yet
strong enough as public/release gates:

1. `docs_drift_validator` checked caller-provided payloads but did not yet build
   its payload from the real repository docs.
2. `verify-public-snapshot.ps1` could pass while forbidden root review artifacts
   still existed in the Git index as delete records.
3. `validate_packet()` accepted some pass decisions whose evidence lacked a
   resolvable source artifact, allowing client projections to trust weak facts.
4. `document_authority` still allowed blank document/evidence/decision
   identities to form an authoritative chain.
5. Public helper scripts and active docs still contained local checkout or
   concrete review-session details.

Local fixes completed:

- added a real repo-path docs drift payload builder and test, and indexed the
  docs drift gate in `reviewer-index.md`;
- added release-gate support for `verify-public-snapshot.ps1
  -FailOnTrackedForbidden`, so forbidden tracked review artifacts block release
  until their delete records are committed;
- parameterized the phase-1B submit helper scripts so bundle paths,
  conversation URL, and CDP endpoint come from arguments or environment
  variables instead of local machine values;
- replaced the active project-local skill binding doc's hard-coded checkout
  path with `<repo-root>` and extended public snapshot tests to reject that
  local path pattern;
- tightened `review_governance_validator.validate_packet()` so review/gate pass
  decisions require non-empty supporting evidence with nonblank,
  artifact-backed `source_artifact_id`;
- tightened `document_authority` identity canonicalization so blank document,
  evidence, or decision IDs cannot produce authoritative client projections;
- added a glob-based reviewer-index guard for public governance validators and
  their tests.

Additional verification:

- docs drift + public snapshot focused suite -> 41 passed;
- review governance/document authority/client projection/docs drift/public
  snapshot focused suite -> 191 passed;
- `scripts/verify-public-snapshot.ps1` -> PASS;
- `scripts/verify-public-snapshot.ps1 -FailOnTrackedForbidden` -> expected FAIL
  before the forbidden review artifact delete records were committed;
- sensitive local path/session scan over public helper scripts and active docs
  -> no matches;
- `git diff --check` -> PASS with line-ending warnings only;
- `packages/control-plane/tests` -> 1403 passed, 1 skipped.

## Common Bug Patterns Discovered Across Phases

| Pattern | Fix |
|---------|-----|
| Whitespace bypass (empty/blank fields) | `.strip()` all string fields |
| Path alias bypass (`/vault/.`, `/vault/sub/..`) | `posixpath.normpath()` |
| Validator/projection divergence | Split helpers shared by both |
| Forbidden ops not in known set | Add forbidden ops to known set |

## Public Surface Gate Fix (2026-07-07)

A follow-up public-surface audit found tracked root review bundles and a bare
`chatgpt-review-reply.txt` in the repository surface. These files are local
review artifacts, not reusable public distribution files.

Cleanup action:

- moved local copies to an ignored local runtime archive;
- committed removal of 90 tracked artifact paths in `15a9d78d`;
- updated `scripts/verify-public-snapshot.ps1` so root `review-bundle-*` paths
  and `chatgpt-review-reply.txt` fail the strict snapshot gate while tracked by
  Git.

Verification:

- `scripts/verify-public-snapshot.ps1` -> PASS after cleanup;
- `packages/control-plane/tests/test_public_snapshot.py` -> 23 passed,
  including release-readiness and P3-2 local-review-status regression checks;
- `scripts/verify-public-snapshot.ps1 -FailOnTrackedForbidden` -> PASS after
  commit `15a9d78d`;
- `git ls-files -- chatgpt-review-reply.txt review-bundle-*` -> 0 tracked
  forbidden review artifact paths.

## Release Gate Stabilization (2026-07-07)

The full release gate initially exposed three dashboard review-gate failures
where `/review-gates/open?gate_id=gate-1` returned HTTP 502. A read-only
subagent audit traced the common cause to developer/system HTTP proxy settings:
`urllib.request.urlopen()` could send loopback dashboard requests through a
proxy instead of directly to the pytest-local server.

Local fix completed:

- added `packages/control-plane/tests/conftest.py` with an autouse pytest
  fixture that preserves existing `NO_PROXY` values while appending
  `127.0.0.1`, `localhost`, and `::1`.

Verification:

- target dashboard review-gate tests under forced bad proxy and empty
  `NO_PROXY` -> 3 passed;
- `packages/control-plane/tests/test_dashboard_actions.py` -> 24 passed;
- `scripts/verify-release.ps1` -> PASS, including `1512 passed, 1 skipped`,
  strict public snapshot PASS, control-plane wheel smoke PASS, and
  `git diff --check` PASS with line-ending warnings only.

## P3-2 Local GPT-Equivalent Review (2026-07-07)

Delegated reviewer: local subagent thread `019f3ad0-7885-7883-ae32-5b0b8d28da64`.

Findings:

- P0: none.
- P1: none.
- P2: none.
- P3: update status docs after accepting local GPT-equivalent review.

Review verdict: PASS. The reviewer confirmed that inferred edges cannot become
source truth, annotations cannot become decisions, context seed authority
requires an authoritative label plus cited incoming authoritative source chain,
authority-bearing cited/source-truth edges cannot propagate through dangling or
shape-invalid endpoints, and `derive_graph_projection()` shares the relevant
helpers while remaining read-only.

Review evidence:

- reviewer-ran target tests -> 58 passed;
- main-thread target tests -> 58 passed;
- main-thread probes for missing/shape-invalid authority sources ->
  `valid=False`, `authority_seeded=0`, `total_edges=0`;
- review bundle source/test hashes match current worktree files.

## P3-2 Commit Evidence

- commit `2725227d`: `Complete review-governance hardening and gates`
- included `packages/control-plane/control_plane/graph_projection_validator.py`
  and `packages/control-plane/tests/test_graph_projection_validator.py`
- pre-commit local release gate: `scripts\verify-release.ps1` -> `1512 passed,
  1 skipped`, strict public snapshot PASS, control-plane wheel smoke PASS, and
  `git diff --check` PASS

## Post-Commit Branch Review And Gate Evidence

- commit `bd73d6bc`: `Update post-commit review-governance status`
- delegated local GPT-equivalent branch-level review: PASS, no P0/P1/P2
  findings; P3 recommendation was to attach the full release-gate rerun evidence
- main-thread full release gate at the checked `bd73d6bc` state:
  `scripts\verify-release.ps1` -> `1512 passed, 1 skipped`, strict public
  snapshot PASS, control-plane wheel smoke PASS, and `git diff --check` PASS
- this evidence is local-only; PR/CI and publication evidence are still missing

## Next Steps for Handoff Agent

1. Prepare a PR/push only after explicit human approval.
2. Re-run the full release gate on the final PR/release candidate HEAD.
3. Keep release-readiness blocked until PR/CI and publication evidence exist.
4. Treat `design-coverage-gap-remediation-plan.md` remediation order as
   locally implementation-complete, but not release-complete, until PR/CI and
   publication evidence are attached.

## Branch

`codex/public-mainline-batch-1`
