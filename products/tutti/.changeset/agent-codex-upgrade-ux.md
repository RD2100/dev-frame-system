---
"@tutti-os/desktop": patch
---

Improve the codex environment wizard for an outdated CLI. Upgrades are now user-driven: instead of a no-op auto-install (npm can't upgrade an already-present binary), the wizard shows the manual upgrade command and re-checks. The outdated state also surfaces the actual versions — "current X · requires ≥ Y" — sourced from the backend's own version gate.
