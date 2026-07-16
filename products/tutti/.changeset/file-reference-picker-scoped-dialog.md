---
"@tutti-os/workspace-file-reference": patch
"@tutti-os/agent-gui": patch
---

Render `WorkspaceFileReferencePicker` on the shared `Dialog` base instead of a hand-rolled `createPortal(document.body)` + `fixed inset-0` overlay, and add a `scoped` prop. When `scoped` is set, the dialog renders inline (non-portaled, `absolute`) with an `absolute` overlay so it stays clipped within the nearest positioned ancestor. The agent GUI node now opens the picker with `scoped` so it is confined to the node window rather than covering the whole viewport.
