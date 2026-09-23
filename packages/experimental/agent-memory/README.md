---
description: "Persistent episodic, semantic, and procedural memory for DSH agents with scope isolation, provenance, lifecycle transitions, bounded context assembly, forgetting, conflict handling, and retrieval traces."
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-agent-memory

English | [中文](README.zh.md)

## Summary

`dsh-experimental-agent-memory` lets an agent carry selected experience between tasks. It stores episodes, sourced semantic facts, procedure candidates, and retrieval traces in the existing DSH storage-domain layer. Retrieval filters by explicit scope, ranks current active records, and assembles only the records that fit the configured context budget. A missing storage backend leaves the plugin mounted but reports `MEMORY_UNAVAILABLE`, so the task can continue without long-term memory.

## Table of Contents

- [Use this package](#use-this-package)
- [Memory lifecycle](#memory-lifecycle)
- [Understand the implementation](#understand-the-implementation)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

Mount the service in a composition that already provides the storage stack. The service also loads when storage is absent and then degrades to explicit failures.

```yaml
- name: '@deepseek-ai/dsh-storage'
- name: '@deepseek-ai/dsh-storage-json'
- name: '@deepseek-ai/dsh-storage-domain'
- name: '@deepseek-ai/dsh-experimental-agent-memory'
  config:
    workspaceId: dsh
    contextBudgetBytes: 12000
    autoRetrieve: true
```

The service is available as `ctx.agentMemory`. The main API is `retrieveContext`, `recordEpisode`, `upsertFact`, `registerProcedure`, `forget`, `inspectTrace`, and `consolidate`.

```ts
const context = await ctx.agentMemory.retrieveContext({
  query: 'database migration',
  scope: { workspaceId: 'dsh', projectId: 'harness' },
  budgetBytes: 4000,
})
```

The model-facing tools are `memory_retrieve`, `memory_record_episode`, `memory_upsert_fact`, and `memory_forget`. Memory text is injected as data with a trace id; it never grants instructions, permissions, or tools.

<a id="memory-lifecycle"></a>
## Memory lifecycle

Semantic facts carry provenance and authority. A stronger source supersedes weaker active facts for the same scoped subject and predicate. Equal-authority disagreement marks all competing facts as `conflicted`; retrieval excludes conflicted, superseded, expired, archived, and deleted rows. `memory_forget` permanently removes one row. Procedure registration defaults to `candidate`, and `consolidate` only proposes candidates from repeated episodes.

Every retrieval writes a trace containing selected ids, scores, injected ids, and the originating query. Scope comparison permits a global or project record to be reused only when every supplied scope component agrees; a different workspace is rejected at the service boundary.

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>Implementation internals</summary>

The package declares one `agent_memory` storage domain with four per-record tables: `episodes`, `facts`, `procedures`, and `traces`. The service mirrors validated rows in maps for synchronous ranking and writes every mutation through the domain table. Its `agent/pre-step` listener asks the service for context once per admitted request and appends a sourced user message, preserving DSH's model-visible-means-logged rule.

The storage open is best effort. A missing facility or failed domain open is recorded as an unavailable state; tool calls return a stable error and the pre-step listener leaves the ordinary messages untouched. This keeps a persistence outage from stopping an unrelated task.

</details>

<a id="model-experience"></a>
## Model Experience

### Bounded memory retrieval

#### What the model sees

When enabled, the model sees four memory tools and may receive one sourced, budgeted context message at the beginning of a request. Facts, episodes, and procedures are labelled as data. The message includes a trace id for diagnostics. Credentials and credential-like text are rejected at the write boundary.

#### Token effect

The tool schemas and the fixed retrieval message add a small prompt cost. Retrieved content is capped by `contextBudgetBytes`; a truncation flag is returned when candidates exceed the budget.

#### KV Cache effect

The tool schemas and static source marker are prefix-stable while the plugin configuration remains unchanged. Retrieved context is appended after the normal request history and changes only when relevant memory changes.

<a id="known-limitations-and-deferred-work"></a>
## Known Limitations and Deferred Work

- Retrieval uses deterministic lexical matching. Embeddings and vector indexes are deferred until measured recall needs them.
- Automatic episode extraction from arbitrary model output is not enabled; callers record bounded structured episodes.
- Consolidation returns procedural candidates but does not promote them automatically.
- Scope permissions are represented by the host-supplied scope identity; an integration that needs file-level ACL checks must validate provenance before calling the service.

<a id="dev-note"></a>
### Dev Note

None.
