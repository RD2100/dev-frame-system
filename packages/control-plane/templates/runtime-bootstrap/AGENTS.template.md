# {{PROJECT_NAME}} Agent Entry

Read `PLAN.md` completely before repository work. `PLAN.md` is the only human
development authority for direction, status, milestones, risks, acceptance,
and the next action.

Mandatory execution rules:

- Follow `PLAN.md`, `rules/`, schemas, tests, and source truth.
- Preserve unrelated user changes and the captured dirty baseline.
- Use bounded TaskSpecs, exact write sets, rollback, and evidence-backed gates.
- Worker success is not acceptance; independent review and FinalVerdict remain
  separate.
- Do not create parallel PRDs, roadmaps, handoffs, or status documents.
- Do not push, merge, release, deploy, install globally, use credentials, or
  perform destructive Git work without an explicit human gate.
- Runtime evidence belongs outside the public repository.

Machine contracts live under `.devframe/contracts/`; negative fixtures live
under `packages/agent-acceptance/fixtures/negative-acceptance/`. These assets
do not schedule work and cannot override `PLAN.md`.

Use `tools/devframe-go.ps1` for the governed code entrypoint.
