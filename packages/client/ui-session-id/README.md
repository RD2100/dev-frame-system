---
description: "Web SessionID badge: the session-header utilities chip showing this session's id with one-click copy; for users and maintainers of the session-identity experience."
kind: "package-reference"
---

# @deepseek-ai/dsh-client-ui-session-id

English | [中文](README.zh.md)

## Summary

This package renders the SessionID badge of the Web GUI: a session-header utilities chip showing the current session's id with a one-click copy control. The id is the same branded `SessionId` the core session store creates and persists — this package only surfaces it to the human and owns no identity of its own. The chip truncates long ids visually while the copy button always places the full value on the clipboard, and the id text stays selectable.

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the implementation](#understand-the-implementation)
- [Further Exploration](#further-exploration)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)

-----

<a id="use-this-package"></a>
## Use this package

Mount this plugin alongside the Web client; the badge then appears in the session-header utilities zone of every session that has an id, before the session-log download action. A click on the copy button writes the full id to the clipboard and shows a one-second success state; a refused write (denied permission, insecure context) keeps the affordance instead of claiming success. No session id — the blank-session Hero — renders nothing.

The copied id addresses the session everywhere ids are accepted: session list search, history reads, the ACP and SDK session addressing, and persisted log filenames.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

The package contributes one entry (`session-id-badge`, order `-10`) to the `conversation.session.header.utilities` list declared by `dsh-client-ui-conversation`, and reads the id through the standard session-scope `sessionId` prop — no RPC and no store. Copy feedback uses the shared `writeClipboard` helper from `dsh-client-ui-primitives`, which prefers the async Clipboard API and falls back to `execCommand('copy')`. All copy is user-visible behavior; the session log never records it, and the id itself reaches the header from the Session Controller wire, so no model-visible surface changes.

</details>

-----

<a id="further-exploration"></a>
## Further Exploration

Read these pages when the badge is not enough and the identity itself matters.

- [Session subsystem](../../../docs/subsystems/session.md) — owns `SessionId`, its branded type, and `SessionHeader` persistence.
- [dsh-client-ui-jobs](../ui-jobs/README.md) — the sibling session-header action pattern this package follows.
- [dsh-client-ui-conversation](../ui-conversation/README.md) — declares the header utilities slot the badge occupies.

-----

<a id="model-experience"></a>
## Model Experience

None. The badge is presentation-only: it renders wire data the Session Controller already delivers, records nothing in the session log, adds no tool, and changes no prompt.

-----

<a id="known-limitations-and-deferred-work"></a>
## Known Limitations and Deferred Work

- The badge shows the id only; renaming the session or joining a workspace never changes it, because `SessionId` is immutable by design.
- Insecure browser contexts fall back to `execCommand('copy')`; a host that refuses both paths leaves the id selectable but does not copy.
