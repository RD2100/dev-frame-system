"""devframe CLI command router."""
from __future__ import annotations

import sys
from pathlib import Path

from ._common import _print_help, _wants_help
from ._usage import *  # noqa: F401,F403 - usage strings referenced by main() below
from ._client import cmd_client
from ._coding import (
    cmd_atgo,
    cmd_code,
    cmd_code_execute,
    cmd_code_providers,
    cmd_code_session,
    cmd_code_status,
    cmd_code_workers,
    cmd_go,
    cmd_workflow,
)
from ._core import (
    cmd_doctor,
    cmd_handoff_bootstrap,
    cmd_handoff_generate,
    cmd_handoff_transfer,
    cmd_handoff_validate,
    cmd_init,
    cmd_adapter_verify,
    cmd_pack_validate,
    cmd_paper_finalize,
    cmd_rdgoal,
    cmd_run,
    cmd_toolchain_preview,
    cmd_toolchain_run,
    cmd_toolchain_status,
)
from ._review import cmd_rdreview
from ._visual import cmd_actions, cmd_dashboard, cmd_sessions, cmd_visual_state
from ._writeback import cmd_writeback_apply
from ._mcp import cmd_mcp_connections
from ._webai import (
    cmd_web_ai_bind_chrome,
    cmd_web_ai_bind_conversation,
    cmd_web_ai_dispatch_task_intakes,
    cmd_web_ai_ensure_browser,
    cmd_web_ai_import,
    cmd_web_ai_import_task_intakes,
    cmd_web_ai_live_check,
    cmd_web_ai_prepare_review_bundle,
    cmd_web_ai_probe,
    cmd_web_ai_record_mcp_result,
    cmd_web_ai_record_task_intake,
    cmd_web_ai_submit_review,
    cmd_web_ai_validate_review_bundle,
)


def main() -> int:
    if len(sys.argv) < 2 or _wants_help(sys.argv[1:2]):
        _print_help()
        return 0

    cmd = sys.argv[1]
    if cmd == "handoff":
        sub = sys.argv[2] if len(sys.argv) > 2 else "generate"
        if sub == "generate":
            return cmd_handoff_generate()
        if sub == "validate":
            return cmd_handoff_validate(sys.argv[3]) if len(sys.argv) > 3 else 1
        if sub == "bootstrap":
            return cmd_handoff_bootstrap()
        if sub == "transfer":
            return cmd_handoff_transfer()
        print(f"Unknown handoff subcommand: {sub}")
        return 1

    if cmd == "init":
        template = sys.argv[2] if len(sys.argv) > 2 else "code_project"
        target = sys.argv[3] if len(sys.argv) > 3 else "."
        return cmd_init(template, target)

    if cmd == "rdgoal":
        return cmd_rdgoal()

    if cmd == "paper":
        sub = sys.argv[2] if len(sys.argv) > 2 else ""
        if sub == "finalize":
            if _wants_help(sys.argv[3:]):
                print(PAPER_FINALIZE_USAGE)
                return 0
            return cmd_paper_finalize(sys.argv[3:])
        print(PAPER_FINALIZE_USAGE)
        return 1

    if cmd == "adapter":
        sub = sys.argv[2] if len(sys.argv) > 2 else ""
        if sub == "verify":
            if _wants_help(sys.argv[3:]):
                print(ADAPTER_VERIFY_USAGE)
                return 0
            return cmd_adapter_verify(sys.argv[3:])
        print(ADAPTER_VERIFY_USAGE)
        return 0 if _wants_help(sys.argv[2:]) else 1

    if cmd == "toolchain":
        sub = sys.argv[2] if len(sys.argv) > 2 else ""
        if sub == "preview":
            if _wants_help(sys.argv[3:]):
                print(TOOLCHAIN_PREVIEW_USAGE)
                return 0
            return cmd_toolchain_preview(sys.argv[3:])
        if sub == "run":
            if _wants_help(sys.argv[3:]):
                print(TOOLCHAIN_RUN_USAGE)
                return 0
            return cmd_toolchain_run(sys.argv[3:])
        if sub == "status":
            if _wants_help(sys.argv[3:]):
                print(TOOLCHAIN_STATUS_USAGE)
                return 0
            return cmd_toolchain_status(sys.argv[3:])
        print(TOOLCHAIN_PREVIEW_USAGE)
        return 0 if _wants_help(sys.argv[2:]) else 1

    if cmd == "code":
        if len(sys.argv) > 2 and sys.argv[2] == "workers":
            if _wants_help(sys.argv[3:]):
                print(CODE_WORKERS_USAGE)
                return 0
            return cmd_code_workers(prog="devframe code workers")
        if len(sys.argv) > 2 and sys.argv[2] == "providers":
            if _wants_help(sys.argv[3:]):
                print(CODE_PROVIDERS_USAGE)
                return 0
            return cmd_code_providers(prog="devframe code providers")
        if len(sys.argv) > 2 and sys.argv[2] == "status":
            if _wants_help(sys.argv[3:]):
                print(CODE_STATUS_USAGE)
                return 0
            return cmd_code_status(prog="devframe code status")
        if len(sys.argv) > 2 and sys.argv[2] == "execute":
            if _wants_help(sys.argv[3:]):
                print(CODE_EXECUTE_USAGE)
                return 0
            return cmd_code_execute(prog="devframe code execute")
        if len(sys.argv) > 2 and sys.argv[2] == "session":
            if _wants_help(sys.argv[3:]):
                print(SESSION_USAGE)
                return 0
            return cmd_code_session(prog="devframe code session")
        if _wants_help(sys.argv[2:]):
            print(CODE_USAGE)
            return 0
        return cmd_code()

    if cmd == "go":
        if len(sys.argv) > 2 and sys.argv[2] == "workers":
            if _wants_help(sys.argv[3:]):
                print(CODE_WORKERS_USAGE.replace("devframe code", "devframe go"))
                return 0
            return cmd_code_workers(prog="devframe go workers")
        if len(sys.argv) > 2 and sys.argv[2] == "providers":
            if _wants_help(sys.argv[3:]):
                print(CODE_PROVIDERS_USAGE.replace("devframe code", "devframe go"))
                return 0
            return cmd_code_providers(prog="devframe go providers")
        if len(sys.argv) > 2 and sys.argv[2] == "status":
            if _wants_help(sys.argv[3:]):
                print(CODE_STATUS_USAGE.replace("devframe code", "devframe go"))
                return 0
            return cmd_code_status(prog="devframe go status")
        if len(sys.argv) > 2 and sys.argv[2] == "execute":
            if _wants_help(sys.argv[3:]):
                print(CODE_EXECUTE_USAGE.replace("devframe code", "devframe go"))
                return 0
            return cmd_code_execute(prog="devframe go execute")
        if _wants_help(sys.argv[2:]):
            print(GO_USAGE)
            return 0
        return cmd_go()

    if cmd == "atgo":
        if _wants_help(sys.argv[2:]):
            print(ATGO_USAGE)
            return 0
        return cmd_atgo()

    if cmd == "workflow":
        return cmd_workflow()

    if cmd == "visual-state":
        return cmd_visual_state()

    if cmd == "actions":
        return cmd_actions()

    if cmd == "sessions":
        if _wants_help(sys.argv[2:]):
            print(SESSIONS_USAGE)
            return 0
        return cmd_sessions()

    if cmd == "client":
        return cmd_client()

    if cmd == "rdreview":
        if _wants_help(sys.argv[2:]):
            print(
                "Usage: devframe rdreview <work_item_id> <intent> "
                "[--project <id>] [--output <file>] [--format packet|bundle]"
            )
            print("  Prepare a review-governance packet or prepare-only runtime-governance bundle.")
            return 0
        return cmd_rdreview(sys.argv[2:])

    if cmd == "web-ai":
        if _wants_help(sys.argv[2:3]):
            print(WEB_AI_IMPORT_USAGE)
            print(WEB_AI_PROBE_USAGE)
            print(WEB_AI_LIVE_CHECK_USAGE)
            print(WEB_AI_ENSURE_BROWSER_USAGE)
            print(WEB_AI_BIND_CHROME_USAGE)
            print(WEB_AI_BIND_CONVERSATION_USAGE)
            print(WEB_AI_PREPARE_REVIEW_BUNDLE_USAGE)
            print(WEB_AI_VALIDATE_REVIEW_BUNDLE_USAGE)
            print(WEB_AI_IMPORT_TASK_INTAKES_USAGE)
            return 0
        if len(sys.argv) > 2 and sys.argv[2] == "import":
            if _wants_help(sys.argv[3:]):
                print(WEB_AI_IMPORT_USAGE)
                return 0
            return cmd_web_ai_import(prog="devframe web-ai import")
        if len(sys.argv) > 2 and sys.argv[2] == "probe":
            if _wants_help(sys.argv[3:]):
                print(WEB_AI_PROBE_USAGE)
                return 0
            return cmd_web_ai_probe(prog="devframe web-ai probe")
        if len(sys.argv) > 2 and sys.argv[2] == "live-check":
            if _wants_help(sys.argv[3:]):
                print(WEB_AI_LIVE_CHECK_USAGE)
                return 0
            return cmd_web_ai_live_check(prog="devframe web-ai live-check")
        if len(sys.argv) > 2 and sys.argv[2] == "bind-chrome":
            if _wants_help(sys.argv[3:]):
                print(WEB_AI_BIND_CHROME_USAGE)
                return 0
            return cmd_web_ai_bind_chrome(prog="devframe web-ai bind-chrome")
        if len(sys.argv) > 2 and sys.argv[2] == "ensure-browser":
            if _wants_help(sys.argv[3:]):
                print(WEB_AI_ENSURE_BROWSER_USAGE)
                return 0
            return cmd_web_ai_ensure_browser(prog="devframe web-ai ensure-browser")
        if len(sys.argv) > 2 and sys.argv[2] == "bind-conversation":
            if _wants_help(sys.argv[3:]):
                print(WEB_AI_BIND_CONVERSATION_USAGE)
                return 0
            return cmd_web_ai_bind_conversation(prog="devframe web-ai bind-conversation")
        if len(sys.argv) > 2 and sys.argv[2] == "submit-review":
            if _wants_help(sys.argv[3:]):
                print(WEB_AI_SUBMIT_REVIEW_USAGE)
                return 0
            return cmd_web_ai_submit_review(prog="devframe web-ai submit-review")
        if len(sys.argv) > 2 and sys.argv[2] == "prepare-review-bundle":
            if _wants_help(sys.argv[3:]):
                print(WEB_AI_PREPARE_REVIEW_BUNDLE_USAGE)
                return 0
            return cmd_web_ai_prepare_review_bundle(prog="devframe web-ai prepare-review-bundle")
        if len(sys.argv) > 2 and sys.argv[2] == "validate-review-bundle":
            if _wants_help(sys.argv[3:]):
                print(WEB_AI_VALIDATE_REVIEW_BUNDLE_USAGE)
                return 0
            return cmd_web_ai_validate_review_bundle(prog="devframe web-ai validate-review-bundle")
        if len(sys.argv) > 2 and sys.argv[2] == "record-mcp-result":
            if _wants_help(sys.argv[3:]):
                print(WEB_AI_RECORD_MCP_RESULT_USAGE)
                return 0
            return cmd_web_ai_record_mcp_result(prog="devframe web-ai record-mcp-result")
        if len(sys.argv) > 2 and sys.argv[2] == "record-task-intake":
            if _wants_help(sys.argv[3:]):
                print(WEB_AI_RECORD_TASK_INTAKE_USAGE)
                return 0
            return cmd_web_ai_record_task_intake(prog="devframe web-ai record-task-intake")
        if len(sys.argv) > 2 and sys.argv[2] == "import-task-intakes":
            if _wants_help(sys.argv[3:]):
                print(WEB_AI_IMPORT_TASK_INTAKES_USAGE)
                return 0
            return cmd_web_ai_import_task_intakes(prog="devframe web-ai import-task-intakes")
        if len(sys.argv) > 2 and sys.argv[2] == "dispatch-task-intakes":
            if _wants_help(sys.argv[3:]):
                print(WEB_AI_DISPATCH_TASK_INTAKES_USAGE)
                return 0
            return cmd_web_ai_dispatch_task_intakes(prog="devframe web-ai dispatch-task-intakes")
        print(f"Unknown web-ai subcommand: {sys.argv[2] if len(sys.argv) > 2 else ''}")
        return 1

    if cmd == "dashboard":
        return cmd_dashboard()

    if cmd == "mcp":
        sub = sys.argv[2] if len(sys.argv) > 2 else ""
        if sub == "connections":
            if _wants_help(sys.argv[3:4]) and len(sys.argv) <= 3:
                print(MCP_CONNECTIONS_USAGE)
                return 0
            return cmd_mcp_connections(prog="devframe mcp connections")
        print(MCP_CONNECTIONS_USAGE)
        return 0 if _wants_help(sys.argv[2:]) else 1

    if cmd == "writeback":
        sub = sys.argv[2] if len(sys.argv) > 2 else ""
        if sub == "apply":
            if _wants_help(sys.argv[3:]):
                print(WRITEBACK_APPLY_USAGE)
                return 0
            return cmd_writeback_apply(prog="devframe writeback apply")
        if _wants_help(sys.argv[2:]):
            print(WRITEBACK_APPLY_USAGE)
            return 0
        print(f"Unknown writeback subcommand: {sub}")
        return 1

    if cmd == "doctor":
        return cmd_doctor()

    if cmd == "run":
        if _wants_help(sys.argv[2:]):
            print(RUN_USAGE)
            return 0
        if "--pipeline" not in sys.argv:
            print(RUN_USAGE)
            return 1
        index = sys.argv.index("--pipeline")
        if index + 1 >= len(sys.argv):
            print(RUN_USAGE)
            return 1
        path = sys.argv[index + 1]
        with_submission = "--with-submission" in sys.argv
        execute = "--execute" in sys.argv
        project_dir = None
        if "--project" in sys.argv:
            project_index = sys.argv.index("--project")
            if project_index + 1 >= len(sys.argv):
                print(RUN_USAGE)
                return 1
            project_dir = Path(sys.argv[project_index + 1]).resolve()

        if execute:
            from ..stage_executor import execute_full_pipeline
            print(f"Pipeline: {path}")
            print("Mode: execute (via framework stage_executor)")
            if project_dir:
                print(f"Project: {project_dir}")
            results = execute_full_pipeline(project_dir=project_dir)
            total = len(results)
            completed = sum(1 for result in results if result.status == "completed")
            for result in results:
                status = "PASS" if result.status == "completed" else "FAIL"
                print(f"  [{status}] {result.stage_id} ({len(result.outputs)} outputs)")
            print(f"\nStages: {completed}/{total} completed")
            return 0 if completed == total else 1
        return cmd_run(path, with_submission=with_submission)

    if cmd == "pack":
        sub = sys.argv[2] if len(sys.argv) > 2 else ""
        if sub == "validate":
            if len(sys.argv) < 4:
                print("Usage: devframe pack validate <zip>")
                return 1
            return cmd_pack_validate(sys.argv[3])
        print("Usage: devframe pack validate <zip>")
        return 1

    print(f"Unknown command: {cmd}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
