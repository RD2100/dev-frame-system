# RD2100 Agent Runtime v2 -- JSON Schemas

> Batch D1, 2026-05-27
> JSON Schema Draft 2020-12

This directory contains JSON Schema definitions for the core integration contracts and @go evidence artifacts.

## Schemas

| # | Schema File | Description |
|---|-------------|-------------|
| 1 | `task-spec.schema.json` | Unit of work description before execution begins |
| 2 | `run-spec.schema.json` | Record of how a task was executed |
| 3 | `evidence-index.schema.json` | Index of evidence artifacts produced during a run |
| 4 | `gate-result.schema.json` | Result of a single verification gate check |
| 5 | `execution-report.schema.json` | Final structured report of a batch execution |
| 6 | `skill-intake-record.schema.json` | Intake evaluation record of an external skill |
| 7 | `tool-risk-record.schema.json` | Risk assessment of a tool available to agents |
| 8 | `memory-update-record.schema.json` | Proposed memory update subject to human approval |
| 9 | `source-lock-record.schema.json` | External skill source lock record (Phase 6) |
| 10 | `review.schema.json` | Independent reviewer verdict for an @go run |
| 11 | `safety-report.schema.json` | Deterministic guard output captured for an @go run |
| 12 | `chain-evidence.schema.json` | Role/session chain for an @go run |
| 13 | `multi-agent-gate0-preflight.schema.json` | Read-only readiness report for multi-agent / multi-GPT pilot startup |
| 14 | `multi-agent-dispatch-plan.schema.json` | Read-only first-wave worker assignment packet with conflict boundaries |
| 15 | `runtime-authorization.schema.json` | Human/coordinator authorization for bounded live or controlled runtime |
| 16 | `test-run-spec.schema.json` | Test-frame run specification with runtime boundary and expected status |
| 17 | `positive-pilot-authorization-packet.schema.json` | Wrapper pairing RuntimeAuthorization with TestRunSpec for exactly one real-resource positive pilot track |
| 17 | `test-execution-report.schema.json` | Test-frame execution result with blocked/failed/pass semantics |
| 18 | `failure-record.schema.json` | Traceable blocked/failed state record |
| 19 | `audit-event.schema.json` | Append-only governance event shape |
| 20 | `final-verdict.schema.json` | Governance final verdict boundary |
| 21 | `executor-contract.schema.json` | Vendor-neutral executor requirements, lifecycle, quota, blocker, and provenance observations |
| 22 | `offline-schema-registry.json` | Local URI-to-file map for offline resolution of cross-schema references |

## Constraints

- All schemas use JSON Schema Draft 2020-12.
- `additionalProperties` is `false` on all schemas.
- Phase 0-5 enum constraints are enforced:
  - SkillIntakeRecord disposition: `reference_only`, `candidate`, `defer`, `reject` only (no `install`, `absorb`, `approved`)
  - MemoryUpdateRecord status: `proposed` only for new records (no `approved` at agent level)
  - GateResult signer_role: must not be `executor`, `fixer`, or `coder`
- RuntimeAuthorization does not imply a quality verdict.
- TestExecutionReport does not imply final acceptance.
- FinalVerdict must not be produced by executor/fixer/coder/worker roles.
- Executor adapter, protocol, provider, and model identifiers are open
  provenance strings; they never change review, gate, or FinalVerdict authority.
- Executor observations must omit credentials, raw personal data, and absolute
  local paths. Adapters fail closed before JSON or Markdown publication rather
  than writing unsafe diagnostics into reports.
- Executor lifecycle terminal state is derived by highest attempt and then the
  newest timezone-aware observation, never by input array order. Negotiated
  capabilities must be a subset of declared capabilities.
- FinalVerdict superseding metadata is append-only lifecycle linkage, not
  acceptance evidence.
- Forbidden patterns (MCP config modification, UI-TARS/computer-use, package managers, external script execution) are documented in descriptions and NOT listed as permitted values.

## Offline consumers

The HTTPS `$id` values are stable identifiers, not network retrieval targets.
Consumers must load `offline-schema-registry.json` from this same directory
into their JSON Schema resolver and resolve every URI to its sibling file. The
Python reference implementation is
`ai_workflow_hub.agent_runtime_schemas.load_offline_validator(schema_filename, schema_dir)`;
it accepts an explicit local schema directory and never performs network I/O.
The Python wheel intentionally does not embed a second copy of these schemas:
callers pass the public distribution bundle they want to validate.
