import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from control_plane.external_review_bundle import (  # noqa: E402
    BLOCKED,
    INCOMPLETE,
    READY,
    ReviewBundleError,
    ReviewSource,
    _PUBLIC_MANIFEST_SCHEMA,
    prepare_external_review_bundle,
    validate_external_review_bundle,
)


DETAIL_LOADER_FINDINGS = (
    "detail_assignment_missing_shape_guard",
    "detail_assignment_missing_identity_guard",
    "route_loader_missing_retry_context",
    "route_loader_missing_lifecycle_invalidation",
    "real_adapter_deferred_probe_missing",
)

DETAIL_LOADER_MATRIX = [
    "null_response",
    "truthy_malformed_response",
    "mismatched_requested_identity",
    "current_valid_response",
    "deep_link_loading",
    "transport_failure",
    "business_failure",
    "one_step_retry",
    "hide_invalidation",
    "unload_invalidation",
]
IDENTITY_DETAIL_PROFILE = "identity_detail_contract"
AUTH_FAIL_CLOSED_PROFILE = "auth_fail_closed_contract"
AUTH_FAIL_CLOSED_COUNTERS = ["init", "collection", "read", "write", "transaction"]


def _write_unsafe_detail_loader(project: Path, name: str = "detail-loader.ts") -> Path:
    source = project / name
    source.write_text(
        """
export class UnsafeRouteDetailPanel {
  async onRouteChanged(requestedId: string) {
    const response = await this.api.loadDetail(requestedId);
    if (response) {
      this.visibleDetail = response;
    }
  }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return source


def _write_safe_detail_loader(project: Path) -> Path:
    source = project / "detail-loader.ts"
    source.write_text(
        """
export class GuardedRouteDetailPanel {
  private generation = 0;
  private retryId: string | null = null;
  async onRouteChanged(requestedId: string) {
    const requestGeneration = ++this.generation;
    this.retryId = requestedId;
    const response = await this.api.loadDetail(requestedId);
    if (requestGeneration !== this.generation) return;
    if (isDetail(response) && response.id === requestedId) {
      this.visibleDetail = response;
    }
  }

  retry() {
    return this.retryId === null
      ? Promise.resolve()
      : this.onRouteChanged(this.retryId);
  }
  hide() {
    ++this.generation;
    this.visibleDetail = null;
  }
  unload() {
    this.hide();
    this.retryId = null;
  }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return source


def _write_toplevel_cloud_handle(project: Path, name: str = "index.js") -> Path:
    source = project / name
    source.write_text(
        """
const cloud = require("wx-server-sdk");
cloud.init();
const db = cloud.database();
const records = db.collection("records");

exports.main = async () => {
  const { OPENID } = cloud.getWXContext();
  if (!OPENID) {
    return { ok: false, error: "unauthenticated" };
  }
  return records.where({ owner: OPENID }).get();
};
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return source


def _auth_probe_text(*, direct: bool) -> str:
    body = """
jest.resetModules();
const sdkCalls = { init: 0, collection: 0, read: 0, write: 0, transaction: 0 };
const collection = {
  where: jest.fn(() => collection),
  get: jest.fn(async () => { sdkCalls.read += 1; }),
  add: jest.fn(async () => { sdkCalls.write += 1; }),
};
const db = {
  collection: jest.fn(() => {
    sdkCalls.collection += 1;
    return collection;
  }),
  runTransaction: jest.fn(async () => { sdkCalls.transaction += 1; }),
};
const cloud = {
  init: jest.fn(() => { sdkCalls.init += 1; }),
  database: jest.fn(() => db),
  getWXContext: jest.fn(),
};
cloud.getWXContext.mockReturnValue({ OPENID: "" });
jest.doMock("wx-server-sdk", () => cloud);
const handler = require("../index");
await handler.main({});
expect(sdkCalls).toEqual({
  init: 0,
  collection: 0,
  read: 0,
  write: 0,
  transaction: 0,
});
""".strip()
    if direct:
        return f'test("empty identity has no SDK side effects", async () => {{\n{body}\n}});\n'
    return (
        f"async function helperOnlyProbe() {{\n{body}\n}}\n"
        'test("empty identity", async () => helperOnlyProbe());\n'
    )


def _adversarial_auth_probe_text(kind: str) -> str:
    text = _auth_probe_text(direct=True)
    if kind.startswith("short-circuit-"):
        counter = kind.removeprefix("short-circuit-")
        return text.replace(
            f"sdkCalls.{counter} += 1;",
            f"false && (sdkCalls.{counter} += 1);",
        )
    if kind == "conditional-no-brace":
        return text.replace(
            "sdkCalls.init += 1;",
            "if (shouldCount) sdkCalls.init += 1;",
        )
    if kind == "conditional-ternary":
        return text.replace(
            "sdkCalls.write += 1;",
            "shouldCount ? (sdkCalls.write += 1) : 0;",
        )
    if kind == "unrelated-sdk":
        return text.replace('"wx-server-sdk"', '"unrelated-sdk"')
    if kind == "unbound-sdk":
        return text.replace(
            'cloud.getWXContext.mockReturnValue({ OPENID: "" });',
            'const unrelatedCloud = { getWXContext: jest.fn() };\n'
            'unrelatedCloud.getWXContext.mockReturnValue({ OPENID: "" });',
        ).replace(
            'jest.doMock("wx-server-sdk", () => cloud);',
            'jest.doMock("wx-server-sdk", () => unrelatedCloud);',
        )
    if kind == "unrelated-handler":
        return text.replace('require("../index")', 'require("../other")')
    if kind == "dead-counters":
        for counter in AUTH_FAIL_CLOSED_COUNTERS:
            text = text.replace(f"sdkCalls.{counter} += 1;", "")
        dead_increments = "\n".join(
            f"  sdkCalls.{counter} += 1;"
            for counter in AUTH_FAIL_CLOSED_COUNTERS
        )
        return text.replace(
            "const sdkCalls = { init: 0, collection: 0, read: 0, "
            "write: 0, transaction: 0 };",
            "const sdkCalls = { init: 0, collection: 0, read: 0, "
            f"write: 0, transaction: 0 }};\nif (false) {{\n{dead_increments}\n}}",
        )
    if kind == "dead-chain":
        prefix = 'test("empty identity has no SDK side effects", async () => {\n'
        body = text.removeprefix(prefix).removesuffix("});\n")
        return f"{prefix}if (false) {{\n{body}\n}}\n}});\n"
    raise AssertionError(f"unknown adversarial probe: {kind}")


def _run_review_cli(
    project: Path,
    runtime: Path,
    sources: list[tuple[str, str]],
    *,
    output_id: str,
    profile: str | None = IDENTITY_DETAIL_PROFILE,
) -> tuple[subprocess.CompletedProcess[str], dict, str]:
    package_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONPATH"] = str(package_root)
    command = [
        sys.executable,
        "-m",
        "control_plane.cli",
        "web-ai",
        "prepare-review-bundle",
        "--project-root",
        str(project),
        "--runtime-dir",
        str(runtime),
        "--output-id",
        output_id,
        "--question",
        "Is this async detail loader safe for production?",
    ]
    if profile is not None:
        command.extend(["--profile", profile])
    for role, path in sources:
        command.extend(["--source", f"{role}={path}"])

    completed = subprocess.run(
        command,
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    bundle_dir = runtime / "external-review-bundles" / output_id
    manifest = json.loads((bundle_dir / "PACK_MANIFEST.json").read_text(encoding="utf-8"))
    prompt = (bundle_dir / "REVIEW_PROMPT.md").read_text(encoding="utf-8")
    return completed, manifest, prompt


def _run_validate_cli(zip_path: Path) -> subprocess.CompletedProcess[str]:
    package_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONPATH"] = str(package_root)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "control_plane.cli",
            "web-ai",
            "validate-review-bundle",
            "--zip",
            str(zip_path),
        ],
        cwd=zip_path.parent,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _repack_with_manifest(
    source_zip: Path,
    target_zip: Path,
    manifest: dict,
    replacements: dict[str, bytes] | None = None,
) -> None:
    manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=True).encode("utf-8")
    replacements = replacements or {}
    with zipfile.ZipFile(source_zip, "r") as source:
        with zipfile.ZipFile(target_zip, "w", zipfile.ZIP_DEFLATED) as target:
            for name in source.namelist():
                payload = (
                    manifest_bytes
                    if name == "PACK_MANIFEST.json"
                    else replacements.get(name, source.read(name))
                )
                target.writestr(name, payload)


def _findings_by_source(contract: dict) -> dict[str, set[str]]:
    findings: dict[str, set[str]] = {}
    for finding in contract["findings"]:
        findings.setdefault(finding["source_path"], set()).add(finding["code"])
    return findings


def _assert_cli_context_incomplete(
    completed: subprocess.CompletedProcess[str],
    manifest: dict,
) -> None:
    assert completed.returncode == 1, completed.stderr
    assert manifest["status"] == INCOMPLETE
    assert "Prepared external review bundle: context_incomplete" in completed.stdout


def _detail_class(
    name: str,
    body: str,
    *,
    method: str = "loadPageDetail",
    setup: str = "const response = await this.api.loadDetail(requestedId);",
    extra_methods: str = "",
) -> str:
    return f"""
class {name} {{
  async {method}(requestedId: string) {{
    {setup}
    {body}
  }}
  {extra_methods}
}}
"""


def test_prepare_review_bundle_is_ready_with_required_roles(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    (project / "docs").mkdir(parents=True)
    (project / "docs" / "README.md").write_text("# Map\n", encoding="utf-8")
    (project / "docs" / "PLAN.md").write_text("# Plan\n", encoding="utf-8")

    result = prepare_external_review_bundle(
        project_root=project,
        runtime_dir=runtime,
        output_id="review-1",
        review_question="Is the plan complete enough for review?",
        required_roles=["map", "plan"],
        sources=[
            ReviewSource("docs/README.md", role="map", authority="stable"),
            ReviewSource("docs/PLAN.md", role="plan", authority="active-plan"),
        ],
    )

    assert result["status"] == READY
    assert result["validator"]["valid"] is True
    assert result["review_contracts"] == []
    zip_path = Path(result["zip_path"])
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        assert "PACK_MANIFEST.json" in names
        assert "CONTEXT_LEDGER.md" in names
        assert "REVIEW_PROMPT.md" in names
        assert "sources/docs/README.md" in names


def test_prepare_review_bundle_marks_missing_required_role_incomplete(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    (project / "README.md").write_text("# Map\n", encoding="utf-8")

    result = prepare_external_review_bundle(
        project_root=project,
        runtime_dir=runtime,
        output_id="review-2",
        review_question="Can GPT decide?",
        required_roles=["map", "evidence"],
        sources=[ReviewSource("README.md", role="map", authority="stable")],
    )

    assert result["status"] == INCOMPLETE
    assert result["validator"]["valid"] is False
    assert "missing_required_role:evidence" in result["blocking_issues"]


def test_prepare_review_bundle_blocks_sensitive_source(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    (project / ".env").write_text("OPENAI_API_KEY=sk-secretsecretsecretsecret\n", encoding="utf-8")

    result = prepare_external_review_bundle(
        project_root=project,
        runtime_dir=runtime,
        output_id="review-3",
        review_question="Should this be uploaded?",
        required_roles=["secret"],
        sources=[ReviewSource(".env", role="secret", authority="forbidden")],
    )

    assert result["status"] == BLOCKED
    assert any(issue.startswith("forbidden_sensitive_path") for issue in result["blocking_issues"])


def test_prepare_review_bundle_blocks_nested_archives(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    (project / "old-review.zip").write_bytes(b"PK nested archive")

    result = prepare_external_review_bundle(
        project_root=project,
        runtime_dir=runtime,
        output_id="review-nested",
        review_question="Can this archive be nested?",
        required_roles=["archive"],
        sources=[ReviewSource("old-review.zip", role="archive")],
    )

    assert result["status"] == BLOCKED
    assert "forbidden_nested_archive:old-review.zip" in result["blocking_issues"]


def test_prepare_review_bundle_allows_token_variable_names_without_secret_literals(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    (project / "cli.py").write_text("parser.add_argument('--token')\nvalue = args.token\n", encoding="utf-8")

    result = prepare_external_review_bundle(
        project_root=project,
        runtime_dir=runtime,
        output_id="review-token-variable",
        review_question="Can source code with token variable names be reviewed?",
        required_roles=["code"],
        sources=[ReviewSource("cli.py", role="code")],
    )

    assert result["status"] == READY


def test_prepare_review_bundle_rejects_source_outside_project(tmp_path):
    project = tmp_path / "project"
    outside = tmp_path / "outside.md"
    project.mkdir()
    outside.write_text("outside\n", encoding="utf-8")

    with pytest.raises(ReviewBundleError, match="at least one explicit source"):
        prepare_external_review_bundle(
            project_root=project,
            review_question="No sources",
            sources=[],
            runtime_dir=tmp_path / "runtime",
        )

    result = prepare_external_review_bundle(
        project_root=project,
        review_question="Outside source",
        sources=[ReviewSource(outside, role="outside")],
        runtime_dir=tmp_path / "runtime",
        output_id="review-outside",
    )
    assert result["status"] == BLOCKED
    assert any(issue.startswith("forbidden_path_outside_project") for issue in result["blocking_issues"])


def test_validate_review_bundle_detects_hash_tamper(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    (project / "README.md").write_text("# Map\n", encoding="utf-8")
    result = prepare_external_review_bundle(
        project_root=project,
        runtime_dir=runtime,
        output_id="review-4",
        review_question="Hash check?",
        required_roles=["map"],
        sources=[ReviewSource("README.md", role="map")],
    )
    zip_path = Path(result["zip_path"])
    tampered = tmp_path / "tampered.zip"

    with zipfile.ZipFile(zip_path, "r") as source_zip:
        with zipfile.ZipFile(tampered, "w", zipfile.ZIP_DEFLATED) as target_zip:
            for name in source_zip.namelist():
                payload = b"tampered\n" if name == "sources/README.md" else source_zip.read(name)
                target_zip.writestr(name, payload)

    validation = validate_external_review_bundle(tampered)
    assert validation["valid"] is False
    assert any(issue.startswith("sha256_mismatch") for issue in validation["issues"])


def _prepare_identity_validation_fixture(tmp_path) -> tuple[Path, dict]:
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    tests_dir = project / "tests"
    tests_dir.mkdir(parents=True)
    code = _write_unsafe_detail_loader(project)
    probe = tests_dir / "detail-loader.test.ts"
    probe.write_text(
        "test('manual probe', async () => await panel.onRouteChanged('a'));\n",
        encoding="utf-8",
    )
    completed, manifest, _ = _run_review_cli(
        project,
        runtime,
        [("code", code.name), ("test", probe.relative_to(project).as_posix())],
        output_id="identity-validation",
    )
    _assert_cli_context_incomplete(completed, manifest)
    return Path(manifest["zip_path"]), manifest


def test_validate_review_bundle_accepts_coherent_identity_context_as_incomplete(
    tmp_path,
):
    zip_path, _ = _prepare_identity_validation_fixture(tmp_path)
    with zipfile.ZipFile(zip_path, "r") as source:
        prompt = source.read("REVIEW_PROMPT.md").decode("utf-8")

    completed = _run_validate_cli(zip_path)
    validation = json.loads(completed.stdout)

    assert (
        '<!-- devframe-review-metadata: {"profile":"identity_detail_contract"} -->'
        in prompt.splitlines()
    )
    assert completed.returncode == 1, completed.stderr
    assert validation == {
        "issues": [],
        "status": INCOMPLETE,
        "valid": False,
    }


def test_validate_review_bundle_rejects_identity_profile_erasure_with_refreshed_hashes(
    tmp_path,
):
    zip_path, _ = _prepare_identity_validation_fixture(tmp_path)
    with zipfile.ZipFile(zip_path, "r") as source:
        packed_manifest = json.loads(source.read("PACK_MANIFEST.json"))
        packed_manifest["profile"] = "external_review"
        packed_manifest["status"] = READY
        packed_manifest["review_contracts"] = []
        packed_manifest["blocking_issues"] = []
        for entry in packed_manifest["package_files"]:
            entry["sha256"] = hashlib.sha256(source.read(entry["path"])).hexdigest()

    tampered_zip = tmp_path / "identity-profile-erasure.zip"
    _repack_with_manifest(zip_path, tampered_zip, packed_manifest)

    completed = _run_validate_cli(tampered_zip)
    validation = json.loads(completed.stdout)

    assert completed.returncode == 1, completed.stderr
    assert validation["valid"] is False
    assert validation["status"] == BLOCKED
    assert (
        "review_profile_manifest_incoherent:prompt_profile_mismatch"
        in validation["issues"]
    )
    assert not any(
        issue.startswith("sha256_mismatch:")
        for issue in validation["issues"]
    )


def test_validate_review_bundle_rejects_identity_contract_erasure_with_rebound_prompt(
    tmp_path,
):
    zip_path, _ = _prepare_identity_validation_fixture(tmp_path)
    with zipfile.ZipFile(zip_path, "r") as source:
        packed_manifest = json.loads(source.read("PACK_MANIFEST.json"))
        prompt_bytes = source.read("REVIEW_PROMPT.md").replace(
            b'<!-- devframe-review-metadata: {"profile":"identity_detail_contract"} -->',
            b'<!-- devframe-review-metadata: {"profile":"external_review"} -->',
            1,
        )
        assert b"Executable review contract: identity-detail-loader.v1" in prompt_bytes
        packed_manifest["profile"] = "external_review"
        packed_manifest["status"] = READY
        packed_manifest["review_contracts"] = []
        packed_manifest["blocking_issues"] = []
        for entry in packed_manifest["package_files"]:
            payload = (
                prompt_bytes
                if entry["path"] == "REVIEW_PROMPT.md"
                else source.read(entry["path"])
            )
            entry["sha256"] = hashlib.sha256(payload).hexdigest()
            entry["size_bytes"] = len(payload)

    tampered_zip = tmp_path / "identity-contract-erasure-rebound-prompt.zip"
    _repack_with_manifest(
        zip_path,
        tampered_zip,
        packed_manifest,
        {"REVIEW_PROMPT.md": prompt_bytes},
    )

    completed = _run_validate_cli(tampered_zip)
    validation = json.loads(completed.stdout)

    assert completed.returncode == 1, completed.stderr
    assert validation["valid"] is False
    assert validation["status"] == BLOCKED
    assert (
        "review_profile_manifest_incoherent:prompt_contract_mismatch"
        in validation["issues"]
    )
    assert not any(
        issue.startswith("sha256_mismatch:")
        for issue in validation["issues"]
    )


def test_validate_review_bundle_rejects_string_review_contracts_for_generic_profile(
    tmp_path,
):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    source = project / "arithmetic.ts"
    source.write_text("export const average = total / count;\n", encoding="utf-8")
    completed, manifest, _ = _run_review_cli(
        project,
        runtime,
        [("code", source.name)],
        output_id="generic-schema-validation",
        profile=None,
    )
    assert completed.returncode == 0, completed.stderr

    zip_path = Path(manifest["zip_path"])
    with zipfile.ZipFile(zip_path, "r") as source_zip:
        packed_manifest = json.loads(source_zip.read("PACK_MANIFEST.json"))
    packed_manifest["review_contracts"] = "identity-detail-loader.v1"
    tampered_zip = tmp_path / "generic-string-review-contracts.zip"
    _repack_with_manifest(zip_path, tampered_zip, packed_manifest)

    validation_completed = _run_validate_cli(tampered_zip)
    validation = json.loads(validation_completed.stdout)

    assert validation_completed.returncode == 1, validation_completed.stderr
    assert validation["valid"] is False
    assert validation["status"] == BLOCKED
    assert "manifest_schema_invalid:review_contracts" in validation["issues"]


def test_validate_review_bundle_rejects_non_string_nested_identity_finding(
    tmp_path,
):
    zip_path, _ = _prepare_identity_validation_fixture(tmp_path)
    with zipfile.ZipFile(zip_path, "r") as source:
        packed_manifest = json.loads(source.read("PACK_MANIFEST.json"))
    findings = packed_manifest["review_contracts"][0]["findings"]
    findings.append(
        {
            "code": 7,
            "source_path": packed_manifest["review_contracts"][0]["source_paths"][0],
        }
    )
    schema_path = (
        Path(__file__).resolve().parents[3]
        / "schemas"
        / "external_review_bundle.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert list(Draft7Validator(schema).iter_errors(packed_manifest))

    tampered_zip = tmp_path / "identity-non-string-finding.zip"
    _repack_with_manifest(zip_path, tampered_zip, packed_manifest)
    completed = _run_validate_cli(tampered_zip)
    validation = json.loads(completed.stdout)

    assert completed.returncode == 1, completed.stderr
    assert validation["valid"] is False
    assert validation["status"] == BLOCKED
    assert any(
        issue.startswith("manifest_schema_invalid:review_contracts[0].findings[")
        and issue.endswith(".code")
        for issue in validation["issues"]
    )


@pytest.mark.parametrize(
    "tamper",
    [
        "ready-status",
        "manual-source-coverage",
        "inspection-complete",
        "required-matrix",
        "required-probes",
        "probe-evidence",
        "profile-contract-mismatch",
    ],
)
def test_validate_review_bundle_rejects_incoherent_identity_manifest(
    tamper,
    tmp_path,
):
    zip_path, _ = _prepare_identity_validation_fixture(tmp_path)
    with zipfile.ZipFile(zip_path, "r") as source:
        packed_manifest = json.loads(source.read("PACK_MANIFEST.json"))
    contract = packed_manifest["review_contracts"][0]
    if tamper == "ready-status":
        packed_manifest["status"] = READY
    elif tamper == "manual-source-coverage":
        missing_source = contract["source_paths"][-1]
        contract["findings"] = [
            finding
            for finding in contract["findings"]
            if finding["source_path"] != missing_source
        ]
    elif tamper == "inspection-complete":
        contract["inspection"] = {"complete": True, "issues": []}
    elif tamper == "required-matrix":
        contract["required_matrix"] = contract["required_matrix"][:-1]
    elif tamper == "required-probes":
        contract["required_probes"] = contract["required_probes"][:-1]
    elif tamper == "probe-evidence":
        contract["probe_evidence"]["status"] = "present"
        contract["probe_evidence"]["matched_source_paths"] = []
    elif tamper == "profile-contract-mismatch":
        packed_manifest["profile"] = "external_review"

    tampered_zip = tmp_path / f"{tamper}.zip"
    _repack_with_manifest(zip_path, tampered_zip, packed_manifest)

    completed = _run_validate_cli(tampered_zip)
    validation = json.loads(completed.stdout)

    assert completed.returncode == 1, completed.stderr
    assert validation["valid"] is False
    assert validation["status"] == BLOCKED
    assert any(
        issue.startswith("identity_contract_manifest_incoherent:")
        for issue in validation["issues"]
    )
    assert not any(
        issue.startswith("sha256_mismatch:")
        for issue in validation["issues"]
    )


def test_prepare_review_bundle_records_identity_detail_loader_contract(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    source = _write_unsafe_detail_loader(project, "DETAIL-LOADER.TS")

    result = prepare_external_review_bundle(
        project_root=project,
        runtime_dir=runtime,
        output_id="detail-loader-contract",
        review_question="Is this async detail loader safe for production?",
        required_roles=["code"],
        profile=IDENTITY_DETAIL_PROFILE,
        sources=[ReviewSource(source.name, role="code", authority="candidate")],
    )

    assert result["status"] == INCOMPLETE
    assert result["validator"]["valid"] is False
    assert len(result["review_contracts"]) == 1
    contract = result["review_contracts"][0]
    assert contract["contract_id"] == "identity-detail-loader.v1"
    assert contract["inspection"]["complete"] is False
    assert [finding["code"] for finding in contract["findings"]] == list(
        DETAIL_LOADER_FINDINGS
    )
    assert contract["required_matrix"] == DETAIL_LOADER_MATRIX
    assert contract["required_probes"] == [
        "real_adapter_deferred_success_at_earliest_state_await",
        "real_adapter_deferred_failure_at_earliest_state_await",
    ]

    with zipfile.ZipFile(result["zip_path"], "r") as zf:
        zipped_manifest = json.loads(zf.read("PACK_MANIFEST.json"))
        prompt = zf.read("REVIEW_PROMPT.md").decode("utf-8")
    assert zipped_manifest["review_contracts"] == result["review_contracts"]
    for finding in DETAIL_LOADER_FINDINGS:
        assert finding in prompt
    for required_text in (
        "visible detail assignment only after both response-shape validation",
        "requested-identity equality",
        "null response",
        "truthy malformed response",
        "mismatched requested identity",
        "current valid response",
        "direct/deep-link loading",
        "transport failure",
        "business failure",
        "one-step retry",
        "hide invalidation",
        "unload invalidation",
        "real adapter-controlled deferred promises",
        "earliest state-producing await",
        "success and failure settlement",
    ):
        assert required_text in prompt


def test_prepare_review_bundle_keeps_guarded_route_lifecycle_unverified(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    source = _write_safe_detail_loader(project)
    tests_dir = project / "tests"
    tests_dir.mkdir()
    probe = tests_dir / "detail-loader.test.ts"
    probe.write_text(
        """
const successDeferred = deferred();
adapter.loadDetail.mockReturnValueOnce(successDeferred.promise);
const successPending = panel.onRouteChanged("a");
successDeferred.resolve(validDetail);
await successPending;
const failureDeferred = deferred();
adapter.loadDetail.mockReturnValueOnce(failureDeferred.promise);
const failurePending = panel.onRouteChanged("a");
failureDeferred.reject(transportError);
await failurePending;
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = prepare_external_review_bundle(
        project_root=project,
        runtime_dir=runtime,
        output_id="safe-detail-loader",
        review_question="Review the guarded route detail loader.",
        required_roles=["code"],
        profile=IDENTITY_DETAIL_PROFILE,
        sources=[
            ReviewSource(source.name, role="code", authority="candidate"),
            ReviewSource(probe.relative_to(project), role="test", authority="evidence"),
        ],
    )

    assert result["status"] == INCOMPLETE
    assert result["validator"]["valid"] is False
    assert len(result["review_contracts"]) == 1
    contract = result["review_contracts"][0]
    assert contract["contract_id"] == "identity-detail-loader.v1"
    codes = {finding["code"] for finding in contract["findings"]}
    assert codes == {
        "detail_assignment_missing_shape_guard",
        "detail_assignment_missing_identity_guard",
        "route_loader_missing_retry_context",
        "route_loader_missing_lifecycle_invalidation",
    }
    assert contract["inspection"]["complete"] is False
    assert any(
        issue["code"] == "detail_loader_analysis_unverified"
        for issue in contract["inspection"]["issues"]
    )
    assert contract["probe_evidence"]["status"] == "present"
    assert contract["required_matrix"] == DETAIL_LOADER_MATRIX
    prompt = Path(result["manifest_path"]).with_name("REVIEW_PROMPT.md").read_text(
        encoding="utf-8"
    )
    assert "identity-detail-loader.v1" in prompt
    assert "Automated inspection incomplete" in prompt
    assert "Automated findings: none" not in prompt
    assert "truthy malformed response" in prompt
    assert "real adapter-controlled deferred promises" in prompt
    assert "detail_assignment_missing_shape_guard" in codes
    assert "detail_assignment_missing_identity_guard" in codes


def test_review_bundle_cli_scopes_guards_aliases_setters_and_ownership(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    fixtures = {
        "wrong-direction.ts": _detail_class(
            "WrongDirectionPanel",
            "if (isDetail(response)) return;\n"
            "if (response.id === requestedId) return;\n"
            "this.visibleDetail = response;",
        ),
        "safe-early-return.ts": _detail_class(
            "SafeEarlyReturnPanel",
            "if (!isDetail(response)) return;\n"
            "if (response.id !== requestedId) return;\n"
            "this.visibleDetail = response;",
        ),
        "safe-alias-setter.ts": _detail_class(
            "SafeAliasSetterPanel",
            "const detailAlias = response;\n"
            "if (!isDetail(detailAlias)) return;\n"
            "if (detailAlias.id !== requestedId) return;\n"
            "setVisibleDetail(detailAlias);",
        ),
        "unproven-alias-setter.ts": _detail_class(
            "UnprovenAliasSetterPanel",
            "if (!isDetail(detailAlias)) return;\n"
            "if (detailAlias.id !== requestedId) return;\n"
            "setVisibleDetail(detailAlias);",
            setup="const detailAlias = readCache();",
        ),
        "multi-class.ts": _detail_class(
            "UnsafeOwnedRoutePanel",
            "if (!isDetail(response)) return;\n"
            "if (response.id !== requestedId) return;\n"
            "this.visibleDetail = response;",
            method="onRouteChanged",
        )
        + """
class UnrelatedOwner {
  retryId = "";
  generation = 0;
  retry() { return this.onRouteChanged(this.retryId); }
  hide() { ++this.generation; }
  unload() { this.hide(); }
}
""",
        "outside-owner.ts": _detail_class(
            "RoutePanel",
            "if (!isDetail(response)) return;\n"
            "if (response.id !== requestedId) return;\n"
            "this.visibleDetail = response;",
            method="onRouteChanged",
            setup="const requestGeneration = ++this.generation;\n"
            "this.retryId = requestedId;\n"
            "const response = await this.api.loadDetail(requestedId);",
        )
        + """
const unrelatedOwner = {
  retry() { return this.onRouteChanged(this.retryId); },
  hide() { ++this.generation; },
  unload() { this.hide(); },
};
""",
        "comments-and-strings.ts": _detail_class(
            "CommentStringPanel",
            "// if (!isDetail(response)) return;\n"
            "// if (response.id !== requestedId) return;\n"
            'const fake = "if (!isDetail(response)) return; response.id !== requestedId";\n'
            "const fakePattern = /if (!isDetail(response)) return; "
            "if (response.id !== requestedId) return/;\n"
            "this.visibleDetail = response;",
        ),
        "other-handler-guard.ts": _detail_class(
            "OtherHandlerGuardPanel",
            "this.visibleDetail = response;",
            extra_methods="validate(response: unknown, requestedId: string) {\n"
            "if (!isDetail(response)) return;\n"
            "if (response.id !== requestedId) return;\n}",
        ),
        "tokens-only.ts": "// this.visibleDetail = response;\n"
        'const fake = "setVisibleDetail(response); onRouteChanged(requestedId)";\n',
    }
    for name, content in fixtures.items():
        (project / name).write_text(content.strip() + "\n", encoding="utf-8")

    completed, manifest, prompt = _run_review_cli(
        project,
        runtime,
        [("code", name) for name in fixtures],
        output_id="cli-adversarial-scope",
    )

    _assert_cli_context_incomplete(completed, manifest)
    assert manifest["profile"] == IDENTITY_DETAIL_PROFILE
    contract = manifest["review_contracts"][0]
    assert contract["required_matrix"] == DETAIL_LOADER_MATRIX
    assert "real adapter-controlled deferred promises" in prompt
    findings = _findings_by_source(contract)
    source_requirements = set(DETAIL_LOADER_FINDINGS[:-1])
    for name in (
        "wrong-direction.ts",
        "safe-early-return.ts",
        "safe-alias-setter.ts",
        "unproven-alias-setter.ts",
        "multi-class.ts",
        "outside-owner.ts",
        "comments-and-strings.ts",
        "other-handler-guard.ts",
        "tokens-only.ts",
    ):
        assert source_requirements <= findings[name]
    assert set(contract["source_paths"]) == set(fixtures)


@pytest.mark.parametrize(
    ("name", "setup", "body"),
    [
        (
            "guard-then-reassignment",
            "let response = await this.api.loadDetail(requestedId);",
            "if (!isDetail(response)) return;\n"
            "if (response.id !== requestedId) return;\n"
            "response = responseAttacker;\n"
            "this.visibleDetail = response;",
        ),
        (
            "skippable-conditional-guards",
            "const response = await this.api.loadDetail(requestedId);",
            "if (validationEnabled)\n"
            "  if (!isDetail(response)) return;\n"
            "if (validationEnabled)\n"
            "  if (response.id !== requestedId) return;\n"
            "this.visibleDetail = response;",
        ),
        (
            "response-attacker-prefix",
            "const response = await this.api.loadDetail(requestedId);",
            "if (!isDetail(response)) return;\n"
            "if (response.id !== requestedId) return;\n"
            "this.visibleDetail = responseAttacker;",
        ),
    ],
)
def test_review_bundle_cli_keeps_source_only_guards_unverified(
    name,
    setup,
    body,
    tmp_path,
):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    source = project / f"{name}.ts"
    source.write_text(
        _detail_class("SourceOnlyGuardPanel", body, setup=setup),
        encoding="utf-8",
    )

    completed, manifest, prompt = _run_review_cli(
        project,
        runtime,
        [("code", source.name)],
        output_id=name,
    )

    assert completed.returncode == 1, completed.stderr
    assert manifest["status"] == INCOMPLETE
    contract = manifest["review_contracts"][0]
    codes = {finding["code"] for finding in contract["findings"]}
    assert set(DETAIL_LOADER_FINDINGS[:-1]) <= codes
    assert contract["inspection"]["complete"] is False
    assert "Automated inspection incomplete" in prompt
    assert "Automated findings: none" not in prompt


def test_review_bundle_cli_activates_identity_profile_without_detail_name_tokens(
    tmp_path,
):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    source = project / "current-record.ts"
    source.write_text(
        """
export async function openRecord(requestedId: string) {
  const response = await api.fetchById(requestedId);
  currentRecord = response;
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    completed, manifest, prompt = _run_review_cli(
        project,
        runtime,
        [("code", source.name)],
        output_id="profile-current-record",
    )

    _assert_cli_context_incomplete(completed, manifest)
    contract = manifest["review_contracts"][0]
    assert contract["source_paths"] == [source.name]
    assert set(DETAIL_LOADER_FINDINGS[:-1]) <= {
        finding["code"] for finding in contract["findings"]
    }
    assert contract["inspection"]["complete"] is False
    assert "Automated inspection incomplete" in prompt


def test_review_bundle_cli_does_not_skip_test_role_under_identity_profile(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    source = _write_unsafe_detail_loader(project)

    completed, manifest, _ = _run_review_cli(
        project,
        runtime,
        [("test", source.name)],
        output_id="profile-test-role",
    )

    _assert_cli_context_incomplete(completed, manifest)
    contract = manifest["review_contracts"][0]
    assert contract["source_paths"] == [source.name]
    assert set(DETAIL_LOADER_FINDINGS[:-1]) <= {
        finding["code"] for finding in contract["findings"]
    }
    assert contract["probe_evidence"]["status"] == "unverified"


def test_review_bundle_cli_leaves_default_arithmetic_source_unclassified(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    source = project / "arithmetic.ts"
    source.write_text("export const average = total / count;\n", encoding="utf-8")

    completed, manifest, prompt = _run_review_cli(
        project,
        runtime,
        [("code", source.name)],
        output_id="default-arithmetic",
        profile=None,
    )

    assert completed.returncode == 0, completed.stderr
    assert manifest["status"] == READY
    assert manifest["profile"] == "external_review"
    assert manifest["review_contracts"] == []
    assert "Executable review contract" not in prompt
    assert (
        '<!-- devframe-review-metadata: {"profile":"external_review"} -->'
        in prompt.splitlines()
    )

    validation_completed = _run_validate_cli(Path(manifest["zip_path"]))
    assert validation_completed.returncode == 0, validation_completed.stderr
    assert json.loads(validation_completed.stdout) == {
        "issues": [],
        "status": READY,
        "valid": True,
    }


def test_review_bundle_cli_keeps_profile_selected_regex_source_manual(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    source = project / "regex-literal.ts"
    source.write_text(
        "const fake = /this.visibleDetail = response; loadDetail(requestedId)/;\n",
        encoding="utf-8",
    )

    completed, manifest, prompt = _run_review_cli(
        project,
        runtime,
        [("code", source.name)],
        output_id="regex-literal-unverified",
    )

    _assert_cli_context_incomplete(completed, manifest)
    contract = manifest["review_contracts"][0]
    assert contract["inspection"]["complete"] is False
    assert set(DETAIL_LOADER_FINDINGS[:-1]) <= {
        finding["code"] for finding in contract["findings"]
    }
    assert any(
        issue["code"] == "detail_loader_analysis_unverified"
        for issue in contract["inspection"]["issues"]
    )
    assert "Automated inspection incomplete" in prompt


def test_review_bundle_cli_marks_truncated_inspection_incomplete(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    source = project / "late-detail-loader.ts"
    source.write_text(
        (" " * 512_100)
        + """
class LatePanel {
  async onRouteChanged(requestedId: string) {
    const response = await this.api.loadDetail(requestedId);
    this.visibleDetail = response;
  }
}
""",
        encoding="utf-8",
    )

    completed, manifest, prompt = _run_review_cli(
        project,
        runtime,
        [("code", source.name)],
        output_id="cli-truncated-inspection",
    )

    _assert_cli_context_incomplete(completed, manifest)
    contract = manifest["review_contracts"][0]
    assert contract["applicable"] is True
    assert contract["inspection"]["complete"] is False
    assert {
        "code": "detail_loader_inspection_truncated",
        "source_path": source.name,
        "inspected_bytes": 512_000,
        "source_size_bytes": source.stat().st_size,
    } in contract["inspection"]["issues"]
    assert any(
        issue["code"] == "detail_loader_analysis_unverified"
        for issue in contract["inspection"]["issues"]
    )
    assert source.name in contract["source_paths"]
    assert contract["required_matrix"] == DETAIL_LOADER_MATRIX
    assert "Automated inspection incomplete" in prompt
    assert "Automated findings: none" not in prompt
    assert "truthy malformed response" in prompt


@pytest.mark.parametrize(
    ("probe_text", "expected_status", "expect_missing"),
    [
        (
            """
test("superficial", async () => {
  // deferred adapter.loadDetail resolve reject await
  const fake = "deferred adapter.loadDetail resolve reject await";
  await panel.onRouteChanged("a");
  expect(panel.loading).toBe(false);
});
""",
            "unverified",
            False,
        ),
        (
            """
test("real deferred adapter success and failure", async () => {
  const successDeferred = deferred();
  adapter.loadDetail.mockReturnValueOnce(successDeferred.promise);
  const successPending = panel.onRouteChanged("a");
  successDeferred.resolve({ id: "a", title: "ok" });
  await successPending;
  const failureDeferred = deferred();
  adapter.loadDetail.mockReturnValueOnce(failureDeferred.promise);
  const failurePending = panel.onRouteChanged("a");
  failureDeferred.reject(new Error("transport"));
  await failurePending;
});
""",
            "present",
            False,
        ),
    ],
)
def test_review_bundle_cli_derives_deferred_probe_evidence(
    tmp_path,
    probe_text,
    expected_status,
    expect_missing,
):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    tests_dir = project / "tests"
    tests_dir.mkdir(parents=True)
    code = _write_unsafe_detail_loader(project)
    probe = tests_dir / "detail-loader.test.ts"
    probe.write_text(probe_text.strip() + "\n", encoding="utf-8")

    completed, manifest, _ = _run_review_cli(
        project,
        runtime,
        [("code", code.name), ("test", probe.relative_to(project).as_posix())],
        output_id=f"cli-probe-{expected_status}",
    )

    _assert_cli_context_incomplete(completed, manifest)
    contract = manifest["review_contracts"][0]
    assert contract["probe_evidence"]["status"] == expected_status
    codes = {finding["code"] for finding in contract["findings"]}
    assert set(DETAIL_LOADER_FINDINGS[:-1]) <= codes
    assert contract["inspection"]["complete"] is False
    assert ("real_adapter_deferred_probe_missing" in codes) is expect_missing


def test_review_bundle_cli_keeps_uncheckable_probe_as_manual_requirement(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    tests_dir = project / "tests"
    tests_dir.mkdir(parents=True)
    code = _write_unsafe_detail_loader(project)
    probe = tests_dir / "detail-loader.test.ts"
    probe.write_text(" " * 512_100, encoding="utf-8")

    completed, manifest, prompt = _run_review_cli(
        project,
        runtime,
        [("code", code.name), ("test", probe.relative_to(project).as_posix())],
        output_id="cli-probe-unverified",
    )

    _assert_cli_context_incomplete(completed, manifest)
    contract = manifest["review_contracts"][0]
    assert contract["probe_evidence"]["status"] == "unverified"
    codes = {finding["code"] for finding in contract["findings"]}
    assert "real_adapter_deferred_probe_missing" not in codes
    assert contract["required_probes"]
    assert contract["inspection"]["complete"] is False
    assert "Deferred adapter probe evidence: unverified" in prompt


@pytest.mark.parametrize(
    ("name", "body"),
    [
        (
            "negated-positive",
            "if (!isDetail(response) && response.id === requestedId) {\n"
            "this.visibleDetail = response;\n}",
        ),
        (
            "unknown-positive",
            "if (isArchived(response) && response.id === requestedId) {\n"
            "this.visibleDetail = response;\n}",
        ),
        (
            "reversed-early",
            "if (isDetail(response)) return;\n"
            "if (response.id === requestedId) return;\n"
            "this.visibleDetail = response;",
        ),
    ],
)
def test_review_bundle_cli_keeps_unprovable_shape_predicates(name, body, tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    source = project / f"{name}.ts"
    source.write_text(_detail_class("ShapePanel", body), encoding="utf-8")

    completed, manifest, _ = _run_review_cli(
        project,
        runtime,
        [("code", source.name)],
        output_id=name,
    )

    _assert_cli_context_incomplete(completed, manifest)
    codes = {item["code"] for item in manifest["review_contracts"][0]["findings"]}
    assert "detail_assignment_missing_shape_guard" in codes


def test_review_bundle_cli_treats_latest_role_as_production_source(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    source = _write_unsafe_detail_loader(project)

    completed, manifest, _ = _run_review_cli(
        project,
        runtime,
        [("latest", source.name)],
        output_id="latest-is-production",
    )

    _assert_cli_context_incomplete(completed, manifest)
    contract = manifest["review_contracts"][0]
    assert source.name in contract["source_paths"]
    assert contract["probe_evidence"]["status"] == "missing"
    assert set(DETAIL_LOADER_FINDINGS) <= {
        finding["code"] for finding in contract["findings"]
    }


def test_review_bundle_cli_requires_same_adapter_for_deferred_probe_evidence(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    tests_dir = project / "tests"
    tests_dir.mkdir(parents=True)
    code = _write_unsafe_detail_loader(project)
    probe = tests_dir / "detail-loader.test.ts"
    probe.write_text(
        """
const successDeferred = deferred();
adapter.loadDetail.mockReturnValueOnce(successDeferred.promise);
const successPending = panel.onRouteChanged("a");
successDeferred.resolve(validDetail);
await successPending;
const failureDeferred = deferred();
otherAdapter.loadDetail.mockReturnValueOnce(failureDeferred.promise);
const failurePending = panel.onRouteChanged("a");
failureDeferred.reject(transportError);
await failurePending;
""".strip()
        + "\n",
        encoding="utf-8",
    )

    completed, manifest, _ = _run_review_cli(
        project,
        runtime,
        [("code", code.name), ("test", probe.relative_to(project).as_posix())],
        output_id="probe-same-adapter",
    )

    _assert_cli_context_incomplete(completed, manifest)
    contract = manifest["review_contracts"][0]
    assert contract["probe_evidence"]["status"] == "unverified"
    assert set(DETAIL_LOADER_FINDINGS[:-1]) <= {
        item["code"] for item in contract["findings"]
    }
    assert "real_adapter_deferred_probe_missing" not in {
        item["code"] for item in contract["findings"]
    }


def test_generated_manifest_validates_against_public_draft7_schema(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    source = _write_unsafe_detail_loader(project)
    result = prepare_external_review_bundle(
        project_root=project,
        runtime_dir=runtime,
        output_id="schema-contract",
        review_question="Validate the public review manifest contract.",
        profile=IDENTITY_DETAIL_PROFILE,
        sources=[ReviewSource(source.name, role="code")],
    )
    schema_path = Path(__file__).resolve().parents[3] / "schemas" / "external_review_bundle.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft7Validator(schema)

    Draft7Validator.check_schema(schema)
    assert _PUBLIC_MANIFEST_SCHEMA == schema
    assert result["schema_version"] == 2
    assert result["status"] == INCOMPLETE
    assert result["validator"]["valid"] is False
    validator.validate(result)
    with zipfile.ZipFile(result["zip_path"], "r") as zf:
        validator.validate(json.loads(zf.read("PACK_MANIFEST.json")))


def test_review_bundle_cli_marks_set_state_publication_unverified(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    source = project / "set-state-detail.ts"
    source.write_text(
        _detail_class(
            "SetStatePanel",
            "this.setState({ visibleDetail: response });",
        ),
        encoding="utf-8",
    )
    fake = project / "fake-set-state.ts"
    fake.write_text(
        '// this.setState({ visibleDetail: response });\n'
        'const sample = "this.setState({ visibleDetail: response })";\n',
        encoding="utf-8",
    )
    custom = project / "custom-publication.ts"
    custom.write_text(
        _detail_class("CustomPublicationPanel", "publishDetail(response);"),
        encoding="utf-8",
    )

    completed, manifest, prompt = _run_review_cli(
        project,
        runtime,
        [("code", source.name), ("code", fake.name), ("code", custom.name)],
        output_id="set-state-unverified",
    )

    _assert_cli_context_incomplete(completed, manifest)
    contract = manifest["review_contracts"][0]
    assert source.name in contract["source_paths"]
    assert custom.name in contract["source_paths"]
    assert fake.name in contract["source_paths"]
    findings = _findings_by_source(contract)
    source_requirements = set(DETAIL_LOADER_FINDINGS[:-1])
    assert source_requirements <= findings[source.name]
    assert source_requirements <= findings[fake.name]
    assert source_requirements <= findings[custom.name]
    assert contract["inspection"]["complete"] is False
    assert any(
        issue["code"] == "detail_loader_analysis_unverified"
        for issue in contract["inspection"]["issues"]
    )
    assert "Automated inspection incomplete" in prompt


def test_review_bundle_cli_records_auth_fail_closed_toplevel_side_effect_contract(
    tmp_path,
):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    source = _write_toplevel_cloud_handle(project)

    completed, manifest, prompt = _run_review_cli(
        project,
        runtime,
        [("code", source.name)],
        output_id="auth-toplevel-side-effect",
        profile=AUTH_FAIL_CLOSED_PROFILE,
    )

    assert completed.returncode == 1, completed.stderr
    assert manifest["status"] == INCOMPLETE
    assert manifest["validator"]["valid"] is False
    assert len(manifest["review_contracts"]) == 1
    contract = manifest["review_contracts"][0]
    assert contract == {
        "contract_id": "auth-fail-closed-top-level-side-effect.v1",
        "applicable": True,
        "source_paths": [source.name],
        "findings": [
            {
                "code": "module_toplevel_sdk_handle_before_handler_auth",
                "source_path": source.name,
            },
            {
                "code": "auth_fail_closed_probe_unverified",
                "source_path": source.name,
            },
        ],
        "inspection": {"complete": True, "issues": []},
        "probe_evidence": {
            "status": "unverified",
            "source_paths": [],
            "matched_source_paths": [],
            "required_zero_counters": AUTH_FAIL_CLOSED_COUNTERS,
        },
        "required_probes": [
            "empty_identity_injected_before_fresh_module_load",
            "handler_invoked_with_sdk_side_effect_counters_all_zero",
        ],
    }
    assert "auth-fail-closed-top-level-side-effect.v1" in prompt
    assert "fresh module load" in prompt
    assert "init=0, collection=0, read=0, write=0, transaction=0" in prompt

    schema_path = (
        Path(__file__).resolve().parents[3]
        / "schemas"
        / "external_review_bundle.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft7Validator.check_schema(schema)
    Draft7Validator(schema).validate(manifest)
    assert _PUBLIC_MANIFEST_SCHEMA == schema


@pytest.mark.parametrize(
    ("tamper", "expected_issue"),
    [
        ("probe-status", "auth_contract_manifest_incoherent:probe_evidence"),
        ("source-path-type", "auth_contract_manifest_incoherent:source_paths"),
        ("matched-path-type", "auth_contract_manifest_incoherent:probe_evidence"),
    ],
)
def test_validate_review_bundle_rejects_incoherent_auth_contract(
    tamper,
    expected_issue,
    tmp_path,
):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    source = _write_toplevel_cloud_handle(project)
    result = prepare_external_review_bundle(
        project_root=project,
        runtime_dir=runtime,
        output_id="auth-manifest-coherence",
        review_question="Does empty identity fail closed before SDK side effects?",
        profile=AUTH_FAIL_CLOSED_PROFILE,
        sources=[ReviewSource(source.name, role="code", authority="candidate")],
    )
    zip_path = Path(result["zip_path"])
    with zipfile.ZipFile(zip_path, "r") as zf:
        manifest = json.loads(zf.read("PACK_MANIFEST.json"))
    contract = manifest["review_contracts"][0]
    if tamper == "probe-status":
        contract["probe_evidence"]["status"] = "present"
    elif tamper == "source-path-type":
        contract["source_paths"] = [{"not": "a path"}]
    elif tamper == "matched-path-type":
        contract["probe_evidence"]["matched_source_paths"] = [{"not": "a path"}]

    tampered = tmp_path / f"auth-incoherent-{tamper}.zip"
    _repack_with_manifest(zip_path, tampered, manifest)
    completed = _run_validate_cli(tampered)
    validation = json.loads(completed.stdout)

    assert completed.returncode == 1, completed.stderr
    assert validation["valid"] is False
    assert validation["status"] == BLOCKED
    assert expected_issue in validation["issues"]


@pytest.mark.parametrize(
    ("name", "text"),
    [
        (
            "comments.js",
            """
// const db = cloud.database();
// const records = db.collection("records");
exports.main = async () => {
  const OPENID = cloud.getWXContext().OPENID;
  const sample = "const db = cloud.database(); db.collection('records')";
  if (!OPENID) return { ok: false };
};
""",
        ),
        (
            "handler-local.js",
            """
exports.main = async () => {
  const OPENID = cloud.getWXContext().OPENID;
  if (!OPENID) return { ok: false };
  const db = cloud.database();
  return db.collection("records").get();
};
""",
        ),
    ],
)
def test_review_bundle_cli_does_not_trigger_auth_contract_for_non_toplevel_handles(
    name,
    text,
    tmp_path,
):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    source = project / name
    source.write_text(text.strip() + "\n", encoding="utf-8")

    completed, manifest, prompt = _run_review_cli(
        project,
        runtime,
        [("code", source.name)],
        output_id=f"auth-negative-{source.stem}",
        profile=AUTH_FAIL_CLOSED_PROFILE,
    )

    assert completed.returncode == 0, completed.stderr
    assert manifest["status"] == READY
    assert manifest["validator"]["valid"] is True
    assert manifest["review_contracts"] == []
    assert "auth-fail-closed-top-level-side-effect.v1" not in prompt


@pytest.mark.parametrize("probe_kind", ["helper", "mock-only"])
def test_review_bundle_cli_does_not_accept_non_real_auth_probe(probe_kind, tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    tests_dir = project / "tests"
    tests_dir.mkdir(parents=True)
    source = _write_toplevel_cloud_handle(project)
    probe = tests_dir / "index.test.js"
    probe.write_text(
        _auth_probe_text(direct=False)
        if probe_kind == "helper"
        else """
test("empty identity", async () => {
  cloud.getWXContext.mockReturnValue({ OPENID: "" });
  const sdkCalls = { init: 0, collection: 0, read: 0, write: 0, transaction: 0 };
  expect(sdkCalls).toEqual({
    init: 0, collection: 0, read: 0, write: 0, transaction: 0,
  });
});
""".strip()
        + "\n",
        encoding="utf-8",
    )

    completed, manifest, _ = _run_review_cli(
        project,
        runtime,
        [("code", source.name), ("test", probe.relative_to(project).as_posix())],
        output_id=f"auth-{probe_kind}",
        profile=AUTH_FAIL_CLOSED_PROFILE,
    )

    assert completed.returncode == 1, completed.stderr
    contract = manifest["review_contracts"][0]
    assert contract["probe_evidence"]["status"] == "unverified"
    assert contract["probe_evidence"]["matched_source_paths"] == []
    assert {
        finding["code"] for finding in contract["findings"]
    } >= {"auth_fail_closed_probe_unverified"}


def test_review_bundle_cli_accepts_direct_structured_auth_probe_evidence(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    tests_dir = project / "tests"
    tests_dir.mkdir(parents=True)
    source = _write_toplevel_cloud_handle(project)
    probe = tests_dir / "index.test.js"
    probe.write_text(_auth_probe_text(direct=True), encoding="utf-8")

    completed, manifest, _ = _run_review_cli(
        project,
        runtime,
        [("code", source.name), ("test", probe.relative_to(project).as_posix())],
        output_id="auth-direct-probe",
        profile=AUTH_FAIL_CLOSED_PROFILE,
    )

    assert completed.returncode == 1, completed.stderr
    contract = manifest["review_contracts"][0]
    assert contract["probe_evidence"] == {
        "status": "present",
        "source_paths": [probe.relative_to(project).as_posix()],
        "matched_source_paths": [probe.relative_to(project).as_posix()],
        "required_zero_counters": AUTH_FAIL_CLOSED_COUNTERS,
    }
    assert "auth_fail_closed_probe_unverified" not in {
        finding["code"] for finding in contract["findings"]
    }
    assert "module_toplevel_sdk_handle_before_handler_auth" in {
        finding["code"] for finding in contract["findings"]
    }


@pytest.mark.parametrize(
    ("name", "content", "expected_issue"),
    [
        (
            "unsupported.txt",
            """
exports.main = async () => {
  const OPENID = cloud.getWXContext().OPENID;
  if (!OPENID) return { ok: false };
};
""",
            "auth_fail_closed_inspection_unavailable",
        ),
        (
            "truncated.js",
            (" " * 512_100)
            + """
const db = cloud.database();
exports.main = async () => {
  const OPENID = cloud.getWXContext().OPENID;
  if (!OPENID) return { ok: false };
};
""",
            "detail_loader_inspection_truncated",
        ),
    ],
    ids=["unsupported", "truncated"],
)
def test_review_bundle_cli_keeps_uninspectable_auth_source_applicable(
    name,
    content,
    expected_issue,
    tmp_path,
):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    source = project / name
    source.write_text(content.rstrip() + "\n", encoding="utf-8")

    completed, manifest, prompt = _run_review_cli(
        project,
        runtime,
        [("code", source.name)],
        output_id=f"auth-uninspectable-{source.stem}",
        profile=AUTH_FAIL_CLOSED_PROFILE,
    )

    assert completed.returncode == 1, completed.stderr
    assert manifest["status"] == INCOMPLETE
    contract = manifest["review_contracts"][0]
    assert contract["applicable"] is True
    assert contract["source_paths"] == [source.name]
    assert contract["inspection"]["complete"] is False
    assert expected_issue in {
        issue["code"] for issue in contract["inspection"]["issues"]
    }
    assert "auth_fail_closed_analysis_unverified" in {
        finding["code"] for finding in contract["findings"]
    }
    assert "Automated inspection incomplete" in prompt


def test_review_bundle_cli_detects_toplevel_split_sdk_handle_assignments(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    source = project / "index.js"
    source.write_text(
        """
const cloud = require("wx-server-sdk");
let db;
db = cloud.database();
let records;
records = db.collection("records");
exports.main = async () => {
  const OPENID = cloud.getWXContext().OPENID;
  if (!OPENID) return { ok: false };
  return records.get();
};
""".strip()
        + "\n",
        encoding="utf-8",
    )

    completed, manifest, _ = _run_review_cli(
        project,
        runtime,
        [("code", source.name)],
        output_id="auth-split-assignment",
        profile=AUTH_FAIL_CLOSED_PROFILE,
    )

    assert completed.returncode == 1, completed.stderr
    assert manifest["status"] == INCOMPLETE
    contract = manifest["review_contracts"][0]
    assert contract["source_paths"] == [source.name]
    assert "module_toplevel_sdk_handle_before_handler_auth" in {
        finding["code"] for finding in contract["findings"]
    }


@pytest.mark.parametrize(
    "probe_kind",
    [
        "unrelated-sdk",
        "unbound-sdk",
        "unrelated-handler",
        "dead-counters",
        "dead-chain",
        "short-circuit-init",
        "short-circuit-collection",
        "short-circuit-read",
        "short-circuit-write",
        "short-circuit-transaction",
        "conditional-no-brace",
        "conditional-ternary",
    ],
)
def test_review_bundle_cli_rejects_adversarial_structured_auth_probe(
    probe_kind,
    tmp_path,
):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    tests_dir = project / "tests"
    tests_dir.mkdir(parents=True)
    source = _write_toplevel_cloud_handle(project)
    probe = tests_dir / "index.test.js"
    probe.write_text(
        _adversarial_auth_probe_text(probe_kind),
        encoding="utf-8",
    )

    completed, manifest, _ = _run_review_cli(
        project,
        runtime,
        [("code", source.name), ("test", probe.relative_to(project).as_posix())],
        output_id=f"auth-adversarial-{probe_kind}",
        profile=AUTH_FAIL_CLOSED_PROFILE,
    )

    assert completed.returncode == 1, completed.stderr
    contract = manifest["review_contracts"][0]
    assert contract["probe_evidence"]["status"] == "unverified"
    assert contract["probe_evidence"]["matched_source_paths"] == []
    assert "auth_fail_closed_probe_unverified" in {
        finding["code"] for finding in contract["findings"]
    }
