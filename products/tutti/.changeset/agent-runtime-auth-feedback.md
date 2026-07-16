---
"@tutti-os/desktop": patch
---

Detect a dropped agent login. A runtime authentication failure (e.g. a 401 when sending a message — the local credentials file still says "logged in") is now fed back from the agent runtime into the status probe, which overrides the stale "authenticated" verdict with "needs login" for both Codex and Claude Code. So re-detecting in the environment wizard (or the dock) now surfaces the dropped login and routes the user to re-authenticate, instead of reporting the agent as ready. The override clears on a successful turn. Also renames the diagnostics toggle to "针对上报".
