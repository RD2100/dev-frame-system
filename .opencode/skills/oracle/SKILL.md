# Oracle — GPT Review Evidence Packager

> **Bundler first.** Oracle packages a prompt together with a tight, selected file set into a single self-contained review pack for GPT review.
> All review output is **advisory only** and must be verified against the actual codebase.

## Principles (adapted from Oracle @ aniketpanjwani/skills)

1. **Minimum file set** — select only what GPT needs to answer the review question. Never bundle the entire repo.
2. **Safety preflight** — exclude secrets, `.env`, keys, caches, dependencies, build artifacts, dotfiles, `node_modules`, `.git`.
3. **Token budget** — target well under 196k input tokens. Use manifest and missing-files reports so GPT knows what wasn't included.
4. **Self-contained prompt** — every evidence pack ships with a `GPT_REVIEW_PROMPT.md` that explains the project context, the review question, and the exact checks GPT must perform.
5. **Advisory only** — no Oracle output should be treated as an automatic pass. A human (or governance gate) must decide.

## Default Ignore Rules

Always exclude:
- `node_modules/`, `__pycache__/`, `.git/`, `dist/`, `build/`
- `.env`, `.env.*`, `*.key`, `*.pem`, `credentials*`, `secrets*`
- Dotfiles (unless explicitly opted in)
- Cache directories, logs, temporary files
- Binary files and large assets (> 1 MB)
- `.zip` and `.tar.*` archives
- Symlinks (never follow)

## Golden Path

1. Select the minimum file set that still contains the truth.
2. Generate `PACK_MANIFEST.md` listing every included file and its purpose.
3. Generate `MISSING_FILES.md` for any expected file not found.
4. Generate `EVIDENCE_CONFLICTS.md` with lightweight consistency checks (never fix — just flag).
5. Generate `GPT_REVIEW_PROMPT.md` with the exact review question and gate-by-gate checks.
6. Bundle into a flat or lightly-nested directory.
7. Zip the directory only (not the whole project).
8. The zip is the upload artifact for GPT review.

## Output Structure

```
_reports/<task>-gpt-review-evidence-pack/
  README.md                  # What this pack is and what GPT should check
  PACK_MANIFEST.md           # Every file, its source, and its purpose
  MISSING_FILES.md           # Expected-but-not-found files
  EVIDENCE_CONFLICTS.md      # Lightweight inconsistency flags (never fix)
  GPT_REVIEW_PROMPT.md       # Self-contained prompt for GPT

  task/                      # Task specification and baseline
  reports/                   # Copied evidence reports
  diff/                      # Read-only git evidence
  source/                    # Copied source files under review
  review_pack/               # Agent-generated review pack
```

## Safety Rules

- **Never modify source logic.**
- **Never re-execute the task under review.**
- **Never change task conclusions.**
- **Never delete, move, or rename original files.**
- **Never fabricate missing evidence — record it as MISSING.**
- **Never resolve conflicts — flag them as CONFLICT.**
- **The pack is GPT advisory input, not an automatic passing grade.**
