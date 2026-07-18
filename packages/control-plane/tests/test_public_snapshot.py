from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import uuid

from jsonschema import Draft7Validator, Draft202012Validator
import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
CONTROL_PLANE_TEMPLATES = REPO_ROOT / "packages" / "control-plane" / "templates"
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release-verify.yml"
REVIEWER_INDEX_REQUIRED_PATHS = [
    "README.md",
    "README.zh-CN.md",
    ".github/workflows/release-verify.yml",
    "docs/agent-runtime/rdgoal-total-control.md",
    "docs/agent-runtime/dispatch-model-profiles.md",
    "docs/agent-runtime/rdpaper-workflow.md",
    "docs/agent-runtime/visual-control-plane.md",
    "docs/agent-runtime/web-ai-adapter-contract.md",
    "docs/status/LAUNCH_NOW.md",
    "docs/status/release-readiness.md",
    "docs/status/reviewer-index.md",
    "docs/status/runtime-governance-batch-a-contract-completion.md",
    "docs/status/runtime-governance-batch-b-read-only-run-index.md",
    "docs/status/runtime-governance-batch-c-rdreview-prepare-only.md",
    "docs/status/runtime-governance-batch-d-independent-gate.md",
    "docs/status/runtime-governance-batch-e-workflow-review-pending.md",
    "docs/status/runtime-governance-batch-e-paper-trust-fail-closed.md",
    "docs/status/runtime-governance-batch-e-explicit-team-evidence-events.md",
    "docs/status/runtime-governance-batch-e-team-context-refs.md",
    "docs/status/runtime-governance-batch-e-team-review-verdict-events.md",
    "docs/status/runtime-governance-batch-e-go-evidence-team-runtime-finalization.md",
    "docs/status/runtime-governance-batch-e-final-verdict-lifecycle.md",
    "docs/status/runtime-governance-batch-e-final-verdict-supersession-projection.md",
    "docs/status/runtime-governance-batch-e-atgo-runtime-finalize-command.md",
    "docs/status/runtime-governance-batch-e-atgo-prepare-finalizer-metadata.md",
    "docs/status/runtime-governance-batch-e-chain-evidence-schema-compatibility.md",
    "docs/status/runtime-governance-batch-e-ai-workflow-hub-chain-evidence-classification.md",
    "docs/status/runtime-governance-status-vocabulary-inventory.md",
    "packages/control-plane/README.md",
    "packages/control-plane/QUICKSTART.md",
    "packages/control-plane/setup.py",
    "packages/control-plane/control_plane/cli/app.py",
    "packages/control-plane/control_plane/dashboard.py",
    "packages/control-plane/templates/paper_iteration/PAPER_PROFILE.yaml",
    "packages/control-plane/templates/paper_iteration/PAPER_STATE.yaml",
    "packages/control-plane/templates/visual_control_plane/CONTROL_PLANE_STATE.yaml",
    "packages/control-plane/templates/paper_iteration/WEB_AI_ADAPTER.yaml",
    "packages/control-plane/control_plane/agent_adapter.py",
    "packages/control-plane/control_plane/backup_guard.py",
    "packages/control-plane/control_plane/decision_engine.py",
    "packages/control-plane/control_plane/dispatch_packet.py",
    "packages/control-plane/control_plane/docs_drift_validator.py",
    "packages/control-plane/control_plane/orchestrator.py",
    "packages/control-plane/control_plane/project_contract.py",
    "packages/control-plane/control_plane/rdgoal.py",
    "packages/control-plane/control_plane/rdgoal_cli.py",
    "packages/control-plane/control_plane/rdreview.py",
    "packages/control-plane/control_plane/evidence_gate.py",
    "packages/control-plane/control_plane/runtime_digest.py",
    "packages/control-plane/control_plane/runtime_store.py",
    "packages/control-plane/control_plane/visual_state.py",
    "packages/control-plane/control_plane/worker.py",
    "packages/control-plane/tests/test_cli.py",
    "packages/control-plane/tests/test_docs_drift_validator.py",
    "packages/control-plane/tests/test_public_snapshot.py",
    "packages/control-plane/tests/test_rdgoal.py",
    "packages/control-plane/tests/test_rdreview.py",
    "packages/control-plane/tests/test_evidence_gate.py",
    "tests/test_go_evidence.py",
    "tools/go_evidence.py",
    "pytest.ini",
    "rules/orchestration.md",
    "rules/project-contracts/_template.md",
    "rules/web-ai-adapters.md",
    "schemas/project_contract.schema.json",
    "schemas/rdgoal_dispatch_packet.schema.json",
    "schemas/runtime-governance/context-packet.schema.json",
    "schemas/runtime-governance/context-ledger.schema.json",
    "schemas/runtime-governance/run-record.schema.json",
    "packages/test-frame/schemas/runtime-governance/context-packet.schema.json",
    "packages/test-frame/schemas/runtime-governance/context-ledger.schema.json",
    "packages/test-frame/schemas/runtime-governance/run-record.schema.json",
    "schemas/examples/runtime-governance/context-packet-valid.json",
    "schemas/examples/runtime-governance/context-packet-stale-valid.json",
    "schemas/examples/runtime-governance/context-ledger-valid.json",
    "schemas/examples/runtime-governance/context-packet-worker-final-ready-invalid.json",
    "schemas/examples/runtime-governance/context-packet-text-final-ready-invalid.json",
    "schemas/examples/runtime-governance/context-ledger-mutable-invalid.json",
    "schemas/examples/runtime-governance/run-record-review-pending-valid.json",
    "schemas/examples/runtime-governance/run-record-worker-final-ready-invalid.json",
    "schemas/examples/runtime-governance/run-record-gate-pass-missing-evidence-invalid.json",
    "schemas/examples/runtime-governance/run-record-executor-review-invalid.json",
    "schemas/examples/runtime-governance/run-record-executor-final-verdict-invalid.json",
    "schemas/examples/runtime-governance/run-record-projection-completed-invalid.json",
    "schemas/examples/runtime-governance/run-record-projection-completed-projection-only-valid.json",
    "schemas/examples/runtime-governance/run-record-test-frame-passed-missing-context-invalid.json",
    "schemas/examples/runtime-governance/run-record-test-frame-code-review-pass-missing-review-invalid.json",
    "schemas/examples/runtime-governance/run-record-final-report-pass-missing-final-verdict-invalid.json",
    "schemas/examples/runtime-governance/run-record-paper-human-required-valid.json",
    "schemas/examples/runtime-governance/run-record-paper-blocked-chain-trusted-valid.json",
    "schemas/examples/runtime-governance/run-record-unknown-domain-status-valid.json",
    "schemas/visual_control_plane_state.schema.json",
    "schemas/web_ai_adapter.schema.json",
    "scripts/verify-control-plane-wheel.ps1",
    "scripts/verify-public-snapshot.ps1",
    "scripts/verify-release.ps1",
]
PUBLIC_MARKDOWN_DOCS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "README.zh-CN.md",
    REPO_ROOT / "packages" / "control-plane" / "QUICKSTART.md",
    REPO_ROOT / "packages" / "control-plane" / "README.md",
    REPO_ROOT / "docs" / "agent-runtime" / "rdgoal-total-control.md",
    REPO_ROOT / "docs" / "agent-runtime" / "dispatch-model-profiles.md",
    REPO_ROOT / "docs" / "agent-runtime" / "rdpaper-workflow.md",
    REPO_ROOT / "docs" / "agent-runtime" / "visual-control-plane.md",
    REPO_ROOT / "docs" / "agent-runtime" / "web-ai-adapter-contract.md",
    REPO_ROOT / "docs" / "agent-runtime" / "runtime-invariants.md",
    REPO_ROOT / "docs" / "agent-runtime" / "project-local-skill-bindings.md",
    REPO_ROOT / "docs" / "status" / "release-readiness.md",
    REPO_ROOT / "docs" / "status" / "reviewer-index.md",
    REPO_ROOT / "docs" / "status" / "runtime-governance-batch-a-contract-completion.md",
    REPO_ROOT / "docs" / "status" / "runtime-governance-status-vocabulary-inventory.md",
    REPO_ROOT / "rules" / "web-ai-adapters.md",
]
DOC_LINK_CHECK_MARKDOWN_DOCS = [
    REPO_ROOT / "docs" / "README.md",
    REPO_ROOT / "docs" / "status" / "status-document-inventory.md",
    REPO_ROOT / "docs" / "status" / "reviewer-index.md",
    REPO_ROOT / "docs" / "status" / "release-readiness.md",
    REPO_ROOT / "docs" / "status" / "review-governance-kernel-completion-20260706.md",
    REPO_ROOT / "docs" / "status" / "runtime-governance-batch-a-contract-completion.md",
    REPO_ROOT / "docs" / "status" / "runtime-governance-status-vocabulary-inventory.md",
]
LIFECYCLE_REQUIRED_STATUS_DOCS = [
    REPO_ROOT / "docs" / "status" / "status-document-inventory.md",
    REPO_ROOT / "docs" / "status" / "governance-spine-and-document-coordination.md",
    REPO_ROOT / "docs" / "status" / "reviewer-index.md",
    REPO_ROOT / "docs" / "status" / "release-readiness.md",
    REPO_ROOT / "docs" / "status" / "workflow-consolidation-and-command-plan.md",
    REPO_ROOT / "docs" / "status" / "context-management-architecture-plan.md",
    REPO_ROOT / "docs" / "status" / "context-led-model-performance-control-plan.md",
    REPO_ROOT / "docs" / "status" / "runtime-governance-batch-a-contract-completion.md",
    REPO_ROOT / "docs" / "status" / "runtime-governance-status-vocabulary-inventory.md",
    REPO_ROOT / "docs" / "status" / "documentation-management-audit-and-plan.md",
    REPO_ROOT / "docs" / "status" / "documentation-management-detailed-rollout-plan.md",
    REPO_ROOT / "docs" / "status" / "review-governance-kernel-completion-20260706.md",
]
MARKDOWN_LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
FENCED_CODE_BLOCK_PATTERN = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_PATTERN = re.compile(r"`[^`\n]*`")


def _relative_markdown_links_from_text(text):
    text = FENCED_CODE_BLOCK_PATTERN.sub("", text)
    text = INLINE_CODE_PATTERN.sub("", text)
    for match in MARKDOWN_LINK_PATTERN.finditer(text):
        target = match.group(1).strip()
        if not target:
            continue
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1].strip()
        elif " " in target:
            target = target.split()[0]
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = target.split("#", 1)[0].strip()
        if target:
            yield target


def _relative_markdown_links(path):
    text = path.read_text(encoding="utf-8-sig")
    yield from _relative_markdown_links_from_text(text)


def _json_semantics(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def test_public_snapshot_allows_python_test_caches():
    for leftover in REPO_ROOT.glob("public-snapshot-probe-*"):
        shutil.rmtree(leftover, ignore_errors=True)

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


def test_runtime_bootstrap_generates_go_wrapper(tmp_path):
    project_root = tmp_path / "demo-project"
    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(REPO_ROOT / "templates" / "runtime-bootstrap" / "bootstrap.ps1"),
            "-ProjectName",
            "demo-project",
            "-ProjectRoot",
            str(project_root),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    output = result.stdout + result.stderr
    wrapper = project_root / "tools" / "devframe-go.ps1"
    agents = project_root / "AGENTS.md"

    assert result.returncode == 0, output
    assert "[GEN] tools/devframe-go.ps1" in output
    assert wrapper.exists()
    text = wrapper.read_text(encoding="utf-8-sig")
    assert "{{PROJECT_ROOT}}" not in text
    assert str(project_root) in text
    assert '"code"' in text
    assert '"--preview"' in text
    assert '"--execute"' in text
    assert "$Prepare -and $Execute" in text
    assert "[switch]$Dashboard" not in text
    assert '"--dashboard"' not in text
    assert "& devframe @argsList" in text
    assert "tools/devframe-go.ps1" in agents.read_text(encoding="utf-8-sig")

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    capture_path = tmp_path / "devframe-args.txt"
    fake_devframe = fake_bin / "devframe.cmd"
    fake_devframe.write_text(
        f"@echo off\r\necho %* > \"{capture_path}\"\r\nexit /b 0\r\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"

    wrapper_result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(wrapper),
            "-Goal",
            "Preview wrapper dispatch.",
            "-Changed",
            "-Target",
            "src/app.py",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env=env,
    )

    captured_args = capture_path.read_text(encoding="utf-8").strip()

    assert wrapper_result.returncode == 0, wrapper_result.stdout + wrapper_result.stderr
    assert 'code "Preview wrapper dispatch."' in captured_args
    assert f"--project {project_root}" in captured_args
    assert "--agents auto" in captured_args
    assert "--target src/app.py" in captured_args
    assert "--changed" in captured_args
    assert "--preview" in captured_args
    assert "--execute" not in captured_args

    prepare_capture_path = tmp_path / "devframe-prepare-args.txt"
    fake_devframe.write_text(
        f"@echo off\r\necho %* > \"{prepare_capture_path}\"\r\nexit /b 0\r\n",
        encoding="utf-8",
    )
    prepare_result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(wrapper),
            "-Goal",
            "Prepare wrapper dispatch.",
            "-Changed",
            "-Prepare",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env=env,
    )

    prepare_args = prepare_capture_path.read_text(encoding="utf-8").strip()

    assert prepare_result.returncode == 0, prepare_result.stdout + prepare_result.stderr
    assert 'code "Prepare wrapper dispatch."' in prepare_args
    assert "--changed" in prepare_args
    assert "--dashboard" not in prepare_args
    assert "--preview" not in prepare_args
    assert "--execute" not in prepare_args

    conflict_result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(wrapper),
            "-Goal",
            "Invalid mode.",
            "-Prepare",
            "-Execute",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env=env,
    )

    assert conflict_result.returncode == 2
    assert "Use either -Prepare or -Execute" in (conflict_result.stdout + conflict_result.stderr)


def test_runtime_bootstrap_dry_run_lists_go_wrapper(tmp_path):
    project_root = tmp_path / "demo-project"
    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(REPO_ROOT / "templates" / "runtime-bootstrap" / "bootstrap.ps1"),
            "-ProjectName",
            "demo-project",
            "-ProjectRoot",
            str(project_root),
            "-DryRun",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    output = result.stdout + result.stderr

    assert result.returncode == 0, output
    assert "devframe-go.template.ps1 -> tools/devframe-go.ps1" in output
    assert not project_root.exists()


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


def test_public_snapshot_ignores_gitignored_tutti_build_outputs():
    probe_dir = (
        REPO_ROOT
        / "products"
        / "tutti"
        / "apps"
        / "desktop"
        / "build"
        / "app-runtime"
        / f"snapshot-probe-{uuid.uuid4().hex}"
    )
    probe_dir.mkdir(parents=True)
    (probe_dir / "generated.txt").write_text("ignored local build output", encoding="utf-8")
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
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)


def test_public_snapshot_ignores_empty_gitignored_tutti_build_dir():
    probe_dir = (
        REPO_ROOT
        / "products"
        / "tutti"
        / "apps"
        / "desktop"
        / "build"
        / "empty-app-runtime-probe"
    )
    probe_dir.mkdir(parents=True)
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
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)


def test_tutti_snapshot_is_external_reference_only():
    tracked = subprocess.check_output(
        ["git", "ls-files", "--", "products/tutti"],
        cwd=REPO_ROOT,
        text=True,
    ).splitlines()

    assert tracked == []
    assert not (REPO_ROOT / "scripts" / "import-tutti-snapshot.py").exists()


def test_strict_public_snapshot_rejects_tracked_product_reference(tmp_path):
    required_dirs = [
        ".github/workflows",
        "docs/agent-runtime/negative-test-fixtures",
        "docs/assets",
        "docs/status",
        "packages/agent-acceptance",
        "packages/ai-workflow-hub",
        "packages/control-plane",
        "packages/test-frame",
        "rules",
        "schemas",
        "templates/runtime-bootstrap",
    ]
    for relative in required_dirs:
        path = tmp_path / relative
        path.mkdir(parents=True, exist_ok=True)

    required_files = [
        "README.md",
        "README.zh-CN.md",
        "AGENTS.md",
        ".github/workflows/release-verify.yml",
        "docs/assets/devframe-system-banner.svg",
        "docs/module-sources.md",
        "docs/status/release-readiness.md",
        "docs/status/reviewer-index.md",
        "rules/recon.md",
        "scripts/verify-control-plane-wheel.ps1",
        "scripts/verify-public-snapshot.ps1",
        "scripts/verify-release.ps1",
    ]
    for relative in required_files:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    (tmp_path / "README.md").write_text("", encoding="utf-8")
    (tmp_path / "README.zh-CN.md").write_text("", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("rules/recon.md", encoding="utf-8")
    (tmp_path / "rules" / "README.md").write_text("recon.md", encoding="utf-8")
    (tmp_path / "rules" / "open-source-reuse.md").write_text("rules/recon.md", encoding="utf-8")
    (tmp_path / "rules" / "recon.md").write_text(
        "RULE recon-001: Recon Gate Before Write-Capable Work",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "agent-runtime" / "negative-test-fixtures" / "NEG-031-missing-recon-receipt.json").write_text(
        '{"name": "Missing Recon Receipt"}',
        encoding="utf-8",
    )
    shutil.copy2(
        REPO_ROOT / "scripts" / "verify-public-snapshot.ps1",
        tmp_path / "scripts" / "verify-public-snapshot.ps1",
    )
    product_file = tmp_path / "products" / "tutti" / "README.md"
    product_file.parent.mkdir(parents=True)
    product_file.write_text("bundled product", encoding="utf-8")

    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "products/tutti/README.md"], cwd=tmp_path, check=True)
    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(tmp_path / "scripts" / "verify-public-snapshot.ps1"),
            "-FailOnTrackedForbidden",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert "tracked bundled product: products/tutti/README.md" in result.stdout


def test_public_snapshot_rejects_root_ai_bridge_dir():
    probe_dir = REPO_ROOT / ".ai-bridge"
    probe_dir.mkdir(parents=True, exist_ok=True)
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
        assert "forbidden name: .ai-bridge" in output
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)


def test_public_snapshot_rejects_root_review_artifacts():
    bundle_dir = REPO_ROOT / f"review-bundle-probe-{uuid.uuid4().hex}"
    reply_file = REPO_ROOT / "chatgpt-review-reply.txt"
    original_reply = None
    if reply_file.exists():
        original_reply = reply_file.read_bytes()
    bundle_dir.mkdir(parents=True)
    reply_file.write_text("local review reply", encoding="utf-8")
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
        assert f"forbidden root review artifact: {bundle_dir.name}" in output
        assert "forbidden root review artifact: chatgpt-review-reply.txt" in output
    finally:
        shutil.rmtree(bundle_dir, ignore_errors=True)
        if original_reply is None:
            reply_file.unlink(missing_ok=True)
        else:
            reply_file.write_bytes(original_reply)


def test_public_snapshot_rejects_private_text_markers():
    probe_file = REPO_ROOT / f"public-snapshot-private-path-probe-{uuid.uuid4().hex}.md"
    concrete_conversation_url = (
        "https://chatgpt.com/c/" + "6a49bdcb-5bc8-83e8-875b-44d9ed0b8e26"
    )
    probe_file.write_text(
        "\n".join([
            "This public file leaked D:\\dev-frame-system in prose.",
            "This public file also leaked D:\\devframe-system in prose.",
            "This public file also leaked D:\\test-frame in prose.",
            "It also leaked C:\\Users\\RD in prose.",
            f"It also leaked {concrete_conversation_url}.",
            "It also leaked mojibake: 锟斤拷.",
        ]),
        encoding="utf-8",
    )
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
        assert probe_file.name in output
        assert "private dev-frame-system checkout path" in output
        assert "private adjacent devframe root path" in output
        assert "private RD user home path" in output
        assert "concrete ChatGPT conversation URL" in output
        assert "mojibake replacement marker" in output
    finally:
        probe_file.unlink(missing_ok=True)


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
        "D:\\dev-frame-system",
        "D:/dev-frame-system",
        "C:\\Users\\RD",
        "C:/Users/RD",
        "锛",
        "绠",
        "绋",
        "鍙",
        "丏eepSeek",
        "€?",
        "һ",
        "Ϊ",
        "ô",
        "Щ",
        "ʲ",
        "С",
        "δ",
        "ǰ",
        "ʷ",
        "¼",
        "Դ",
        "ʹ",
        "ֻ",
        "ǿ",
        "Ҫ",
        "Լ",
        "֪",
        "Ǩ",
        "װ",
        "˽",
        "ִ",
        "ָ",
        "û",
        "ÿ",
        "ı",
        "̨",
        "ƫ",
        "Ƭ",
        "Ʒ",
        "΢",
        "ţ",
        "ƽ",
        "У",
        "֤",
        "λ",
        "˵",
        "С",
        "ʧ",
        "ʿ",
        "֮",
        "ʼ",
        "ϣ",
        "λ",
        "¼",
        "ղ",
        "ܰ",
        "д",
        "δ",
        "ƫ",
        "Ư",
        "ѡ",
        "ͣ",
        "ͬ",
        "ʵ",
        "ǰ",
        "ܰ",
        "λ",
        "ֻ",
        "ֹ",
        "ÿ",
        "û",
        "ϣ",
        "΢",
        "т",
        "Ǩ",
        "֣",
        "¡",
        "ҳ",
        "Ĭ",
    ]

    for path in PUBLIC_MARKDOWN_DOCS:
        text = path.read_text(encoding="utf-8-sig")
        for marker in forbidden:
            assert marker not in text, f"{path} contains forbidden marker {marker!r}"


def test_current_entry_markdown_links_resolve_to_repo_files():
    missing = []
    for path in DOC_LINK_CHECK_MARKDOWN_DOCS:
        for target in _relative_markdown_links(path):
            if target.startswith("/"):
                resolved = REPO_ROOT / target.lstrip("/")
            else:
                resolved = path.parent / target
            if not resolved.exists():
                try:
                    resolved_label = resolved.relative_to(REPO_ROOT).as_posix()
                except ValueError:
                    resolved_label = f"outside repo: {resolved}"
                missing.append(
                    (
                        path.relative_to(REPO_ROOT).as_posix(),
                        target,
                        resolved_label,
                    )
                )

    assert missing == []


def test_current_status_entry_docs_have_lifecycle_state():
    missing = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in LIFECYCLE_REQUIRED_STATUS_DOCS
        if not re.search(r"(?m)^Lifecycle state:\s+\S", path.read_text(encoding="utf-8-sig"))
    ]

    assert missing == []


def test_runtime_governance_status_inventory_records_unsafe_promotions():
    path = REPO_ROOT / "docs" / "status" / "runtime-governance-status-vocabulary-inventory.md"
    text = path.read_text(encoding="utf-8-sig")
    required_terms = [
        "queued",
        "pending",
        "prepared",
        "ready",
        "draft",
        "started",
        "running",
        "active",
        "leased",
        "dispatched",
        "completed",
        "passed",
        "verified",
        "executed",
        "skipped",
        "warning",
        "open",
        "info",
        "missing",
        "unknown",
        "unreadable",
        "insufficient_evidence",
        "human_required",
        "waiting_for_you",
        "needs_human",
        "blocked",
        "failed",
        "fail",
        "error",
        "cancelled",
        "continue",
        "revise",
        "stop",
        "approved",
        "accepted",
        "proceed",
    ]
    required_phrases = [
        "final_ready",
        "chain_trusted",
        "fail-open legacy behavior",
        "codeReview=PASS",
        "independent review pass",
    ]

    for term in required_terms:
        assert re.search(rf"`?{re.escape(term)}`?", text), f"missing status term: {term}"
    for phrase in required_phrases:
        assert phrase in text


def test_markdown_link_check_ignores_non_file_link_shapes():
    links = list(_relative_markdown_links_from_text(
        "\n".join([
            "![image](missing-image.png)",
            "[external](https://example.com)",
            "[anchor](#local-heading)",
            "`[inline](missing-inline.md)`",
            "```",
            "[fenced](missing-fenced.md)",
            "```",
            "[local](docs/README.md#section)",
            "[titled](docs/status/reviewer-index.md \"Reviewer Index\")",
            "[angled](<docs/status/status-document-inventory.md>)",
        ])
    ))

    assert links == [
        "docs/README.md",
        "docs/status/reviewer-index.md",
        "docs/status/status-document-inventory.md",
    ]


def test_public_scripts_and_adapters_exclude_private_machine_paths():
    forbidden = [
        "C:\\Users\\RD",
        "C:/Users/RD",
        "D:\\dev-frame-system",
        "D:/dev-frame-system",
        "D:\\agent-acceptance",
        "D:/agent-acceptance",
    ]
    paths = [
        REPO_ROOT / "packages" / "agent-acceptance" / "templates" / "ci-preflight" / "install.ps1",
        REPO_ROOT / "packages" / "ai-workflow-hub" / "src" / "ai_workflow_hub" / "context_layer" / "adapters" / "zotero_web_metadata_pilot.py",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8-sig")
        for pattern in forbidden:
            assert pattern not in text, f"{path} contains private path pattern {pattern!r}"


def test_dispatch_model_profiles_doc_is_ascii_only():
    path = REPO_ROOT / "docs" / "agent-runtime" / "dispatch-model-profiles.md"
    raw = path.read_bytes()
    assert all(byte <= 127 for byte in raw), f"{path} contains non-ASCII byte"


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
    assert 'python -m pip install -e ".\\packages\\control-plane[dev]" -e ".\\packages\\ai-workflow-hub[dev]"' in run_steps
    assert release_gate_steps == [
        "powershell -ExecutionPolicy Bypass -File scripts\\verify-release.ps1",
    ]


def test_release_gate_enables_git_index_artifact_check():
    release_script = (REPO_ROOT / "scripts" / "verify-release.ps1").read_text(
        encoding="utf-8",
    )
    snapshot_script = (
        REPO_ROOT / "scripts" / "verify-public-snapshot.ps1"
    ).read_text(encoding="utf-8")

    assert "-FailOnTrackedForbidden" in release_script
    assert "tracked forbidden review artifact" in snapshot_script
    assert "tracked bundled product" in snapshot_script


def test_release_gate_runs_docs_drift_validator_through_pytest():
    release_script = (REPO_ROOT / "scripts" / "verify-release.ps1").read_text(
        encoding="utf-8",
    )
    docs_drift_test = (
        REPO_ROOT / "packages" / "control-plane" / "tests" / "test_docs_drift_validator.py"
    ).read_text(encoding="utf-8")

    assert 'Invoke-Step "pytest" "python" @("-m", "pytest", "-q")' in release_script
    assert "build_docs_drift_payload(REPO_ROOT)" in docs_drift_test
    assert "validate_docs_drift(payload)" in docs_drift_test


def test_release_readiness_documents_strict_gate_blockers():
    path = REPO_ROOT / "docs" / "status" / "release-readiness.md"
    text = path.read_text(encoding="utf-8-sig")

    assert "scripts\\verify-public-snapshot.ps1 -FailOnTrackedForbidden" in text
    assert "commit `15a9d78d` removed the tracked root review artifacts" in text
    assert "ordinary public snapshot gate and the strict" in text
    assert "`-FailOnTrackedForbidden` public snapshot gate pass" in text
    assert "public snapshot gate pass locally" in text
    assert "Commit `2725227d`" in text
    assert "status commit" in text
    assert "`bd73d6bc` received local GPT-equivalent branch-level review PASS" in text
    assert "strict snapshot gate now checks that they do not" in text
    assert "P3-2 graph projection has local GPT-equivalent review PASS" in text


def test_current_entry_docs_keep_p3_2_local_review_pass_non_release_ready():
    expected = {
        REPO_ROOT / "docs" / "README.md": [
            "local GPT-equivalent review PASS, committed in `2725227d`",
            "local branch-level review PASS at `bd73d6bc`",
            "not a release-ready record",
        ],
        REPO_ROOT / "docs" / "status" / "reviewer-index.md": [
            "local GPT-equivalent review PASS",
            "not treated as release-ready",
        ],
        REPO_ROOT / "docs" / "status" / "status-document-inventory.md": [
            "projection has local GPT-equivalent review PASS and landed in commit",
            "local branch-level review PASS at `bd73d6bc`",
            "current release route now has PR CI, main CI, merge, and GitHub Release evidence",
            "PyPI publication remains outside this repository's defined workflow",
        ],
    }

    for path, literals in expected.items():
        text = path.read_text(encoding="utf-8-sig")
        missing = [literal for literal in literals if literal not in text]
        assert missing == [], f"{path} missing P3-2 local-review/release-readiness literals: {missing}"


def test_post_release_docs_do_not_reopen_pr_publication_holds():
    launch_now = (REPO_ROOT / "docs" / "status" / "LAUNCH_NOW.md").read_text(
        encoding="utf-8-sig",
    )
    batch_map = (
        REPO_ROOT / "docs" / "status" / "current-dirty-tree-batch-map-20260708.md"
    ).read_text(encoding="utf-8-sig")

    assert "GITHUB RELEASED as `v0.1.0`" in launch_now
    assert "Post-Release Remaining Decisions" in launch_now
    assert "approve-pr-route" not in launch_now
    assert "Keep PR #4 as the review surface" not in launch_now
    assert "HOLD for merge and publication until owner approval" not in batch_map
    assert "not authorize merge or public release" not in batch_map
    assert "historical execution evidence" in batch_map
    assert "GitHub Release `v0.1.0`" in batch_map


def test_launch_now_is_frozen_release_snapshot():
    launch_now = (REPO_ROOT / "docs" / "status" / "LAUNCH_NOW.md").read_text(
        encoding="utf-8-sig",
    )

    assert "FROZEN RELEASE SNAPSHOT" in launch_now
    assert "Initial Owner-Gate Snapshot" in launch_now
    assert "historical owner-gate snapshot head, not the current" in launch_now
    assert "This was the launch-control entrypoint for the recorded release snapshot" in launch_now


def test_handoff_is_the_single_current_execution_root():
    handoff = (REPO_ROOT / "docs" / "status" / "HANDOFF.md").read_text(
        encoding="utf-8-sig",
    )
    inventory = (
        REPO_ROOT / "docs" / "status" / "status-document-inventory.md"
    ).read_text(encoding="utf-8-sig")
    docs_readme = (REPO_ROOT / "docs" / "README.md").read_text(
        encoding="utf-8-sig",
    )
    agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8-sig")
    supporting_paths = [
        REPO_ROOT / "docs" / "status" / "LAUNCH_NOW.md",
        REPO_ROOT / "docs" / "status" / "release-readiness.md",
        REPO_ROOT / "docs" / "status" / "reviewer-index.md",
    ]

    assert "CANONICAL EXECUTION ROOT" in handoff
    assert "Do not create another master plan" in handoff
    assert "| `current-entry` | `HANDOFF.md` |" in inventory
    assert "| `current-entry` | `LAUNCH_NOW.md`" not in inventory
    assert "Active plans may set direction" not in inventory
    assert "unless the master plan is updated" not in inventory
    assert "newer coordination record" not in inventory
    assert "only document that selects the active milestone" in docs_readme
    assert "## Current Planning Docs" not in docs_readme
    assert "single current execution root" in agents
    for path in supporting_paths:
        text = path.read_text(encoding="utf-8-sig")
        assert "HANDOFF.md" in text, path

    launch_now = supporting_paths[0].read_text(encoding="utf-8-sig")
    assert "## Current Decision" not in launch_now
    assert "## Next 3 Actions" not in launch_now

    for path in (REPO_ROOT / "docs" / "status").glob("*.md"):
        if path.name == "HANDOFF.md":
            continue
        text = path.read_text(encoding="utf-8-sig")
        lifecycle_lines = [
            line for line in text.splitlines()
            if line.lower().startswith("lifecycle state:")
        ]
        assert not any(
            re.search(r"\bactive\b", line, flags=re.IGNORECASE)
            for line in lifecycle_lines
        ), path


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


def test_reviewer_index_mentions_governance_validators_and_tests():
    reviewer_index = (REPO_ROOT / "docs" / "status" / "reviewer-index.md").read_text(
        encoding="utf-8",
    )
    source_dir = REPO_ROOT / "packages" / "control-plane" / "control_plane"
    tests_dir = REPO_ROOT / "packages" / "control-plane" / "tests"
    source_files = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in source_dir.glob("*validator.py")
    )
    source_files.append(
        "packages/control-plane/control_plane/client_governance_projection.py"
    )
    source_files.append("packages/control-plane/control_plane/document_authority.py")
    test_files = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in tests_dir.glob("test_*validator.py")
    )
    test_files.append(
        "packages/control-plane/tests/test_client_governance_projection.py"
    )
    test_files.append("packages/control-plane/tests/test_document_authority.py")

    missing = [
        path
        for path in sorted(set(source_files + test_files))
        if path not in reviewer_index
    ]
    assert missing == []


def test_default_web_ai_adapter_template_matches_schema():
    schema = json.loads((REPO_ROOT / "schemas" / "web_ai_adapter.schema.json").read_text(encoding="utf-8"))
    template = yaml.safe_load(
        (
            REPO_ROOT
            / "packages"
            / "control-plane"
            / "templates"
            / "paper_iteration"
            / "WEB_AI_ADAPTER.yaml"
        ).read_text(encoding="utf-8")
    )

    Draft7Validator.check_schema(schema)
    Draft7Validator(schema).validate(template)
    assert template["browser"]["provider"] == "chrome"
    assert template["web_ai"]["provider"] == "chatgpt"
    assert template["safety"]["allow_browser_profile_export"] is False
    assert template["manual_fallback"]["enabled"] is True


def test_paper_iteration_metadata_templates_parse_as_yaml():
    template_dir = REPO_ROOT / "packages" / "control-plane" / "templates" / "paper_iteration"

    profile = yaml.safe_load((template_dir / "PAPER_PROFILE.yaml").read_text(encoding="utf-8"))
    state = yaml.safe_load((template_dir / "PAPER_STATE.yaml").read_text(encoding="utf-8"))

    assert profile["paper_id"] == "{{PAPER_ID}}"
    assert profile["title"] == "{{PAPER_TITLE}}"
    assert profile["versions"][0]["date"] == "{{DATE}}"
    assert state["paper_id"] == "{{PAPER_ID}}"
    assert state["status"] == "initialized"


def test_default_visual_control_plane_state_template_matches_schema():
    schema = json.loads((REPO_ROOT / "schemas" / "visual_control_plane_state.schema.json").read_text(encoding="utf-8"))
    template = yaml.safe_load(
        (
            REPO_ROOT
            / "packages"
            / "control-plane"
            / "templates"
            / "visual_control_plane"
            / "CONTROL_PLANE_STATE.yaml"
        ).read_text(encoding="utf-8")
    )

    Draft7Validator.check_schema(schema)
    Draft7Validator(schema).validate(template)
    assert template["provider_bindings"][0]["provider"] == "chatgpt"
    assert template["provider_bindings"][0]["manual_fallback_instructions"][0].startswith("Prepare")
    assert {agent["role"] for agent in template["agents"]} == {"coordinator", "reviewer"}
    assert template["runs"][0]["entrypoint"] == "rdgoal"
    assert template["gates"][0]["next_action"].startswith("Confirm human approval")
    assert template["next_actions"][0]["source_id"] == "human-gate"
    assert template["next_actions"][0]["status"] == "open"
    assert template["safety"]["raw_transcripts_persisted"] is False
    assert template["safety"]["remote_execution_default"] is False
    assert "secret_exposure" in template["safety"]["human_gate_required_for"]


def test_runtime_governance_schemas_validate_fixtures():
    cases = [
        (
            REPO_ROOT / "schemas" / "runtime-governance" / "context-packet.schema.json",
            [
                REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "context-packet-valid.json",
                REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "context-packet-stale-valid.json",
            ],
            [
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "context-packet-worker-final-ready-invalid.json",
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "context-packet-text-final-ready-invalid.json",
            ],
        ),
        (
            REPO_ROOT / "schemas" / "runtime-governance" / "context-ledger.schema.json",
            [
                REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "context-ledger-valid.json",
            ],
            [
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "context-ledger-mutable-invalid.json",
            ],
        ),
        (
            REPO_ROOT / "schemas" / "runtime-governance" / "run-record.schema.json",
            [
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-review-pending-valid.json",
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-paper-human-required-valid.json",
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-paper-blocked-chain-trusted-valid.json",
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-unknown-domain-status-valid.json",
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-projection-completed-projection-only-valid.json",
            ],
            [
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-worker-final-ready-invalid.json",
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-gate-pass-missing-evidence-invalid.json",
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-executor-review-invalid.json",
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-executor-final-verdict-invalid.json",
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-projection-completed-invalid.json",
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-test-frame-passed-missing-context-invalid.json",
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-test-frame-code-review-pass-missing-review-invalid.json",
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-final-report-pass-missing-final-verdict-invalid.json",
            ],
        ),
    ]

    for schema_path, valid_paths, invalid_paths in cases:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        for fixture_path in valid_paths:
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
            validator.validate(fixture)
            if "constraints" in fixture:
                assert fixture["constraints"]["authority_boundary"]["can_claim_final_acceptance"] is False
            if "entries" in fixture:
                previous_hash = None
                for expected_index, entry in enumerate(fixture["entries"]):
                    assert entry["entry_index"] == expected_index
                    assert entry["previous_entry_hash"] == previous_hash
                    previous_hash = entry["entry_hash"]
            if "acceptance_state" in fixture:
                assert fixture["acceptance_state"] != "final_ready"
                if fixture_path.name == "run-record-review-pending-valid.json":
                    assert fixture["outcome"] == "passed"
                    assert fixture["review_state"] == "review_pending"
        for fixture_path in invalid_paths:
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
            errors = sorted(validator.iter_errors(fixture), key=lambda error: list(error.path))
            assert errors, f"{fixture_path} should fail {schema_path.name}"
        if schema_path.name == "context-packet.schema.json":
            uppercase_bypass = json.loads(valid_paths[0].read_text(encoding="utf-8"))
            uppercase_bypass["constraints"]["allowed_actions"] = ["CLAIM FINAL_READY"]
            errors = sorted(
                validator.iter_errors(uppercase_bypass),
                key=lambda error: list(error.path),
            )
            assert errors, "allowed_actions must reject uppercase final acceptance claims"
        if schema_path.name == "run-record.schema.json":
            final_ready_without_verdict = json.loads(valid_paths[0].read_text(encoding="utf-8"))
            final_ready_without_verdict["acceptance_state"] = "final_ready"
            final_ready_without_verdict["review_state"] = "review_passed"
            final_ready_without_verdict["gate_state"] = "gate_passed"
            errors = sorted(
                validator.iter_errors(final_ready_without_verdict),
                key=lambda error: list(error.path),
            )
            assert errors, "final_ready must require FinalVerdict, review, and gate evidence"
            review_passed_with_blocked_review = json.loads(valid_paths[0].read_text(encoding="utf-8"))
            review_passed_with_blocked_review["review_state"] = "review_passed"
            review_passed_with_blocked_review["review_refs"] = [
                {
                    "review_id": "review-blocked",
                    "reviewer_id": "reviewer-1",
                    "reviewer_role": "reviewer",
                    "verdict": "blocked",
                    "uri": "reviews/blocked.yaml",
                    "reviewed_evidence_refs": ["e-runrecord-schema"],
                }
            ]
            errors = sorted(
                validator.iter_errors(review_passed_with_blocked_review),
                key=lambda error: list(error.path),
            )
            assert errors, "review_passed must require a pass review ref"
            gate_passed_with_warning_gate = json.loads(valid_paths[0].read_text(encoding="utf-8"))
            gate_passed_with_warning_gate["gate_state"] = "gate_passed"
            gate_passed_with_warning_gate["gate_refs"] = [
                {
                    "gate_id": "gate-warning",
                    "result": "warning",
                    "uri": "reports/gate-warning.json",
                    "evidence_refs": [],
                }
            ]
            errors = sorted(
                validator.iter_errors(gate_passed_with_warning_gate),
                key=lambda error: list(error.path),
            )
            assert errors, "gate_passed must require a pass gate ref"


def test_runtime_governance_required_negative_case_fixtures_are_present():
    fixture_dir = REPO_ROOT / "schemas" / "examples" / "runtime-governance"
    expected = {
        "worker succeeded with no review": (
            "run-record-review-pending-valid.json",
            ["succeeded", "review_pending"],
        ),
        "gate pass with no evidence": (
            "run-record-gate-pass-missing-evidence-invalid.json",
            ["gate_passed", '"evidence_refs": []'],
        ),
        "final report pass missing final verdict": (
            "run-record-final-report-pass-missing-final-verdict-invalid.json",
            ["final_report_text", "PASS"],
        ),
        "executor authored review": (
            "run-record-executor-review-invalid.json",
            ['"reviewer_role": "executor"'],
        ),
        "test-frame passed missing context": (
            "run-record-test-frame-passed-missing-context-invalid.json",
            ["aggregate_status", "passed"],
        ),
        "test-frame codeReview pass missing review": (
            "run-record-test-frame-code-review-pass-missing-review-invalid.json",
            ["codeReview", "PASS"],
        ),
        "paper completed human required": (
            "run-record-paper-human-required-valid.json",
            ["acceptance_status", "human_required"],
        ),
        "paper blocked chain trusted": (
            "run-record-paper-blocked-chain-trusted-valid.json",
            ["chain_trusted", "blocked"],
        ),
        "unknown domain status": (
            "run-record-unknown-domain-status-valid.json",
            ["legacy_status", "mystery_done"],
        ),
        "projection completed without source authority": (
            "run-record-projection-completed-projection-only-valid.json",
            ['"projection_state": "completed"', '"acceptance_state": "review_pending"'],
        ),
        "stale context": (
            "context-packet-stale-valid.json",
            ["stale_refs", "blocks_acceptance"],
        ),
    }

    for label, (filename, literals) in expected.items():
        path = fixture_dir / filename
        assert path.exists(), f"missing runtime-governance fixture for {label}: {filename}"
        text = path.read_text(encoding="utf-8-sig")
        missing = [literal for literal in literals if literal not in text]
        assert missing == [], f"{filename} missing coverage literals for {label}: {missing}"

    parsed = {
        filename: json.loads((fixture_dir / filename).read_text(encoding="utf-8-sig"))
        for filename, _literals in expected.values()
    }
    assert parsed["run-record-review-pending-valid.json"]["worker_results"][0]["status"] == "succeeded"
    assert parsed["run-record-review-pending-valid.json"]["acceptance_state"] == "review_pending"
    assert "context_packet_id" not in parsed["run-record-test-frame-passed-missing-context-invalid.json"]
    assert parsed["run-record-test-frame-code-review-pass-missing-review-invalid.json"]["review_refs"] == []
    assert parsed["run-record-final-report-pass-missing-final-verdict-invalid.json"]["acceptance_state"] == "final_ready"
    assert "final_verdict_ref" not in parsed["run-record-final-report-pass-missing-final-verdict-invalid.json"]
    paper_human_required = parsed["run-record-paper-human-required-valid.json"]
    assert paper_human_required["outcome"] == "human_required"
    assert paper_human_required["acceptance_state"] == "blocked"
    paper_chain_trusted = parsed["run-record-paper-blocked-chain-trusted-valid.json"]
    assert paper_chain_trusted["domain_refs"]["chain_trusted"] is True
    assert paper_chain_trusted["outcome"] == "blocked"
    assert paper_chain_trusted["acceptance_state"] == "blocked"
    unknown_status = parsed["run-record-unknown-domain-status-valid.json"]
    assert unknown_status["outcome"] == "unknown"
    assert unknown_status["projection_state"] == "unknown"
    projection_only = parsed["run-record-projection-completed-projection-only-valid.json"]
    assert projection_only["projection_state"] == "completed"
    assert projection_only["acceptance_state"] == "review_pending"
    stale_context = parsed["context-packet-stale-valid.json"]
    assert stale_context["completeness_state"] == "insufficient_evidence"
    assert stale_context["omitted_required_refs"][0]["impact"] == "blocks_acceptance"


def test_runtime_governance_schema_mirrors_match_semantically():
    pairs = [
        (
            REPO_ROOT / "schemas" / "runtime-governance" / "context-packet.schema.json",
            REPO_ROOT
            / "packages"
            / "test-frame"
            / "schemas"
            / "runtime-governance"
            / "context-packet.schema.json",
        ),
        (
            REPO_ROOT / "schemas" / "runtime-governance" / "context-ledger.schema.json",
            REPO_ROOT
            / "packages"
            / "test-frame"
            / "schemas"
            / "runtime-governance"
            / "context-ledger.schema.json",
        ),
        (
            REPO_ROOT / "schemas" / "runtime-governance" / "run-record.schema.json",
            REPO_ROOT
            / "packages"
            / "test-frame"
            / "schemas"
            / "runtime-governance"
            / "run-record.schema.json",
        ),
    ]

    for root_path, mirror_path in pairs:
        root_semantics = _json_semantics(root_path)
        mirror_semantics = _json_semantics(mirror_path)
        assert mirror_semantics == root_semantics

        drift_probe = json.loads(json.dumps(mirror_semantics))
        drift_probe["title"] = f"{drift_probe.get('title', '')} drift"
        assert drift_probe != root_semantics


def test_agent_runtime_chain_evidence_schema_mirror_matches_semantically():
    root_path = REPO_ROOT / "schemas" / "agent-runtime" / "chain-evidence.schema.json"
    mirror_path = (
        REPO_ROOT
        / "packages"
        / "test-frame"
        / "schemas"
        / "agent-runtime"
        / "chain-evidence.schema.json"
    )

    root_semantics = _json_semantics(root_path)
    mirror_semantics = _json_semantics(mirror_path)
    assert mirror_semantics == root_semantics


def test_chain_evidence_schema_rejects_acceptance_creating_next_command():
    schema = json.loads(
        (REPO_ROOT / "schemas" / "agent-runtime" / "chain-evidence.schema.json").read_text(
            encoding="utf-8-sig"
        )
    )
    validator = Draft202012Validator(schema)
    payload = {
        "run_id": "run-1",
        "executor_id": "executor-1",
        "mode": "prepare",
        "planner": None,
        "task": "task-spec.md",
        "methodology": None,
        "evidence_files": ["chain-evidence.json"],
        "timestamps": {"created_at": "2026-07-07T00:00:00+00:00"},
        "next_commands": {
            "finalize": {
                "command_args": ["tools/go_evidence.py", "finalize", "run"],
                "authority": "guidance_only",
                "creates_acceptance": True,
                "requires_independent_review": True,
            },
        },
    }

    errors = list(validator.iter_errors(payload))

    assert errors
    assert any(
        list(error.path) == ["next_commands", "finalize", "creates_acceptance"]
        for error in errors
    )


def _final_verdict_payload(**overrides):
    payload = {
        "verdict_id": "fv-runtime-lifecycle-v2",
        "produced_by": "devframe-system-main-coordinator",
        "produced_at": "2026-07-08T00:00:00Z",
        "producer_role": "governance",
        "final_state": "blocked",
        "inputs_reviewed": ["evidence/final-verdict-v1.json", "review/review.yaml"],
        "gate_summary": [
            {
                "gate_id": "gate-runtime-lifecycle",
                "result": "blocked",
                "evidence_path": "review/review.yaml",
            }
        ],
        "reviewer_summary": {
            "reviewer_id": "reviewer-1",
            "verdict": "blocked",
            "evidence_path": "review/review.yaml",
        },
        "limitations": ["supersedes earlier verdict after new evidence"],
        "human_or_governance_reference": "governance:runtime-lifecycle-review",
    }
    payload.update(overrides)
    return payload


def test_final_verdict_schema_supports_append_only_superseding_record():
    schema = json.loads(
        (REPO_ROOT / "schemas" / "agent-runtime" / "final-verdict.schema.json").read_text(
            encoding="utf-8-sig"
        )
    )
    validator = Draft202012Validator(schema)
    payload = _final_verdict_payload(
        supersedes={
            "verdict_id": "fv-runtime-lifecycle-v1",
            "uri": "evidence/final-verdict-v1.json",
            "reason": "New independent review evidence invalidated the earlier verdict.",
        }
    )

    validator.validate(payload)


def test_final_verdict_schema_rejects_incomplete_superseding_record():
    schema = json.loads(
        (REPO_ROOT / "schemas" / "agent-runtime" / "final-verdict.schema.json").read_text(
            encoding="utf-8-sig"
        )
    )
    validator = Draft202012Validator(schema)
    payload = _final_verdict_payload(
        supersedes={
            "verdict_id": "fv-runtime-lifecycle-v1",
            "uri": "evidence/final-verdict-v1.json",
        }
    )

    errors = list(validator.iter_errors(payload))

    assert errors
    assert any(list(error.path) == ["supersedes"] for error in errors)


def test_final_verdict_schema_keeps_blocked_producer_roles_for_superseding_record():
    schema = json.loads(
        (REPO_ROOT / "schemas" / "agent-runtime" / "final-verdict.schema.json").read_text(
            encoding="utf-8-sig"
        )
    )
    validator = Draft202012Validator(schema)
    for role in ["executor", "fixer", "coder", "worker"]:
        payload = _final_verdict_payload(
            producer_role=role,
            supersedes={
                "verdict_id": "fv-runtime-lifecycle-v1",
                "uri": "evidence/final-verdict-v1.json",
                "reason": f"{role}-authored verdict must still be rejected.",
            },
        )

        errors = list(validator.iter_errors(payload))

        assert errors
        assert any(list(error.path) == ["producer_role"] for error in errors)


def test_public_docs_mention_release_gate_and_visual_control_plane_surfaces():
    expected = {
        REPO_ROOT / "README.md": [
            ".\\scripts\\verify-release.ps1",
            "devframe visual-state --runtime-dir <dir>",
            "devframe dashboard serve --runtime-dir <dir>",
            "devframe actions --runtime-dir <dir>",
            "/actions.json",
            "/actions.md",
            "--action-id",
            "--allow-remote",
        ],
        REPO_ROOT / "README.zh-CN.md": [
            ".\\scripts\\verify-release.ps1",
            "devframe visual-state --runtime-dir <dir>",
            "devframe dashboard serve --runtime-dir <dir>",
            "devframe actions --runtime-dir <dir>",
            "/actions.json",
            "/actions.md",
            "--action-id",
            "--allow-remote",
        ],
        REPO_ROOT / "packages" / "control-plane" / "QUICKSTART.md": [
            "powershell -ExecutionPolicy Bypass -File scripts\\verify-release.ps1",
            "devframe visual-state --runtime-dir C:\\Users\\you\\.devframe-runtime",
            "devframe dashboard serve --runtime-dir C:\\Users\\you\\.devframe-runtime",
            "devframe actions --runtime-dir C:\\Users\\you\\.devframe-runtime",
            "/actions.json",
            "/actions.md",
            "--action-id",
            "--fail-on-match",
            "--allow-remote",
        ],
        REPO_ROOT / "packages" / "control-plane" / "README.md": [
            "powershell -ExecutionPolicy Bypass -File scripts\\verify-release.ps1",
            "devframe visual-state --runtime-dir C:\\Users\\you\\.devframe-runtime",
            "devframe dashboard serve --runtime-dir C:\\Users\\you\\.devframe-runtime",
            "devframe actions --runtime-dir C:\\Users\\you\\.devframe-runtime",
            "/actions.json",
            "/actions.md",
            "--action-id",
            "--fail-on-match",
            "--allow-remote",
        ],
    }

    for path, literals in expected.items():
        text = path.read_text(encoding="utf-8-sig")
        missing = [literal for literal in literals if literal not in text]
        assert missing == [], f"{path} missing documented literals: {missing}"


def test_release_readiness_mentions_action_queue_and_dashboard_safety_flags():
    path = REPO_ROOT / "docs" / "status" / "release-readiness.md"
    text = path.read_text(encoding="utf-8-sig")
    for literal in ["--action-id", "--fail-on-match", "--allow-remote"]:
        assert literal in text, f"{path} missing required literal: {literal}"


def test_public_schemas_docs_and_fixtures_exclude_private_paths():
    forbidden = [
        "C:\\Users\\RD",
        "C:/Users/RD",
        "D:\\agent-acceptance",
        "D:/agent-acceptance",
    ]
    paths = [
        REPO_ROOT / "schemas" / "resource-integration" / "script-safety-record.schema.json",
        REPO_ROOT / "schemas" / "resource-integration" / "memory-context-record.schema.json",
        REPO_ROOT / "schemas" / "resource-integration" / "codegraph-index-record.schema.json",
        REPO_ROOT / "schemas" / "agent-runtime" / "memory-update-record.schema.json",
        REPO_ROOT / "packages" / "test-frame" / "schemas" / "resource-integration" / "script-safety-record.schema.json",
        REPO_ROOT / "packages" / "test-frame" / "schemas" / "resource-integration" / "memory-context-record.schema.json",
        REPO_ROOT / "packages" / "test-frame" / "schemas" / "resource-integration" / "codegraph-index-record.schema.json",
        REPO_ROOT / "packages" / "test-frame" / "schemas" / "agent-runtime" / "memory-update-record.schema.json",
        REPO_ROOT / "schemas" / "runtime-governance" / "context-packet.schema.json",
        REPO_ROOT / "schemas" / "runtime-governance" / "context-ledger.schema.json",
        REPO_ROOT / "schemas" / "runtime-governance" / "run-record.schema.json",
        REPO_ROOT / "packages" / "test-frame" / "schemas" / "runtime-governance" / "context-packet.schema.json",
        REPO_ROOT / "packages" / "test-frame" / "schemas" / "runtime-governance" / "context-ledger.schema.json",
        REPO_ROOT / "packages" / "test-frame" / "schemas" / "runtime-governance" / "run-record.schema.json",
        REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "context-packet-valid.json",
        REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "context-packet-stale-valid.json",
        REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "context-ledger-valid.json",
        REPO_ROOT
        / "schemas"
        / "examples"
        / "runtime-governance"
        / "context-packet-worker-final-ready-invalid.json",
        REPO_ROOT
        / "schemas"
        / "examples"
        / "runtime-governance"
        / "context-packet-text-final-ready-invalid.json",
        REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "context-ledger-mutable-invalid.json",
        REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "run-record-review-pending-valid.json",
        REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "run-record-worker-final-ready-invalid.json",
        REPO_ROOT
        / "schemas"
        / "examples"
        / "runtime-governance"
        / "run-record-gate-pass-missing-evidence-invalid.json",
        REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "run-record-executor-review-invalid.json",
        REPO_ROOT
        / "schemas"
        / "examples"
        / "runtime-governance"
        / "run-record-executor-final-verdict-invalid.json",
        REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "run-record-projection-completed-invalid.json",
        REPO_ROOT
        / "schemas"
        / "examples"
        / "runtime-governance"
        / "run-record-projection-completed-projection-only-valid.json",
        REPO_ROOT
        / "schemas"
        / "examples"
        / "runtime-governance"
        / "run-record-test-frame-passed-missing-context-invalid.json",
        REPO_ROOT
        / "schemas"
        / "examples"
        / "runtime-governance"
        / "run-record-test-frame-code-review-pass-missing-review-invalid.json",
        REPO_ROOT
        / "schemas"
        / "examples"
        / "runtime-governance"
        / "run-record-final-report-pass-missing-final-verdict-invalid.json",
        REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "run-record-paper-human-required-valid.json",
        REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "run-record-paper-blocked-chain-trusted-valid.json",
        REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "run-record-unknown-domain-status-valid.json",
        REPO_ROOT / "docs" / "agent-runtime" / "negative-test-fixtures" / "NEG-024-path-traversal-read.json",
        REPO_ROOT / "docs" / "agent-runtime" / "negative-test-fixtures" / "NEG-017-write-outside-scope.json",
        REPO_ROOT / "docs" / "agent-runtime" / "integration-contracts.md",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8-sig")
        for pattern in forbidden:
            assert pattern not in text, f"{path} contains private path pattern {pattern!r}"
