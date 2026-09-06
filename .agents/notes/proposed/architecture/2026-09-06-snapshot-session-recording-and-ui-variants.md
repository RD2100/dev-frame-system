# Agent Note: Snapshot Session Recording and UI Expectation Variants

Status: proposed

English | [中文](2026-09-06-snapshot-session-recording-and-ui-variants.zh.md)

## Problem

After the platform expectation variants landed for pinned sidecars, four residual faces of the Windows B-family drift remained: the persisted-replay comparison still failed because `session.jsonl` is both the replay script and the comparison target and its recorded tool calls name `bash`, which does not exist in the win32 composition; the tool-schema pin assertion remained unreachable because `assertReplaySession` executes the persisted-replay comparison first and masks everything after it; use case 1's inline snapshot lived in the test file with no platform consumption channel; and `ui.expected.md` sat outside the expectation vocabulary, so its `[data-sample="bash"]` selector could never match the pwsh card win32 renders. The win32 run kept failing even though the mechanism existed.

## Proposal

Extend the snapshot scenario configuration with two recording-side and presentation-side variants:

- A root-level `sessionVariants` manifest field (`win32: true`) declares a platform variant of the canonical recording, resolved by a new `resolveSessionFixturePath` seam to `session.win32.jsonl` beside the base file (naming parallel to the existing `session.<n>.jsonl` child family); a declared variant that is missing fails loud, and a borrower scenario (one with a `session` source reference) must not declare it.
- `ui` joins `SnapshotExpectationKind` (stem `ui`, extension `md`), so `ui.expected.md` gains the full expectation machinery: variant resolution, inventory admission, existence checks on every host, and corpus-gate scanning.
- The web lane consumes both: `assertReplaySession` resolves the fixture through the seam, the pin assertions move ahead of the persisted-replay comparison (unshadowing them), and the minimal-preset use cases drive the shell through a single platform seam with a POSIX-normalized inline snapshot (cwd tokenized, separators normalized) while the tool list is asserted explicitly per platform instead of being renamed into a false common shape.
- The minimal-preset corpus lands `session.win32.jsonl` (exactly the four recorded bash calls rewritten to pwsh) and `ui.win32.expected.md` (the pwsh card rows), the manifest declares both, and the corpus gate admits declared recording variants while running the same typed-identity and scrub checks over them.

The PROMPT constant stays unparameterized, on the record: the system prompt face is identical on both platforms (the stage-2 measurement), the authored wording has no platform-conditional behavior, and parameterizing it would force variant chains through the script and UI lines with no assertion benefit. The honest residual — a win32 user prompt asks about bash while the scripted model calls pwsh — is an authored-corpus cosmetic divergence, registered rather than hidden.

## Key design

- **Explicit declaration over inference.** The reading host's `process.platform` maps onto the existing expectation-variant vocabulary through the same injected seam; nothing reads the global inside the resolvers, and a platform without a declared variant reads the base file, so POSIX behavior is unchanged by construction.
- **Two-sided inventory closure extends to recordings.** A declared recording variant must be committed and is checked for existence on every host; a recording variant on disk that no manifest declares is rejected; declared variant JSONL files run the same typed-identity fixed-point and request-header scrub checks as the base file — the corpus gate was extended to admit them, not to exempt them.
- **Unshadowing earns an independent observation.** Moving the pin assertions ahead of the persisted-replay comparison is proven by a destructive negative observation: corrupting the win32 schema variant fails the run at exactly the tool-schema pin assertion, which the masked ordering could never exhibit.
- **Honesty over normalization.** The inline snapshot keeps one POSIX-normalized shape shared by both platforms; the tool list moves out of the snapshot into an explicit per-platform assertion (`[pwsh, str_replace_editor]` on win32) rather than renaming pwsh to bash to preserve a common shape.

## Alternatives considered

**Put variants inside the existing `session` field.** The `session` field is the borrower discriminator (`session !== undefined` marks a read-only borrower in the corpus gate and the scaffold); overloading it with variant declarations would corrupt that semantic. A separate root field keeps the discriminator clean.

**Exempt the UI golden from the vocabulary.** Leaving `ui.expected.md` outside the expectation machinery would keep its platform divergence unmanaged and its win32 row invisible to the inventory guard and the corpus gate. Admitting `ui` as a kind closes the same loop the sidecar kinds already have.

**Rename pwsh to bash in the win32 tool assertions.** A false common name would make the win32 run green while asserting a tool that does not exist. The per-platform explicit assertion is longer but true.

**Parameterize the PROMPT constant.** Rejected on the record above; the seams delivered in this wave (shell seam, variant files) cover every platform-conditional behavior actually observed.

## Acceptance criteria

- The minimal-preset lib-mode delta run passes 3/3 after failing 2/3 at baseline: persisted replay, the inline snapshot, and the web-card use case all green, with the inventory guard staying green.
- Corrupting the win32 schema variant fails at exactly the tool-schema pin assertion (destructive negative observation), and restoring it returns the tree to clean.
- `session.win32.jsonl` differs from the base recording in exactly the four recorded tool-call lines (bash→pwsh with the pwsh command text), with the session header tokenized identically (`{{cwd}}`, stable `createdAt`); `ui.win32.expected.md` differs in exactly the pwsh card rows.
- The corpus gate passes with declared variant admission and identical typed-identity/scrub checks; the session-snapshot package suite, package `tsc -b`, the repository build, and `gen-cordis-catalog` are all clean; translation pairing stays consistent.

## Risks

- All execution evidence in this wave is win32-host; POSIX behavior is guaranteed by construction (no posix declaration, base-file resolution) and pinned by unit tests, but the lib-mode delta has not run on a POSIX host — the merge CI gate owns that lane.
- The headless/sdk/acp suite channels do not consume recording variants; a non-web scenario declaring `sessionVariants` today would parse but have no consumer, same interim discipline as the pinned-sidecar wave.
- Record mode (keyed re-recording) has not been exercised against recording variants; the corpus is authored and not re-recorded, but a future live-recording scenario with platform variants needs the refresh/record write-back path re-validated.
- The corpus-gate extension is a mechanical necessity (undeclared-name rejection would fail the committed variant); it admits only declared variants and runs the base-file checks over them, but future manifest contract changes must keep the gate and the parser vocabularies in lockstep.
