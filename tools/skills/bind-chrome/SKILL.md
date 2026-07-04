---
name: bind-chrome
description: Bind DevFrame to a ChatGPT conversation or Chrome-hosted ChatGPT session. Use when user says "@bind-chrome", "bindChrome", "bind Chrome", "ChatGPT /c/ URL", "bind conversation", "Chrome binding", or asks to connect this project to a web GPT conversation without capturing raw transcripts.
---

# bind-chrome - ChatGPT Conversation Binding

Role: methodology skill for binding DevFrame to a browser-hosted ChatGPT
conversation without making the browser transcript project authority.

## Core Rule

Bind only summary metadata. Do not capture cookies, browser profiles, local
storage, passwords, raw transcripts, or message text.

DevFrame browser automation is currently CDP-family only. Any action that tests
a ChatGPT page, submits a prompt, reads a provider response, discovers an open
tab, or validates that a conversation is reachable must use an existing or
explicitly started Chrome DevTools Protocol compatible endpoint. Future
multi-browser transports are deferred to
`docs/status/browser-automation-transport-roadmap.md`.

Allowed stable transport:

- Chrome CDP endpoint such as `http://127.0.0.1:9222`.
- Edge or another Chromium-compatible CDP endpoint only after it passes the
  same loopback, target-page, submit, wait, extract, and evidence checks.

Not allowed as normal runtime transport:

- Chrome extension bridge;
- standalone Playwright browser sessions;
- screenshot/keyboard/mouse simulation;
- transcript scraping through non-CDP browser adapters.

If the user provides a `https://chatgpt.com/c/<id>` URL and asks only to record
the binding, `bind-conversation` may import that URL as metadata without
touching the browser. That metadata-only path is not a browser test. If the user
also asks to test, submit, inspect, or verify the web page, switch to CDP and
drive the existing Chrome page through the CDP endpoint.

## Runtime Commands

For a known ChatGPT conversation URL:

```powershell
devframe web-ai bind-conversation `
  --conversation https://chatgpt.com/c/<conversation-id> `
  --project dev-frame-system `
  --project-root <repo> `
  --runtime-dir <runtime>
```

For an already-open Chrome tab with CDP enabled:

```powershell
devframe web-ai bind-chrome `
  --project dev-frame-system `
  --runtime-dir <runtime> `
  --cdp-endpoint http://127.0.0.1:9222
```

## Expected Outputs

- summary-only session JSON under runtime `web-ai-sessions/`;
- user-level binding files under `~/.agents/bindings/<project-id>/`;
- no `.agent/` files in the public repository;
- no raw transcript or browser credential material.

## CDP Verification Checklist

Before claiming browser-level success:

1. Confirm `http://127.0.0.1:9222/json/version` is reachable.
2. Connect to Chrome over CDP.
3. Find the target `chatgpt.com/c/<id>` page through CDP.
4. For page tests, verify the submitted user message and latest assistant
   response from the CDP-controlled page.
5. Record only minimized evidence: URL, title, status, and a short response
   summary. Do not persist raw transcripts.

## Hard Stops

- Do not write `.agent/` inside a public repo that forbids it.
- Do not bind URLs with credentials, query strings carrying secrets, or
  unsupported hosts.
- Do not treat a bound conversation as an accepted review.
- Do not submit review bundles through this skill; use `external-brain` for the
  review package gate.
- Do not report a browser test as passed if it used the extension bridge,
  standalone browser automation, or screenshot/keyboard simulation instead of
  CDP-family transport.
