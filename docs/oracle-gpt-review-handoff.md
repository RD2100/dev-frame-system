# Oracle GPT Review Handoff

Chrome CDP-based GPT review submission and monitoring system.

## Architecture

```
Chrome CDP (port 9222) ← Playwright connect_over_cdp
         ↓
ChatGPT session (fixed URL, no sidebar search)
         ↓
Full Review Flow: paste → upload → confirm → submit → monitor → parse
         ↓
Multi-Round Loop: blocked → reconcile → resubmit → re-evaluate
```

## Scripts

| Script | Purpose |
|--------|---------|
| `oracle_chatgpt_cdp_handoff.py` | Open ChatGPT, paste prompt, manual handoff |
| `oracle_gpt_reply_monitor.py` | Capture and parse GPT reply from existing session |
| `oracle_gpt_full_review_flow.py` | Complete submit→monitor→parse pipeline |
| `oracle_gpt_review_loop_once.py` | One round: reconcile→submit→parse |
| `oracle_gpt_review_loop.py` | Multi-round loop harness |
| `self_check_report.py` | Validate final-report.md against S1 rule |

## Multi-Round Review Loop

### Configuration
`_reports/gpt-review-loop/<task>/LOOP_CONFIG.yaml`

### State
`_reports/gpt-review-loop/<task>/LOOP_STATE.json`

### Rounds
`_reports/gpt-review-loop/<task>/round-N/`

### Stop Rules
1. GPT accepted + S3 allowed → stop
2. GPT human_required → stop
3. Max rounds reached → stop
4. Unknown decision → stop
5. Repeated block reason → stop

### allow_next_stage Gate
Only true when GPT explicitly accepts AND S3 is allowed.
Even when true, S3 is NOT auto-executed.
