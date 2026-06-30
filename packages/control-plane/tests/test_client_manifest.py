import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from jsonschema.validators import validator_for

from control_plane.client_manifest import build_visual_client_manifest
from control_plane.dashboard import build_dashboard_server


REPO_ROOT = Path(__file__).resolve().parents[3]


def load_schema() -> dict:
    return json.loads((REPO_ROOT / "schemas" / "visual_client_manifest.schema.json").read_text(encoding="utf-8"))


def validate_schema(schema: dict, data: dict) -> None:
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    validator_class(schema).validate(data)


def test_visual_client_manifest_matches_public_schema():
    schema = load_schema()

    manifest = build_visual_client_manifest()

    validate_schema(schema, manifest)
    assert manifest["reuse"]["client"] == "t3code"
    assert manifest["reuse"]["client_role"] == "primary-native-client-shell"
    assert manifest["reuse"]["executor"] == "opencode"
    assert manifest["reuse"]["devframe_role"] == "governance-protocol-and-read-model"
    assert manifest["transport"]["client_plan_endpoint"] == "/client-plan.json"
    assert manifest["transport"]["t3_bridge_endpoint"] == "/t3-bridge.json"
    assert manifest["transport"]["t3_environment_endpoint"] == "/.well-known/t3/environment"
    assert manifest["transport"]["t3_auth_session_endpoint"] == "/api/auth/session"
    assert manifest["transport"]["shell_endpoint"] == "/t3-shell.json"
    assert manifest["write_policy"]["default"] == "read-only"
    assert set(manifest["write_policy"]["blocked_methods"]) == {"PUT", "PATCH", "DELETE"}
    assert manifest["write_policy"]["allowed_mutation_endpoints"] == [
        {
            "method": "POST",
            "path": "/go/dispatch",
            "requires": ["loopback-client", "same-origin", "registered-project-root"],
        },
        {
            "method": "POST",
            "path": "/actions/execute",
            "requires": ["loopback-client", "confirm=execute", "queued-go-run-or-web-gpt-task-intake-action"],
        },
        {
            "method": "POST",
            "path": "/api/t3/approval-response",
            "requires": ["loopback-client", "loopback-origin", "approval.requested", "approve-or-reject"],
        },
        {
            "method": "POST",
            "path": "/api/t3/writeback-propose",
            "requires": ["loopback-client", "loopback-origin", "registered-project-root", "human-approval-before-write"],
        },
        {
            "method": "POST",
            "path": "/api/t3/cluster-run",
            "requires": ["loopback-client", "loopback-origin", "valid-cluster-target", "human-inline-confirm-in-conversation"],
        },
        {
            "method": "POST",
            "path": "/api/t3/cluster-roster",
            "requires": ["loopback-client", "loopback-origin", "validated-roster"],
        },
        {
            "method": "POST",
            "path": "/api/t3/skills",
            "requires": ["loopback-client", "loopback-origin", "validated-skills"],
        },
        {
            "method": "POST",
            "path": "/api/t3/rules",
            "requires": ["loopback-client", "loopback-origin", "validated-rules"],
        },
        {
            "method": "POST",
            "path": "/api/t3/run-defaults",
            "requires": ["loopback-client", "loopback-origin", "validated-run-defaults"],
        },
        {
            "method": "POST",
            "path": "/api/t3/memory",
            "requires": ["loopback-client", "loopback-origin", "validated-memory"],
        },
        {
            "method": "POST",
            "path": "/api/t3/cluster-run-delete",
            "requires": ["loopback-client", "loopback-origin", "existing-run"],
        },
        {
            "method": "POST",
            "path": "/api/t3/cluster-run-rename",
            "requires": ["loopback-client", "loopback-origin", "existing-run", "non-empty-goal"],
        },
    ]
    mappings = {mapping["id"]: mapping for mapping in manifest["surface_mappings"]}
    assert mappings["client-launch"]["client_surface"] == "zero-config-primary-native-client-entry"
    assert mappings["project-workbench"]["client_surface"] == "native-project-list-and-active-project"
    assert mappings["session-workbench"]["client_surface"] == "native-conversation-list-and-session-detail"
    assert mappings["go-dispatch"]["client_surface"] == "auxiliary-dashboard-project-level-go-dispatch"
    assert mappings["web-gpt-review-gate"]["client_surface"] == "external-web-gpt-review-gate"
    assert mappings["web-gpt-review-gate"]["source_endpoint"] == "/actions.md"
    assert mappings["web-gpt-review-gate"]["object_types"] == ["Action", "Gate", "DevFrameSession"]
    descriptions = {endpoint["id"]: endpoint["description"] for endpoint in manifest["endpoints"]}
    assert "Primary T3 Code native-client" in descriptions["t3-shell"]
    assert "lightweight web dashboard" in descriptions["go-dispatch-page"]
    mutating_endpoints = [endpoint for endpoint in manifest["endpoints"] if endpoint["mutates"]]
    assert mutating_endpoints == [
        {
            "id": "go-dispatch-submit",
            "path": "/go/dispatch",
            "method": "POST",
            "contract": "go_dispatch_request",
            "object_types": ["Project", "Run", "Action"],
            "mutates": True,
            "description": "Loopback-only, same-origin /go dispatch request that prepares packets or starts coding-agent shards.",
        },
        {
            "id": "controlled-action-execute",
            "path": "/actions/execute",
            "method": "POST",
            "contract": "controlled_action_execution",
            "object_types": ["Action", "Run", "DevFrameSession"],
            "mutates": True,
            "description": "Loopback-only, confirm-gated execution entry for queued DevFrame Code go-runs and Web GPT task-intake dispatch.",
        },
        {
            "id": "t3-approval-response",
            "path": "/api/t3/approval-response",
            "method": "POST",
            "contract": "t3_approval_response",
            "object_types": ["Action", "Run", "DevFrameSession"],
            "mutates": True,
            "description": "Loopback-only approval callback used by T3 approval.requested activities to execute controlled actions.",
        },
        {
            "id": "t3-writeback-propose",
            "path": "/api/t3/writeback-propose",
            "method": "POST",
            "contract": "t3_writeback_proposal",
            "object_types": ["Project", "DevFrameSession"],
            "mutates": True,
            "description": "Loopback-only write-back proposal staging; nothing is written until a human approves the proposal via /api/t3/approval-response.",
        },
        {
            "id": "t3-cluster-run",
            "path": "/api/t3/cluster-run",
            "method": "POST",
            "contract": "t3_cluster_run",
            "object_types": ["Agent", "Run", "Project"],
            "mutates": True,
            "description": "Loopback-only cluster run start for a &-mentioned target. Authorized by the human's inline confirm in the conversation; starts a project-coordinator run. No dashboard approval is involved.",
        },
        {
            "id": "t3-cluster-roster-save",
            "path": "/api/t3/cluster-roster",
            "method": "POST",
            "contract": "t3_cluster_roster_save",
            "object_types": ["Agent"],
            "mutates": True,
            "description": "Loopback-only save of the user-customizable cluster agent roster (the visual customization of which agents the coordinator can dispatch to).",
        },
        {
            "id": "t3-skills-save",
            "path": "/api/t3/skills",
            "method": "POST",
            "contract": "t3_skills_save",
            "object_types": ["Skill"],
            "mutates": True,
            "description": "Loopback-only save of user-created methodology skills (the visual creation/editing of complete skill units: identity + behavior profile).",
        },
        {
            "id": "t3-rules-save",
            "path": "/api/t3/rules",
            "method": "POST",
            "contract": "t3_rules_save",
            "object_types": ["Rule"],
            "mutates": True,
            "description": "Loopback-only save of user-created governance rules (the visual editing of machine-readable rule records).",
        },
        {
            "id": "t3-run-defaults-save",
            "path": "/api/t3/run-defaults",
            "method": "POST",
            "contract": "t3_run_defaults_save",
            "object_types": ["RunDefaults"],
            "mutates": True,
            "description": "Loopback-only save of run defaults at a chosen scope (global or project).",
        },
        {
            "id": "t3-memory-save",
            "path": "/api/t3/memory",
            "method": "POST",
            "contract": "t3_memory_save",
            "object_types": ["Preferences", "ProjectMemory"],
            "mutates": True,
            "description": "Loopback-only save of global preferences or project memory at the targeted layer.",
        },
        {
            "id": "t3-cluster-run-delete",
            "path": "/api/t3/cluster-run-delete",
            "method": "POST",
            "contract": "t3_cluster_run_delete",
            "object_types": ["Run"],
            "mutates": True,
            "description": "Loopback-only delete of a recorded cluster run from the coordinator overview.",
        },
        {
            "id": "t3-cluster-run-rename",
            "path": "/api/t3/cluster-run-rename",
            "method": "POST",
            "contract": "t3_cluster_run_rename",
            "object_types": ["Run"],
            "mutates": True,
            "description": "Loopback-only rename of a recorded cluster run's goal/title in the coordinator overview.",
        },
    ]
    assert {endpoint["path"] for endpoint in manifest["endpoints"]} >= {
        "/client-plan.json",
        "/t3-bridge.json",
        "/.well-known/t3/environment",
        "/api/auth/session",
        "/state.json",
        "/t3-shell.json",
        "/sessions.json",
        "/web-ai-sessions.json",
        "/actions.json",
        "/actions.md",
        "/go/dispatch",
        "/actions/open",
        "/actions/execute",
        "/api/t3/approval-response",
    }
    assert manifest["governance"]["reconReceipt"] == "docs/status/recon-receipt-local-agent-client-mainline.md"
    assert manifest["governance"]["rkrRulePath"] == "rules/recon.md"
    assert manifest["governance"]["reuseAssessment"] == "docs/status/t3code-client-mainline-reuse-assessment.md"
    assert "T3Code" in manifest["governance"]["primaryClientDecision"]
    assert "OpenCode" in manifest["governance"]["workerDecision"]
    assert "ZIP/report is fallback" in manifest["governance"]["webAiAdapterDecision"]
    assert manifest["governance"]["nextApprovedSlice"]
    supported = manifest.get("supported_methodologies") or []
    assert len(supported) >= 2
    assert any(m["skill_id"] == "agent-acceptance" for m in supported)
    assert any(m["skill_id"] == "tdd" for m in supported)
    for entry in supported:
        assert "skill_id" in entry
        assert "title" in entry
        assert "display_label" in entry
        assert "triggers" in entry
        assert "source_kind" in entry
    agent_acceptance = next(m for m in supported if m["skill_id"] == "agent-acceptance")
    assert agent_acceptance.get("profiles")
    go_read_profile = next(p for p in agent_acceptance["profiles"] if p["selected_trigger_label"] == "@go read")
    assert go_read_profile["profile_id"] == "read-only"
    assert go_read_profile["read_only"] is True
    assert go_read_profile["network_enabled"] is False
    tdd = next(m for m in supported if m["skill_id"] == "tdd")
    assert tdd.get("profiles") is None


def test_dashboard_serves_client_manifest_as_read_only_contract(tmp_path):
    schema = load_schema()
    server = build_dashboard_server(runtime_dir=tmp_path / "runtime", port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with urlopen(f"{base_url}/client-manifest.json", timeout=5) as response:
            manifest = json.loads(response.read().decode("utf-8"))

        validate_schema(schema, manifest)
        assert manifest["transport"]["manifest_endpoint"] == "/client-manifest.json"
        assert manifest["transport"]["client_plan_endpoint"] == "/client-plan.json"
        assert manifest["transport"]["t3_bridge_endpoint"] == "/t3-bridge.json"
        assert manifest["transport"]["t3_environment_endpoint"] == "/.well-known/t3/environment"
        assert manifest["transport"]["t3_auth_session_endpoint"] == "/api/auth/session"
        assert manifest["transport"]["shell_endpoint"] == "/t3-shell.json"
        mappings = {mapping["id"]: mapping for mapping in manifest["surface_mappings"]}
        assert mappings["client-launch"]["client_surface"] == "zero-config-primary-native-client-entry"
        assert any(mapping["id"] == "t3-bridge" for mapping in manifest["surface_mappings"])
        assert mappings["session-workbench"]["client_surface"] == "native-conversation-list-and-session-detail"
        assert any(endpoint["id"] == "t3-shell" for endpoint in manifest["endpoints"])
        assert any(endpoint["id"] == "t3-environment-descriptor" for endpoint in manifest["endpoints"])
        assert any(endpoint["id"] == "t3-auth-session" for endpoint in manifest["endpoints"])
        assert any(endpoint["id"] == "go-dispatch-page" for endpoint in manifest["endpoints"])
        assert any(endpoint["id"] == "go-dispatch-submit" for endpoint in manifest["endpoints"])
        assert any(endpoint["id"] == "controlled-action-page" for endpoint in manifest["endpoints"])
        assert any(endpoint["id"] == "controlled-action-execute" for endpoint in manifest["endpoints"])
        assert mappings["go-dispatch"]["client_surface"] == "auxiliary-dashboard-project-level-go-dispatch"
        assert mappings["web-gpt-review-gate"]["client_surface"] == "external-web-gpt-review-gate"
        assert manifest["governance"]["reconReceipt"] == "docs/status/recon-receipt-local-agent-client-mainline.md"
        assert manifest["governance"]["primaryClientDecision"]
        assert manifest["governance"]["workerDecision"]

        try:
            urlopen(Request(f"{base_url}/client-manifest.json", method="POST"), timeout=5)
        except HTTPError as error:
            assert error.code == 405
        else:
            raise AssertionError("dashboard accepted a client manifest write request")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
