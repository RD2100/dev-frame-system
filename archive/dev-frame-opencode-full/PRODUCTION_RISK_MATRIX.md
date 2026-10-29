# Production Risk Matrix

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| GPT review failure | Med | High | Watchdog, retry, human_required |
| review_unverified | Med | High | MIN_REPLY_CHARS=100, RID verify |
| RID mismatch | Low | Critical | Stop on mismatch |
| CDP unavailable | Med | High | human_required, no fallback |
| CDP 403 | Low | High | Restart Chrome |
| URL mismatch | Low | Critical | human_required, stop |
| OpenCode write-boundary | Low | High | WRITE_SET verify |
| False route interpretation | Med | Critical | POST_REVIEW_ROUTE gate |
| Source edit risk | Low | Critical | SAFETY_CHECK, git diff |
| Production promotion | N/A | Critical | BLOCKED |
| Guard removal | N/A | Critical | BLOCKED |
| Evidence cleanup | Low | Critical | append-only policy |
