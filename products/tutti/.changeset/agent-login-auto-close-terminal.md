---
"@tutti-os/desktop": patch
---

Auto-close the login terminal once authentication succeeds. The "login" action opens a terminal for `codex login` / `claude auth login` (which open the browser for OAuth); previously that terminal lingered after login finished. The terminal now closes automatically when the provider becomes ready, and stays open on failure or timeout so the error remains readable.
