---
description: P22 project-memory 收尾证据：agent 侧回执 rehydration 端到端验证（真实存储、零 mock）与复跑命令。
---

# P22 evidence: agent-side receipt rehydration (real storage, zero mocks)

- Closes the remaining P22 checklist item for `packages/experimental/project-memory`: the AGENT-SIDE receipt-rehydration path verified end to end over real storage.
- New spec: `packages/experimental/project-memory/tests/agent-rehydration.spec.ts` — 5 cases; no `vi.mock`, no spies, no fake fs anywhere (real tempdir Vault, real dsh-session logs, real `ctx.tools.execute` dispatch, plugin mounted exactly like `tests/plugin.spec.ts`).
- Test commit: `2dd9b4ab0c` on `p/memrx` (base `9dbf3911f0`); docs commit: see git log for `docs(devframe): ...`.

## Verified assertions → test pointers

| Assertion | Test (all in `tests/agent-rehydration.spec.ts`) |
| --- | --- |
| Multi-note appends log one `memory/receipt` event per note in append order; conflicting re-append (same `source_ref`, changed body) returns `memory_conflict` (the service's actual conflict status per `src/memory.ts`) and commits no extra receipt | "logs one receipt per created note in append order and keeps it live across a conflicting re-append" |
| Latest-per-noteId fold over the live log yields exactly one live receipt per note; that receipt's `digest` equals `digestTag` of the file on disk, `relativePath` matches the note's actual location, `recordedAt` present | same test |
| Cold recovery through the plugin's real `agent/created` hook — `Session.create(id, snapshotEvents())` replay + second fresh context over the same Vault + `ctx.emit('agent/created', { agent })` (no fallback needed); the hook's async rehydration is awaited on the observable outcome (`read` → `found` + `verified: true`) | "rehydrates a fresh context from the replayed log and drives honest service outcomes" |
| Replayed log preserves receipt append order; receipt ↔ note correspondence (digest on disk, relativePath, recordedAt) holds after rehydration | same test |
| Retrying the same append through the rehydrated tool surface → `already_exists`; changed body → `memory_conflict`; neither writes a duplicate receipt into the recovered log | same test |
| Service-level outcome: fresh `ProjectMemoryService(spec, rehydratedIndex)` over the SAME Vault root — `read` → `found`/`verified: true`; service retry → `already_exists`; changed body → `memory_conflict` | "serves verified reads and idempotent retries from receipts folded out of the agent log" |
| Genuine re-commit replaces the earlier receipt: real note-file loss + fresh un-rehydrated index → exclusive create re-commits a receipt into the same agent log (order [F, G, F]); replay folds to the re-committed receipt (new digest matches the recreated file) while the bystander note's receipt is untouched | "folds the replayed log to the re-committed receipt and leaves the other note untouched" |
| Strict decode still guards the path: a `memory/receipt` row with a bad digest shape fails `foldMemoryReceipts` and `rehydrateMemoryReceipts` loud (the file's only `as unknown as SessionEvent` cast, reusing the `tests/receipt-log.spec.ts` pattern; every other object in the file is real) | "fails loud when a replayed receipt row carries a malformed digest" |

Note: a same-source_ref retry never re-commits a receipt under normal operation (idempotency; the tool logs a receipt only on `created`, and a note file is created exactly once), so the re-committed-receipt case is driven through the real file-loss + fresh-index path above rather than any mock.

## Rerun commands

```sh
pnpm install
pnpm exec vitest run packages/experimental/project-memory   # 66 passed (61 existing + 5 new), 10 test files
pnpm exec tsc -b packages/experimental/project-memory       # exit 0
```

## Gates observed

- `pnpm exec vitest run packages/experimental/project-memory` → 10 files, 66/66 tests passed.
- `pnpm exec tsc -b packages/experimental/project-memory` → exit 0.
- `git diff --cached --check` → exit 0 for both commits.

## Gaps found

- none.
