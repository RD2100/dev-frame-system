---
"@tutti-os/browser-node": patch
"@tutti-os/workspace-issue-manager": patch
---

Move published dock and illustration assets onto explicit package asset subpaths so consumers can opt in to the default visuals without runtime 404s or unconditional bundle bloat.
