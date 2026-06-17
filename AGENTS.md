# AGENTS.md -- dev-frame-system

> Canonical public repo: `RD2100/dev-frame-system`
> Purpose: clean, curated distribution of the devframe external-brain workflow.

## Working Model

This repository is the public, submodule-free version of devframe-system. Treat it as a product distribution repo, not as an internal work log.

Keep the root clean:

- Do not add `.gitmodules` or Git submodules.
- Do not commit local agent state, browser profiles, evidence packs, report dumps, paper drafts, or generated archives.
- Put reusable modules under `packages/`.
- Put user-facing docs under `docs/`.
- Put bootstrap assets under `templates/runtime-bootstrap/`.
- Put rules and JSON schemas under `rules/` and `schemas/`.

## Core Promise

The project is about using a web AI session, usually GPT Web, as an external brain for software development. The web AI coordinates direction, tasks, evidence, and review while IDEs, CLIs, browsers, scripts, tests, and coding agents act as interchangeable executors.

## Before Changing Files

1. Read the relevant files first.
2. Keep changes scoped to the public distribution surface.
3. Run `scripts/verify-public-snapshot.ps1` before committing.
4. If a change introduces licensing, secret, privacy, or publication risk, stop and ask for human confirmation.

## Public-Surface Rule

Only commit files that a new open-source reader can understand and use. If a file mainly explains internal delivery history, archived evidence, private runtime state, or one-off execution logs, it belongs outside this repository.
