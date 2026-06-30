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
- the `devframe code` output loop has started converging around
  inspect/resume/control/queue

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
