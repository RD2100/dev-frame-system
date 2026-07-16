# Recon Receipt: M2 read-only session detail projection

> Governs the M2 session-detail slice under `rules/recon.md` recon-001/003/008
> and `rules/open-source-reuse.md` reuse-000/001/002.

## Target

- user_goal: expose one auditable DevFrameSession detail through the existing
  local dashboard without adding an action, approval, or runtime mutation path.
- target: the existing `/sessions.json` dashboard surface and the existing
  `public_session_summaries()` projection.
- current_slice_goal: add an exact-match `/sessions/<session-id>.json`
  read-only route that returns a public session projection or `404`.
- out of scope: mutation endpoints, browser/provider access, credentials,
  raw transcripts, packet/report paths, evidence browsing, and UI changes.

## Resource Map And Reuse Decision

| Capability | Existing candidate | Decision |
| --- | --- | --- |
| Dashboard HTTP routing | `control_plane.dashboard` | Reuse directly |
| Session state construction | `build_visual_control_plane_state()` | Reuse directly |
| Public list projection | `public_session_summaries()` | Reuse its field allowlist |
| Detail UI/client | external T3 checkout | Do not build or vendor in this slice |

No new client, agent UI, session runtime, provider adapter, or transport is
needed. The detail route is a narrow read model over already-public fields.

## Risk Table

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Local runtime paths or native refs leak | P0 | Reuse public projection only; detail strips TaskSpec to its filename. |
| Unknown or malformed session reads as another session | P0 | Exact session-id match; return `404` otherwise. |
| Detail route becomes an execution seam | P0 | `GET` only; no command, action, approval, or dispatch calls. |
| List API compatibility regresses | P1 | Keep `/sessions.json` and its projection unchanged. |

## Frozen TaskSpec

- write_set:
  - `packages/control-plane/control_plane/dashboard.py`
  - `packages/control-plane/control_plane/visual_state.py`
  - `packages/control-plane/tests/test_dashboard_actions.py`
  - `docs/status/recon-receipt-session-detail-read-model.md`
  - `docs/status/status-document-inventory.md`
- real RED probe: a running local dashboard returned `404` for
  `/sessions/demo-session.json` before the route existed.
- GREEN evidence: a running local dashboard returns a matching session's
  public projection, does not include runtime/native/path fields, and returns
  `404` for a missing session.
