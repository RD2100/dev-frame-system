# Web AI Adapter Contract

This contract defines how dev-frame-system talks to browser-hosted AI products
such as ChatGPT, DeepSeek, Doubao, Kimi, or an internal web AI.

Chrome plus ChatGPT is the default reference path. It is not the architecture
boundary. The boundary is:

```text
slash entrypoint -> local agent -> browser adapter -> web AI adapter -> report/evidence
```

## Goals

- Keep `/rdpaper`, `/rdgoal`, and future slash entrypoints independent from a
  single browser or provider.
- Let users choose Chrome, Edge, Playwright, manual handoff, or a future custom
  browser bridge.
- Let third-party agents adapt a new web AI by following a written contract
  instead of copying hidden selectors from this repository.
- Preserve privacy boundaries for real papers, browser sessions, cookies, and
  provider transcripts.

## Adapter Layers

### Browser Adapter

The browser adapter owns transport only. It opens or reuses a browser surface
and provides a page handle or a manual handoff target.

Required fields:

- `provider`: `chrome`, `edge`, `playwright`, `manual`, or `custom`.
- `mode`: `cdp`, `playwright`, `manual`, or `custom`.
- `profile_policy`: whether an existing profile is reused, isolated, or manual.
- `endpoint`: optional connection URL, such as a local CDP endpoint.

The browser adapter must not export cookies, session storage, local browser
profiles, or credential stores.

### Web AI Adapter

The web AI adapter owns provider-specific interaction. It knows how to submit a
prompt, wait for completion, and extract the latest response.

Required fields:

- `provider`: `chatgpt`, `deepseek`, `doubao`, `kimi`, `custom`, or another
  documented provider id.
- `url`: the user-visible page to open.
- `submit_strategy`: how the prompt is placed and submitted.
- `response_strategy`: how completion and response extraction are detected.
- `capabilities`: file upload, paste-only, multi-turn, markdown response, and
  manual login support.

Provider-specific selectors are optional and must be treated as brittle. A
custom adapter may provide prose instructions instead of selectors when the
target web AI changes often.

## `/rdpaper` Flow

`/rdpaper <paper-project> <goal>` uses the adapter contract like this:

1. The local agent initializes or reads the paper project workspace.
2. The local agent prepares a privacy-safe task packet.
3. The browser adapter opens or reuses the selected browser.
4. The web AI adapter submits the packet to the chosen web AI.
5. The web AI returns review guidance, issues, or revision strategy.
6. The local agent writes `PAPER_LEDGER.md`, reports, and evidence summaries.
7. Any request for real full text, raw PDF upload, publication, payment, or
   external side effect stops at a human gate.

## Default Reference Adapter

```yaml
browser:
  provider: chrome
  mode: cdp
  profile_policy: user_selected
  endpoint: http://127.0.0.1:9222

web_ai:
  provider: chatgpt
  url: https://chatgpt.com/
  submit_strategy: textarea_submit
  response_strategy: latest_assistant_message
  capabilities:
    file_upload: optional
    markdown_response: true
    manual_login_required: true
```

This is only the reference adapter. Users can choose a different browser or web
AI by supplying a config that validates against
`schemas/web_ai_adapter.schema.json`.

## Summary-only Chrome Binding Probe

For a running local Chrome instance with CDP enabled, DevFrame can bind an
already-open ChatGPT tab as a summary-only session:

```powershell
devframe web-ai bind-chrome --runtime-dir <runtime> --project <project-id> --cdp-endpoint http://127.0.0.1:9222
```

The probe reads Chrome debugger metadata and the ChatGPT tab URL. It must not
read cookies, local storage, browser profile files, passwords, raw transcripts,
or message text. A successful probe writes
`<runtime>/web-ai-sessions/chatgpt-chrome-binding.json`, which appears in the
Visual Control Plane as an active `chatgpt` session and marks the default
`chatgpt-web` provider binding as ready.

The probe is a binding check, not a task submission. Sending project context,
paper content, files, or prompts to the provider remains a separate
action-time decision.

## MCP Task Intake Boundary

When a web AI host supports MCP/tool calling, the preferred runtime path is a
small task-intake call, not a context ZIP or full workspace handoff. The web AI
may submit only a minimized task title, task summary, priority, suggested local
agent, provider id, and conversation reference. The local DevFrame runtime then
turns that intake into local agent work, evidence, review gates, and client
state.

`task_intake` is the safe default entrypoint for turning ChatGPT Web guidance
into local work:

```text
ChatGPT Web MCP task_intake
  -> local DevFrame task/evidence record
  -> @go/OpenCode worker dispatch
  -> review gate and evidence store
  -> T3/native client team workbench projection
```

The MCP task-intake payload must not include raw transcripts, cookies, browser
profile data, bearer tokens, full local paths, archives, private source dumps,
or generated diff bundles. ZIP/report submission remains a fallback review
artifact and must stay under the evidence/review layer, not the main runtime
channel.

## Custom Provider Guidance

A custom provider document should answer these questions:

- How does the agent open the page?
- How does the user authenticate?
- Where is the prompt box?
- How is the prompt submitted?
- How does the agent detect that generation is finished?
- How is the latest answer copied or read?
- Does the provider support file upload?
- What content must remain manual-only?
- What failure states should stop the run?

Selectors are allowed, but the adapter must include a manual fallback because
web UIs change without notice.

## Privacy Rules

- Do not persist raw web AI transcripts unless the project explicitly allows it.
- Do not commit paper full text, private author identity, browser profiles,
  cookies, or provider session data.
- Do not upload real paper full text, PDFs, Zotero content, or WriteLab payloads
  without explicit runtime authorization.
- Record only minimized evidence: run id, provider id, decision, issue summary,
  report paths, and redaction status.

## Failure Semantics

An adapter run is not successful unless it returns a response and the local
agent records evidence. Login prompts, captcha, provider rate limits, missing
selectors, incomplete generation, or privacy-boundary requests must produce
`human_required`, `blocked`, or `failed`; they must not be reported as pass.
