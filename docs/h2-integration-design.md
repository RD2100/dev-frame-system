# H2 — DevFrame OpenCode Integration Design

## Architecture

Control Plane drives dev-frame-opencode pipeline stages: authorization, execution, closure, audit.

## Mapping

| Control Plane Stage | dev-frame-opencode Phase |
|---------------------|-------------------------|
| authorization | GPT review pack submission |
| execution_closure | Code change + test + evidence |
| audit | Smoke + readiness check |

## Integration Points

1. Pipeline YAML defines dev-frame-opencode task sequences
2. Runner dry-run validates stage sequence
3. Submission Adapter handles CDP for auth/closure
4. State Machine enforces CURRENT_ROUTE invariants

## Current State

- Control Plane: G0-G8 + H1 complete, 43/43 tests
- dev-frame-opencode: production promoted, live CDP verified
- Integration: design only
