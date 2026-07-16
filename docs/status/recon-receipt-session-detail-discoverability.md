# Recon Receipt: M3 session-detail discoverability

> Governs the M3 discoverability slice under `rules/recon.md` recon-001/003/008
> and `rules/open-source-reuse.md` reuse-000/001/002.

## Target

- user_goal: let an operator discover the existing public session-detail read
  model from the dashboard and client manifest.
- target: the Session Stream HTML lane and the visual client manifest.
- current_slice_goal: link each displayed session id to its own exact
  `/sessions/<session-id>.json` GET route and record that route in the
  manifest.
- out of scope: session mutation, dispatch, approval, provider/browser access,
  raw transcript rendering, external client implementation, and URL-driven
  runtime lookup.

## Resource Map And Reuse Decision

| Capability | Existing candidate | Decision |
| --- | --- | --- |
| Session Stream rendering | `_workbench_session_lane()` | Extend in place |
| URL encoding | `urllib.parse.quote` already imported by `visual_state` | Reuse directly |
| Endpoint catalog | `build_visual_client_manifest()` | Add a read-only endpoint entry |
| Detail API | M2 `/sessions/<session-id>.json` | Reuse unchanged |

No external client, session runtime, or visual-agent UI is introduced.

## Risk Table

| Risk | Severity | Mitigation |
| --- | --- | --- |
| A link targets a different session or a mutation endpoint | P0 | Derive the href only from that row's `session_id`; GET route only. |
| Detail discovery leaks native/runtime state | P0 | Link only; M2 public detail projection remains the response boundary. |
| Manifest implies a write capability | P1 | Explicit `GET` and `mutates: false`. |
| Existing dashboard list behavior regresses | P1 | Direct HTTP rendering regression test. |

## Frozen TaskSpec

- write_set:
  - `packages/control-plane/control_plane/visual_state.py`
  - `packages/control-plane/control_plane/client_manifest.py`
  - `packages/control-plane/tests/test_dashboard_actions.py`
  - `packages/control-plane/tests/test_client_manifest.py`
  - `docs/status/recon-receipt-session-detail-discoverability.md`
  - `docs/status/status-document-inventory.md`
- real RED evidence: rendered Session Stream had no
  `/sessions/review-session-1.json` href; the manifest lacked the parameterized
  detail route.
- GREEN evidence: the local dashboard renders the exact href for the same
  session and the schema-validated manifest registers a non-mutating GET
  detail endpoint.
