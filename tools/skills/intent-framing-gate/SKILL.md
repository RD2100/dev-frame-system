---
name: intent-framing-gate
description: Triggered pre-work framing for ambiguous, recurring, completeness, or meta-agent-failure requests. Use when user says "@intent-frame", "is this complete", "next time", "similar problem", "why did the agent miss this", "not just the literal edit", "underlying intent", "ensure this will not recur", "意图上浮", "类似问题", or "下次不会再出问题".
---

# intent-framing-gate - Intent Framing Before Execution

Role: methodology skill for turning high-signal user wording into an explicit
problem frame before coding, documentation, or workflow changes.

## Core Rule

Do not guess hidden intent silently. Frame it explicitly, then continue only
inside the approved scope.

## Trigger Profile

Use this gate when the user asks about:

- completeness: "is this full", "is the map enough", "can we ensure";
- recurrence: "next time", "similar problem", "avoid this again";
- meta-agent misses: "you only did what I said", "why did you not notice";
- ambiguity: "underlying intent", "not just the literal edit";
- governance: directory, skill, rule, workflow, handoff, evidence, review.

## Required Output

Before executing, produce or internally record:

1. Literal request.
2. Inferred systemic concern.
3. Recurrence class: one-off, recurring, unknown, or policy-risk.
4. Affected durable asset: documentation map, skill, rule, schema, test,
   evaluation record, runtime policy, or human attention workflow.
5. Action level: answer-only, documentation update, skill/rule update,
   schema/test proposal, or runtime-policy proposal.
6. Ask-or-continue decision.

Ask at most one focused question when the answer changes authority, risk, or
write scope. Otherwise continue with a low-risk assumption and state it.

## Hard Stops

- Do not use intent framing to expand implementation scope silently.
- Do not turn every small task into a planning exercise.
- Do not claim mind-reading; this is a triggered governance check.
- Do not treat framing as final acceptance or implementation evidence.
