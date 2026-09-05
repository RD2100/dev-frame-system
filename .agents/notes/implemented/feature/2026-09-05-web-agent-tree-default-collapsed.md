# Agent Note: Collapsed project agent tree by default

Status: implemented

English | [中文](2026-09-05-web-agent-tree-default-collapsed.zh.md)

## Problem

The grouped sidebar can contain a controller, several delegated leads, and deeper executors. Expanding every agent row at mount makes a large project tree consume the sidebar before the user chooses a branch.

## Decision

`dsh-client-ui-workspace` initializes every Agent row with direct children collapsed. The browser keeps the ids of rows the user opens in transient state, and the existing chevron continues to toggle one direct level. Workspace-group expansion remains independent, so opening a Workspace reveals its top-level Agent rows without automatically revealing their descendants.

The same rule applies at every Agent depth. A user can open a controller, then open one of its delegated leads, while unrelated branches remain folded. Catalog membership is announced only for rows that are open, so the default projection does not subscribe to descendant catalogs.

## Alternatives considered

**Start every Agent row expanded.** Rejected: a project with many delegates becomes noisy immediately and forces the user to collapse branches before finding a target.

**Collapse only the top-level controller.** Rejected: nested leads with executors would still expand unexpectedly, so the same tree would behave differently at different depths.

**Persist Agent expansion in the Workspace view store.** Rejected: the request is a compact initial projection, while the existing browser-local state already preserves an active branch for the mounted tree without adding durable view-schema fields.

## Consequences

The initial sidebar shows the Workspace's top-level Agent rows and their status without showing descendants. Opening a chevron is required to inspect each level, and opening a row still opens its Session while toggling that row's direct children. Agent expansion resets when the browser tree unmounts; Workspace-group expansion keeps its existing persistence.

## Verification

`pnpm exec vitest run packages/client/ui-workspace/tests/workspace-browser.client.spec.tsx packages/client/ui-workspace/tests/agent-tree-rows.client.spec.tsx` covers the collapsed initial tree and manual one-level expansion. The client bundle is rebuilt with `pnpm --filter @deepseek-ai/dsh-client-ui-workspace bundle` before browser verification.
