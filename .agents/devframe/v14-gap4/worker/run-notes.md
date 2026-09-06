# v14-gap4 worker run notes (worktree codex/v14-gap4-w1 @ 1a22444f6f)

## Scope honored
- Write scope: packages/test-support/llm-replay/src/index.ts, packages/test-support/llm-replay/tests/llm-replay.spec.ts, .agents/devframe/v14-gap4/worker/** only.
- No agents created; no push/PR/rebase/merge; no file deletions; forbidden zones untouched (snapshots/**, vendor/**, packages/experimental/**, packages/subagent/**, packages/test-support/session-snapshot/**, .agents/devframe/v14/**, other worktrees, main tree).

## CHANGE 1 (src/index.ts, inferStartedSubagents)
- Regex: `/started subagent ([^\s"'<>]+)/g` -> `/started (?:continuable )?subagent(?:; SessionID)? ([^\s"'<>]+)/g`.
- Note: the wave brief transcribed the capture class as `[^s"'<>]`; the actual file bytes are `[^\s"'<>]` (backslash-s, whitespace). Ground truth via codepoint dump (92=backslash, 115=s). The fix preserves the existing class semantics exactly and only widens the prefix.
- Comment above the function now names both accepted start texts, their source (packages/subagent/tool-subagent continuable start render), and why the job wording never binds (a job id is not a session id).
- De-duplication guard and first-unbound-slot ordering untouched.

## CHANGE 2 (tests/llm-replay.spec.ts, describe installLlmReplay (per-session keying))
- R1 new: "learns a continuable child session id from its current started-subagent tool result" — current wording "started continuable subagent; SessionID live-child-before-call" (twice, exercising dedup) binds slot 2; scripted `{{session:2}}` materializes to the live id.
- R2 kept: "learns a background child id from its started-subagent tool result" (legacy wording) stays green unmodified under the new pattern.
- R3 new: "does not learn a session id from a background subagent job start text" — "started background subagent job subagent-1" does not bind; `{{session:2}}` still fails loud with /used before.*bound/.
- No existing test weakened, skipped, or deleted.

## Gates
- G0 pnpm install --prefer-offline: exit 0 (20.6s). Log: logs/g0-pnpm-install.log
- G1 pnpm exec vitest run packages/test-support/llm-replay: exit 0, 105 passed / 105. Logs: logs/g1-vitest-llm-replay.log, logs/g1-vitest-llm-replay-verbose.log
- G2 tsbuildinfo cleanup (8 removed) + pnpm run build: exit 0. Log: logs/g2-build.log
- G3 git diff --check: exit 0; both product files end with exactly one trailing newline. Log: logs/g3-diffcheck.log
- G4 pnpm run test:docs: exit 0, 15/15 doc-quick gates. Log: logs/g4-test-docs.log
- G5 pnpm run test:snapshot: see logs/g5-test-snapshot.log
