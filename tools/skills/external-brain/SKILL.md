---
name: external-brain
description: External-brain review and coordination workflow with trustworthy review-bundle preparation. Use when user says "@external-brain", "external brain", "web AI review", "GPT review", "Claude review", "prepare review prompt", "context ZIP", "review bundle", "send to web GPT", "外置大脑", "网页版GPT审查", or when DevFrame needs to use a browser/web AI as an external reviewer, direction coordinator, or critique loop without treating its answer as project authority.
---

# external-brain - Web AI Review Bundle Workflow

Role: methodology skill, not a runtime executor. Use it to prepare, constrain,
submit, and ingest web AI review loops.

## Core Rule

The web AI can critique, coordinate, and suggest. It does not become project
authority.

A ZIP is not trusted because it exists. A web AI review bundle is trusted only
when it has:

- a manifest with file hashes;
- a context ledger naming selected and missing context;
- a redaction report;
- a review prompt that tells the web AI to audit context before answering;
- validator output proving ZIP/manifest consistency.

If these are missing, treat the package as `review_unverified` or
`context_incomplete`, not as ready.

## Runtime Shape

Use the prepare-only runtime path before external submission:

```text
explicit source list
  -> devframe web-ai prepare-review-bundle
  -> ZIP + PACK_MANIFEST.json + CONTEXT_LEDGER.md + REVIEW_PROMPT.md
  -> devframe web-ai validate-review-bundle
  -> optional manual or guarded web AI submission
  -> conservative feedback ingestion
```

Do not auto-upload. Submission is a separate human-visible action.

When submission or response extraction is automated, use only the project
CDP path described in `bind-chrome` and `web-ai-adapter-contract.md`. Preparing
or validating a bundle is local/offline work. Sending it to ChatGPT, pasting a
prompt, checking that it appeared in the page, or reading the reviewer response
is browser automation and must be driven through Chrome CDP. Do not use the
Chrome extension bridge, standalone browser sessions, screenshots, or
keyboard/mouse simulation as normal runtime transport.

## Workflow

1. Define the review question.
   State what the web AI must decide: GO/NO-GO, missing context,
   implementation readiness, risk review, or narrowing.

2. Select explicit sources.
   Prefer current active docs, exact code paths, schemas, tests, reviewer
   indexes, evidence manifests, diffs, and known gaps. Do not rely on "whole
   repo" intuition.

3. Declare required roles.
   Examples: `map`, `plan`, `schema`, `test`, `diff`, `evidence`, `rules`,
   `known-gaps`. If a required role is missing, the bundle must be
   `context_incomplete`.

4. Prepare the bundle.

   ```powershell
   devframe web-ai prepare-review-bundle `
     --project-root <repo> `
     --runtime-dir <runtime> `
     --question "<exact review question>" `
     --source map=docs/README.md `
     --source plan=docs/status/document-driven-transformation-master-plan.md `
     --required-role map `
     --required-role plan
   ```

5. Validate the bundle before sharing.

   ```powershell
   devframe web-ai validate-review-bundle --zip <bundle.zip>
   ```

   Only `ready_for_review` is suitable for normal review. `context_incomplete`
   can be shared only if the prompt asks the web AI to identify missing context.
   `blocked` must not be submitted.

6. Instruct the web AI to audit first.
   The prompt must require the reviewer to list inspected files, authority
   levels, missing context, and cited bundle paths before giving conclusions.

7. Ingest feedback conservatively.
   Fold accepted feedback into documents, evidence, decisions, or bounded tasks.
   Keep rejected and deferred feedback explicit.

8. Verify repo-facing results.
   Check edited paths, links, generated manifests, tests, and public snapshot
   verification relevant to the resulting repo change.

## Reviewer Prompt Contract

The web AI must answer these before the main review:

- Which bundle files did you inspect?
- Which files are authoritative for this decision?
- What important context is missing, stale, or only summarized?
- Is the context sufficient: yes/no?
- Which claims cite which bundle paths?
- Recommendation: `GO`, `NO-GO`, or `NEEDS_MORE_CONTEXT`.

If the web AI skips the context audit, treat the review as weak feedback.

## Default Outputs

For a prepared review bundle:

- bundle status: `ready_for_review`, `context_incomplete`, or `blocked`;
- ZIP path;
- manifest path;
- required roles and missing roles;
- blocking issues;
- validation result.

For feedback ingestion:

- accepted changes;
- rejected or deferred suggestions;
- edited repo paths;
- verification run;
- remaining human decision, if any.

## Hard Stops

- Do not expose secrets, raw private transcripts, API keys, credentials, browser
  profiles, local agent state, or unpublished sensitive data.
- Do not submit a `blocked` bundle.
- Do not present web AI output as a final project decision.
- Do not let external feedback override local evidence, tests, or governance
  rules.
- Do not claim the web AI had complete context unless the manifest, ledger, and
  required-role gate prove it.
- Do not claim a browser-hosted review was submitted or read unless the evidence
  came from the CDP-controlled page.
