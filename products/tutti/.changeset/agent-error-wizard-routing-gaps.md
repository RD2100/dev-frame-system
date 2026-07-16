---
"@tutti-os/desktop": patch
"@tutti-os/agent-gui": patch
---

Close two gaps in routing agent errors to the setup wizard. A failure the provider reports as a plain failed message (e.g. Claude Code's dropped-login 401, "Failed to authenticate … 401 Invalid authentication credentials") now renders as the structured remediation card with a wizard call-to-action instead of dead red text, by recovering the env-fixable code from the message text (auth / CLI-missing / version / network) and routing to the right provider. And opening the wizard from a remediation CTA (auth/install/repair/upgrade/network) now re-probes status instead of reusing the cached snapshot, so it reflects the real problem and can auto-remediate rather than contradicting the error with "ready".
