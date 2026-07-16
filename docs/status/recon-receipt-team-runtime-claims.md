# Recon Receipt: M1 task-claim contention

> Governs the bounded M1 claim-ownership slice under `rules/recon.md`
> recon-001/003/008/009 and `rules/open-source-reuse.md` reuse-000/001/002.

## Target

- user_goal: prevent two agents from claiming the same target in a run while the
  conflict view hides the second claim.
- target: the local `TeamRuntime` append-only journal and its direct tests.
- current_slice_goal: add fail-closed target ownership to `record_task_claimed`.
- out of scope: A2A/network transport, HTTP/MCP writes, shared memory, UI,
  distributed leases, cross-runtime locking, task execution, and new packages.

## Resource Map

- write boundary: `packages/control-plane/control_plane/team_runtime.py`.
- production caller: `tools/go_evidence.py` records created then claimed events
  for each agent packet; `/go` dispatch shares the `TeamRuntime` instance.
- durable state: outside-repository `team-events.jsonl`, serialized by the
  existing runtime lock.
- read model: `build_team_runtime_view()` derives Task Board and Conflict
  Control from the journal.
- direct verification: `packages/control-plane/tests/test_team_runtime.py`.

## Current Gap

`record_task_claimed(run_id, agent_id)` records no target identity and does not
check prior created/claimed events. A real probe created two agents for
`shared.py`; both tasks reached `claimed`, while Conflict Control retained only
the first owner. This is unsafe because a projection appears conflict-free while
the durable journal proves two owners.

## Capability Matrix And Reuse Decision

| Capability | Candidate | Decision |
| --- | --- | --- |
| In-process atomic journal mutation | Existing `TeamRuntime._lock` and JSONL reader | Reuse directly |
| Target ownership projection | Existing `task_created` targets and Conflict Control shape | Reuse directly |
| Distributed task lease/queue | A2A and external queues | Do not import |

This runtime has one trusted local process and an existing serialized writer.
Adding an A2A SDK, broker, or distributed lease would enlarge the security and
deployment surface without solving the local duplicate-claim defect more safely.

## Integration Risks

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Two agents edit one target | P0 | Reject a claim when any target is already owned by another agent in the run. |
| Failed claim mutates journal | P0 | Check before append; leave current owner unchanged. |
| Read model hides a real conflict | P1 | Test durable events and projected owner together. |
| Existing distinct-target parallelism regresses | P1 | Preserve claims for disjoint target sets. |

## Frozen TaskSpec

- write_set:
  - `packages/control-plane/control_plane/team_runtime.py`
  - `packages/control-plane/tests/test_team_runtime.py`
  - this receipt and the public status inventory entry
- production contract: a claim derives its target set from that agent's created
  event; overlapping targets already claimed by another agent in the same run
  raise `ValueError` before any new journal line is appended.
- real RED probe: create two agents for `shared.py`, claim the first, then prove
  the second currently succeeds and the view conceals it.
- GREEN evidence: duplicate-target rejection with unchanged journal/owner,
  disjoint-target success, targeted runtime and `/go` regressions, actual-diff
  review, and Reviewer Index.

## Team Objects

In scope: Task Board and Conflict Control. Reused but unchanged: Agent Registry,
Message Bus, Event Log, Evidence Store, Review Gate. Deferred: blackboard,
cross-runtime coordination, and remote A2A transport.
