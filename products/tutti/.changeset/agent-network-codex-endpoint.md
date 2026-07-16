---
"@tutti-os/desktop": patch
---

Fix a false "service API unreachable" for Codex in the network check. A ChatGPT-login Codex talks to `chatgpt.com`, not `api.openai.com`, so probing only `api.openai.com` reported the service unreachable for users where that host is blocked even though Codex worked fine. The probe now checks Codex's actual endpoints (`chatgpt.com`, then `api.openai.com`) and counts the service reachable if either answers. Network probe outcomes are also logged for diagnosability.
