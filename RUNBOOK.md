# Project Runbook

> 2026-06-04T14:52:01Z

## GPT Review Submission
1. Verify AUTHORIZED_GPT_CONVERSATION.json
2. Verify Chrome CDP port 9222
3. Verify authorized page in browser
4. Upload zip + paste prompt + send
5. Wait for reply with exact REVIEW_RUN_ID
6. Reject <100 char captures
7. Persist result files

## Failure Handling
- review_unverified: do NOT write accepted; stop
- CDP unavailable: do NOT fallback; human_required
- REVIEW_RUN_ID mismatch: stop; review_unverified
- template echo: mark review_unverified; stop
- needs_more_evidence: assess scope; stop if expansion needed

## When to Stop
- GPT rejected/blocked/human_required
- authorized page missing / URL mismatch
- new GPT conversation required
- base URL fallback required
- source edits required
- production/driver/guard/cleanup required


## Automation Hardening Rules (2026-06-04)

### 1. Script File Requirement
Multi-step phases MUST use script files (tools/_*.py), NOT inline bash -c.
Inline bash limited to <20 lines. Script files recorded in COMMAND_LOG.

### 2. Auto-Polling After GPT Submission
After CDP submission:
- Wait 60s, poll for new assistant message
- Verify exact REVIEW_RUN_ID in reply
- Filter assistant-scoped messages only (not user prompts)
- Short (<100 chars), template echo, or unrelated replies -> review_unverified
- Retry up to 3 times at 30s intervals

### 3. Auto-Chain on Accepted Review
After persisting GPT_REVIEW_DECISION.md + POST_REVIEW_ROUTE.json:
- If POST_REVIEW_ROUTE authorizes next phase -> auto-execute
- If POST_REVIEW_ROUTE has review_submitted=true and authorized=true -> proceed
- If any blocked flag is true -> do NOT chain (stop)
- Auto-chain only within current goal scope

### 4. Standard Pipeline Flow
authorize -> execute -> submit -> poll (auto) -> persist -> verify route -> chain/close
