# Recon Receipt: M6 human-readable session detail

> Governs the M6 dashboard slice under `rules/recon.md` recon-001/003/009 and
> `rules/open-source-reuse.md` reuse-000/001/002.

## Target

- user_goal: let a dashboard reader open one exact public session detail in a
  human-readable, read-only HTML page.
- current_slice_goal: add `GET /sessions/<session-id>` beside the existing
  machine-facing `GET /sessions/<session-id>.json`, then point Session Stream
  links at the HTML page.
- out_of_scope: POST routes, dispatch, approvals, execution, providers,
  browsers, network calls, native-client changes, raw transcripts, tool input,
  evidence browsing, runtime paths, credentials, and runtime-state artifacts.

## Resource Map And Reuse Decision

| Capability | Existing candidate | Decision |
| --- | --- | --- |
| HTTP routing and response handling | `packages/control-plane/control_plane/dashboard.py` | Reuse directly. |
| Public session allowlist | `public_session_detail()` in `visual_state.py` | Reuse directly; do not project raw session data. |
| Safe standalone HTML pattern | `_render_review_gate_open_html()` in `dashboard.py` | Adapt its escaped, read-only detail layout. |
| Session Stream link rendering | `_session_detail_href()` / `_session_detail_link()` in `visual_state.py` | Retarget to the HTML route. |
| Detail UI/client | Existing local dashboard | Adapt; no external source, vendoring, or new client shell. |

The dashboard remains a support-only local read surface. T3Code/OpenCode are
not used by this bounded route because no client/runtime integration is added.

## Risk Table

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Private runtime/native/path/transcript/tool data leaks into HTML | P0 | Render only `public_session_detail()` fields and HTML-escape every value. |
| Unknown or malformed IDs return another session | P0 | Exact lookup and fail-closed `404`; reject empty or slash-containing IDs. |
| Human page becomes a mutation seam | P0 | `GET` only; no forms, actions, dispatch calls, or write-capable links. |
| Existing JSON consumers or Session Stream regress | P1 | Keep `.json` route unchanged and add direct HTTP/link regression tests. |

## Frozen TaskSpec

- write_set:
  - `packages/control-plane/control_plane/dashboard.py`
  - `packages/control-plane/control_plane/visual_state.py`
  - `packages/control-plane/tests/test_dashboard_actions.py`
  - `docs/status/recon-receipt-session-detail-html.md`
  - `docs/status/status-document-inventory.md`
- real RED probe: a running local dashboard must return `404` for
  `/sessions/review-session-1` before implementation.
- GREEN evidence: direct HTTP proves the HTML page contains only public
  session fields, escapes content, fails closed for unknown/malformed IDs, and
  Session Stream links to the HTML page while `.json` remains available.
- review gate: inspect actual diff for route precedence, allowlist-only data,
  escaping, and absence of forms or mutation endpoints.
