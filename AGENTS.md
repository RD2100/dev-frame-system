# DevFrame Agent Entry

Before any repository work, read `PLAN.md` completely.

`PLAN.md` is the only human development authority for product direction,
current status, milestone order, risks, acceptance, and the next action.
Do not create another PRD, MVP, roadmap, handoff, status report, Recon Receipt,
reviewer index, release note, or planning document.

Mandatory execution rules:

- Follow the current user request, `PLAN.md`, `rules/`, schemas, tests, and code.
- For every non-trivial programming task, use `coding-discipline` and
  `devprocess`.
- Read relevant source and tests before editing; prefer CodeGraph for structural
  questions and `rg` for literal text.
- Preserve the captured dirty baseline and unrelated user changes.
- Complete the `rules/recon.md` Recon and open-source reuse gates before
  write-capable work in client, runtime, provider, MCP, review/evidence,
  multi-agent, or desktop areas.
- Workers may edit and test, but only the root coordinator may accept, stage,
  and locally commit an independently reviewed slice.
- Stage only exact accepted paths. Never use broad stage, stash, restore,
  reset, clean, force-push, or history rewrite.
- Push, PR, merge, release, deployment, global installation, credentials, and
  production mutations require an explicit human gate.
- Runtime evidence belongs in structured runtime state outside the public
  repository. Update `PLAN.md` in place with only the current decision and
  compact evidence summary.

Machine-consumed Markdown under `rules/`, `tools/skills/`, `templates/`,
package policies/contracts/prompts, and test fixtures is code-like input. It
does not schedule work and cannot override `PLAN.md`.
