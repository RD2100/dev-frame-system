# Agent Note: The stop chain composes project-tree stop behind /devframe-stop

Status: implemented

English | [中文](2026-09-08-command-goal-binding-stop-chain-composition.zh.md)

## Problem

`/devframe-stop` recorded stop vocabulary but never cancelled anything: no owned job was killed, no captured process was terminated, no session was flushed, and no writer was released. The delivered `stopProject` primitive owns the drain protocol, but it is call-only — the composition had to decide who enumerates the project tree, who owns the writer release, and how the flow converges when a crash window leaves the log between `stop_requested`, `quiescence_confirmed`, and the release.

## Decision

The composition wires the real chain behind `/devframe-stop` behind the `stopChain` config gate; the default `false` keeps the vocabulary-only face byte-identical for existing deployments. Three faces are host-injected on the composition service, not Schema config: the project tree face returns the root plus every real descendant agent, host-verified for owner and worktree identity; the process face returns every captured descendant process; the release hook performs the writer release and must tolerate repeat invocation.

The chain fails closed on every absent face. A missing or empty tree inventory, a missing jobs registry, and an unwired release hook each refuse the release — an empty list never stands in for a verified full tree, and absence is never quiet. The stop chain runs only over the host's verified members, so an unrelated project's jobs and processes are never drained.

The confirmed-quiescence record is the durable pre-release prerequisite. The stopped terminal record, store entry, and checkpoint land only after the release actually succeeded, each landing bounded by the stop grace through a race so a never-settling persistence face returns instead of hanging. A release failure folds `needs_attention` and never lands `stopped`.

Interrupted flows converge on the repeat stop. A log left at `stop_requested` (a crash while the chain waited in its drain — a normal failure window for a stop the human explicitly asked for) re-enters the drain through `resumeStopRequestedStop` over the host's current inventory and live registry identities; a log left at `quiescence_confirmed` re-enters the release through `finishConfirmedStop`. Missing live identities surface as `needs_attention` naming the resource with the writer held — never a silent bypass, and interrupted goal work is never restarted.

## Alternatives considered

**Enumerating descendants inside the composition.** The composition would guess project membership and duplicate the host's owner and worktree verification. The host already owns the live registry and the captured handles, so the verified-inventory face keeps membership authoritative and lets the composition fail closed on what it cannot verify.

**Landing the stopped terminal before the release.** A release callback can throw and the process can die after a pre-landed `stopped` but before the release, which misstates a stopped-but-writer-held goal and refuses the repeat stop. The terminal therefore lands only after the release actually succeeded, and the durable pre-release state is the existing `quiescence_confirmed` record.

**A transaction framework around the release and the bookkeeping.** Rolling back a release is not possible, so a general transaction adds scope without removing the window; the bounded landings plus the re-entry paths give every failure state a named, retryable convergence instead.

## Consequences

Focused real-face tests cover the ordered child-process drain, the descendant tree with a child-owned job, process, and session flush plus an untouched unrelated project, the grace-timeout needs-attention rerun, the budget across a cold restart, the repeat-stop refusal, the in-flight mutex, the unwired release fail-safe, the absent and empty tree, the missing jobs registry, the release-failure convergence, the cold confirmed-state convergence, the never-settling save's bounded return, the cold `stop_requested` continuation, and the stale-identity refusal.

Two boundaries remain deliberate. `finishConfirmedStop`'s terminal-bookkeeping call sites are not individually failure-wrapped the way the fresh chain's are — behavior stays bounded and non-blocking, but the asymmetry is recorded here. The stop chain drains and converges; it never resumes or restarts interrupted goal work, and the writer stays held until a run confirms the tree quiescent.

## Related

[Admission deadlines invoke native project stop](2026-09-08-admission-deadline-native-stop.md) owns the primitive's deadline face, and the [host command surface note](2026-09-06-command-goal-binding-host-command-surface.md) owns the command composition and attribution decisions; neither covers this composition wiring.
