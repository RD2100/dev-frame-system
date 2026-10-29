# Oracle GPT Review Handoff (Claude Code)

CDP-based Chrome automation for submitting GPT review evidence packs.

## Commands
- `oracle-review-loop` — multi-round loop
- `oracle-review-loop-dry-run` — harness test
- Full flow: `python tools/oracle_gpt_full_review_flow.py --task-id s2`
- Monitor: `python tools/oracle_gpt_reply_monitor.py --task-id s2`
- Loop once: `python tools/oracle_gpt_review_loop_once.py --task-id s2 --round 1`

## Multi-Round Review Loop
See `.opencode/skills/oracle-gpt-review-handoff/SKILL.md` for full documentation.

### Key Rules
- Never auto-execute S3
- Never modify S2 core logic
- Never fabricate evidence
- Stop on human_required
- allow_next_stage requires explicit GPT acceptance
