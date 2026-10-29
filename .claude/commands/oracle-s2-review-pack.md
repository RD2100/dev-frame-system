# Oracle S2 Review Pack Command (Claude Code)

## Purpose

Collect S2 execution evidence into a self-contained GPT-reviewable evidence pack.

## Invocation

Run the packaging script:

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
2. Copies source files from `tools/`.
3. Runs read-only git commands and saves output.
4. Generates the full evidence pack structure.
5. Zips into `s2-gpt-review-evidence-pack.zip`.

## Output

- Directory: `_reports/s2-gpt-review-evidence-pack/`
- Zip: `s2-gpt-review-evidence-pack.zip`

## After Running

Upload `s2-gpt-review-evidence-pack.zip` to GPT for review.
Do NOT enter S3 until GPT accepts the evidence pack.
