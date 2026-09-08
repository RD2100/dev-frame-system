# Agent Note: Host terminal ownership outlives isolated instances

Status: implemented

English | [中文](2026-09-08-terminal-host-ownership.zh.md)

## Problem

A host-visible terminal service cannot enumerate sessions owned by isolated service instances. An empty provider inventory also cannot prevent a newly mounted service from spawning after a stop.

## Decision

The host mounts `terminalOwnership` once. Each terminal service registers during construction and checks the shared exact-Agent admission fence before reserving a spawn. Drain closes the fence before awaiting every registered instance. Successful service disposal unregisters the instance; failed cleanup retains both its registration and unresolved activity.

Batch resume captures directory membership and every owner's drain generation. Commit revalidates all owners and provider readiness before synchronously opening any owner. This supplements the independently owned lineage and writer rules in the [host stop adapter decision](2026-09-08-command-goal-binding-host-stop-adapters.md).

## Alternatives considered

Looking up one `ctx.terminals` value loses isolated instances. Registering only services that have already spawned misses the zero-instance stop case. Clearing failed cleanup records during disposal turns unresolved backend resources into false quiescence.

## Consequences

Custom terminal compositions must mount the shared ownership plugin. The directory is process-local and does not replace durable Goal recovery. Direct tests cover late mounting, multiple instances, foreign owners, retained cleanup failure, and batch invalidation after another drain; product cold-restart acceptance remains a separate check.
