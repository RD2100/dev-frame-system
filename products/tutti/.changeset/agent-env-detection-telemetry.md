---
"@tutti-os/desktop": patch
---

Add `agent.env_detected` and `agent.env_issue_reported` analytics events for the agent environment wizard. `agent.env_detected` reports each provider's detection outcome automatically — availability, CLI/adapter/auth state, and the network registry/API/proxy reachability — using only privacy-safe booleans and enums (no file paths, account email, or proxy address), and fires once per distinct outcome so routine polling doesn't spam the funnel. When an environment anomaly is detected, the wizard proactively prompts to send a fuller diagnostic payload (CLI paths, endpoints, proxy address, error detail); with reporting already enabled it sends silently. The opt-in lives as an "Agent diagnostics reporting" toggle in Settings → General (the account email is never sent).
