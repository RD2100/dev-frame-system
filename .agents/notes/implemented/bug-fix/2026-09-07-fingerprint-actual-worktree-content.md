# Agent Note: Fingerprint Actual Worktree Content

Status: implemented

English | [中文](2026-09-07-fingerprint-actual-worktree-content.zh.md)

## Problem

HEAD and index records describe committed and staged content. They do not describe an unstaged edit or an untracked file that a check or tool reads. Using only those records lets completion accept changed source after review while both Git observations remain unchanged.

## Decision

The [source fingerprint](../../../../packages/experimental/devframe/src/source-fingerprint.ts) includes actual tracked and nonignored untracked entries selected by Git. Its `stateHash` hashes framed index records and sorted unique repository-relative paths together with their entry types, file-content digests, and regular-file executable bits. A missing tracked path contributes a deletion record. HEAD remains a separate component of `dsh-source-fp-v2-<headCommit>-<stateHash>`. `entryCount` counts selected paths, including tracked deletions.

The [start command](../../../../packages/experimental/command-goal-binding/src/composition.ts) derives `snapshot-v2-<headCommit>-<stateHash>` using the complete state hash. Completion compares the stored fingerprint with a fresh computation. Unstaged changes and newly added or modified nonignored untracked files therefore invalidate the recorded source without staging or committing them. The [completion admission decision](../architecture/2026-09-06-goal-completion-admission-seam.md) continues to own the evidence conjunction and native Goal completion; this decision defines the source observation it consumes.

File bytes remain raw: a line-ending change changes source evidence. Timestamps help detect changes during observation but do not enter the digest. A symlink contributes its link-target text without reading the referent. Symlink ancestors, submodules including missing Git links, special file types, non-UTF-8 paths, unreadable entries, and observed concurrent changes fail closed. Ignored untracked paths and empty directories remain outside the selected source inventory.

Source contents are streamed with bounded memory. `maxOutputBytes` retains its per-Git-output meaning; optional `maxSourceBytes` bounds aggregate source-content bytes without imposing a default total cap. Cancellation and a configured file-reading deadline stop owned work and close its resources. These checks are observations, not an atomic filesystem snapshot or a substitute for the caller's writer ownership.

## Alternatives considered

**Use only HEAD and index records.** Git provides a compact canonical representation and avoids reading the worktree, but unstaged and untracked source can change while that representation stays identical. The completion contract requires those changes to invalidate evidence.

**Normalize through staged Git blobs.** Clean filters and line-ending normalization improve equality across checkouts, but the resulting bytes can differ from what checks and tools actually read. Raw worktree bytes preserve that distinction instead of treating source normalization as evidence equivalence.

## Consequences

Verification reads all selected source contents instead of relying only on Git metadata. Byte limits, deadlines, and ignored-file policy remain explicit host choices. Two checkouts with the same HEAD and index can have different fingerprints because their actual file bytes or executable modes differ. A version-one fingerprint cannot compare equal to the version-two value; the engine does not silently reinterpret earlier evidence.

Symlink referent changes and ignored-file changes are outside this fingerprint's claim. A host whose checks depend on those external inputs needs separate evidence for them. Writer ownership must span observation and the operation consuming it; concurrent filesystem mutation cannot be made atomic by hashing.
