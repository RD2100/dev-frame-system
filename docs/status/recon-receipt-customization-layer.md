# Recon Receipt: customization layer

Status: ACCEPTED to proceed in governed slices.
Domain: control-plane configuration, project-scoped customization, governance
constraints, and RD-Code visual editing surface.
Date: 2026-06-30.

## Goal

Turn framework units that were previously hardcoded or global-only into
machine-readable configuration objects that can be resolved by the control plane
and edited by RD-Code without committing local or project state to the public
repository.

The governed categories are:

- team roster
- custom skills
- custom rules
- run defaults
- global preferences and project memory

## Scope Model

The customization layer uses exactly three scopes, ordered from least to most
specific:

1. `builtin`
2. `global`
3. `project`

The most-specific scope defining a record wins. Path and glob scopes are
deferred. Scope selection is intentionally separate from conflict resolution.

## Conflict Model

Capability-bearing records use a deny-overrides rule:

- any restrictive vote wins over permissive votes
- disabled records do not vote
- P0 rules act as hard denies
- P0 hard denies cannot be weakened by a project override

These constraints are resolved in `scope_resolver.py` and passed to dispatch as
hard constraints, not as prompt-only guidance.

## Storage Boundary

Global and project customization files must live under the runtime directory:

- global: `<runtime>/<category-file>.json`
- project: `<runtime>/<project_id>/<category-file>.json`

The public repository may only add reusable code, tests, schemas, and public
documentation. Local tool drafts such as `.kiro/specs/customization-layer/` are
ignored workspace state and must not be treated as the public source of truth.

## Reuse Assessment

- Reuse the existing control-plane modules for team, skills, rules, dispatch,
  dashboard endpoints, and visual manifests.
- Build one shared resolver (`scope_resolver.py`) and one storage helper
  (`scoped_store.py`) instead of duplicating merge and malformed-file handling
  in every category.
- Reuse the existing dashboard loopback and origin gating for all write paths.
- Reuse the RD-Code manifest and coordinator-pane extension model; do not vendor
  or commit the editor fork into this public repository.

## Integration Risk Table

- risk: project overrides weaken governance.
  - severity: high
  - mitigation: deny-overrides and P0 hard-deny tests at resolver and dispatch
    packet boundaries.
- risk: malformed local config breaks runs.
  - severity: medium
  - mitigation: malformed-safe loaders fall back to less-specific valid layers.
- risk: customization writes leak into the public repo.
  - severity: high
  - mitigation: `ScopedStore` confines writes under the runtime root and
    `scripts/verify-public-snapshot.ps1` ignores local tool state while still
    failing on forbidden generated/public-surface files.
- risk: old global-only callers regress.
  - severity: medium
  - mitigation: existing `load_*` and `save_*` APIs remain global-scope aliases.

## Evidence Required For Completion

- resolver and property tests:
  - `packages/control-plane/tests/test_scope_resolver.py`
  - `packages/control-plane/tests/test_scope_resolver_properties.py`
- category tests:
  - `packages/control-plane/tests/test_cluster_control.py`
  - `packages/control-plane/tests/test_custom_skills.py`
  - `packages/control-plane/tests/test_rules_config.py`
  - `packages/control-plane/tests/test_run_defaults.py`
  - `packages/control-plane/tests/test_memory_prefs.py`
- API and dispatch tests:
  - `packages/control-plane/tests/test_dashboard_customization.py`
  - `packages/control-plane/tests/test_dashboard_run_defaults.py`
  - `packages/control-plane/tests/test_dashboard_memory.py`
  - `packages/control-plane/tests/test_executor_constraints.py`
  - `packages/control-plane/tests/test_dashboard_customization_smoke.py`
- public surface gate:
  - `powershell -ExecutionPolicy Bypass -File scripts\verify-public-snapshot.ps1`

## Deferred

- path-scope and glob-scope configuration
- live RD-Code fork visual acceptance
- publishing or installer signing
- any live worker run that would spend model tokens without explicit human
  approval
