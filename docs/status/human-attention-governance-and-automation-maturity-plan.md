# Human Attention Governance And Automation Maturity Plan

Lifecycle state: Draft active planning record

Plan status: Accepted as the attention-governance layer for the document-driven
transformation plan. Not yet an implementation claim.

Reader: DevFrame maintainers designing automation that should save human
attention instead of creating new interruptions.

Post-read action: treat human attention as a scarce governed resource, classify
automation by maturity level, let policy handle routine decisions, and require
every human interruption to be actionable, scoped, and resumable.

Related docs: [Document-Driven Transformation Master Plan](document-driven-transformation-master-plan.md), [Total-Control Policy Engine And Human Escalation Governance Plan](total-control-policy-engine-and-human-escalation-governance-plan.md), [Review-First Governance Kernel Contraction Plan](review-first-governance-kernel-contraction-plan.md), [Governance Rules Spec](governance-rules-spec.md)

## Purpose

DevFrame's long-term automation goal is not to remove humans from the system.

The goal is to protect scarce human attention.

Automation should handle repeatable context gathering, checking, routing,
evidence collection, status projection, and low-risk continuation. Humans should
be asked only when their judgment, ownership, risk acceptance, or domain
preference is actually needed.

This plan makes that idea explicit so the Global Coordinator does not become a
noisy automation layer that still asks humans to supervise every step.

The important correction is that governance must not mean constant approval.
Most users do not want to approve every step. They want the system to follow the
standard, continue when evidence is sufficient, and interrupt only for real
exceptions.

## External Lessons

| Source | Relevant lesson for DevFrame |
|---|---|
| Parasuraman, Sheridan, and Wickens, "A model for types and levels of human interaction with automation" | Automation should be considered across different function types: information acquisition, information analysis, decision/action selection, and action implementation. DevFrame should not use one global autonomy level for all work. |
| Microsoft Guidelines for Human-AI Interaction | AI systems need different behavior at initial use, regular use, when wrong, and over time. DevFrame should design escalation and feedback as part of the lifecycle, not as an afterthought. |
| Google SRE Monitoring Distributed Systems | Human interruption should be reserved for issues that require human action. DevFrame should treat unnecessary prompts like noisy pages. |
| Google SRE Eliminating Toil | Repetitive operational work expands unless deliberately reduced. DevFrame should measure and reduce repeated human decisions the way SRE reduces toil. |
| LangGraph interrupts | Human-in-the-loop is strongest when execution can pause, persist state, surface a JSON-serializable payload, and resume. DevFrame escalation should be resumable and evidence-linked. |
| OpenAI Agents SDK human-in-the-loop | Tool calls can declare approval requirements and runs can surface pending approvals. DevFrame should model approval as a governed decision, not a chat convention. |
| AutoGen human input modes | Human input can be never, always, or conditional. DevFrame needs a richer version tied to policy, evidence, and work item risk. |

## Core Decision

Human attention becomes a governance concern.

The system should answer:

```text
Can automation continue under the current policy?
If yes, continue and record why.
If not, why exactly is human attention needed?
What is the smallest decision the human must make?
What evidence and context must be shown?
How does the run resume after the decision?
Can repeated decisions become an automation proposal later?
```

If the system cannot answer those questions, it should not ask the human yet.
It should collect better context, evidence, or policy rationale first.

## Attention Governance Principles

### 1. Interruptions must be actionable

A human request must name the decision needed. Do not ask the human to inspect a
large report without stating what is being decided.

### 2. Policy should handle routine work

The default path should be automatic when:

- the work stays inside declared scope;
- required evidence is present;
- the action is reversible or low blast-radius;
- no higher-priority rule conflicts;
- no new authority, secret, or external side effect is introduced.

This is the main product promise. The user should feel that the system follows
their standards, not that it constantly asks them to re-confirm those standards.

### 3. Attention requests must be minimal

Ask for the smallest decision that unblocks the workflow:

- approve or reject a risky action;
- choose between documented options;
- supply missing intent;
- accept a policy exception;
- confirm adoption of a rule or document.

### 4. Context must travel with the interruption

The interruption must include:

- work item;
- current status;
- blocked reason;
- relevant context snapshot;
- evidence summary;
- proposed decision;
- consequence of approve and reject.

### 5. Resumption must be explicit

After the human responds, the system must record the decision and resume from a
known state. The response should not disappear into chat history.

### 6. Repeated human decisions become automation candidates

If humans repeatedly approve the same low-risk pattern with the same evidence,
the system may create an automation proposal. It must not silently promote that
proposal into a rule.

### 7. Automation must reduce toil, not hide it

The system should reduce repeated manual checking, not bury necessary judgment
inside opaque model behavior.

### 8. Defense should be lightweight

The first defense layer should be small and cheap:

- capability envelope: what the run may touch;
- evidence gate: what proof is needed before completion;
- escalation trigger: what condition requires human attention;
- rollback or recovery note: how to undo or continue if the automatic path was
  wrong.

Do not make defense depend on a heavyweight policy engine before the review
kernel proves the lifecycle.

## Automation Maturity Ladder

Use this ladder to describe capability maturity without overclaiming.

| Level | Name | Human role | Automation role | DevFrame phase-one stance |
|---|---|---|---|---|
| L0 | Manual | Human performs and judges everything | Records may exist | Not the target |
| L1 | Assisted | Human decides; system prepares context and evidence | Gathers, formats, validates | `/rdreview` starts here |
| L2 | Proposed | Human approves; system proposes action or verdict | Produces recommendation and evidence | Allowed for review/gate proposals |
| L3 | Supervised | Human handles exceptions; system continues low-risk paths | Executes within policy and stops on uncertainty | Early target after review kernel passes |
| L4 | Governed autonomous | Human sets policy; system acts and records decisions within scope | Executes, reviews, and escalates by policy | Future total-control target |
| L5 | Self-improving with governance | Human adopts or rejects rule changes; system proposes improvements | Finds repeated patterns and proposes automation | Future learning target |

The same workflow may have different levels for different function types.
For example, DevFrame may automate information acquisition at L3 while keeping
action implementation at L1.

## Function-Type Automation Map

Borrowing from human-automation research, classify automation by function:

| Function type | DevFrame examples | Early target |
|---|---|---|
| Information acquisition | Find docs, collect status, retrieve evidence, build context snapshot | L2-L3 |
| Information analysis | Detect missing context, compare evidence, identify repeated decisions | L1-L2 |
| Decision/action selection | Propose gate result, escalation, adoption, rollback | L1-L2 |
| Action implementation | Write files, change rules, promote docs, release, mutate memory | L0-L1 until evidence gates mature |

This prevents a common failure: because context gathering is safe to automate,
the system accidentally treats rule promotion or writeback as equally safe.

The target direction is L3 for routine, reversible, evidence-backed work:
automation continues by standard, while humans handle exceptions.

## Attention Objects In Phase One

Do not add a new top-level object for attention in phase one.

Represent attention through existing objects:

| Need | Phase-one representation |
|---|---|
| Human approval needed | `Decision(kind=gate)` with pending or blocked outcome payload |
| Human question payload | `Artifact(kind=attention_request)` only if a durable payload is needed |
| Human response | `Decision` rationale and evidence references |
| Policy-handled continuation | `Decision` rationale or work item state citing the policy and evidence used |
| Repeated decision pattern | `Artifact(kind=automation_proposal)` or later `DocumentRevision` |
| UI display | Projection fields derived from work item, evidence, and decision state |

Future versions may add `Decision(kind=escalate)`, but phase one should avoid
expanding the decision kind set until the review kernel is proven.

## Projection Requirements

RDCode, dashboard, or any shell should show:

- when automation continued under policy without asking the human;
- why human attention is needed;
- what exact decision is requested;
- what evidence is available;
- what happens on approve;
- what happens on reject;
- whether the workflow can resume automatically afterward.

They must not:

- turn a notification into authority;
- mark work completed because the user clicked through a UI;
- ask broad open-ended questions when a specific decision is required;
- bury missing evidence behind a friendly status.

## Attention Metrics

DevFrame should eventually track:

| Metric | Why it matters |
|---|---|
| Human interruptions per work item | Measures attention cost |
| Avoidable interruption rate | Shows where automation or context should improve |
| Policy-handled continuation rate | Shows whether automation is actually saving attention |
| Time to human decision | Shows whether prompts are clear and actionable |
| Repeated approval pattern count | Finds candidates for supervised automation |
| Rejected automation proposal count | Shows where automation is overreaching |
| Insufficient-evidence rate | Shows whether evidence collection is improving |
| Rollback after automation | Shows where autonomy created harm or rework |

These are future metrics, but the review-first kernel should already preserve
the data needed to compute them later.

## Impact On Current Roadmap

The current `/rdreview` contraction remains correct.

It should now also prove:

- a work item can enter a human-needed state without being completed;
- routine low-risk work can continue under policy without human approval;
- the projection can show a precise human decision request;
- a human response is recorded as a decision, not chat-only feedback;
- a repeated human decision can be stored as a future automation proposal without
  becoming an adopted rule.

Do not expand implementation yet. Add these requirements to the contract and
fixture thinking first.

## Stop Lines

Stop and revise the plan if:

- automation asks the human to read vague output instead of making a specific
  decision request;
- automation asks for approval when policy and evidence already allow
  continuation;
- human responses are recorded only in chat;
- repeated approvals silently become rules;
- projection turns a click into final authority;
- total-control work expands before attention requests are evidence-backed and
  resumable.

## Summary

Human attention is not a fallback mechanism. It is a governed resource.

The Global Coordinator should eventually become an attention router: it should
continue automatically where policy and evidence allow, stop where judgment is
needed, and learn from repeated human decisions only through documented,
evidence-backed adoption.
