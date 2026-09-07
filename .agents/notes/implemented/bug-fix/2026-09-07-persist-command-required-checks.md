# Agent Note: Persist Command Required Checks

Status: implemented

English | [中文](2026-09-07-persist-command-required-checks.zh.md)

## Problem

The command composition could restore a Goal and its verification evidence from the Session log, but the mounted plugin selected an in-memory required-checks store. After a cold restart, completion could read the recorded checklist digest without finding the approved commands behind it. The existing [file-backed store](../architecture/2026-09-06-required-checks-file-store.md) supplied persistence, but the [host command composition](../architecture/2026-09-06-command-goal-binding-host-command-surface.md) did not select it.

## Decision

The mounted command plugin requires a non-empty absolute `requiredChecksPath` without surrounding whitespace and injects `FileRequiredChecksConfigStore` through the composition’s existing store override. Programmatic compositions retain that override. Plugin activation validates the path without creating its parent directory or registering the current checklist. Start saves the approved configuration under its canonical digest; completion resolves the digest already attributed to the Goal’s evidence.

Operators provision the parent directory, place the ledger outside the fingerprinted source worktree, and reuse the same path across deployment restarts. A first registration can create the ledger, but completion refuses a missing ledger, absent historical digest, or corrupt registration. Changing the deployment’s checklist does not replace the historical approval. Delivery and integration readers use the same ledger when resolving that evidence.

## Alternatives considered

**Register the current checklist during startup or on a lookup miss.** A new deployment configuration cannot establish what a previous Goal was authorized to execute. Preserving historical registrations keeps approval tied to the recorded digest and makes missing state visible.

**Create another command-specific persistence format.** The existing store already owns digest validation and file publication. Selecting it at the plugin boundary avoids a second ledger owner.

## Consequences

The [command package configuration](../../../../packages/experimental/command-goal-binding/README.md#use-this-package) owns the operator instructions. Deployments must retain registrations needed by existing evidence, designate one writer, and serialize saves. The file store does not create directories, merge concurrent writes, provide cross-process locking, or guarantee fsync durability.

Cold-restart verification must mount a fresh command plugin over restored Session evidence and the same ledger, including with a changed valid deployment checklist. Completion must resolve the original approval; missing and corrupt ledger cases must refuse completion. These cases distinguish persistent plugin wiring from a test that retains an in-memory store across instances.

The ACP recorded scenario closes the first process before resuming the same durable Session in a second process. Its fixture runs real Git checks and a scripted file-inspecting reviewer, then invokes the public resume and completion commands. The snapshot harness pins resumed headers, retains both protocol transcripts, and preserves equality relationships when tokenizing workspace-derived checklist hashes. This fixture does not establish autonomous model review or SDK resume support.
