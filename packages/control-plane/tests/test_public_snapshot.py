from pathlib import Path
import shutil
import subprocess
import uuid

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
CONTROL_PLANE_TEMPLATES = REPO_ROOT / "packages" / "control-plane" / "templates"
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release-verify.yml"
REVIEWER_INDEX_REQUIRED_PATHS = [
    ".github/workflows/release-verify.yml",
    "docs/agent-runtime/rdgoal-total-control.md",
    "docs/status/release-readiness.md",
    "docs/status/reviewer-index.md",
    "packages/control-plane/control_plane/agent_adapter.py",
    "packages/control-plane/control_plane/backup_guard.py",
    "packages/control-plane/control_plane/decision_engine.py",
    "packages/control-plane/control_plane/dispatch_packet.py",
    "packages/control-plane/control_plane/orchestrator.py",
    "packages/control-plane/control_plane/project_contract.py",
    "packages/control-plane/control_plane/rdgoal.py",
    "packages/control-plane/control_plane/rdgoal_cli.py",
    "packages/control-plane/control_plane/runtime_digest.py",
    "packages/control-plane/control_plane/runtime_store.py",
    "packages/control-plane/control_plane/worker.py",
    "packages/control-plane/tests/test_cli.py",
    "packages/control-plane/tests/test_public_snapshot.py",
    "packages/control-plane/tests/test_rdgoal.py",
    "pytest.ini",
    "rules/orchestration.md",
    "rules/project-contracts/_template.md",
    "schemas/project_contract.schema.json",
    "schemas/rdgoal_dispatch_packet.schema.json",
    "scripts/verify-control-plane-wheel.ps1",
    "scripts/verify-release.ps1",
]
PUBLIC_MARKDOWN_DOCS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "README.zh-CN.md",
    REPO_ROOT / "packages" / "control-plane" / "QUICKSTART.md",
    REPO_ROOT / "packages" / "control-plane" / "README.md",
    REPO_ROOT / "docs" / "agent-runtime" / "rdgoal-total-control.md",
    REPO_ROOT / "docs" / "status" / "release-readiness.md",
    REPO_ROOT / "docs" / "status" / "reviewer-index.md",
]


def test_public_snapshot_allows_python_test_caches():
    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(REPO_ROOT / "scripts" / "verify-public-snapshot.ps1"),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_public_snapshot_rejects_generated_build_dirs():
    probe_name = f"public-snapshot-probe-{uuid.uuid4().hex}"
    probe_root = REPO_ROOT / probe_name
    build_dir = probe_root / "build"
    build_dir.mkdir(parents=True)
    try:
        result = subprocess.run(
            [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(REPO_ROOT / "scripts" / "verify-public-snapshot.ps1"),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        output = result.stdout + result.stderr
        assert result.returncode == 1, output
        assert f"forbidden name: {probe_name}\\build" in output
    finally:
        shutil.rmtree(probe_root, ignore_errors=True)


def test_control_plane_packaged_templates_do_not_reference_private_paths():
    forbidden = [
        "D:\\agent-acceptance",
        "D:/agent-acceptance",
    ]

    for path in CONTROL_PLANE_TEMPLATES.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8-sig")
        for marker in forbidden:
            assert marker not in text, f"{path} contains private path {marker}"


def test_public_markdown_docs_are_utf8_and_do_not_contain_mojibake_or_private_paths():
    forbidden = [
        "D:\\agent-acceptance",
        "D:/agent-acceptance",
        "锛",
        "绋",
        "鍙",
        "丏eepSeek",
        "€?",
    ]

    for path in PUBLIC_MARKDOWN_DOCS:
        text = path.read_text(encoding="utf-8-sig")
        for marker in forbidden:
            assert marker not in text, f"{path} contains forbidden marker {marker!r}"


def test_release_workflow_installs_deps_and_invokes_single_release_gate():
    workflow = yaml.safe_load(RELEASE_WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"]["release-verify"]
    run_steps = [step["run"] for step in job["steps"] if "run" in step]
    release_gate_steps = [
        step for step in run_steps
        if "scripts\\verify-release.ps1" in step
    ]

    assert workflow["on"] == {
        "push": {"branches": ["main"]},
        "pull_request": None,
        "workflow_dispatch": None,
    }
    assert job["runs-on"] == "windows-latest"
    assert 'python -m pip install -e ".\\packages\\control-plane[dev]"' in run_steps
    assert release_gate_steps == [
        "powershell -ExecutionPolicy Bypass -File scripts\\verify-release.ps1",
    ]


def test_reviewer_index_mentions_new_public_files():
    reviewer_index = (REPO_ROOT / "docs" / "status" / "reviewer-index.md").read_text(
        encoding="utf-8",
    )
    missing = [
        path
        for path in REVIEWER_INDEX_REQUIRED_PATHS
        if path not in reviewer_index
    ]

    for path in REVIEWER_INDEX_REQUIRED_PATHS:
        assert (REPO_ROOT / path).exists(), path
    assert missing == []
