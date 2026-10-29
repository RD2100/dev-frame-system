# Oracle S2 Review Pack Command

## Purpose

Collect S2 execution evidence into a self-contained GPT-reviewable evidence pack.

## Invocation

```
/oracle-s2-review-pack
```

Or run the script directly:

```
python tools/oracle_s2_review_pack.py
```

## Hard Constraints

1. Do NOT modify S2 source logic.
2. Do NOT re-execute S2.
3. Do NOT change S2 conclusions.
4. Do NOT delete, move, or rename any original file.
5. Do NOT fabricate missing evidence — record it as MISSING.
6. Do NOT resolve conflicts — flag them as CONFLICT.
7. Only copy evidence; never alter it.
8. This pack is GPT advisory input, not an automatic passing grade.

## What This Command Does

1. Reads S2 evidence from `_reports/s2-review-pack/`, `.ai/reports/`, and `.ai/runs/s2-*/`.
2. Copies source files from `tools/` (ai_guard.py, go_evidence.py, test_status_synthesis.py, test_report_consistency.py).
3. Runs read-only git commands (`status`, `diff --stat`, `diff`) and saves output.
4. Generates:
   - `task/S2_TASKSPEC.md` — S2 objective, required preservation, required evidence
   - `task/S1_BASELINE_SUMMARY.md` — S1 status and verified rules
   - `reports/` — copied evidence files
   - `diff/` — git status, diff stat, diff patch, files changed, diff summary
   - `source/` — copied source files
   - `review_pack/` — copied agent review pack files
   - `README.md` — pack overview and review questions
   - `PACK_MANIFEST.md` — every file, source, and purpose
   - `MISSING_FILES.md` — expected-but-not-found files
   - `EVIDENCE_CONFLICTS.md` — lightweight inconsistency checks
   - `GPT_REVIEW_PROMPT.md` — self-contained GPT review prompt
5. Zips the directory into `s2-gpt-review-evidence-pack.zip`.

## Output

- Directory: `_reports/s2-gpt-review-evidence-pack/`
- Zip: `s2-gpt-review-evidence-pack.zip`

## After Running

Upload `s2-gpt-review-evidence-pack.zip` to GPT for review.
Do NOT enter S3 until GPT accepts the evidence pack.
