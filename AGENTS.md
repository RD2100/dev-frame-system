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
- For any write-capable work in a mature capability area, complete the
  Recon Gate in `rules/recon.md` before dispatching coder workers.
- Prefer mature open-source reuse before hand-rolling visual-agent UI or local
  coding-agent runtime behavior; follow `rules/open-source-reuse.md`.
- Do not hand-roll client, agent UI, session, runtime, terminal, diff, browser,
  provider, MCP bridge, review gate, evidence store, multi-agent surface, or
  desktop/mobile behavior before recording a Recon Receipt and reuse
  assessment.
- Multi-agent work must model team communication as first-class objects; follow
  `rules/recon.md` RULE recon-008 instead of treating parallel sessions as a
  complete team.

## Core Promise

The project is about using a web AI session, usually GPT Web, as an external brain for software development. Through MCP, that web AI becomes a local agent entrypoint. The web AI coordinates direction, tasks, evidence, and review while IDEs, CLIs, browsers, scripts, tests, and coding agents act as interchangeable executors.

## Document Authority

Read `docs/status/HANDOFF.md` before planning or resuming repository work. It
is the single current execution root: it selects the active milestone, risk
register, write set, verification gate, and next action. Do not create a
parallel master plan, roadmap, handoff, or current backlog in `docs/status/`.

Other status documents are supporting evidence, scoped Recon Receipts, stable
runtime explanations, or historical research. They may constrain a slice in
their own scope, but they do not choose the next task. If they conflict with
the execution root, record the conflict there and follow the root plus the
mandatory rules in this file and `rules/`.

## Accepted Slice Git Lifecycle

Follow `rules/git.md` RULE git-006 for every write-capable slice:

- Coding workers may edit, test, and report, but they must not stage, commit, or
  set `root_accepted`.
- Only the root coordinator may set `root_accepted`, and only after independent
  review, required evidence, and reconciliation against the actual diff pass.
- Each `root_accepted` slice must become exactly one local logical commit. The
  root coordinator stages only the accepted paths and verifies that the cached
  path set and content exactly match the accepted slice before committing.
- Failed, blocked, rejected, or unreviewed slices must not be committed. In a
  dirty worktree, broad staging, broad restore, stash, reset, and clean are not
  part of the slice lifecycle; the captured baseline remains protected.
- Push, pull request creation, merge, release, history rewrite, hook
  registration, and global Git or agent configuration require an explicit
  human gate. Force-push to `main` or `master` remains forbidden.

## Before Changing Files

Follow [Agent Coding Discipline](docs/agent-runtime/agent-coding-discipline.md)
for project-wide agent behavior rules. Cite its rule IDs in plans, handoffs, and
review reports when a task depends on discipline such as interface truth,
requirement alignment, reuse, verification, or scope control.

1. Read the relevant files first.
2. Check CodeGraph before broad code exploration. If `.codegraph/` is missing
   or stale, initialize or rebuild it only when the user has authorized that
   local index write, then prefer CodeGraph for structural questions such as
   definitions, callers, callees, impact, and task context.
3. Keep changes scoped to the public distribution surface.
4. For client, runtime, provider, MCP, review/evidence, or multi-agent work,
   check `rules/recon.md` first. Missing Recon Receipt is a blocker, not a
   style preference.
5. For visual control-plane work, check `rules/open-source-reuse.md` before
   building a new UI or runtime layer from scratch. Missing reuse assessment is
   a blocker, not a style preference.
6. Run `scripts/verify-public-snapshot.ps1` before committing.
7. If a change introduces licensing, secret, privacy, or publication risk, stop and ask for human confirmation.

## CodeGraph Cost Control

CodeGraph is the default cost-control layer for this repository. Agents should
not start wide grep/read loops or parallel code-reading subagents until they
have checked the CodeGraph status. The local `.codegraph/` directory is
generated agent state and must stay uncommitted. Use native search only for
literal strings, logs, comments, or when CodeGraph cannot answer the question.

## Public-Surface Rule

Only commit files that a new open-source reader can understand and use. If a file mainly explains internal delivery history, archived evidence, private runtime state, or one-off execution logs, it belongs outside this repository.
