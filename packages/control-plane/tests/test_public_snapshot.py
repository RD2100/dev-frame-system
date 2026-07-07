from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import uuid

from jsonschema import Draft7Validator
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
    "docs/status/release-readiness.md",
    "docs/status/reviewer-index.md",
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
    "packages/control-plane/control_plane/runtime_digest.py",
    "packages/control-plane/control_plane/runtime_store.py",
    "packages/control-plane/control_plane/visual_state.py",
    "packages/control-plane/control_plane/worker.py",
    "packages/control-plane/tests/test_cli.py",
    "packages/control-plane/tests/test_docs_drift_validator.py",
    "packages/control-plane/tests/test_public_snapshot.py",
    "packages/control-plane/tests/test_rdgoal.py",
    "pytest.ini",
    "rules/orchestration.md",
    "rules/project-contracts/_template.md",
    "rules/web-ai-adapters.md",
    "schemas/project_contract.schema.json",
    "schemas/rdgoal_dispatch_packet.schema.json",
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
    REPO_ROOT / "rules" / "web-ai-adapters.md",
]
DOC_LINK_CHECK_MARKDOWN_DOCS = [
    REPO_ROOT / "docs" / "README.md",
    REPO_ROOT / "docs" / "status" / "status-document-inventory.md",
    REPO_ROOT / "docs" / "status" / "reviewer-index.md",
    REPO_ROOT / "docs" / "status" / "release-readiness.md",
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
            "Prepare dashboard dispatch.",
            "-Changed",
            "-Dashboard",
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
    assert 'code "Prepare dashboard dispatch."' in prepare_args
    assert "--changed" in prepare_args
    assert "--dashboard" in prepare_args
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
            "pending PR/CI and publication evidence",
        ],
    }

    for path, literals in expected.items():
        text = path.read_text(encoding="utf-8-sig")
        missing = [literal for literal in literals if literal not in text]
        assert missing == [], f"{path} missing P3-2 local-review/release-readiness literals: {missing}"


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
        REPO_ROOT / "docs" / "agent-runtime" / "negative-test-fixtures" / "NEG-024-path-traversal-read.json",
        REPO_ROOT / "docs" / "agent-runtime" / "negative-test-fixtures" / "NEG-017-write-outside-scope.json",
        REPO_ROOT / "docs" / "agent-runtime" / "integration-contracts.md",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8-sig")
        for pattern in forbidden:
            assert pattern not in text, f"{path} contains private path pattern {pattern!r}"
