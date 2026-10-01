# Agent Note: Win32 folder dialog no longer dies on every folder selection

Status: implemented

English | [中文](2026-10-01-win32-folder-dialog-worker-crash-on-selection.zh.md)

## Problem

Selecting a folder in the DSH Desktop app killed the folder-dialog worker before it reported a result: the pick failed with `directory picker failed: directory picker failed: win32 folder dialog worker exited before reporting a result`. The worker spawns, opens the dialog, and receives the selection; the death happens inside result extraction. `readUtf16` in `packages/host/directory-picker-native/src/win32-dialog-bindings.ts` translated the `IFileOpenDialog` result with `Buffer.from(koffi.view(address, 32768))`, and `koffi.view` creates an ArrayBuffer over **external memory**. The Desktop app runs the host and the dialog worker as electron-as-node (`DeepSeek Harness.exe`), and Electron forbids external buffers: the attempt raises a fatal N-API error that no JavaScript `try`/`catch` can survive, so the worker dies with no IPC message and the driver can only report the exit.

Reproduced in the shipped runtime: a 64-byte `CoTaskMemAlloc` block with a valid UTF-16 path dies on `koffi.view` at any length (32 KiB and 34 bytes alike), while plain Node 24.17 executes the same call. The buffer length is irrelevant — the view call itself is the fatality.

The defect escaped every existing gate. The unit tests mock koffi, and the fake `view` returns a plain ArrayBuffer, so no mock observes the runtime restriction; the real win32 smoke in `tests/win32-dialog.spec.ts` opens a dialog and abort-closes it, and the cancel path never reaches `readUtf16`; the `dsh web` host runs plain Node, where the view succeeds.

## Decision

`readUtf16` reads the string through `koffi.decode(address, 'char16_t', -1)`: koffi copies the characters natively up to the string's own NUL terminator, and no external buffer exists for the runtime to forbid. Because koffi decodes complete code units, a path containing a U+XX00 code unit (for example 开, U+5F00) survives — the byte scan that truncated such paths is gone with the buffer it scanned. Verified end to end against the shipped electron-as-node host: a real dialog, a real selection, and a returned path.

The binding surface drops `view` entirely, and the fake koffi in `tests/win32-dialog-bindings.spec.ts` records and throws on any `view` call, so a reintroduced external-buffer read fails the suite on the mock lane instead of dying silently in production.

## Alternatives considered

**Bound the read with `lstrlenW` and view exactly that length.** Rejected: the view call itself is fatal under the Electron runtime, at any length — bounding it changes nothing.

**`koffi.decode(address, 'str16')`.** Rejected: `'str16'` is the string-pointer type, so decode dereferences the result address as a pointer and kills the worker (verified: the process dies on the first real `GetDisplayName` address).

**Move the dialog off the electron-as-node worker, or out of the child process.** Rejected: the child-process architecture owns the modal block and the abort lever of the [child-process folder dialog note](../feature/2026-08-02-win32-in-process-folder-dialog.md); only the string read needed to change.

## Consequences

- Folder selection works in the Desktop app on win32; the worker survives result extraction and reports the path over IPC.
- Paths containing U+XX00 code units keep working through native code-unit decoding, superseding the scan mechanism of the archived [2026-08-23 UTF-16 truncation note](../../archived/bug-fix/2026-08-23-win32-utf16-nul-truncation.md) — that note's rejected alternative "ask COM or koffi for a string length" is now the shipped mechanism.
- The desktop runtime carries the worker as bundled `lib/worker.cjs`: an installed app keeps the fatal worker until a runtime with the fix ships.
- The mocked binding suite still proves the COM conversation (vtable order, memory hygiene, abort poster); the win32-only smoke still covers the cancel path; the selection path's runtime safety rests on the electron-as-node reproduction recorded here and in the fix's verification.
