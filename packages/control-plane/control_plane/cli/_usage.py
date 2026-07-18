"""Usage and help strings for the devframe CLI."""
from __future__ import annotations

HELP_TEXT = """DevFrame Code CLI
  Primary workflow: use devframe code as an OpenCode-first local coding tool.

  Daily coding loop
  1. Prepare : devframe code [[<goal>] | --prompt-file <path>]
  2. Status  : devframe code status [latest|<go-run-id>]
  3. Execute : devframe code execute [latest|<go-run-id>]

  Optional setup
  devframe code workers              - show available coding worker profiles
  devframe code providers            - show selectable model providers (api/local/web-shim)
  devframe code session [latest|<go-run-id>] - inspect a previous /go coding run sessions

  Control plane
  devframe client                    - launch the zero-config local Agent client
  devframe dashboard serve           - serve read-only local dashboard
  devframe actions                   - show Visual Control Plane action queue
  devframe sessions [--session-id <id>] - show public Visual Control Plane session summaries or one exact detail
  devframe visual-state              - export Visual Control Plane state

  Advanced orchestration
  devframe go <project> <goal>       - dispatch coding agents through /go
  devframe atgo <goal>               - @go evidence + coding dispatch entrypoint
  devframe rdgoal <project> <goal>   - route work through rdgoal
  devframe run --pipeline <path>     - run pipeline
  devframe init [template] [target]  - initialize project
  devframe doctor                    - check package health

  Specialist tools
  devframe web-ai ...               - Web AI binding, review, and task-intake helpers
  devframe pack validate ...        - validate an evidence pack
  devframe adapter verify ...       - compare canonical executor projections offline
  devframe toolchain preview ...    - validate a compiler/test manifest without executing it
  devframe paper finalize ...       - finalize a paper run after external review
  devframe writeback apply ...      - audited single-file workspace write-back
  devframe handoff ...              - generate, validate, bootstrap, or transfer handoffs

  Run devframe <command> --help for command-specific options.
"""

RUN_USAGE = "Usage: devframe run --pipeline <path> [--execute] [--project <dir>]"
PAPER_FINALIZE_USAGE = (
    "Usage: devframe paper finalize --project <dir> "
    "--review <independent-review.json> --review-sha256 <sha256> "
    "--reviewer-id <review-run-id>"
)
ADAPTER_VERIFY_USAGE = (
    "Usage: devframe adapter verify --reference-runtime <dir> "
    "--candidate-runtime <dir> [--reference-run-id <id>] "
    "[--candidate-run-id <id>] [--format text|json]"
)
TOOLCHAIN_PREVIEW_USAGE = (
    "Usage: devframe toolchain preview --manifest <path> [--format text|json]"
)
DASHBOARD_USAGE = "Usage: devframe dashboard serve [--runtime-dir <dir>] [--paper-project <dir>] [--host 127.0.0.1] [--port 8765] [--allow-remote]"
GO_USAGE = "Usage: devframe go <project> <goal> [--agents 2|auto] [--max-agents 4] [--target <path>] [--changed] [--since <git-ref>] [--preview] [--execute] [--worker opencode] [--model provider/model]"
ATGO_USAGE = "Usage: devframe atgo \"<goal>\" [--project <dir>] [--runtime-dir <dir>] [--target <path>] [--execute] [--auto-finalize]"
CODE_USAGE = (
    "Usage: devframe code [[\"<goal>\"] | --prompt-file <path>] [--project <dir>] "
    "[--agents 1|auto] [--max-agents 4] [--target <path>] [--changed] "
    "[--since <git-ref>] [--preview] [--execute] [--worker opencode]\n"
    "  Start optional diagnostics separately with devframe dashboard serve."
)
CODE_WORKERS_USAGE = "Usage: devframe code workers [--format text|json]"
CODE_PROVIDERS_USAGE = "Usage: devframe code providers [--format text|json]"
CODE_STATUS_USAGE = "Usage: devframe code status [latest|<go-run-id>] [--runtime-dir <dir>] [--format text|json]"
CODE_EXECUTE_USAGE = "Usage: devframe code execute [latest|<go-run-id>] [--runtime-dir <dir>] [--timeout <seconds>] [--rerun-passed] [--evidence-dir <dir>] [--auto-finalize | --prepare-evidence-dir <dir>]"
SESSION_USAGE = "Usage: devframe code session [latest|<go-run-id>] [--runtime-dir <dir>] [--format text|json]"
CLIENT_USAGE = "Usage: devframe client [serve|plan|bridge|t3desktop|smoke|doctor] [--runtime-dir <dir>] [--paper-project <dir>] [--host 127.0.0.1] [--port 8765] [--lang en|zh-CN] [--dry-run] [--format text|json] [--open] [--allow-remote] [--output <dir>] [--t3-root <dir>] [--force] [--prod]"
SESSIONS_USAGE = "Usage: devframe sessions [--runtime-dir <dir>] [--session-id <id>] [--format text|json]"
WEB_AI_IMPORT_USAGE = "Usage: devframe web-ai import <source> [--runtime-dir <dir>]"
WEB_AI_PROBE_USAGE = "Usage: devframe web-ai probe codexpro|devspace --endpoint <url> [--project <id>] [--format text|json|session-json]"
WEB_AI_LIVE_CHECK_USAGE = "Usage: devframe web-ai live-check codexpro|devspace --endpoint <url> [--token <token>] [--project <id>] [--tool server_config|handoff_to_agent|task_intake|project_summary] [--format text|json|session-json] [--import] [--runtime-dir <dir>]"
WEB_AI_ENSURE_BROWSER_USAGE = "Usage: devframe web-ai ensure-browser [--runtime-dir <dir>] [--config <json>] [--browser-exe <path>] [--profile-dir <dir>] [--cdp-endpoint http://127.0.0.1:9222] [--url https://chatgpt.com/] [--no-open] [--write-config] [--format text|json]"
WEB_AI_BIND_CHROME_USAGE = "Usage: devframe web-ai bind-chrome [--runtime-dir <dir>] [--project <id>] [--cdp-endpoint http://127.0.0.1:9222] [--dry-run] [--format text|json]"
WEB_AI_BIND_CONVERSATION_USAGE = "Usage: devframe web-ai bind-conversation --conversation <https://chatgpt.com/c/id> [--runtime-dir <dir>] [--project <id>] [--project-root <dir>] [--binding-root <dir>] [--output-name <file>] [--format text|json]"
WEB_AI_SUBMIT_REVIEW_USAGE = "Usage: devframe web-ai submit-review --zip <path> --prompt-file <path> (UTF-8/UTF-8-SIG or UTF-16 BOM) --conversation <url-or-id> [--cdp-endpoint http://127.0.0.1:9222] [--execute]"
WEB_AI_PREPARE_REVIEW_BUNDLE_USAGE = "Usage: devframe web-ai prepare-review-bundle --question <text> --source role=path [--source role=path ...] [--required-role role] [--project-root <dir>] [--runtime-dir <dir>] [--profile external_review] [--output-id <id>]"
WEB_AI_VALIDATE_REVIEW_BUNDLE_USAGE = "Usage: devframe web-ai validate-review-bundle --zip <path>"
WEB_AI_RECORD_MCP_RESULT_USAGE = "Usage: devframe web-ai record-mcp-result --conversation <url> --tool-name <name> --status completed|blocked|failed|web_host_completed|web_host_no_result|local_mcp_completed [--origin web_host|local_mcp] [--outcome completed|blocked|failed|no_result] [--provider chatgpt] [--project dev-frame-system] [--connector-name <name>] [--connector-app-id <id>] [--marker <text>] --result <summary> [--output-id <id>] [--output-name <name>] [--runtime-dir <dir>]"
WEB_AI_RECORD_TASK_INTAKE_USAGE = "Usage: devframe web-ai record-task-intake --conversation <url> --task-title <text> --task-summary <text> [--provider chatgpt] [--project dev-frame-system] [--connector-name <name>] [--connector-app-id <id>] [--priority high|medium|low] [--suggested-agent opencode|codex|custom] [--marker <text>] [--runtime-dir <dir>]"
WEB_AI_IMPORT_TASK_INTAKES_USAGE = "Usage: devframe web-ai import-task-intakes [--project-root <dir>] [--runtime-dir <dir>] [--provider codexpro] [--project dev-frame-system] [--connector-name <name>] [--connector-app-id <id>]"
WEB_AI_DISPATCH_TASK_INTAKES_USAGE = "Usage: devframe web-ai dispatch-task-intakes [--project-root <dir>] [--runtime-dir <dir>] [--provider codexpro] [--project dev-frame-system] [--connector-name <name>] [--connector-app-id <id>] [--intake-id <id>] [--agents 1] [--limit <n>] [--execute] [--model provider/model] [--opencode-agent build]"

WRITEBACK_APPLY_USAGE = (
    "Usage: devframe writeback apply --workspace <root> --path <rel> "
    "--contents-file <f> [--action-id <id>] [--runtime-dir <dir>] [--confirm] "
    "[--format text|json]\n"
    "  Human-gated single-file workspace write-back. Without --confirm it only "
    "previews (exit 3); with --confirm it applies the write and records an audit."
)

MCP_CONNECTIONS_USAGE = (
    "Usage: devframe mcp connections list|allow|allow-always|deny|revoke "
    "[--id <connectionId>] [--host 127.0.0.1] [--port 8765] [--format text|json]\n"
    "  Review and decide AI MCP connection authorizations against the running "
    "dashboard. 'list' shows pending/active connections; allow/deny/revoke need --id."
)
