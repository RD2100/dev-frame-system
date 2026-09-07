# Agent Note: Controller integration merges parallel reviewed branches

Status: implemented

English | [中文](2026-09-08-controller-parallel-branch-merge.zh.md)

## Problem

The [controller Git integration recovery decision](2026-09-07-controller-git-integration-recovery.md) accepts only fast-forward changes: `merge-base --is-ancestor` refuses a second task whose reviewed commit branched from the same base as an already-integrated sibling. Two Workers developing in parallel therefore can never both integrate — the second is refused forever, and the only escapes were serializing development or rewriting one side.

## Decision

The exact-source contract stays; the mode becomes explicit. `IntegrationGitRequest` carries `mode: 'fast-forward' | 'merge'`, persisted on the durable integration intent (storage domain version 4 adds the mode and the applied result head; earlier domains reject at open). A read-only relation probe classifies the two heads as identical, fast-forward, already-integrated, or diverged, and the integration consumer selects the mode explicitly: a diverged reviewed source — the normal shape of two Workers branching from one base — integrates as a real merge commit whose parents are the observed target head and the exact reviewed source; every other relation keeps the fast-forward path and its refusals. Both integrations of the parallel scenario go through the same admission: goal binding with both task ids, independent deliveries, verifications, and reviews, and the controller as the only writer.

The merge boundary isolates its environment. The mutating command runs with an explicit config bundle (`merge.ff=false`, `commit.gpgsign=false`, `core.hooksPath=/dev/null`) and `--no-verify`, its subprocess strips global and system Git config by redirecting `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM` to an empty file, and inspection refuses a target whose local config defines custom merge drivers or external filters. An in-tree `.gitattributes` naming a mechanism that no reachable config defines is inert: only Git's built-in merge runs. The author identity comes from the host-owned target checkout's local config. The applied receipt records the observed merge head, never the source commit standing in for it (a fast-forward's head is the source commit, which is the honest observation).

Failure states keep their names. A conflicted merge stops with HEAD unmoved and is reported `conflicted` only when both `MERGE_HEAD` and unmerged index entries confirm the merge state — a dirty target with an unchanged HEAD from cancellation or an external write stays `ambiguous`. An octopus commit (more than two parents) can never satisfy the applied shape and stays `ambiguous`. Reconciliation distinguishes two phases: a prepared intent whose Git already applied repairs recording from the observed two-parent merge; an applied receipt pins the exact applied head, so a target amended to a different commit with the same two parents refuses to report applied.

## Alternatives considered

**Serializing the second task behind a rebase.** Rebasing the second Worker onto the advanced target before redelivery converts parallel development into a serial re-confirmation and rewrites a reviewed commit; the merge mode integrates the reviewed commit as delivered.

**Auto-selecting the mode inside the Git layer.** A hidden default hides which path ran; the relation probe makes the selection explicit and inspect re-verifies the relation for the chosen mode.

**Refusing every repository with global filter config.** Stripping global and system config from the merge subprocess isolates the machine-level face without making LFS-configured hosts unusable; the local config face stays host-owned and is refused outright when it defines process-running entries.

## Consequences

The real-Git suite covers the clean sibling merge with exact two-parent order and final content, the explicit conflict with merge-state evidence, the octopus and dirty-target ambiguities, the mode-mismatch refusals, unrelated histories, the local driver refusal with the fast-forward face intact, and attribute-selected mechanisms with no reachable config. The controller suite drives two sibling tasks through the real Loader — fast-forward then merge with no rebase or redelivery — and persists the mode and applied head; a cold restore reconciles the prepared merge intent, and an amended same-parents target refuses to report applied.

The fast-forward path keeps its reviewed face, including its existing exposure to hooks and filters; only the merge path carries the isolation bundle. Domain version 4 rejects version 3 state at open, which is a deployment-activation decision, not a migration.
