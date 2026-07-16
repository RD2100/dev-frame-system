# Recon Receipt: M4 session-detail CLI consumption

> Governs the M4 CLI detail slice under `rules/recon.md` recon-001/003/008.

## Target

- user_goal: inspect one existing DevFrameSession through `devframe sessions`.
- target: `cmd_sessions()` and the existing `public_session_detail()` projection.
- out of scope: runtime writes, action execution, approvals, provider/browser
  access, raw transcripts, native references, and local path output.

## Reuse Decision

| Capability | Existing candidate | Decision |
| --- | --- | --- |
| Session state | `build_visual_control_plane_state()` | Reuse directly |
| Public detail boundary | `public_session_detail()` | Reuse directly |
| CLI list command | `cmd_sessions()` | Add one optional exact-id read branch |

No new CLI transport, agent runtime, or provider integration is needed.

## Frozen TaskSpec

- write_set:
  - `packages/control-plane/control_plane/cli/_visual.py`
  - `packages/control-plane/tests/test_cli.py`
  - `docs/status/recon-receipt-session-detail-cli.md`
- RED: `devframe sessions --session-id review-session-1` was rejected as an
  unknown argument.
- GREEN: an exact id returns the public detail projection; a missing id exits
  nonzero instead of falling back to the list.

## Risks

| Risk | Mitigation |
| --- | --- |
| Runtime/path/native-ref leakage | Reuse only `public_session_detail()`. |
| Unknown id returns unrelated data | Exact match; parser error on absence. |
| CLI becomes a mutation path | No new command, network, or write call. |
