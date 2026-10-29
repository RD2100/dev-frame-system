# Failure Response Runbook

| Failure | Response | Exit | Retry |
|---------|----------|------|-------|
| blocked | Stop, record | 20 | No |
| rejected | Stop, record | 20 | No |
| needs_more_evidence | Assess scope | 20 | Yes if in scope |
| review_unverified | Stop, record | 20 | Yes |
| human_required | Stop, wait | 10 | No |
| CDP 403 | Stop, human_required | 30 | Yes after restart |
| GPT capture fail | Stop, review_unverified | 20 | Yes |
| Test failure | Stop, fix | 1 | Yes after fix |
| Write-boundary violation | Stop, human_required | 10 | No |
