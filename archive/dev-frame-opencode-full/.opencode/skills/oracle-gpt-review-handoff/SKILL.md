# Oracle GPT Review Handoff

**Framework Freeze v1 — 正式能力**

CDP-based Chrome automation for submitting GPT review evidence packs.
See `docs/AUTONOMOUS_PROGRESS_POLICY.md` for autonomous progression rules.

## Single Submission
```bash
python tools/oracle_gpt_full_review_flow.py --task-id s2
```

## GPT Reply Monitor
```bash
python tools/oracle_gpt_reply_monitor.py --task-id s2
```

## Multi-Round Review Loop
```bash
python tools/oracle_gpt_review_loop.py --task-id s2 --max-rounds 3
python tools/oracle_gpt_review_loop.py --task-id s2 --max-rounds 3 --dry-run true
```

### Loop Configuration
- `max_rounds`: 3 (default)
- `stop_on_human_required`: true — immediately stops loop if GPT returns human_required
- `stop_on_scope_violation`: true — stops if scope violation detected
- `stop_on_repeated_block_reason`: 2 — stops if same block reason appears twice
- `auto_submit`: true — auto-submits via CDP (still requires SEND confirmation)
- `auto_monitor`: true — auto-monitors GPT reply completion
- `auto_execute_code`: false — NEVER auto-executes S3 or code changes

### allow_next_stage Gate
Only true when ALL conditions met:
- GPT overall_judgment: accepted
- GPT S3 allowed: yes
- new_reply_verified: true
- completion_status: complete

Even when allow_next_stage=true, the harness does NOT execute S3 automatically.

### Loop Stop Rules
1. accepted + S3 allowed → stop (allow_next_stage=true)
2. human_required → stop immediately
3. unknown decision → stop
4. max_rounds reached → stop
5. repeated block reason → stop

### Safety
- Never executes S3
- Never modifies S2 core logic
- Never modifies original evidence pack
- Never fabricates baseline or test results
- Never wraps blocked/human_required as accepted
