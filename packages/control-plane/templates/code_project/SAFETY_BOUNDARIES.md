# Safety Boundaries

## Do Not Commit

- `.env` or `.env.*`
- `private/` or local workspaces
- `evidence_packs/`
- `browser_profile/`, `sessions/`, or `cookies/`
- generated archives such as `*.zip`
- raw logs that may contain secrets or local-only state

## Change Boundaries

- Risky implementation work needs external-brain authorization.
- Guards must not be removed while `guard_removal_approved` is false.
- Evidence must not be cleaned while `evidence_cleanup_approved` is false.
- Production promotion requires separate explicit approval.

## Review Requirements

- Capture the exact commands used for verification.
- Include changed files, evidence, known gaps, and reviewer focus in the final
  ExecutionReport.
- If a boundary is violated, stop and restore the last safe state.
