# Release Readiness

This page records the current public-release gate for `dev-frame-system`.
It is meant for reviewers who need to decide whether the repository is ready
to share, package, or hand off.

For a file-level review map, see `docs/status/reviewer-index.md`.

## Release Gate

Run the full release verification from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1
```

The release gate currently runs:

- `python -m pytest -q`
- `scripts\verify-public-snapshot.ps1`
- `scripts\verify-control-plane-wheel.ps1`
- `git diff --check`

The same gate is wired into `.github/workflows/release-verify.yml` for push,
pull request, and manual workflow runs.

The wheel smoke test builds `packages/control-plane`, installs the wheel into a
temporary virtual environment, then runs the installed `devframe` console script
through `devframe --help`, `devframe run --help`, `devframe dashboard --help`,
`devframe visual-state`, `devframe actions`, `devframe dashboard serve`, and
`--paper-project` coverage, and the installed `rdgoal` console script through
`rdgoal`, `rdgoal worker`, and `rdgoal digest`.

## Expected Public Surface

- Root documentation: `README.md`, `README.zh-CN.md`, `AGENTS.md`.
- Runtime docs and status files under `docs/`.
- Reusable modules under `packages/`.
- Public rules and schemas under `rules/` and `schemas/`.
- Bootstrap assets under `templates/runtime-bootstrap/`.
- Verification scripts under `scripts/`.

Do not include local agent state, browser profiles, evidence packs, generated
archives, `build`, `dist`, or package metadata directories in the public tree.

## Known Behavior

- Source checkout `rdgoal --apply-rdinit` can run the full bootstrap when the
  root bootstrap assets are present.
- Wheel installs do not carry the full repository root bootstrap assets. In
  that mode `rdgoal --apply-rdinit` returns `bootstrap_unavailable`, still
  creates the project contract, and still emits a dispatch packet.
- `rdgoal worker` returns exit code `0` only for `pass`, `passed`, or
  `completed` reports. `blocked`, `failed`, and unknown statuses are non-zero.
- Runtime packets, reports, and snapshots are written outside the public
  repository by default.
- Visual Control Plane read-only exports include `/`, `/state.json`,
  `/actions.json`, and `/actions.md`. These endpoints are intended for
  inspection only and do not accept writes.
- Action Queue resume and filtering use `--action-id` as the focused selector.
- Scripts use `--fail-on-match` as a read-only gate to surface blocked or
  failed actions without mutating state.
- Dashboard binds to non-loopback hosts only when `--allow-remote` is
  explicitly provided.
- `stepfun/step-3.7-flash` is documented for narrow single-file post-TaskSpec
  execution. Its external evidence-dir write limitations are captured in
  `dispatch-model-profiles.md`.

## Reviewer Focus

- Confirm `scripts\verify-release.ps1` is the final gate used before sharing.
- Confirm `scripts\verify-public-snapshot.ps1` catches forbidden generated
  output and private runtime state.
- Confirm the wheel smoke test exercises the installed `devframe` and `rdgoal`
  console scripts, not only `python -m control_plane.*`.
- Confirm rdgoal blocked and failed states cannot be reported as success.
- Confirm public docs do not reference private machine paths.
- Confirm the Visual Control Plane dashboard endpoints `/`, `/state.json`,
  `/actions.json`, and `/actions.md` are documented as read-only exports.
- Confirm `--action-id`, `--fail-on-match`, and `--allow-remote` are
  documented and tested as the Action Queue resume/filter mechanism,
  read-only script gate, and dashboard remote-bind safety guard
  respectively.
- Confirm `stepfun/step-3.7-flash` is documented only for narrow post-TaskSpec
  execution and that its evidence-dir write limitations are traceable to
  `dispatch-model-profiles.md`.

## Current Verdict

The repository should not be called release-ready unless the release gate above
passes on the current worktree and no generated artifacts remain afterward.
