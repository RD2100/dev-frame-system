# Local Agent Control Plane Stage 8 Open-source Reuse Visual MVP

Date: 2026-06-24
Status: `visual_mvp_acceptance_pass`

This stage moves the Local Agent Control Plane from a read-only engineering
dashboard toward a directly inspectable visual product. It does not claim a
production release, package publication, PR, push, or live remote execution.

## Goal

Build the next MVP as a reuse-first visual control plane:

- prefer mature open-source agent UI/runtime projects before hand-rolling;
- use T3 Code as the first visual-client reuse candidate;
- use OpenCode as the first local coding-agent runtime/provider reference;
- keep devframe responsible for project contracts, external-brain workflow
  semantics, evidence, review, gates, and decisions;
- preserve zero-configuration local acceptance so the user can open the product
  surface directly.

## Source Review

Reference clones were inspected outside this public repository.

| Project | Source | Revision | License | Reuse role |
|---|---|---:|---|---|
| T3 Code | `https://github.com/pingdotgg/t3code` | `4abf8b4` | MIT | Primary visual-client candidate: web UI, session UX, server/client split, coding-agent control surface patterns. |
| OpenCode | `https://github.com/anomalyco/opencode` | `8e2d422` | MIT | Primary executor/runtime reference: local coding-agent behavior, provider/session boundaries, CLI/desktop split. |

No external source tree has been vendored into this repository. Any future
source import must pass `rules/open-source-reuse.md`, including license,
attribution, source revision, and public-surface review.

## Execution Phases

| Phase | Purpose | Acceptance |
|---|---|---|
| 8.1 Rules | Make reuse-first behavior mandatory for future agents. | `rules/open-source-reuse.md` exists and is linked from `AGENTS.md` and the rules index. |
| 8.2 Source boundary | Confirm what T3 Code and OpenCode should supply. | Stage report records source URL, revision, license, and reuse role. |
| 8.3 Visual workbench | Make the first dashboard viewport feel like a product cockpit, not a command report. | Browser-opened dashboard shows project, agents, sessions, gates, and primary action together. |
| 8.4 Runtime bridge | Keep the UI reading the existing devframe runtime model. | No new private state model or external side effect is required for the MVP. |
| 8.5 Zero-config acceptance | Let the user inspect the product without setup. | Temporary local demo runtime can serve the dashboard on loopback and pass browser checks. |

## Current Progress

- Phase 8.1 is implemented.
- Phase 8.2 is implemented as a non-vendored source assessment.
- Phase 8.3 is implemented with a first-viewport Control Plane Workbench in the
  existing local dashboard.
- Phase 8.4 remains intentionally thin: the current UI still reads the existing
  schema-compatible runtime state.
- Phase 8.5 passed with a temporary local demo runtime served on loopback and
  inspected through Chrome/CDP on desktop and narrow viewports.

## Verification

Latest local verification:

```powershell
python -m pytest packages\control-plane\tests\test_rdgoal.py::test_devframe_cli_exports_visual_state_html_file packages\control-plane\tests\test_rdgoal.py::test_dashboard_server_serves_html_and_state_json_read_only packages\control-plane\tests\test_rdgoal.py::test_render_visual_control_plane_html_defaults_to_english -q
powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1
```

Results:

- focused dashboard HTML tests: `3 passed`;
- full release gate: `160 passed`;
- public snapshot: `[OK]`;
- control-plane wheel smoke: `[OK]`;
- browser acceptance: desktop and 390px narrow viewport both showed the Control
  Plane Workbench, primary action, `/go` agent section, provider gate, and
  action handoff link with no page-level horizontal overflow.

## User Acceptance

The next human acceptance should be visual:

- open the local dashboard URL;
- confirm the first screen reads as a usable control plane;
- confirm project, agents, sessions, gates, and next action are visible without
  reading CLI output;
- reject only if the product direction is wrong or the UI is not useful enough
  as a daily cockpit.

CLI checks remain support evidence only. They are not the final product
acceptance for this stage.

## Known Boundaries

- No fork or vendor import has been committed.
- No deployment, publishing, remote execution, or browser-profile extraction is
  part of this stage.
- Full T3 Code UI integration is a later slice; this stage first aligns the
  devframe control model and visual acceptance path.
