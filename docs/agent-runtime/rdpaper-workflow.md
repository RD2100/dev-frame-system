# `/rdpaper` Workflow

`/rdpaper` is the paper-focused external-brain entrypoint.

It uses a web AI as the reviewer and coordinator, while a local agent prepares
privacy-safe material, runs local workflow steps, and records evidence.

## Entry Shape

```text
/rdpaper <paper-project> <goal>
```

Shell implementations may expose an equivalent command later:

```powershell
rdpaper "D:\papers\demo" "Check whether this paper is ready for submission"
```

The slash entrypoint is the product contract. The shell command is an
implementation detail.

## Responsibilities

The web AI external brain:

- interprets the paper goal;
- reviews structure, argument quality, citation reliability, and journal fit;
- recommends revision strategy;
- decides whether human review is needed.

The local agent:

- initializes the `paper_iteration` workspace;
- prepares redacted summaries, outlines, citation lists, or approved excerpts;
- submits the task packet through the configured Web AI Adapter;
- writes `PAPER_LEDGER.md`, status files, reports, and evidence summaries;
- stops when the run needs real paper content, browser credentials, payment,
  publication, or another external side effect.

## Normal Flow

1. Receive `/rdpaper <paper-project> <goal>`.
2. Create or read the paper workspace.
3. Load `WEB_AI_ADAPTER.yaml`.
4. Validate it against `schemas/web_ai_adapter.schema.json`.
5. Prepare a minimized paper task packet.
6. Submit the packet through the selected browser and web AI adapter.
7. Extract the response or require manual copy-paste in `manual` mode.
8. Convert the response into issues, decisions, and next actions.
9. Write paper ledger and evidence summaries.
10. Return `run_id`, `status`, blocking issues, report path, and next action.

## Multi-Provider Model

Chrome and ChatGPT are the reference path, not a hard dependency.

Valid implementations may use:

- Chrome CDP with ChatGPT;
- Edge or Playwright with ChatGPT;
- Chrome CDP with DeepSeek, Doubao, Kimi, or an internal web AI;
- manual mode, where the local agent creates the packet and the user copies the
  answer back into the run.

## Human Gate Conditions

`/rdpaper` must stop before:

- reading or committing real paper full text without authorization;
- uploading a PDF or full manuscript to a web AI;
- exporting cookies, browser profiles, or session data;
- calling WriteLab or another external service with real content;
- submitting to a journal, paying fees, or sending email;
- persisting raw web AI transcripts when only minimized evidence is allowed.

## Initial Implementation Target

The first implementation should be contract-first:

- `WEB_AI_ADAPTER.yaml` in the paper template;
- `schemas/web_ai_adapter.schema.json`;
- documentation for provider-specific adapters;
- manual fallback instructions;
- tests that prove the template validates.

Provider-specific automation can be added after the contract is stable.
