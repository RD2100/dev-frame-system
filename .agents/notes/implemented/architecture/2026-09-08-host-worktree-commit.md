# Agent Note: Host-authorized commits for linked worktrees

Status: implemented

English | [中文](2026-09-08-host-worktree-commit.zh.md)

## Problem

A linked checkout stores its index outside the checkout and shares Git objects and branch references with its anchor repository. A Worker restricted to writing its checkout cannot complete a Git commit. Granting shell access to the shared Git directory also exposes other branches and worktrees.

## Decision

The [worktree registry](2026-09-05-worktree-registry.md) provides a host-only commit operation with a registered worktree ID, matching holder, full expected HEAD, explicit relative file paths, and a commit message. It serializes the operation with registry mutations, pins the verified Git directory, rejects pre-existing staged changes, and checks that the resulting commit has the expected HEAD as its sole parent.

The consumer authorizes the request, derives the holder from the calling session's binding, and quiesces other writers. The registry's [single-writer binding](../feature/2026-09-05-per-agent-worktree-single-writer-seam.md) does not stop arbitrary filesystem writes. The service grants no additional shell capabilities and exposes no model-facing tool.

Host commits disable hooks, signing, filesystem monitors, and automatic maintenance; tracked or selected files with filter attributes are rejected. Missing paths must name exact tracked files; symbolic links and junctions in selected paths are rejected. Cancellation or failure can leave staging or a completed commit, so consumers inspect the index and HEAD before retrying. The result distinguishes the new commit ID from whole-checkout cleanliness.

## Alternatives considered

- Granting only the per-worktree Git directory is insufficient because commits also write shared objects and branch references. Granting the entire common directory exposes unrelated repository state.
- Standalone clones remove the shared metadata requirement but do not preserve linked-worktree registration and reconciliation semantics.
- Running checkout hooks or filters inside the host commit lets checkout-controlled programs execute outside the Worker's execution boundary.

## Consequences

Trusted consumers can commit selected Worker output while retaining the checkout's shell boundary. They must provide authorization and writer quiescence, handle uncertain outcomes, and run required checks through their existing verification path. Repository workflows that require commit hooks or file filters cannot use this operation unchanged.
