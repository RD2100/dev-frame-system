# Agent Note: DevFrame Global Controller Sidebar Entry and Session ID

Status: implemented

English | [中文](2026-08-15-devframe-global-controller-sidebar-entry.zh.md)

## Problem

The DevFrame control session is durable and addressable, but a normal Web profile needs a visible way to open it and inspect its stable session identity. A blank controller session must not be mistaken for the ordinary New Session placeholder, and a user should not have to inspect storage or network traffic to copy its Session ID.

## Decision

The desktop launcher serves the normal Web profile with a thin `scripts/devframe-web.patch.yml` overlay. The overlay mounts the existing DevFrame control-session Host service and browser package without mounting the bounded headless task command, so Web flags retain their normal behavior.

The control-session browser package contributes one sidebar footer action labelled `总控` / `Global Controller`. It reads the loaded session catalog and opens the existing `devframe-global:<profile-id>` session; it does not create a second session or add a write route. The same footer entry owns an ellipsis menu with `复制 Session ID` / `Copy Session ID`; the callback uses the shared browser clipboard helper and does not change session or server state.

The workspace browser deliberately excludes `devframe-global:` from ordinary workspace and ungrouped session rows, so the dedicated footer is the single Global entry. The durable `controller/identity` event remains available to the Host and client projection, but its metadata is not rendered as a chat card; the conversation area stays available for actual dialogue.

## Alternatives considered

**Keep the global session hidden until it has a message** — this makes a durable controller unreachable from the product UI. The dedicated footer keeps it reachable without duplicating it among ordinary sessions.

**Put the controller behind a project row** — a global controller is not owned by a project; nesting it there would imply the wrong scope and make cross-project coordination ambiguous.

**Mount the complete DevFrame task bundle in the Web launcher** — the task command parser consumes Web arguments such as `--port`; the launcher therefore mounts only the control-session and browser rows, while the complete task bundle remains available to the headless `devframe` profile.

**Expose the ID only in a developer inspector** — the Session ID is part of the user-facing identity contract, so the dedicated footer menu is the stable and discoverable place to copy it.

## Consequences

The first screen of the DevFrame launcher now has one persistent Global footer action. It remains usable before the controller has produced a model message, while ordinary project/session rows keep their native meaning. Multiple profiles can still have distinct global IDs in one shared catalog; the ID prefix keeps their scope explicit.

## Testing

The workspace and control-session client suites cover exclusion from the ordinary tree, the footer action's open/disabled states, lifecycle disposal, the copy-ID menu callback, and suppression of the identity metadata card. A real Web smoke check with the desktop launcher confirms one footer entry, no duplicate ordinary Global row, no identity card in the chat stream, and a working `复制 Session ID` menu item.
