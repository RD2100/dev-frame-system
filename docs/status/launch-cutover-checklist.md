# Launch Cutover Checklist

Last updated: 2026-06-30.

This document splits the remaining path to launch into two buckets:

- work Codex can continue to automate safely
- work that requires the human owner to finish or approve

The intent is practical, not ceremonial: keep automation moving until the last
responsible moment, then make the handoff to launch explicit and short.

## Current State

What is already true in the current branch/PR:

- the public control-plane batch is on `codex/public-mainline-batch-1`
- PR `#4` is open against `main`
- the local release gate passes:
  - `python -m pytest -q`
  - `scripts\verify-public-snapshot.ps1`
  - `scripts\verify-control-plane-wheel.ps1`
  - `scripts\verify-release.ps1`
- the top-level product story has been converged around `devframe code`
- the `devframe code` output loop now converges around
  inspect / resume / control / queue
- the default text path has already been tightened so `devframe code` feels
  more like a resumable product loop and less like raw dispatch plumbing
- the dashboard read model has started translating internal status terms into
  more user-facing display language in the HTML surface

## Automated Progress Already Landed

These items are already in the branch and PR:

1. top-level docs now present `devframe code` as the main product
2. secondary and advanced surfaces are demoted rather than presented as equal
   first-class entrypoints
3. `devframe code` prepare/status/execute output now shares a common "Next"
   model
4. the launch cutover boundary is documented in this file rather than living
   only in chat
5. release-gate stability fixes for `public_snapshot` and `mcp_consent` test
   lifecycle issues are in place

## Codex Can Keep Doing

These are safe to continue automating:

1. keep tightening the `devframe code` main loop:
   - reduce default-path concept noise
   - improve output consistency
   - keep advanced detail in JSON/dashboard rather than default text
2. keep aligning docs and help text with the chosen main product:
   - root README
   - Chinese README
   - control-plane README
   - quickstart
   - CLI help surfaces
3. keep strengthening test stability and release-gate reliability
4. keep updating PR `#4` with committed, verified changes
5. keep preserving a clean boundary between:
   - primary product
   - control plane
   - experimental surfaces

## Human Must Finish

These are the final actions that require you:

1. decide whether you accept the product direction:
   - `devframe code` as the single primary product
   - dashboard/client/protocol work as secondary or advanced layers
2. review PR `#4` and decide when it is good enough to merge
3. merge the PR into `main`
4. perform the formal release action you want:
   - tag
   - GitHub Release
   - distribution/public announcement
5. run the final real-user sanity check on the exact release candidate you
   intend to publish

## Human Checklist, Reduced To Actions

### Before merge

1. open PR `#4`
2. confirm you still agree with the product direction:
   - `devframe code` is the primary product
   - dashboard/client/protocol work is secondary or advanced
3. skim the latest verification summary in the PR discussion or commit history
4. merge when satisfied

### After merge

1. pull or confirm `main` is the release candidate you intend to publish
2. run your final real-user smoke on that exact candidate
3. create the release artifact you want:
   - tag
   - GitHub Release
   - other external distribution step
4. publish/announce

## Do Not Hand Off Yet

The owner does **not** need to intervene yet when the remaining work is still
in these categories:

- CLI output convergence
- documentation convergence
- release-gate hardening
- test flake removal
- non-destructive packaging verification
- PR iteration on the same branch

## Handoff Trigger

The correct handoff point is:

- the branch is pushed
- PR `#4` reflects the current intended release candidate
- the release gate is green on the latest committed state
- the remaining items are judgment/release actions rather than engineering work

At that point the owner should step in, because the next actions are no longer
"implement and verify" but "approve, merge, publish, and announce".

## Working Rule

Until the handoff trigger is met, Codex should keep moving.

When the trigger is met, the owner should receive:

- the exact PR URL
- the latest verification summary
- the short list of human-only actions
