# Stage Gate Policy

> Authority: agent-acceptance
> Consumers: dev-frame-opencode, GPT reviewer, any automation agent
> Version: 1.0.0

---

## Gate Definitions

### Gate Result Enum

| Gate | Meaning | allow_next_stage | Behavior |
|------|---------|-----------------|----------|
| **accepted** | All evidence present, no blocking issues | true | Advance to next stage |
| **blocked** | Evidence missing, scope violation, or fake-green risk | false | Stop, generate reconciliation plan |
| **human_required** | Decision requires human attestation or input | false | Stop, provide resume condition |
| **partial** | Some aspects accepted, others need work | dependent | Advance only the accepted subset |
| **unknown** | Decision cannot be parsed or is ambiguous | false | Fail-closed, re-run review |

---

## Stage Advancement Conditions

### To advance to next stage, ALL of these must be true:

1. Current stage gate is `accepted` (or `partial` with explicit `allow_next_stage=true` for a specific subset)
2. `allow_next_stage` is `true` in FLOW_OUTCOME
3. Next stage TaskSpec exists and is valid per TASKSPEC.schema.json
4. No `human_required` taxonomy code applies to next-stage actions
5. Dispatcher has written `dispatch_status: dispatched` or `ready_to_dispatch` with valid `next_task_spec_path`

### Stage-Critical Blockers (P0)

These block stage advancement unconditionally:

| Blocker | Detection |
|---------|----------|
| Missing required evidence | FLOW_OUTCOME `errors[]` non-empty |
| Scope violation | GPT flagged scope_violation |
| Fake-green risk | GPT flagged fake_green_risk |
| Unresolved human_required | business_decision = human_required |
| Schema validation failure | FLOW_OUTCOME does not validate against schema |
| Missing next_task_spec_path when terminal=false | Schema validation failure |

### Non-Stage-Critical Warnings (P2)

These do NOT block stage advancement but should be logged:

| Warning | Detection |
|---------|----------|
| Optional evidence missing | EXISTING_EVIDENCE_INDEX lists as missing |
| Transport retried | transport_status changed from failed to success after retry |
| Extraction confidence low | GPT reply extraction confidence < medium |
| Non-standard dispatch path | dispatch_status path different from accepted->dispatched |

---

## GPT Review vs. Agent-Acceptance Gate Priority

### Priority Chain

```
GPT Review (business_decision)
  ↓
Agent-Acceptance Gate (validates against schemas & policies)
  ↓
Dispatch (if both above pass)
```

- GPT review provides `business_decision` and `allow_next_stage`
- Agent-acceptance gate validates that the decision is consistent with schemas and policies
- If agent-acceptance gate detects a schema/policy violation that GPT missed, it overrides with `blocked`
- GPT review is ADVISORY on the business logic; agent-acceptance gate is NORMATIVE on the contract

### Conflict Resolution

If GPT says `accepted` but agent-acceptance gate detects a schema violation:

1. The gate result becomes `blocked`
2. `errors[]` is populated with the specific schema violation
3. A reconciliation TaskSpec is generated
4. GPT is re-invoked with the specific violation for re-review

---

## S-Stage Specific Conditions

### S2 → S3

- S2 evidence pack must exist and be complete
- S2 GPT review must return `accepted`
- S3 TaskSpec must not contain destructive actions
- Independent reviewer evidence must be present (per SADP 0.R)

### S3 → S4

- S3 Phase 1 must be `accepted`
- S3 Phase 2 TaskSpec must exist
- AA-1 Flow Contract must be defined (after AA-1 is complete)
- S4 scope must be within approved boundaries
