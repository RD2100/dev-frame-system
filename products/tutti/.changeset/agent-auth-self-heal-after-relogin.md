---
"@tutti-os/desktop": patch
---

Fix the agent environment check staying stuck on "needs login" after a successful re-login. A runtime 401 (e.g. an expired/revoked Codex token) records an auth-failure flag that overrides the local "logged in" marker; previously only a later _successful run_ cleared it, but re-login is a terminal action that never reports a run — so the dock and wizard stayed red no matter how many times the user re-checked. The probe now self-heals: when the provider's credential file is rewritten by a fresh login (its mtime moves past the recorded failure), the stale flag is dropped and normal detection resumes.
