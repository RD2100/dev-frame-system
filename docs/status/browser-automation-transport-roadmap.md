# Browser Automation Transport Roadmap

Lifecycle state: Deferred module plan

Plan status: Future implementation module. Do not implement before the
review-first governance lifecycle and CDP-family evidence path are proven.

Reader: DevFrame maintainers and coding agents who need to add browser
automation transports without weakening evidence, privacy, or runtime
reliability.

Post-read action: keep the current stable browser automation path on CDP
family only, then implement this module later as a staged adapter expansion
when the master plan allows runtime transport work.

Related docs: [Document-Driven Transformation Master Plan](document-driven-transformation-master-plan.md), [Web AI Adapter Contract](../agent-runtime/web-ai-adapter-contract.md), [Methodology Skills Registry](../agent-runtime/methodology-skills.md)

## Purpose

DevFrame should eventually support more than one browser. That does not mean
the current runtime should let agents choose any automation method.

The product direction is multi-browser. The current engineering discipline is
single stable transport family.

```text
now:
  browser-hosted Web AI automation -> CDP family only

later:
  browser-hosted Web AI automation -> governed transport adapter registry
```

This roadmap exists so a future coding agent can implement multi-browser
support from a documented sequence instead of reopening the transport decision
from scratch.

## Current Boundary

Current stable runtime:

- Chrome CDP through a loopback endpoint.
- Edge or another Chromium-compatible browser may be considered only when it
  passes the same CDP endpoint and target-page probes.
- Metadata-only conversation URL import is not a browser test.

Not stable runtime evidence:

- Chrome extension bridge;
- standalone Playwright-launched browsers;
- screenshot, keyboard, or mouse simulation;
- Firefox treated as a CDP target;
- provider transcript copy/paste without a governed run record.

These paths may help with manual diagnosis, but they must not be reported as
successful browser automation evidence.

## Target Shape

The future module should expose a small adapter registry:

```yaml
browser_transport:
  id: chrome-cdp
  family: cdp
  browser: chrome
  endpoint: http://<cdp-host>:<cdp-port>
  profile_policy: user_selected
  evidence_level: stable
```

The registry should distinguish:

| Level | Meaning |
|---|---|
| `stable` | Can submit, wait, extract, and produce evidence in normal runs |
| `experimental` | Can run probes and collect findings, but cannot satisfy delivery evidence |
| `manual` | Human-visible fallback only; cannot be claimed as automation success |
| `unsupported` | Known not to satisfy current evidence requirements |

User choice should be limited to adapters that have already passed the required
evidence level for the requested action.

## Adapter Families

### CDP Family

Scope:

- Chrome;
- Edge;
- Chromium-compatible browsers that expose a compatible loopback debugging
  endpoint.

Expected strengths:

- existing project support;
- direct target discovery;
- file upload and DOM interaction;
- useful page-level evidence.

Risks:

- browser-specific launch flags;
- profile/session ownership;
- provider UI selector drift;
- users may confuse URL binding with page verification.

### WebDriver BiDi Family

Scope:

- Firefox and other browsers where BiDi is the correct modern automation route.

Expected strengths:

- cross-browser standard direction;
- event-oriented browser automation;
- a better long-term fit for Firefox than CDP.

Risks:

- not yet proven in this project;
- different capability model from CDP;
- likely needs separate probes, waits, response extraction, and failure
  semantics.

WebDriver BiDi must start as `experimental`. It cannot become `stable` until it
passes the same external-brain submission and evidence tests as CDP.

### Manual Family

Scope:

- human copies a prompt;
- human uploads a bundle;
- human pastes back a response summary.

Manual mode is allowed for privacy-sensitive or blocked sessions, but it should
produce `manual_feedback` evidence, not browser automation evidence.

## Implementation Phases

### Phase A: Keep CDP Family Stable

Status: current operating boundary.

Goal: make the existing CDP path boring and repeatable.

Required behavior:

- probe loopback endpoint;
- find target browser page;
- submit prompt or upload review bundle;
- wait for completion;
- extract latest assistant response;
- record minimized evidence;
- classify login, captcha, provider error, upload failure, timeout, and selector
  drift as blocked or human-required.

Acceptance evidence:

- CDP smoke test against a ChatGPT conversation;
- external review bundle submission through CDP;
- response extraction evidence;
- public snapshot verification.

Stop line: do not add user-selectable transport before this path has a reusable
runbook and tests.

### Phase B: Define Transport Adapter Schema

Status: deferred.

Goal: represent transport selection without letting selection bypass evidence.

Expected outputs:

- adapter schema or config fixture;
- stable, experimental, manual, and unsupported evidence levels;
- capability flags for file upload, prompt submit, response extraction, and
  page health checks;
- failure-state taxonomy shared across transports.

Acceptance evidence:

- invalid adapter configs are rejected;
- an experimental adapter cannot satisfy a stable run;
- manual mode cannot be reported as automated browser success;
- CDP adapter remains the only stable fixture.

Stop line: do not add new browser implementation in this phase.

### Phase C: Edge And Chromium-Compatible CDP Probe

Status: deferred until Phase B passes.

Goal: expand CDP family without changing the automation model.

Expected outputs:

- probe for browser identity and CDP endpoint compatibility;
- fixture examples for Chrome and Edge;
- evidence showing that target discovery, upload, submit, wait, and extraction
  work the same way or fail with explicit reasons.

Acceptance evidence:

- Chrome remains passing;
- Edge passes the same CDP smoke path or stays experimental;
- a non-compatible Chromium browser is rejected or marked experimental.

Stop line: do not add Firefox in this phase.

### Phase D: WebDriver BiDi Spike

Status: deferred until CDP family and adapter schema are stable.

Goal: evaluate Firefox through the protocol family that actually fits Firefox.

Expected outputs:

- BiDi capability probe;
- Firefox page open and target discovery probe;
- minimal submit/wait/extract experiment;
- comparison against CDP evidence requirements.

Acceptance evidence:

- explicit `experimental` status until all evidence tests pass;
- documented gaps versus CDP;
- no automatic fallback from CDP to BiDi without user-visible adapter selection;
- no claim that Firefox is CDP-compatible.

Stop line: do not promote BiDi to stable because one probe succeeds.

### Phase E: User-Selectable Transport

Status: deferred until at least two adapters have evidence records.

Goal: allow users to choose browser transport safely.

Expected behavior:

- users choose from eligible adapters only;
- unsupported or experimental choices are visible but cannot satisfy stable run
  evidence;
- the selected adapter is recorded in the run evidence;
- provider-specific failures are separated from transport failures.

Acceptance evidence:

- stable CDP run still passes;
- experimental BiDi run cannot be marked complete;
- manual fallback creates manual evidence only;
- adapter choice appears in reviewer output and visual projection.

Stop line: do not make adapter choice a UI preference that can override
governance state.

## Review Checklist

Before implementing any part of this module, answer:

1. Which phase does the change serve?
2. Which adapter evidence level is being created or consumed?
3. Does the transport prove submit, wait, extract, and evidence recording?
4. Can an experimental adapter accidentally satisfy a stable run?
5. Does the change avoid cookies, browser profile export, and raw transcript
   persistence?
6. Does failure become `blocked`, `human_required`, or `failed` instead of a
   false pass?
7. Does user choice select only eligible adapters for the requested action?

## Non-Goals

- no multi-browser free-for-all in the current runtime;
- no Firefox-over-CDP claim;
- no hidden fallback from one transport to another;
- no browser profile export;
- no raw transcript persistence;
- no stable promotion without the same evidence requirements as CDP.
