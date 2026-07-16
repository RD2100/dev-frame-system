# Dispatcher Policy

> Authority: agent-acceptance
> Consumers: dev-frame-opencode post-decision driver, any dispatcher component
> Version: 1.1.0

---

## Core Rule

The dispatcher MUST produce a consumable `DISPATCH_RESULT` that automation can
read and act on. The dispatcher SHALL NOT merely "suggest" - it must generate
actionable state for an explicit bounded chain. It must not manufacture a new
stage after natural milestone completion.

---

## Dispatch Decision Matrix

| Business Decision | allow_next_stage | Dispatcher Action | dispatch_status | terminal | should_execute_next |
|-------------------|------------------|-------------------|-----------------|----------|---------------------|
| accepted | true | Generate TaskSpec + dispatch | dispatched | false | true |
| accepted | false | Close the bounded milestone with reason `accepted_done`; keep only a resumable backlog pointer | stopped | true | false |
| partial | true (subset) | Dispatch allowed subset | dispatched | false | true |
| partial | false | TaskSpec generated, manual confirm | manual_confirm_required | false | false |
| blocked | N/A | Generate reconciliation plan | stopped | true | false |
| human_required | N/A | Stop, provide resume condition | stopped | true | false |
| unknown | N/A | Fail-closed, do not guess | stopped | true | false |

---

## Dispatcher Output Requirements

Every dispatch result MUST include:
1. `dispatch_status` — exactly one of the 6 enum values
2. `terminal` — boolean
3. `should_execute_next` — boolean
4. When NOT terminal: `next_task_spec_path` OR `required_next_action`
5. When terminal: `required_next_action`
6. When stopped/manual_confirm_required: `resume_command`

---

## Accepted + allow_next_stage=true Path

This is the normal progression path.

```
GPT accepts → allow_next_stage=true
  → dispatcher writes DISPATCH_RESULT with:
    dispatch_status: dispatched
    terminal: false
    should_execute_next: true
    next_task_spec_path: <path>
  → runner picks up TaskSpec and executes
```

The dispatcher MUST NOT stop here. The flow is explicitly non-terminal.

This path is valid only when the active milestone already defines the next
stage. `allow_next_stage=true` must not be synthesized merely because later
project backlog exists.

---

## accepted + allow_next_stage=false Path

When current milestone evidence and required gates pass and no explicit stage
remains active:

```
business_decision: accepted
allow_next_stage: false
  -> dispatcher writes DISPATCH_RESULT with:
    dispatch_status: stopped
    terminal: true
    should_execute_next: false
    reason: accepted_done
    required_next_action: <resumable backlog pointer or "none">
```

The pointer is not a `next_task_spec_path`. A later coordinator activation
creates the next bounded chain.

---

## human_required Path

```
GPT returns human_required
  → dispatcher writes DISPATCH_RESULT with:
    dispatch_status: stopped
    terminal: true
    should_execute_next: false
    required_next_action: <what human must do>
    resume_command: <how to resume after human action>
```

The flow stops until human action is complete.

---

## blocked Path

```
GPT returns blocked
  → dispatcher writes DISPATCH_RESULT with:
    dispatch_status: stopped
    terminal: true (or false if reconciliation is possible)
    should_execute_next: false
    required_next_action: <reconciliation plan>
```

If reconciliation is possible (e.g., missing evidence), the dispatcher may generate a reconciliation TaskSpec instead of stopping.

---

## unknown Path

```
GPT decision cannot be parsed → unknown
  → dispatcher MUST fail-closed:
    dispatch_status: stopped
    terminal: true
    should_execute_next: false
    reason: "GPT decision unparseable, fail-closed for safety"
```

The dispatcher must never guess or assume acceptance when the decision is unknown.

---

## Anti-Patterns

| Anti-Pattern | Why Wrong | Correct |
|-------------|-----------|---------|
| Dispatcher outputs Markdown report only | Not machine-readable | Output DISPATCH_RESULT JSON |
| Dispatcher writes "ready" but doesn't dispatch | ready_to_dispatch without dispatch is stuck | Either dispatch or explicitly stop |
| Dispatcher assumes accepted on transport success | Transport != business decision | Read business_decision from FLOW_OUTCOME |
| Dispatcher emits "suggestion" without action fields | Suggestion != dispatch | Must include should_execute_next and next_task_spec_path |
| Dispatcher creates a next stage only to avoid idle | Scheduling metadata becomes fabricated work | Close with accepted_done and leave a resumable pointer |
