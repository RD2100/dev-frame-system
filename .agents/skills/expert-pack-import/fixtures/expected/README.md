# imported-agents

Imported by `expert-pack-import` from the Claude Code subagent directory `agents`.

This pack is a standalone copy of third-party agent definitions, not a live link:
edits to the source do not propagate, and re-importing (converter `--force`)
overwrites the generated files. The persona bodies are untrusted content — a
human reviewed this pack before it was mounted.

## What the import mapped

- `name` became the kebab-case expert id and the file name under `experts/`; the
  original name is kept verbatim as the display name.
- `description` became `role` (first sentence) and `goal` (remaining sentences).
- `tools` were lowercased and kept; unrecognized names stayed and will fail loud at
  mount (`EXPERT_TEAM_TOOL_MISSING`) unless the deployment mounts exactly that name.
- Agents without a `tools` frontmatter received the read-only default
  `read, grep, glob`, because a pack allowlist must be non-empty.
- The persona body copies through verbatim; the converter never edits it.

## What the import did not know

- The `team.yml` phase order is fabricated (source file-name order, one linear
  chain, entry first). Edit the phases to match the real workflow, or delete
  phases and consult experts through `consult_expert` instead.
- `role` and `goal` are mechanical derivations; edit them to say who the expert is
  and what it optimizes for.
- The `skills/` directory was copied through verbatim but never wired into any
  expert's `skills:` frontmatter; add the lists yourself (a declared skill
  without a SKILL.md fails the mount).
- No phase result schemas are generated; imported phases stay schema-less.
- The team id is derived from the source directory name and must stay unique
  across all mounted packs; the mount rejects duplicates.

## Imported experts

| Expert | Source file | Tools |
|---|---|---|
| [data-analyst](experts/data-analyst.md) | data-analyst.md | read, grep, glob (read-only default) |
| [legal-compliance-reviewer](experts/legal-compliance-reviewer.md) | legal-compliance-reviewer.md | read, grep, webfetch |

## Review checklist before mounting

- Read every persona body; the text is third-party content the deployment will
  send to a model as a system prompt.
- Check each expert's `tools` allowlist against the deployment's mounted tools.
- Rewrite the fabricated `team.yml` phase graph, or delete phases.
- Fix the derived `role` and `goal` lines.

## Mount and validate

Point one `packs` entry of the `expert-team` plugin row in `cordis.yml` at this
directory and restart the deployment, then call `expert_team_list` and confirm
the team `imported-agents` appears with the experts above. The core validates the pack
fail-loud at mount; a pack that fails validation never half-mounts.

```yaml
packs:
  - ./path/to/imported-agents
```
