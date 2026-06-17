# Evidence Pack Contract

> Authority: agent-acceptance
> Consumers: dev-frame-opencode evidence pack generator, GPT reviewer
> Version: 1.0.0

---

## Minimum Evidence Pack Requirements

Every evidence pack submitted to GPT MUST include:

### 1. Manifest (PACK_MANIFEST.md or manifest.json)

Lists every file in the pack with:
- File path (relative to pack root)
- Source path (where the file came from)
- Purpose (what this file proves)
- Hash (for integrity verification)

### 2. GPT Review Prompt (GPT_REVIEW_PROMPT.md)

Must include:
- Background context
- What GPT must judge
- Required output format with structured fields
- Rules (when to return blocked vs human_required vs accepted)

### 3. Evidence Index

Lists what evidence is present AND what is missing:
- Present evidence with paths
- Missing evidence explicitly flagged (not silently omitted)
- Purpose of each expected piece of evidence

### 4. Machine-Readable State

At least one of:
- FLOW_OUTCOME.json
- DISPATCH_RESULT.json
- TaskSpec JSON

Markdown-only evidence packs are NOT sufficient for automation.

---

## Evidence Pack Manifest Format

```json
{
  "pack_name": "string",
  "created_at": "ISO8601",
  "task_id": "string",
  "files": [
    {
      "path": "relative/path/in/pack",
      "source_path": "absolute/original/path",
      "purpose": "what this file proves",
      "hash_sha256": "hex string",
      "required": true
    }
  ],
  "missing_evidence": [
    {
      "expected_file": "path",
      "reason_missing": "why it doesn't exist",
      "impact": "what gap this creates"
    }
  ],
  "integrity": {
    "pack_hash_sha256": "hash of entire pack",
    "generated_by": "script or agent name",
    "verification_command": "how to verify integrity"
  }
}
```

---

## GPT Review Prompt Requirements

The prompt MUST include structured output fields for machine parsing:

```
Overall Judgment: [accepted / partial / blocked / human_required]
allow_next_stage: [true / false]
Blocking Reasons: [list or "none"]
Missing Evidence: [list or "none"]
Scope Violation: [true / false / unknown]
Fake-Green Risk: [true / false / unknown]
Required Next Action: [concrete step]
```

Without these fields, the GPT reply cannot be reliably parsed by automation.

---

## Result Preservation

After GPT review:
1. GPT_REVIEW_RESULT.md — full reply text (preserved unchanged)
2. GPT_REVIEW_DECISION.md — parsed decision (machine-readable)
3. FULL_FLOW_REPORT.md — flow status report
4. FULL_FLOW_LOG.md — timestamped event log
5. FLOW_OUTCOME.json — machine-readable outcome

ALL of these must be preserved. None may be overwritten by subsequent rounds.

---

## Missing Evidence Policy

- Missing evidence MUST be explicitly listed in the manifest
- The GPT review prompt MUST mention missing evidence
- Missing evidence does NOT automatically mean `blocked` — GPT decides
- But silently omitting missing evidence is a P1 violation
- If critical evidence is missing, the pack should flag itself as `integrity: partial`
