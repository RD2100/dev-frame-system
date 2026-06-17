# Module Sources

This repository is a curated, submodule-free public snapshot. The previous working tree used four source repositories as Git submodules; this repo integrates only their reusable public surfaces.

## Source Mapping

| Public path | Source repository path | Pinned source commit used for snapshot | Included surface |
|---|---|---:|---|
| `packages/agent-acceptance/` | `agent-acceptance` | `bad61c9bf8274181a24cb70ed54aad17534c6333` | contracts, governance manifest helpers, policies, CI preflight templates |
| `packages/ai-workflow-hub/` | `dev-frame-opencode/ai-workflow-hub` | `a22f3bb68988a2107973c46a2df4dab31def31b8` | Python package source, configs, reusable scripts |
| `packages/control-plane/` | `devframe-control-plane` | `09167bc656f8625c97bfae5c52dae5a0280b116c` | control-plane package, pipelines, templates, setup metadata |
| `packages/test-frame/` | `test-frame` | `de0602b9ee9bcd48c9d786da34be48e3400758a9` | core test orchestration packages, schemas, mini-program E2E package |

## What Was Intentionally Not Imported

- Git submodule pointers and submodule history.
- Local agent state such as `.agent/`, `.ai/`, `.claude/`, `.opencode/`, and browser profiles.
- Evidence packs, report archives, paper draft packages, generated ZIP/DOCX artifacts, and runtime logs.
- One-off execution scripts whose only purpose was internal delivery, review submission, or historical cleanup.
- Large binary assets and generated caches.

## Why This Shape

The goal is to make the public repository easy to read, clone, and evaluate. The old multi-repo setup was useful while the system was being explored, but it mixed product surface with internal process history. This snapshot keeps the reusable operating system and removes the archaeological layers.

The expected public mental model is:

```text
web AI external brain
  -> rules + schemas + TaskSpec
  -> executor modules under packages/
  -> evidence + review gates
  -> reusable lessons
```
