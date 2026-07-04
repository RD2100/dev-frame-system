# Working Tree Cleanup Inventory - 2026-07-05

Lifecycle state: Current worktree triage record

Reader: DevFrame maintainers and coding agents deciding whether to continue UI
or product design on the current dirty tree.

Post-read action: do not run `git reset`, `git clean`, or `git add .`. Use the
batch plan below to review, verify, and stage only intentional groups.

Related docs: [Document-Driven Transformation Master Plan](document-driven-transformation-master-plan.md), [Design Coverage Gap Remediation Plan](design-coverage-gap-remediation-plan.md), [Status Document Inventory](status-document-inventory.md), [Reviewer Index](reviewer-index.md)

## Decision

Clean the working tree before UI/product prototype work, but do not restart the
project design from a blank slate.

The current dirty tree contains useful project direction, runtime helpers, and
reviewed planning records. It is not disposable clutter. The right cleanup is a
controlled consolidation:

1. preserve the accepted planning spine and documentation map;
2. preserve the external-brain/CDP/runtime helper slice if tests continue to
   pass;
3. preserve methodology skills as governed public assets;
4. keep T3/RD-Code and visual-control changes as projection substrate, not as
   the final UI design;
5. avoid starting graph UI, Paper KB UI, multi-browser selection, marketplace,
   or workflow-builder work before the review-governance kernel proves Phase
   1A.

## Current Snapshot

Observed on 2026-07-05.

- Dirty paths: 58.
- Modified tracked paths: 15.
- Untracked paths: 43.
- Main dirty areas: `docs/`, `packages/control-plane/`, `schemas/`, and
  `tools/skills/`.
- Tracked diff size before this inventory: about 1,211 insertions and 61
  deletions across 15 tracked files.
- Runtime review bundles and browser evidence are outside the repo under
  `.devframe-runtime` and should stay outside the public snapshot.

This snapshot is a cleanup guide, not release evidence and not a claim that
Phase 1A is implemented.

## Keep As Mainline Documentation

These files should be preserved and reviewed together as the current planning
and navigation spine:

- `docs/README.md`
- `docs/status/status-document-inventory.md`
- `docs/status/governance-spine-and-document-coordination.md`
- `docs/status/document-driven-transformation-master-plan.md`
- `docs/status/design-coverage-gap-remediation-plan.md`
- `docs/status/current-coverage-audit-evidence-20260704.md`
- `docs/status/reviewer-index.md`
- `docs/status/review-first-governance-kernel-contraction-plan.md`
- `docs/status/review-first-governance-kernel-implementation-spec.md`
- `docs/status/reuse-first-constraint-governance-implementation-plan.md`
- `docs/status/unified-object-model-decision-record.md`
- `docs/status/governance-contradiction-matrix.md`
- `docs/status/governance-rules-spec.md`

Reason: these files now define the current phase order, stop lines, evidence
boundary, and next implementation slice. Removing them would recreate the same
context-loss problem that the documentation map was written to prevent.

Cleanup action: keep, review links, and stage as a documentation batch only
after public snapshot verification passes.

## Keep As Supporting Plans

These files should remain visible, but they are not authority to start their
capabilities now:

- `docs/status/workflow-consolidation-and-command-plan.md`
- `docs/status/context-management-architecture-plan.md`
- `docs/status/context-noise-governance-and-automation-plan.md`
- `docs/status/context-led-model-performance-control-plan.md`
- `docs/status/model-knowledge-gap-governance-plan.md`
- `docs/status/project-and-cross-project-memory-harness-governance-plan.md`
- `docs/status/goal-bound-evidence-gate-plan.md`
- `docs/status/paper-claim-integrity-gate-to-cluster-plan.md`
- `docs/status/human-attention-governance-and-automation-maturity-plan.md`
- `docs/status/early-adopter-user-asset-governance-plan.md`
- `docs/status/competitive-moat-and-user-demand-critical-review.md`
- `docs/status/runtime-governance-and-evidence-closure-transformation-plan.md`
- `docs/status/evaluation-feedback-learning-governance-plan.md`
- `docs/status/total-control-policy-engine-and-human-escalation-governance-plan.md`
- `docs/status/documentation-management-audit-and-plan.md`
- `docs/status/documentation-management-detailed-rollout-plan.md`

Reason: these plans capture useful design pressure, but the master plan already
places the next implementation focus on Phase 1A.

Cleanup action: keep as planning records; do not let them expand the immediate
implementation scope.

## Keep As Deferred Module Plans

These files should be preserved but explicitly kept behind Phase 1A and
projection derivation:

- `docs/status/browser-automation-transport-roadmap.md`
- `docs/status/paper-knowledge-base-iteration-mvp-plan.md`
- `docs/status/graph-projection-knowledge-canvas-plan.md`

Reason: they answer important user questions, but the accepted remediation plan
marks these as later modules.

Cleanup action: keep; do not implement UI, writeback, or runtime commands from
these files until their prerequisites pass.

## Keep As Stable Runtime Contract Updates

These tracked modifications are consistent with the current project direction
and should be reviewed as a small documentation/runtime-contract batch:

- `docs/agent-runtime/methodology-skills.md`
- `docs/agent-runtime/web-ai-adapter-contract.md`

Reason: they document the current split between built-in methodology skills,
runtime custom skills, explicit triggers, and the current Chrome CDP-only Web AI
automation path.

Cleanup action: keep if related tests and public snapshot verification pass.

## Keep As External-Brain And CDP Runtime Slice

These files form a coherent implementation batch for external-brain review
bundles, ChatGPT conversation binding, and persistent browser launch:

- `packages/control-plane/control_plane/conversation_binding.py`
- `packages/control-plane/control_plane/external_review_bundle.py`
- `packages/control-plane/control_plane/web_ai_browser_launcher.py`
- `packages/control-plane/control_plane/chrome_binding_probe.py`
- `packages/control-plane/control_plane/cli/_webai.py`
- `packages/control-plane/control_plane/cli/app.py`
- `packages/control-plane/control_plane/cli/_usage.py`
- `packages/control-plane/tests/test_external_review_bundle.py`
- `packages/control-plane/tests/test_web_ai_browser_launcher.py`
- `packages/control-plane/tests/test_cli.py`
- `packages/control-plane/tests/test_rdgoal.py`
- `schemas/external_review_bundle.schema.json`
- `tools/skills/bind-chrome/`
- `tools/skills/context-pack-builder/`
- `tools/skills/evidence-driven-acceptance/`
- `tools/skills/external-brain/`
- `tools/skills/intent-framing-gate/`
- `tools/skills/review-governance-kernel/`

Reason: this group has a direct user-facing purpose and is backed by focused
tests from the previous review loop. It should not be mixed with UI design work
or graph/Paper deferred-module work.

Cleanup action: keep as a dedicated runtime batch; verify with focused tests
before staging.

## Keep But Isolate As T3 Projection Substrate

These files should not drive a full UI rewrite, but they are useful substrate
for a future Command Center projection layer:

- `packages/control-plane/control_plane/t3_adapter.py`
- `packages/control-plane/control_plane/t3_bridge_bundle.py`
- `packages/control-plane/tests/test_t3_adapter.py`
- `packages/control-plane/tests/test_t3_bridge_bundle.py`

Reason: the diff reduces coordinator-entry payload exposure and normalizes the
T3 shell projection. That helps a future UI read smaller, safer objects, but it
does not make the current T3 surface the final product UI.

Cleanup action: keep as a separate projection batch; test separately from the
external-brain/CDP batch.

## Keep As Handoff Records, Then Retire Later

These files are useful for continuity but should not remain active authority
forever:

- `docs/status/continue-global-coordinator-conversation-mainline.md`
- `docs/status/next-agent-global-coordinator-prompt.md`

Reason: they preserve prior global-coordinator work, but the accepted master
plan and remediation plan should drive new implementation.

Cleanup action: keep for now; later supersede with a shorter implementation
handoff after Phase 1A lands.

## Do Not Put In The Public Repo

These are intentionally outside the dirty tree and should stay outside the
public snapshot:

- external review ZIP bundles;
- browser profile directories;
- ChatGPT response captures;
- project binding JSON under user-level `.agents` directories;
- runtime session JSON under `.devframe-runtime`;
- screenshots, temporary review exports, and local evidence packs.

Cleanup action: do not move these into `docs/` or `packages/`; reference only
bounded conclusions or sanitized paths when needed.

## Recommended Batch Order

1. Documentation spine batch:
   - `docs/README.md`
   - `docs/status/status-document-inventory.md`
   - `docs/status/governance-spine-and-document-coordination.md`
   - `docs/status/document-driven-transformation-master-plan.md`
   - `docs/status/design-coverage-gap-remediation-plan.md`
   - `docs/status/current-coverage-audit-evidence-20260704.md`
   - `docs/status/reviewer-index.md`
   - current review-governance and object-model planning docs
2. External-brain/CDP runtime batch:
   - `conversation_binding.py`
   - `external_review_bundle.py`
   - `web_ai_browser_launcher.py`
   - `chrome_binding_probe.py`
   - web-AI CLI/router usage changes
   - `schemas/external_review_bundle.schema.json`
   - matching tests
3. Methodology skill asset batch:
   - new `tools/skills/*` directories
   - `docs/agent-runtime/methodology-skills.md`
4. T3 projection batch:
   - `t3_adapter.py`
   - `t3_bridge_bundle.py`
   - matching tests
5. Handoff cleanup batch:
   - global-coordinator handoff files
   - any final next-agent prompt updates after Phase 1A direction is stable

## UI Design Implication

Do not redesign from scratch, but also do not treat the current T3/dashboard
surface as the final UI.

The next UI design should use the current repo as a product substrate:

- DevFrame command center as the top-level product frame;
- review-governance kernel status as the first authority-bearing panel;
- external-brain review bundle and CDP browser state as evidence panels;
- skills as governed methodology assets;
- T3/RD-Code bridge as a projection/input compatibility surface;
- graph, Paper KB, and multi-browser surfaces as deferred read-only concepts
  until their stop lines are lifted.

The design should wait until the cleanup batches above are reviewed enough that
the prototype is not based on transient or unaccepted worktree state.

## Verification Before Staging

Run these checks after reviewing each batch:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1
python -m pytest packages\control-plane\tests\test_external_review_bundle.py packages\control-plane\tests\test_web_ai_browser_launcher.py packages\control-plane\tests\test_custom_skills.py -q
python -m pytest packages\control-plane\tests\test_t3_adapter.py packages\control-plane\tests\test_t3_bridge_bundle.py -q
git diff --check
```

Treat CRLF warnings as cleanup notes, not blockers, unless they hide whitespace
errors or corrupt generated artifacts.
