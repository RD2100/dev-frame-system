# Failure Mode Matrix

| Mode | Detection | Action | Retry |
|------|-----------|--------|-------|
| review_unverified | <100 chars or missing RID | stop | yes |
| RID mismatch | reply RID!=expected | stop | no |
| short capture | <100 chars | stop | yes |
| template echo | matches task desc | stop | yes |
| CDP unavailable | no port response | human_required | yes |
| CDP 403 | WS connection error | human_required | yes |
| URL mismatch | page!=authorized | human_required | no |
| new GPT needed | page missing | human_required | no |
| base URL fallback | target is base | human_required | no |
| blocked | GPT=blocked | stop | no |
| rejected | GPT=rejected | stop | no |
| human_required | GPT=human_required | stop | no |
| needs_more_evidence | GPT=needs_more_evidence | assess | conditional |
