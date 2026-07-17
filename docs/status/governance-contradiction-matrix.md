# Governance Contradiction Matrix

Lifecycle state: Historical coordination record; scheduling superseded by `HANDOFF.md`

Reader: DevFrame maintainers reconciling active planning documents before
writing the document-driven transformation master plan.

Post-read action: check any new plan or implementation proposal against this
matrix, then either follow the provisional resolution or record a deliberate
exception.

Related docs: [Unified Object Model Decision Record](unified-object-model-decision-record.md), [Governance Spine And Document Coordination](governance-spine-and-document-coordination.md), [Governance Rules Spec](governance-rules-spec.md)

## Purpose

The planning documents are converging, but they still contain terms and
directions that can be read in more than one way. This matrix makes the
conflicts explicit so the final master plan does not hide unresolved choices
behind smooth prose.

## Matrix

| Conflict | Why it matters | Provisional resolution | Follow-up |
|---|---|---|---|
| Context packet as runtime input vs evidence object | Context explains both what the model saw and whether a run is reproducible | Store context as immutable `Artifact(kind=context_snapshot)` and reference it from `Run.input_context_ref` | Prove in `/rdreview` slice |
| Context packet as top-level object vs artifact kind | Making it top-level expands the model before it has independent authority | Do not make it top-level in phase one | Reopen only if context snapshots gain independent lifecycle and policy ownership |
| Goal, task spec, review request, and change unit as separate objects | Too many work nouns make status and evidence hard to join | Use `WorkItem` as the common object | Keep task-spec revisions as payloads or document revisions |
| Run success vs work completion | A tool can exit successfully while the work remains unreviewed or unsupported | `Run.success` is only an observation; completion requires a `Decision` with evidence | Encode in rules spec and later schema/tests |
| Report claims vs evidence | Pretty reports can overclaim actual proof | Evidence must cite observed results, artifacts, or commands; reports can summarize but not replace evidence | Gate `/rdreview` on evidence references |
| Review, verdict, gate, policy decision, and promotion as separate top-level objects | Separate objects create drift and duplicate authority | Use `Decision` as a typed envelope with kind-specific payload | Limit phase-one kinds to `review`, `gate`, and `adopt` |
| Decision as typed envelope vs all-purpose table | A generic decision object can become meaningless | Every decision kind must define required payload and valid targets | Add kinds only through decision records |
| Document authority from newest file vs explicit adoption | Newer files are not always more correct | Authority comes from `DocumentRevision` plus `Decision(kind=adopt)` or a future supersede/archive decision | Add lifecycle labels and authority projection later |
| Documentation governance vs runtime governance | Docs define intent; runtime proves what happened | Keep docs and runtime linked but separate; neither silently overrides the other | Master plan should define promotion path from status docs to stable runtime docs |
| Evaluation score vs acceptance verdict | A high score can mask an unsafe or unproven run | Evaluation cannot override a blocked or insufficient-evidence gate | Make scorecards advisory until adopted by decision |
| Learning proposal vs promoted rule | Improvement suggestions can destabilize defaults | Learning produces proposals; adoption requires decision, evidence, regression case, and rollback path | Keep promotion disabled in first slice |
| Policy confidence vs authority | A model can be confident without being allowed to act | Authority is decided by policy and principal scope, not confidence | Human escalation rules must be explicit |
| Total-control autonomy vs human ownership | Coordinator convenience can become silent delegation of owner power | Coordinator may propose or prepare high-power changes; human or independent policy must authorize them | Start with blocked self-promotion tests later |
| Principal vs agent | Treating agents as special creates fragmented permission logic | Use `Principal`; model agents as `Principal.kind=agent` | Update later runtime schemas only after object model proof |
| RDCode as source of truth vs projection shell | If the UI owns facts, backend governance becomes bypassable | RDCode displays and requests; DevFrame backend owns facts, evidence, and decisions | Keep writeback behind decision requests |
| Conversation transcript vs durable fact | Chat history is useful but unstable as governance data | Treat transcripts as artifacts or source material unless adopted into structured facts | Do not drive final status from transcript alone |
| Event sourcing everywhere vs fact objects | Event-only systems become hard to query and govern | Use fact objects as the public model; add events where replay or audit earns the cost | Avoid platform-wide event sourcing in phase one |
| Long-term memory vs source-backed project knowledge | Memory can preserve stale or unverifiable claims | Memory updates require source, scope, freshness, and conflict checks | Defer broad memory learning until review slice works |
| Model routing vs governance correctness | Better models do not remove the need for evidence | Model routing is advisory and profile-driven; gates still decide acceptance | Keep fair comparison tied to context snapshots |
| Recon receipt vs platform architecture | A receipt proves scoped research, not whole-system truth | Receipts remain local authority; cross-plan decisions live in coordination docs | Inventory should keep receipts classified |

## Severity Guide

Use this guide when deciding which contradiction to resolve first:

| Severity | Meaning |
|---|---|
| `P0` | Can create false completion, unsafe authority, or unverifiable public claims |
| `P1` | Can fragment the model or make future implementation hard to maintain |
| `P2` | Can confuse readers or reviewers but is unlikely to cause unsafe behavior alone |

Current P0 contradictions:

- run success vs work completion;
- report claims vs evidence;
- evaluation score vs acceptance verdict;
- policy confidence vs authority;
- RDCode as source of truth vs projection shell.

## Use In Reviews

When reviewing a new status document, ask:

1. Does it introduce a top-level object not accepted by the object model?
2. Does it let a run, report, score, or UI state stand in for a decision?
3. Does it give authority to a coordinator, agent, model, or client without a
   policy boundary?
4. Does it treat a recon receipt or old handoff as current platform truth?
5. Does it make a document authoritative without an adoption decision?

If the answer to any question is yes, either revise the document or add an
explicit exception decision.
