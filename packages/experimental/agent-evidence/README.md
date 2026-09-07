---
description: "Cordis service holding the append-only evidence ledger for agent work: task/Goal binding receipts, submission receipts, and verification snapshots tied to the shared work identities."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-agent-evidence

English | [中文](README.zh.md)

## Summary

`dsh-experimental-agent-evidence` mounts `ctx.agentEvidence`, the Cordis service that records and serves the append-only provenance trail of agent work over the `agent_evidence` storage domain: task/Goal binding receipts (the DevFrame goal-result binding tuple for one task), submission receipts (commit object name, changed paths, and the digest of the source inputs the work started from), and verification snapshots (command, exit code, and artifact paths — a non-zero exit code is recorded as-is). The ledger stores provenance only: acceptance stays with the Goal binding and task states, so no separate acceptance database exists here. Receipts are restored verbatim on start. The package also exports the honest DevFrame evidence producer (`AgentEvidenceJournal`): it executes the stored approved required checks through a real subprocess face and appends the real results as `devframe/verification` records, and records reviewer decisions as `devframe/review` records — both through the schema-checked DevFrame Session journal.

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the implementation](#understand-the-implementation)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

Mount the service beside the storage stack; it hard-injects `ctx.storageDomain` and fails at activation when the storage backend is absent.

```yaml
- name: '@deepseek-ai/dsh-storage'
- name: '@deepseek-ai/dsh-storage-json'
- name: '@deepseek-ai/dsh-storage-domain'
- name: '@deepseek-ai/dsh-experimental-agent-evidence'
```

### Record and read the evidence trail

Every recording call validates through the durable schema and returns the frozen receipt; queries serve append-only trails in recorded order.

```ts
import type {
  AgentEvidenceLedger, SubmissionRequest, TaskGoalBindingRequest, VerificationRequest,
} from '@deepseek-ai/dsh-experimental-agent-evidence'

async function recordEvidence(
  ctx: { agentEvidence: AgentEvidenceLedger },
  binding: TaskGoalBindingRequest,
  submission: Omit<SubmissionRequest, 'taskId'>,
  verification: Omit<VerificationRequest, 'taskId'>,
) {
  await ctx.agentEvidence.recordTaskGoalBinding(binding)
  await ctx.agentEvidence.recordSubmission({ ...submission, taskId: binding.taskId })
  await ctx.agentEvidence.recordVerification({ ...verification, taskId: binding.taskId })
  return {
    trail: ctx.agentEvidence.byTask(binding.taskId),
    bindings: ctx.agentEvidence.bindingsByGoal(binding.controllerSessionId, binding.goalId),
  }
}
```

Malformed receipts fail loud with `AGENT_EVIDENCE_INVALID_RECEIPT`; storage refusals surface as `AGENT_EVIDENCE_PERSISTENCE`.

### Record DevFrame verification and review evidence

For task output evidence, the host supplies the latest task delivery's `deliveryId` and its `deliveryResultBinding` as `binding` to both journal methods. The journal preserves the delivery reference; the DevFrame projection checks its current Goal, latest delivery, and output identity. The original Goal input remains unchanged. Omitting `deliveryId` still records whole-Goal evidence, which does not replace the task delivery evidence required for integration.

The journal producer is a plain class the host composes (no plugin mount): construct it with the Session durability callback and the reviewer role authority, then call the two record methods at the moments verification and review complete.

```ts
import { AgentEvidenceJournal } from '@deepseek-ai/dsh-experimental-agent-evidence'
import type {
  AgentEvidenceJournalOptions, ReviewEvidenceRequest, VerificationEvidenceRequest,
} from '@deepseek-ai/dsh-experimental-agent-evidence'

async function recordJournalEvidence(
  options: AgentEvidenceJournalOptions,
  verificationRequest: VerificationEvidenceRequest,
  reviewRequest: Omit<ReviewEvidenceRequest, 'session' | 'binding'>,
) {
  // The host supplies native Session flushing and reviewer role authority.
  const journal = new AgentEvidenceJournal(options)
  // Execute the approved checks resolved from the stored digest.
  const verification = await journal.recordVerification(verificationRequest)
  // Cross-authorize the reviewer Session before appending its decision.
  const review = await journal.recordReview({
    ...reviewRequest, session: verificationRequest.session, binding: verificationRequest.binding,
  })
  return { verification, review }
}
```

The producer records evidence, it does not judge completion. Store failures propagate as the existing `RequiredChecksError` codes (`REQUIRED_CHECKS_CONFIG_NOT_FOUND`, `REQUIRED_CHECKS_INVALID_CONFIG`) before any event is written; gate rejections surface as `AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED` without latching; durability failures surface as `DevFramePersistenceError` and latch the Session's journal. Every record is validated by the durable `devframe/verification`/`devframe/review` schemas before it lands.

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals — click to expand</summary>

This section explains the design decisions behind the feature and points at the code that realizes them; the observable behavior is fully covered in [Use this package](#use-this-package).

### Design decisions

- **Identity reuse, not re-declaration.** Binding receipts carry the DevFrame goal-result binding vocabulary — `ControllerSessionId`, `GoalId`, `AcceptanceHash`, `SourceFingerprint`, `WorkspaceId` — imported from the experimental DevFrame packages, so evidence resolves to the same work identity dispatch and completion already use.
- **Provenance only.** The ledger holds no acceptance verdict: a failing verification snapshot is a recorded fact, and acceptance decisions stay with the Goal binding (DevFrame) and task states (project-controller). This is why no separate acceptance database exists.
- **Schema-owned branding at the durable boundary.** Recording parses each receipt through the same zod schema the storage domain validates restores with, so brand application and validation share one definition; storage refusals surface as `AGENT_EVIDENCE_PERSISTENCE` with the original cause.
- **Append-only trails.** Re-recording a binding under a new Goal revision adds a receipt; nothing rewrites or deletes a receipt. `byTask` and `bindingsByGoal` return the full trail in recorded order.

### Source map

| File | Role |
|---|---|
| [`src/ledger.ts`](src/ledger.ts) | The `ctx.agentEvidence` service: record, query, cold restore |
| [`src/spec.ts`](src/spec.ts) | The `agent_evidence` domain spec and the zod receipt schemas |
| [`src/types.ts`](src/types.ts) | Receipt record types over the shared work identities |
| [`src/ids.ts`](src/ids.ts) | `EvidenceReceiptId` and `CommitSha` brand factories |
| [`src/errors.ts`](src/errors.ts) | `AgentEvidenceError` and its stable code union |
| [`src/check-runner.ts`](src/check-runner.ts) | The reference subprocess execution face for required checks |
| [`src/journal.ts`](src/journal.ts) | The DevFrame evidence producer over the Session journal |
| [`src/index.ts`](src/index.ts) | Package entry and default export |

### Invariant

No runtime invariant companion is published: receipts are append-only single-table rows with no cross-table derivation, the JSON backend refuses a second live handle on the same unit, and queries read the same in-process maps the writes populate, so no independent observation exists that could diverge.

</details>

-----

<a id="model-experience"></a>
## Model Experience

### Agent evidence ledger

#### What the model sees

Nothing reaches a model request. The package registers no tools and no prompt sections, and it introduces no new event types; the `AgentEvidenceJournal` producer appends DevFrame evidence records — `devframe/verification` and `devframe/review`, existing DevFrame vocabulary — to the owning controller Session log. That log is a host-side durable record: it never enters a model request, so no request field carries the package's data.

#### Token effect

Zero direct tokens on every request.

#### KV Cache effect

Independent of live requests: the package never touches a request prefix, so it cannot invalidate provider cache reuse.

<a id="known-limitations-and-deferred-work"></a>
## Known Limitations and Deferred Work

These limits define when the ledger is a poor fit or needs special operational care. They are current package constraints, not a task backlog.

- **Receipts are trusted provenance, not verified truth** — changed paths and artifact paths are recorded as the caller reports them; the ledger does not inspect the repository to confirm them.
- **The ledger does not validate task or Goal existence** — receipts reference the ids their caller supplies; referential integrity stays with the project controller and the Goal binding.
- **Trails grow unbounded** — receipts are never rewritten or pruned; long-running deployments accumulate rows in the three tables.
- **No bounded output capture** — the execution face classifies outcomes by exit code alone and captures no stdout/stderr (`outputRef` is never produced); bounded log capture and artifact persistence are deferred to the toolface slice.
- **The producer records evidence, it does not judge completion** — the two record methods write honest records; the admission conjunct (fingerprint → checks → review) belongs to the DevFrame controller.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
