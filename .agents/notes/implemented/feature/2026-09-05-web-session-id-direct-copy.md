# Agent Note: Direct Session ID copying from row actions

Status: implemented

English | [中文](2026-09-05-web-session-id-direct-copy.zh.md)

## Problem

The row actions menu must serve callers who need a durable Session ID without creating a second navigation surface. A modal adds an extra activation and makes copying the only requested value depend on opening temporary UI.

The row-menu placement and identity ownership remain defined by the [row-menu note](2026-09-05-web-session-id-row-menu.md); this note owns the copy interaction.

## Decision

`dsh-client-ui-workspace` keeps the Session ID action in each session row's existing actions menu and copies the row's branded `SessionId` directly through the shared `writeClipboard` helper. The flat session row and every Agent tree row use the same direct-copy behavior.

Selecting the action closes the menu and does not open a modal. A transient Toast reports an accepted write or an explicit failure; a refused write never produces a success message. Each row allows one clipboard request at a time and ignores an asynchronous result after the row unmounts.

`SessionIdDialog` and its stylesheet are removed. Locale entries that described the modal are removed; the menu, success, and failure entries remain owned by `ui-workspace`.

No identity is minted, transformed, or duplicated. The copied value is the same `SessionId` created by the API and persisted in the session header.

## Alternatives considered

**Keep a modal copy flow.** Rejected: it costs a second activation and creates a temporary surface for an action that only needs a clipboard write.

**Copy silently with no result.** Rejected: a host can refuse both clipboard paths, so the user needs a visible distinction between an accepted write and a failed attempt.

**Add a separate copy button beside every row title.** Rejected: it consumes permanent row space and duplicates a verb already owned by the row actions menu.

## Consequences

The common path is one menu activation, and the session list remains in place. Success or failure is visible through a transient Toast rather than a modal. Copy remains best-effort because browser permissions and host clipboard support remain outside the plugin's control.

## Verification

`pnpm exec vitest run packages/client/ui-workspace/tests/session-id-copy.client.spec.tsx packages/client/ui-workspace/tests/agent-tree-rows.client.spec.tsx` covers direct copying from both row types, no session navigation, no modal, success feedback, and refused writes. The generated client bundle is rebuilt with `pnpm --filter @deepseek-ai/dsh-client-ui-workspace bundle` before browser verification.
