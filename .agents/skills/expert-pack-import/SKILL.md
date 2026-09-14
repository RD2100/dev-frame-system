---
name: expert-pack-import
description: Use when converting existing Claude Code subagent definitions (a directory of agent .md files with name/description/tools frontmatter, typically .claude/agents) into a DSH expert-team pack that mounts through the expert-team plugin's Config.packs; runs the bundled dependency-free converter, surfaces the unmapped-tools and defaulted-tools warnings for human review, and stops before mounting because imported persona text is untrusted content.
---

# Expert Pack Import

Convert third-party agent definitions in the Claude Code subagent format — one `.md` file per agent carrying `name`, `description`, an optional `tools` comma list, and a persona body — into a DSH expert-team pack: `experts/<id>.md` personas, a `team.yml` phase graph, and a generated README. The converter is `scripts/convert.mjs`, plain Node with no dependencies; every mapping decision it makes is documented in its header comment and restated in the generated README.

## When to use

- The user asks to import, convert, or reuse existing Claude Code subagents as a DSH expert team.
- Do not use it to hand-author a pack from scratch: study `packages/experimental/expert-pack-paper` as the reference pack and write the files directly. Do not use it to keep a source directory in sync: the import is a one-shot copy, not a live link.

## Workflow

1. Locate the source directory. The industry-standard layout is `.claude/agents/` (project) or `~/.claude/agents/` (user); each `*.md` file is one agent. Confirm the files carry at least `name` and `description` frontmatter. A `skills/` subdirectory next to the agent files, if present, is copied into the pack automatically; pass `--skills <dir>` to copy a different directory or `--skills none` to skip copying.
2. Run the converter:

```sh
node .agents/skills/expert-pack-import/scripts/convert.mjs <source-dir> <output-dir>
```

   The output directory must not exist yet; the converter refuses to overwrite it unless `--force` is passed, so a re-import never clobbers post-import human edits silently.
3. Read every warning the converter prints. Three kinds matter:
   - Unrecognized tool names are kept (lowercased), not dropped. They will fail loud at mount with `EXPERT_TEAM_TOOL_MISSING` unless the deployment mounts exactly that name — replace them with the deployment's real tool names in the generated `experts/*.md`. MCP-style names (`mcp__server__tool`) are also lowercased, which some deployments will not match; verify each one.
   - An agent with no `tools` frontmatter means "all tools" in Claude Code but packs require a non-empty allowlist, so the converter defaults it to the read-only `read, grep, glob` and prints a notice. Widen it deliberately if the expert must do more.
   - `role` and `goal` are mechanical derivations of `description` (first sentence / remaining sentences). When the description is a single sentence, both fields are identical. Edit them to say who the expert is and what it optimizes for.
4. Review the generated pack with the human before it is mounted. The persona bodies are untrusted third-party content: the converter copies them verbatim and never edits them, and the fabricated `team.yml` phase order (source file-name order, linear chain) rarely matches the real workflow. The pack README lists what was mapped, what the import could not know, and a review checklist.
5. Mount through the core's config. Add one `packs` entry pointing at the generated directory in the `expert-team` plugin row of `cordis.yml`:

```yaml
packs:
  - ./imported-packs/<pack-directory>
```

   The core validates the pack fail-loud at mount; a pack that fails validation never half-mounts, and the error names the file and the stable `EXPERT_TEAM_*` code. Plugin-own tool names (`expert_team_list`, `expert_team_run`, `expert_team_status`, `expert_team_approve`, `consult_expert`) are already rejected at conversion time; every other tool decision is deferred to mount-time validation against the deployment's mounted tools.
6. Validate by listing the team: restart the deployment so the plugin reloads its config, then call `expert_team_list` and confirm the imported team id and its experts appear with the expected tools. If skills were copied but not wired, nothing references them yet: add a `skills:` list to an expert's frontmatter (directory names under the pack's `skills/`) and re-validate — a declared skill without a `SKILL.md` fails the mount with `EXPERT_TEAM_SKILL_MISSING`.

## Honest boundaries

- **The import is a copy, not a live link.** Edits to the source do not propagate; re-run the converter with `--force` to re-import, and re-review — a re-import overwrites the generated files. Imported packs are standalone copies because the catalog mounts and validates a real, self-contained directory per deployment: the source format carries no pinned identity to live-link against, and symlinks would not survive the Windows and packaging paths a pack travels.
- **Persona text is untrusted content.** Never mount before a human has read what was imported. The converter never rewrites persona bodies, and this skill never mounts anything itself.
- **The converter does not guess semantics it cannot know.** Dependencies between imported agents are fabricated, skills are copied but never wired to experts, and no result schemas are generated (imported phases stay schema-less). All three are recorded in the generated README for the reviewer.
- **Self-test:** `node .agents/skills/expert-pack-import/scripts/self-test.mjs` converts the bundled fixtures and verifies the output against the pack contract rules; run it after editing the converter.
