# Agent Note: Workspace Expectation Platform Variants

Status: implemented

English | [中文](2026-09-06-workspace-expectation-platform-variants.zh.md)

## Problem

Keyless recorded-session replay compared every scenario against a single POSIX-authored expectation set. On win32 the three shell-hook scenarios replay their recorded sessions cleanly but fail the workspace comparison: the POSIX sidecar records `.posttool-blocked` / `.stop_fired` marker files that only the POSIX hook semantics produce, so the win32 host — whose recorded session already carries the honest `sh: not recognized` outcomes — could never match. Session-fixture variants existed for some scenario families, but workspace expectation dirs had no variant path at all, and the final workspace check in the headless runner read the base directory unconditionally.

## Decision

The session-snapshot package grows a minimal platform-variant seam. The scenario manifest may declare `sessionVariants.win32` for session fixtures and `expectations.variants.win32` naming which pinned expectation sidecars have platform variants; manifest parsing is whitelist-strict and fails loud on unknown keys, and declared variant files must exist. A shared resolver (`resolveWorkspaceExpectedDir`, alongside the existing expectation-path resolvers) picks the platform directory; `suite.ts` and the headless runner's final workspace check both route through it. The corpus gate gains presence, marker, and paired-existence rules plus invalid-case coverage, and the package tests pin the resolver and the strict manifest behavior (+12 cases). The three hook scenarios ship harvested `session.win32.jsonl` fixtures and hand-authored `workspace.win32.expected/` directories authored from the actual side of real replay failures; base fixtures carry zero diff.

## Alternatives considered

**Normalizing marker names across platforms.** The markers are real workspace effects of platform hook semantics; pretending they match would falsify the workspace proof the scenarios exist to give.

**Per-platform scenario copies.** Duplicating whole scenario dirs to vary one expectation directory multiplies maintenance for every future platform question; the resolver keeps one scenario with declared variants.

**Auto-harvesting workspace variants during refresh.** Harvest writes what the host produced; the win32 workspace variants are hand-authored from real replay failures precisely so the committed expectation states the intended-accepted platform difference instead of whatever the last run happened to produce.

## Consequences

- The three hook scenarios are green on win32 end to end — session, stdout/stderr, and workspace — with base fixtures untouched.
- Declared-but-missing variant files fail loud at manifest load, so the variant surface cannot silently rot.
- Two findings remain registered outside this wave: the acp pin-sidecar harvest pipeline has no variant write path (image-compaction's platform prompt drift needs a fixture-lane decision), and code-runtime stack traces embed the recording tree's absolute path, so `both-mode-turn`/`ptc-turn` replay red in any non-recording tree.
