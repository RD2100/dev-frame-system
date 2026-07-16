---
"@tutti-os/desktop": patch
---

Redact credentials from custom npm registry URLs before they reach the setup wizard, telemetry, or logs. A custom registry override can embed `user:token@host` userinfo; the codex installer now surfaces and logs a sanitized URL while still using the raw URL for the npm environment.
