from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.request import urlopen

from control_plane.cli._core import cmd_init
from control_plane.client_launcher import build_client_launch_plan
from control_plane.dashboard import build_dashboard_server
from control_plane.paper_pipeline_gate import finalize_paper_project
from control_plane.t3_bridge_bundle import (
    build_t3_bridge_bundle,
    install_t3_bridge_bundle,
)


REQUIRED_REVIEW_EVIDENCE = (
    "TASKSPEC.json",
    "execution-report.json",
    "closure/FLOW_OUTCOME.json",
    "evidence/PAPER_PIPELINE_GATE.json",
    "evidence/ref-paper-review-pack.zip",
)


def _install_generated_bridge(tmp_path: Path, runtime_dir: Path) -> Path:
    t3_root = tmp_path / "t3code"
    (t3_root / "apps" / "web").mkdir(parents=True)
    (t3_root / "package.json").write_text('{"type":"module"}\n', encoding="utf-8")
    bundle = build_t3_bridge_bundle(build_client_launch_plan(runtime_dir=runtime_dir))
    install_t3_bridge_bundle(t3_root, bundle)
    return t3_root


def _run_generated_paper_request(
    t3_root: Path,
    base_url: str,
    paper_root: Path,
) -> dict[str, object]:
    probe_path = t3_root / "paper-request-probe.ts"
    request = {
        "projectId": str(paper_root),
        "target": "rdpaper",
        "goal": "Run the bounded local synthetic paper review vertical.",
        "proposedBy": "rd-code-paper-e2e",
    }
    probe_path.write_text(
        "import { startDevFrameCoordinatorGoal,\n"
        "  type DevFrameCoordinatorGoalRequest }\n"
        '  from "./apps/web/src/devframe/devframeShellBridge.ts";\n\n'
        f"const config = {{ controlPlaneBaseUrl: {json.dumps(base_url)} }};\n"
        f"const request: DevFrameCoordinatorGoalRequest = {json.dumps(request)};\n"
        "const started = await startDevFrameCoordinatorGoal(config, request);\n"
        "console.log(JSON.stringify(started));\n",
        encoding="utf-8",
    )
    node = shutil.which("node")
    assert node is not None, (
        "Node.js is required for the generated RD-Code bridge probe"
    )
    completed = subprocess.run(
        [node, str(probe_path)],
        cwd=t3_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(completed.stdout)


def _get_json(base_url: str, path: str) -> dict[str, object]:
    with urlopen(f"{base_url}{path}", timeout=10) as response:
        assert response.status == 200
        return json.loads(response.read())


def _wait_for_paper_run(
    base_url: str,
    run_id: object,
) -> dict[str, object]:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        runs = _get_json(base_url, "/api/t3/cluster-runs")["runs"]
        record = next(
            (item for item in runs if item.get("runId") == run_id),
            None,
        )
        if record and record.get("status") in {"review_pending", "failed", "cancelled"}:
            return record
        time.sleep(0.05)
    raise AssertionError(
        f"paper run did not reach a durable terminal boundary: {run_id}"
    )


def _wait_for_paper_thread(
    base_url: str,
    paper_run_id: object,
    session_status: str,
) -> tuple[dict[str, object], dict[str, object]]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        shell = _get_json(base_url, "/t3-shell.json")
        thread = next(
            (
                item
                for item in shell["t3"]["threads"]
                if item.get("devframe", {}).get("runId") == paper_run_id
            ),
            None,
        )
        if thread and thread["session"]["status"] == session_status:
            return shell, thread
        time.sleep(0.05)
    raise AssertionError(
        f"paper thread did not reach session status {session_status}: {paper_run_id}"
    )


def _review_artifact(paper_root: Path) -> dict[str, object]:
    evidence_pack = paper_root / "evidence" / "ref-paper-review-pack.zip"
    return {
        "REVIEW_RUN_ID": "independent-rdcode-paper-e2e-reviewer",
        "template_version": "gpt-review-template-v1",
        "task_type": "paper_revision_review",
        "review_stage": "closure",
        "overall_judgment": "accepted",
        "reviewer_type": "agent",
        "evidence_pack": {
            "path": "evidence/ref-paper-review-pack.zip",
            "sha256": hashlib.sha256(evidence_pack.read_bytes()).hexdigest(),
            "manifest_valid": True,
        },
        "evidence_inspected": [
            {
                "path": relative,
                "sha256": hashlib.sha256(
                    (paper_root / relative).read_bytes()
                ).hexdigest(),
                "inspected": True,
                "role": "paper_execution_evidence",
            }
            for relative in REQUIRED_REVIEW_EVIDENCE
        ],
        "blocking_reasons": [],
        "missing_evidence": [],
        "scope_violation": False,
        "fake_green_risk": False,
        "safety_boundaries_respected": True,
        "required_next_action": "none",
        "allow_proceed": True,
        "rationale": "Independent identity verified the bounded synthetic paper evidence.",
        "created_at": "2026-07-23T00:00:00Z",
        "next_task_authorization": {
            "task_id": "close-rdcode-paper-e2e",
            "authorized": "已授权",
            "execute_immediately": "否",
            "ask_before_starting": "是",
        },
        "task_type_specific": {"paper_revision_review": {}},
    }


@contextmanager
def _running_dashboard(
    runtime_dir: Path,
    paper_root: Path,
):
    server: ThreadingHTTPServer = build_dashboard_server(
        runtime_dir=runtime_dir,
        paper_project_dirs=[paper_root],
        host="127.0.0.1",
        port=0,
        refresh_seconds=0,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_rdcode_paper_vertical_reaches_review_finalize_and_terminal_detail(
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / "runtime"
    paper_root = tmp_path / "task-owned-paper"
    assert cmd_init("paper_iteration", str(paper_root)) == 0
    t3_root = _install_generated_bridge(tmp_path, runtime_dir)

    with _running_dashboard(runtime_dir, paper_root) as base_url:
        started = _run_generated_paper_request(t3_root, base_url, paper_root)
        assert started["started"] is True
        assert started["target"] == "rdpaper"

        cluster_record = _wait_for_paper_run(base_url, started["runId"])
        assert cluster_record["kind"] == "paper"
        assert cluster_record["status"] == "review_pending"
        assert cluster_record["status"] not in {"completed", "succeeded", "passed"}
        assert cluster_record["paperRunId"]
        evidence_paths = {Path(path) for path in cluster_record["evidenceRefs"]}
        assert {
            paper_root / relative for relative in REQUIRED_REVIEW_EVIDENCE
        } <= evidence_paths
        assert all(path.is_file() for path in evidence_paths)
        flow = json.loads(
            (paper_root / "closure" / "FLOW_OUTCOME.json").read_text(
                encoding="utf-8"
            )
        )
        assert list(flow["stages"]) == [
            "project_init",
            "load_input",
            "paper_review",
            "build_evidence_pack",
            "pre_submission_check",
            "submission_dry_run",
            "closure",
        ]
        assert set(flow["stages"].values()) == {"completed"}
        assert (paper_root / "input" / "SYNTHETIC_PAPER.md").is_file()
        assert (paper_root / "input" / "SYNTHETIC_REFERENCES.yaml").is_file()
        evidence_hashes = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in evidence_paths
        }

        _, review_pending_thread = _wait_for_paper_thread(
            base_url,
            cluster_record["paperRunId"],
            "ready",
        )

        external_review = tmp_path / "independent-review.json"
        external_review.write_text(
            json.dumps(_review_artifact(paper_root), indent=2) + "\n",
            encoding="utf-8",
        )
        review_sha256 = hashlib.sha256(external_review.read_bytes()).hexdigest()
        finalization = finalize_paper_project(
            paper_root,
            external_review,
            review_sha256,
            "independent-rdcode-paper-e2e-reviewer",
        )
        assert finalization.passed, finalization.errors

        final_verdict_path = paper_root / "closure" / "FINAL_VERDICT.json"
        final_verdict = json.loads(final_verdict_path.read_text(encoding="utf-8"))
        assert final_verdict["final_state"] == "accepted_with_limitation"
        assert (
            final_verdict["reviewer_summary"]["reviewer_id"]
            == "independent-rdcode-paper-e2e-reviewer"
        )
        assert (paper_root / "governance" / "INDEPENDENT_REVIEW.json").is_file()
        assert (paper_root / "governance" / "REVIEW_GATE.json").is_file()

        final_shell, final_thread = _wait_for_paper_thread(
            base_url,
            cluster_record["paperRunId"],
            "stopped",
        )
        final_detail = next(
            item
            for item in final_shell["t3"]["threadDetails"]
            if item["id"] == final_thread["id"]
        )
        final_refs = {
            item["refPath"] for item in final_thread["devframe"]["evidenceRefs"]
        }
        team_evidence_refs = {
            item["refPath"]
            for item in final_shell["devframe"]["team"]["evidenceStore"]
            if item.get("runId") == cluster_record["paperRunId"]
        }
        assert "accepted_with_limitation" in final_thread["devframe"]["diffSummary"]
        assert final_detail["activities"]
        assert any(path.endswith("INDEPENDENT_REVIEW.json") for path in final_refs)
        assert any(path.endswith("FINAL_VERDICT.json") for path in team_evidence_refs)

        verdict_bytes = final_verdict_path.read_bytes()
        duplicate = finalize_paper_project(
            paper_root,
            external_review,
            review_sha256,
            "independent-rdcode-paper-e2e-reviewer",
        )
        assert not duplicate.passed
        assert final_verdict_path.read_bytes() == verdict_bytes
        assert {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in evidence_paths
        } == evidence_hashes
