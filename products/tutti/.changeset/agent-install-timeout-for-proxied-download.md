---
"@tutti-os/desktop": patch
---

Stop the codex CLI install from failing under a slow system proxy. The npm install pulls a large platform binary; direct it's ~6-44s, but through a throttled proxy it's ~76-100s+ — right at the old 90s per-registry cap, so otherwise-succeeding installs were killed and the whole registry chain timed out. Raise the per-registry timeout to 150s (and the overall install budget to 8 min so the chain can still fail over) so a working-but-slow registry can finish.
