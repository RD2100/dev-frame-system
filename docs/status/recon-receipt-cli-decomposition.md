# Recon Receipt -- control-plane CLI decomposition

> Governs write-capable work on `packages/control-plane/control_plane/cli.py`
> per `rules/recon.md` RULE recon-001 and recon-005. This receipt unlocks only
> the minimal, behavior-preserving slice described in "Recommended Next Slice".
> A broader rewrite requires re-approval of an updated receipt.

## Target
- user_goal: Reduce the maintenance risk of the oversized CLI entry module.
- target_repo_or_kb: dev-frame-system (control-plane package).
- current_slice_goal: Split the single `cli.py` into a `control_plane/cli/`
  subpackage organized by domain, with zero user-visible behavior change.
- requested_outcome: Remove the single-file cognitive load; keep all 519 tests
  green; no new runtime dependencies; preserve the public import contract.
- date: 2026-06-26
- planner_agent_id: kiro
- approval: Human owner approved Plan B (decompose into per-domain submodules)
  on 2026-06-26, scoping out the argparse migration as a later slice.

## Resource Map
- runtime_entrypoint: `packages/control-plane/control_plane/cli.py` (1866 lines).
- console scripts (`setup.py`): `devframe=control_plane.cli:main`,
  `rdgoal=control_plane.rdgoal_cli:main`.
- CLI structure today:
  - One module holds ~50 `cmd_*` functions plus ~20 `_helper` functions.
  - `main()` routes with ~21 hand-written `if cmd == ...` branches over raw
    `sys.argv`; `web-ai` and `client` add nested `if sub == ...` blocks.
  - Per-command usage strings are module-level constants (`*_USAGE`, `HELP_TEXT`).
  - Argument parsing is fully manual; no `argparse`, `click`, or `typer`.
- primary test coverage: `packages/control-plane/tests/test_cli.py` (and others)
  exercise routing, usage text, exit codes, and help behavior. Behavior is
  effectively locked by these tests.
- out_of_scope state: dashboard/visual-state/t3 projection modules are consumed
  by CLI commands but are not edited by this slice.

## Core Concepts
- execution_model: thin CLI that parses argv, dispatches to a `cmd_*` function,
  and returns its int exit code to `sys.exit` via the console script.
- review_model: exit-code contract (0 pass / non-zero blocked|failed) is part of
  the public contract and must not change.

## Capability Matrix
- argument parsing
  - location: `cli.py` (manual `sys.argv` slicing).
  - maturity: stable but high-complexity, duplicated across commands.
  - reusable_as_is: no (the manual approach is what we want to contain).
  - reusable_with_adapter: yes, via stdlib `argparse` over time.
- command routing
  - location: `main()` if/elif chain.
  - maturity: works, but adds branches per command and is easy to break.
  - reusable_with_adapter: yes, via a routing table (this slice).

## Reuse Candidate List
- candidate: stdlib `argparse`
  - source: Python standard library (zero new dependency).
  - exact_scope_to_reuse: subcommand parsing, in a later slice.
  - expected_adapter_work: per-command parser definitions; must reproduce exact
    usage strings and exit codes that tests assert.
  - blocking_constraints: large surface; risky to migrate in one step.
  - decision: defer to a future slice; not part of this receipt's unlocked work.
- candidate: `click` / `typer`
  - decision: rejected for now. `setup.py` install_requires is intentionally
    minimal (`pyyaml`, `jsonschema`); adding a CLI framework dependency is not
    justified by current need (RULE core-008 reuse-before-build: format/aesthetic
    preference is not a gap).

## Integration Risk Table
- risk: behavior drift in routing/usage/exit codes
  - type: correctness | severity: high
  - mitigation: keep this slice behavior-preserving; rely on the full pytest
    suite (519 tests) as the regression gate before and after.
- risk: scope creep into a full parser rewrite
  - type: maintenance | severity: medium
  - mitigation: this receipt unlocks only the routing-table slice; argparse
    migration needs a new/updated receipt.

## Build-vs-Buy Decision
- must_reuse: stdlib only; no new dependency.
- should_adapt: migrate manual parsing to `argparse` subcommands incrementally
  in future slices.
- can_spike: a `main()` command-routing table that maps command name -> handler,
  preserving current behavior exactly.
- must_build_new: nothing; do not author a custom argument parser.
- rationale: the value is in containing complexity and duplication, not in a new
  capability. The safest first increment changes structure, not behavior.

## Unknowns / Questions
- Whether any external caller depends on the exact ordering of `main()` checks
  (unlikely; commands are mutually exclusive). The routing table preserves
  precedence to avoid this risk.

## Recommended Next Slice (approved: Plan B)
- smallest_safe_increment: convert `control_plane/cli.py` into a
  `control_plane/cli/` package, moving each `cmd_*` function and its private
  helpers into a domain module **byte-for-byte** (function bodies unchanged).
  `main()` moves into `cli/app.py`; `cli/__init__.py` re-exports `main` and keeps
  `import shutil` so the test monkeypatch target `control_plane.cli.shutil`
  stays valid (the global `shutil` singleton makes the patch apply wherever the
  worker probe lives).
- module layout:
  - `_usage.py`: `HELP_TEXT` and all `*_USAGE` string constants (no imports).
  - `_common.py`: `_wants_help`, `_print_help`, `_is_loopback_host` (shared).
  - `_core.py`: init, doctor, run, rdgoal, handoff, pack commands.
  - `_coding.py`: code/go/atgo commands and their preview/status/session/worker
    helpers.
  - `_webai.py`: all `web-ai` subcommands and `_load_json_summary_file`.
  - `_client.py`: client command and client doctor.
  - `_visual.py`: visual-state, actions, sessions, dashboard and filter helpers.
  - `app.py`: `main()` router importing the domain handlers.
  - `__init__.py`: `import shutil`; `from .app import main`.
- dependency_direction: `_usage` <- `_common` <- domain modules <- `app` <-
  `__init__`. All heavy module dependencies are function-local lazy imports, so
  no top-level import cycles are introduced.
- worker_type_needed: single maintainer.
- files_or_modules_in_scope: `packages/control-plane/control_plane/cli.py`
  (removed) and the new `packages/control-plane/control_plane/cli/` package.
- public_contract_preserved: `from control_plane.cli import main` and the
  monkeypatch path `control_plane.cli.shutil.which` both keep working.
- evidence_required_for_completion: full `python -m pytest -q` stays at 519
  passed; `scripts/verify-public-snapshot.ps1` stays green.
- review_gate_definition: no user-visible behavior change; the diff is a code
  move plus import wiring, with no edits to any command body's logic.

## Deferred (requires updated receipt)
- Incremental migration of the manual `sys.argv` parsing to `argparse`
  subcommand parsers, done one domain module at a time so behavior-contract risk
  stays isolated and individually verifiable.
