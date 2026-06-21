# Web AI Adapter Rules

These rules apply to `/rdpaper`, `/rdgoal`, `/bindChrome`, and any workflow that
uses a browser-hosted AI as an external brain.

## Provider Boundary

- Chrome and ChatGPT are the default reference path only.
- Do not hard-code `/rdpaper` or `/rdgoal` to a single browser or web AI.
- New providers must be introduced through a config that validates against
  `schemas/web_ai_adapter.schema.json`.
- If a provider cannot be automated reliably, use `manual` mode rather than
  inventing fragile success signals.

## Browser Boundary

- Do not export cookies, sessions, local storage, browser profiles, or password
  stores.
- CDP endpoints are local transport details, not portable project state.
- Browser profile paths and screenshots that reveal private content must not be
  committed.

## Paper Safety Boundary

- Real paper full text, PDFs, author identity, institution names, funding
  details, acknowledgements, Zotero content, and WriteLab payloads require
  explicit runtime authorization before upload or external submission.
- Default `/rdpaper` input should be a minimized packet: title placeholder,
  abstract summary, outline, citation list, issue list, and requested review
  dimensions.
- Raw web AI transcripts must not be persisted unless the project contract
  explicitly permits it.

## Failure Semantics

Treat the following as `human_required`, `blocked`, or `failed`:

- login required and no user is present;
- captcha or anti-automation challenge;
- selector not found;
- generation did not finish;
- response cannot be extracted;
- provider asks for disallowed content;
- user asks for publication, payment, or another external side effect.

Never report a web AI adapter run as passed unless a response was captured and
the local agent wrote minimized evidence.

## Documentation Requirement

Every custom provider adapter must document:

- browser provider and mode;
- target web AI URL;
- prompt submission strategy;
- response completion strategy;
- extraction strategy;
- supported file behavior;
- manual fallback;
- known limits;
- privacy and human-gate boundaries.
