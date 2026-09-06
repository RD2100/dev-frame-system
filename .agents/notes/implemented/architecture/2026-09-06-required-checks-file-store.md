# Agent Note: File-Backed Required-Checks Store

Status: implemented

English | [中文](2026-09-06-required-checks-file-store.zh.md)

## Problem

The required-checks admission predicate consumes a `RequiredChecksConfigStore`, but the only implementation was process-local memory: every restart reset the checks source to empty, so the durable coverage rule recorded for P05 had no durable backing and a restarted host could only answer `REQUIRED_CHECKS_CONFIG_NOT_FOUND` for evidence whose checks had been registered in a previous process. The [completion admission seam](2026-09-06-goal-completion-admission-seam.md) therefore stayed restart-fragile at exactly the predicate that anchors evidence integrity.

## Decision

`FileRequiredChecksConfigStore` implements the existing interface over a JSON ledger at a `Config`-provided path: the envelope carries `{ version: 1, registrations: [{ digest, config }] }`, and every read re-decodes the registered payload and compares the claimed digest against `requiredChecksDigest(decoded)`. Byte-unparseable ledgers, envelope mismatches, and digest drift all fail loud with the new stable `REQUIRED_CHECKS_STORE_CORRUPT` code, which `save` also refuses to bypass — a corrupt ledger is never repaired in place. Publishing writes a same-directory temp file and renames, a repeated save of a known digest is an idempotent no-op, and the semantics of `sameRequiredCheckCommand`, `acceptanceCheckComponent`, `evaluateRequiredChecks`, and the digest algorithm are untouched. The store ships only as an injectable alternative implementation; choosing it in a profile or composition belongs to the owner wave.

## Alternatives considered

**Auto-repairing or truncating a corrupt ledger.** Repairs would silently destroy tamper evidence; failing loud with a stable code keeps the ledger an integrity surface, matching the admission's fail-closed direction.

**fsync and multi-writer locking in the same slice.** Crash-level durability and concurrent-writer merges expand the surface without a caller that needs them yet; single-writer last-write-wins semantics are documented in the store's contract and the design record lists them as explicit ruling requests.

**Wiring the store into profiles now.** The composition that would hold it already accepts a store injection point; picking the durable implementation per profile is a deployment decision, not a library fact.

## Consequences

- A host that configures a ledger path gets a required-checks source that survives restarts; the admission's checks predicate is no longer memory-bound.
- `REQUIRED_CHECKS_STORE_CORRUPT` joins the error family; readers of a drifted or corrupt ledger get one stable code instead of raw parse failures.
- Concurrency, fsync, directory creation, non-`ENOENT` IO error wrapping, and ledger compaction remain out of scope and recorded as ruling requests.
