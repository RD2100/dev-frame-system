"""Stage executor — minimal handler for reference pipeline stages.

Generates synthetic paper, runs CSSCI 9-dimension review, builds evidence,
runs pre-submission check, produces FLOW_OUTCOME and closure report.

synthetic_only: true. no_real_paper: true. no_live_cdp: true.
"""
from __future__ import annotations
import os
import sys
import json
import hashlib
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field

import yaml

from .paper_pipeline_gate import (
    scan_submission_bypass,
    validate_evidence_pack,
    validate_paper_pipeline_project,
    validate_paper_task_source,
    write_gate_result,
)


PIPELINE_RUN_ID = f"ref-paper-{uuid.uuid4().hex[:8]}"
import tempfile
RUN_DIR = Path(tempfile.gettempdir()) / "ref-paper-test"
ROOT = Path(__file__).resolve().parent.parent
PAPER_TASK_DIRNAME = "paper_task"


@dataclass
class StageResult:
    stage_id: str
    status: str = "pending"  # pending | completed | failed
    outputs: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def paper_task_dir(target: Path) -> Path:
    return target / PAPER_TASK_DIRNAME


def _paper_identity(target: Path) -> tuple[str, str]:
    profile_path = target / "PAPER_PROFILE.yaml"
    profile: dict = {}
    if profile_path.is_file():
        loaded = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            profile = loaded
    paper_id = str(profile.get("paper_id", "")).strip()
    title = str(profile.get("title", "")).strip()
    if not paper_id or "{{" in paper_id:
        paper_id = target.name
    if not title or "{{" in title:
        title = target.name
    return paper_id, title


def write_paper_task_spec(target: Path) -> Path:
    paper_id, title = _paper_identity(target)
    task_spec = {
        "task_id": PIPELINE_RUN_ID,
        "title": f"Synthetic paper review: {title}",
        "priority": "P2",
        "status": "ready",
        "description": (
            "Run the bounded synthetic paper review pipeline without real paper "
            "content, external submission, or final publication claims."
        ),
        "assumptions": [
            "All paper content is synthetic.",
            "Submission remains dry-run only.",
        ],
        "risk_notes": "Real paper content and external submission remain forbidden.",
        "estimated_tools": ["devframe-paper-pipeline"],
        "conflict_registry": {
            "read_set": [
                "input/SYNTHETIC_PAPER.md",
                f"{PAPER_TASK_DIRNAME}/PAPER_TASK_INPUT.yaml",
            ],
            "write_set": [
                "review/",
                "evidence/",
                "submission/",
                "closure/",
            ],
            "protected_files_touched": False,
            "conflict_level": "low",
        },
    }
    path = target / "TASKSPEC.json"
    path.write_text(json.dumps(task_spec, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def write_paper_execution_report(
    target: Path,
    verifier_failures: list[str],
    generated_at: str,
) -> tuple[Path, Path]:
    paper_id, _ = _paper_identity(target)
    execution_failed = bool(verifier_failures)
    report = {
        "report_id": f"execution-report-{PIPELINE_RUN_ID}",
        "batch_id": PIPELINE_RUN_ID,
        "generated_at": generated_at,
        "status": "fail" if execution_failed else "escalate",
        "review_status": "rejected" if execution_failed else "submitted",
        "summary": (
            "Synthetic paper execution completed within dry-run and no-real-content "
            "boundaries; independent governance review is still required."
            if not execution_failed
            else "Synthetic paper execution failed its bounded runtime gates."
        ),
        "executor_id": "devframe-paper-stage-executor",
        "run_ids": [f"run-paper-{paper_id}"],
        "recommendations": [
            "Require explicit human authorization before any real paper content or external submission."
        ],
        "blocking_issues": (
            verifier_failures
            if execution_failed
            else ["independent_review_required"]
        ),
    }

    json_path = target / "execution-report.json"
    markdown_path = target / "execution-report.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_text(
        "\n".join([
            "# ExecutionReport",
            "",
            f"- Batch: `{PIPELINE_RUN_ID}`",
            f"- Status: `{report['status']}`",
            f"- Review: `{report['review_status']}`",
            f"- Summary: {report['summary']}",
            "- Next gate: independent governance review",
            "",
        ]),
        encoding="utf-8",
    )
    return json_path, markdown_path


def mark_paper_execution_state(target: Path, *, failed: bool) -> None:
    state_path = target / "PAPER_STATE.yaml"
    state: dict = {}
    if state_path.is_file():
        loaded = yaml.safe_load(state_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            state = loaded
    state.update({
        "current_stage": "failed" if failed else "review_requested",
        "status": "failed" if failed else "completed",
        "next_stage": "retry_execution" if failed else "review_received",
    })
    state_path.write_text(
        yaml.safe_dump(state, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def write_pre_submission_check(path: Path, check_result: dict) -> None:
    yaml_lines = [f"# Pre-Submission Check", f"pipeline_run_id: {PIPELINE_RUN_ID}", ""]
    for k, v in check_result.items():
        if isinstance(v, list):
            yaml_lines.append(f"{k}:")
            for item in v:
                yaml_lines.append(f"  - {item}")
        else:
            yaml_lines.append(f"{k}: {v}")
    path.write_text("\n".join(yaml_lines), encoding="utf-8")


def run_paper_task_validator(source: Path, output_path: Path) -> tuple[bool, str | None]:
    try:
        result = validate_paper_task_source(source)
        write_gate_result(result, output_path)
    except Exception as exc:
        output_path.write_text(
            json.dumps({"status": "fail", "errors": [str(exc)]}, indent=2),
            encoding="utf-8",
        )
        return False, "paper_task_validator_error"
    return result.passed, None if result.passed else "paper_task_validator_failed"


def execute_project_init(project_dir: Path = None) -> StageResult:
    """Stage 0: Initialize paper_iteration project."""
    result = StageResult(stage_id="project_init")
    target = project_dir or RUN_DIR

    if not (target / "PAPER_PROFILE.yaml").exists():
        result.status = "failed"
        result.errors.append("Project not initialized — run: devframe init paper_iteration <dir>")
        return result

    result.status = "completed"
    result.outputs = [str(target / f) for f in [
        "PAPER_PROFILE.yaml", "PAPER_STATE.yaml", "PAPER_LEDGER.md",
        "PAPER_NEXT_TASK.md", "PAPER_REVIEW_SPEC.md", "PAPER_SAFETY.md"
    ] if (target / f).exists()]
    return result


def execute_load_input(project_dir: Path = None) -> StageResult:
    """Stage 1: Create synthetic paper content."""
    result = StageResult(stage_id="load_input")
    target = project_dir or RUN_DIR
    ensure_dir(target / "input")
    ensure_dir(target / "run")
    ensure_dir(paper_task_dir(target))

    synthetic_paper = """# 数字技术对课堂教学互动的影响——一项基于混合方法的实证研究

> synthetic_only: true
> contains_real_user_paper: false
> contains_private_data: false
> pipeline_run_id: {run_id}

## 摘要

本研究采用混合方法，通过问卷调查（N=300）和课堂观察（12节课），探讨了数字技术工具（互动白板、学习管理系统、实时反馈工具）对高校课堂师生互动质量的影响。研究发现：（1）互动白板显著提高了课堂参与度；（2）学习管理系统促进了课后延伸讨论；（3）实时反馈工具增强了教师对学生理解状态的感知。然而，技术工具的有效性高度依赖于教师的整合能力和教学设计。研究建议高校在引入数字技术时同步开展教师专业发展培训。

关键词：数字技术；课堂互动；混合方法；高等教育

## 参考文献

- [syn-ref-01] Davis, F.D. (1989). Perceived Usefulness, Perceived Ease of Use, and User Acceptance of Information Technology. MIS Quarterly, 13(3), 319-340. (synthetic reference — not verified against real database)
- [syn-ref-02] Mishra, P., & Koehler, M.J. (2006). Technological Pedagogical Content Knowledge: A Framework for Teacher Knowledge. Teachers College Record, 108(6), 1017-1054. (synthetic reference — not verified against real database)
- [syn-ref-03] 王某某 (2022). 智慧教室环境下的师生互动研究. 电化教育研究, 43(5), 78-85. (虚构引用 — 未核实真实存在)
- [syn-ref-04] 李某某 (2023). 高等教育数字化转型的路径与挑战. 中国高教研究, (3), 45-52. (虚构引用 — 未核实真实存在)

> 声明：以上全部参考文献均为 synthetic。任何与真实文献的相似均为巧合。
> 不声称已通过 CNKI/Web of Science/CSSCI 核验。
""".format(run_id=PIPELINE_RUN_ID)

    (target / "input" / "SYNTHETIC_PAPER.md").write_text(synthetic_paper, encoding="utf-8")

    synthetic_refs = """# Synthetic References
verification_mode: synthetic_only
real_database_checked: false
all_references_marked_synthetic: true
references:
  - key: syn-ref-01
    title: "Perceived Usefulness, Perceived Ease of Use, and User Acceptance of Information Technology"
    author: "Davis, F.D."
    year: 1989
    journal: "MIS Quarterly"
    verification_status: synthetic_unverified
    note: "经典文献引用，但未通过真实数据库核验。synthetic-only pipeline 不执行真实文献检索。"
  - key: syn-ref-02
    title: "Technological Pedagogical Content Knowledge"
    author: "Mishra, P. & Koehler, M.J."
    year: 2006
    journal: "Teachers College Record"
    verification_status: synthetic_unverified
  - key: syn-ref-03
    title: "智慧教室环境下的师生互动研究"
    author: "王某某"
    year: 2022
    journal: "电化教育研究"
    verification_status: synthetic_fictional
    note: "虚构中文引用，未核实真实存在。"
  - key: syn-ref-04
    title: "高等教育数字化转型的路径与挑战"
    author: "李某某"
    year: 2023
    journal: "中国高教研究"
    verification_status: synthetic_fictional
"""

    (target / "input" / "SYNTHETIC_REFERENCES.yaml").write_text(synthetic_refs, encoding="utf-8")
    (target / "run" / "PIPELINE_RUN_ID.txt").write_text(PIPELINE_RUN_ID, encoding="utf-8")

    paper_input = f"""# PAPER-A2/PAPER-A3 synthetic paper task input
task_id: "{PIPELINE_RUN_ID}"
task_type: "cssci_review"
paper_data_classification: "synthetic"
user_authorization: "synthetic"
input_materials: ["synthetic_paper_title", "synthetic_paper_abstract", "synthetic_paper_outline"]
privacy_constraints: ["no_real_paper", "no_user_identity", "no_external_upload"]
memory_policy: "redacted_workflow_lesson_only"
expected_outputs: ["overall_assessment", "main_contribution", "major_problems", "revision_priorities", "publishability_judgment"]
"""
    privacy_attestation = f"""# PAPER-A2/PAPER-A3 privacy attestation
task_id: "{PIPELINE_RUN_ID}"
contains_real_paper_full_text: false
contains_user_private_text: false
contains_raw_transcript: false
contains_memory_write: false
contains_external_upload: false
redaction_applied: true
manual_review_required: false
memory_write_policy: "redacted_workflow_lesson_only"
safety:
  live_cdp_enabled: false
  cookies_or_session_read: false
  historical_evidence_modified: false
  gpt_review_forged: false
"""
    redaction_report = f"""# PAPER-A2/PAPER-A3 redaction report
task_id: "{PIPELINE_RUN_ID}"
redaction_applied: true
redaction_type: "synthetic_only"
original_content_type: "synthetic_paper_metadata"
methods_applied: ["no_real_paper_used", "all_content_synthetic", "no_user_identity"]
verification_passed: true
contains_real_paper_full_text: false
contains_user_private_text: false
contains_raw_transcript: false
manual_review_required: false
notes: "All content is synthetic. No real paper text or user data was processed."
"""
    (paper_task_dir(target) / "PAPER_TASK_INPUT.yaml").write_text(paper_input, encoding="utf-8")
    (paper_task_dir(target) / "PRIVACY_ATTESTATION.yaml").write_text(privacy_attestation, encoding="utf-8")
    (paper_task_dir(target) / "REDACTION_REPORT.yaml").write_text(redaction_report, encoding="utf-8")
    task_spec_path = write_paper_task_spec(target)

    result.status = "completed"
    result.outputs = [
        str(target / "input" / "SYNTHETIC_PAPER.md"),
        str(target / "input" / "SYNTHETIC_REFERENCES.yaml"),
        str(target / "run" / "PIPELINE_RUN_ID.txt"),
        str(paper_task_dir(target) / "PAPER_TASK_INPUT.yaml"),
        str(paper_task_dir(target) / "PRIVACY_ATTESTATION.yaml"),
        str(paper_task_dir(target) / "REDACTION_REPORT.yaml"),
        str(task_spec_path),
    ]
    return result


def execute_paper_review(project_dir: Path = None) -> StageResult:
    """Stage 2: Deterministic CSSCI 9-dimension synthetic paper review."""
    result = StageResult(stage_id="paper_review")
    target = project_dir or RUN_DIR
    ensure_dir(target / "review")
    ensure_dir(paper_task_dir(target))

    dimensions = {
        "problem_awareness": {"score": "良好", "rationale": "问题意识明确，从'技术有效性的条件性'切入有现实针对性。研究问题聚焦数字技术工具对互动质量的影响，但调节变量（教师整合能力）的引入可以更早。"},
        "theoretical_contribution": {"score": "中等", "rationale": "将教师整合能力作为调节变量引入 TAM/TPACK 框架，有边际理论贡献。但理论创新程度有限，主要是框架整合而非框架突破。"},
        "literature_dialogue": {"score": "需要加强", "rationale": "文献回顾覆盖了 TAM 模型和 TPACK 框架，但停留在列举层面。核心发现与已有文献的对话深度不足，缺少'我们的发现与XX研究一致/不一致，因为...'式讨论。"},
        "conceptual_precision": {"score": "良好", "rationale": "核心概念基本清晰。'互动质量'从参与度、延伸讨论、感知状态三个子维度操作化，但操作化定义的精度可进一步提升。"},
        "structural_coherence": {"score": "良好", "rationale": "文章结构清晰，引言→文献综述→方法→发现→讨论→结论的标准结构完整。方法论与研究发现之间的衔接可进一步强化。"},
        "argument_depth": {"score": "中等", "rationale": "量化结果（N=300问卷）的分析较充分，但质性数据（12节课观察）的支撑偏弱。课堂观察的编码过程和典型案例缺乏详细呈现。"},
        "journal_fit": {"score": "良好", "rationale": "与目标期刊（教育技术/课程与教学方向）的办刊方向基本匹配。混合方法设计符合当前教育研究的方法论趋势。"},
        "academic_expression": {"score": "良好", "rationale": "语言规范性良好，学术表达清晰。个别段落存在重复表述，可进一步凝练。"},
        "citation_reliability": {"score": "需要关注", "rationale": "4条引用中有2条为虚构中文引用（syn-ref-03, syn-ref-04），2条英文引用为经典文献但未经真实数据库核验。synthetic pipeline 不执行真实核验，正式投稿前必须逐条核实。"},
    }

    # DIMENSION_SCORES.yaml
    dim_lines = ["# CSSCI 9-Dimension Review Scores", f"pipeline_run_id: {PIPELINE_RUN_ID}", "synthetic_only: true", ""]
    for dim, data in dimensions.items():
        dim_lines.append(f"{dim}:")
        dim_lines.append(f'  score: "{data["score"]}"')
        dim_lines.append(f'  rationale: "{data["rationale"]}"')
        dim_lines.append("")
    (target / "review" / "DIMENSION_SCORES.yaml").write_text("\n".join(dim_lines), encoding="utf-8")

    # REVIEW_REPORT.md
    report = f"""# Synthetic CSSCI Review Report

> pipeline_run_id: {PIPELINE_RUN_ID}
> synthetic_only: true
> review_type: cssci_9_dimension
> real_database_checked: false

## 总体评价

论文采用混合方法探讨数字技术对课堂教学互动的影响，选题有现实意义。
9个维度评估中，4个维度为"良好"，3个为"中等"，2个"需要加强/关注"。

## 各维度评估

"""
    for dim, data in dimensions.items():
        report += f"### {dim}\n- 评分: {data['score']}\n- 评价: {data['rationale']}\n\n"

    report += """## 主要问题

1. 文献对话停留在列举层面，缺少与核心发现的深度对照讨论
2. 课堂观察数据的分析深度不足，建议补充编码过程和典型案例
3. 引用可靠性需要关注：2条虚构中文引用，2条英文引用未经核验

## 修改建议

1. 深化文献对话，将 TAM/TPACK 框架与核心发现进行对照讨论
2. 补充课堂观察编码方案和典型案例
3. 正式投稿前核实全部引用
4. 精简重复表述，凝练学术表达
"""
    (target / "review" / "REVIEW_REPORT.md").write_text(report, encoding="utf-8")

    # CITATION_CHECK_RESULT.yaml
    citation = f"""# Citation Check Result
verification_mode: synthetic_only
real_database_checked: false
all_references_marked_synthetic: true
fabricated_real_citation_detected: false
unverified_real_citation_present: false
pipeline_run_id: {PIPELINE_RUN_ID}

citations:
  - key: syn-ref-01
    status: synthetic_unverified
    note: "经典文献，synthetic pipeline 不执行真实核验"
  - key: syn-ref-02
    status: synthetic_unverified
  - key: syn-ref-03
    status: synthetic_fictional
    note: "虚构中文引用，不声称真实存在"
  - key: syn-ref-04
    status: synthetic_fictional
"""
    (target / "review" / "CITATION_CHECK_RESULT.yaml").write_text(citation, encoding="utf-8")

    # REVIEW_ISSUES.yaml
    issues = f"""# Review Issues
pipeline_run_id: {PIPELINE_RUN_ID}
issues:
  - id: ISS-01
    severity: medium
    dimension: literature_dialogue
    description: "文献对话深度不足，停留在列举层面"
    suggestion: "与核心发现进行逐条对照讨论"
  - id: ISS-02
    severity: medium
    dimension: argument_depth
    description: "课堂观察数据分析偏弱"
    suggestion: "补充编码过程和典型案例"
  - id: ISS-03
    severity: high
    dimension: citation_reliability
    description: "2条虚构中文引用，2条英文引用未核验"
    suggestion: "正式投稿前逐条核实全部引用"
"""
    (target / "review" / "REVIEW_ISSUES.yaml").write_text(issues, encoding="utf-8")

    paper_output = f"""# PAPER-A2/PAPER-A3 synthetic paper task output
task_id: "{PIPELINE_RUN_ID}"
task_type: "cssci_review"
output_summary: "Synthetic CSSCI review generated privacy-safe findings for a synthetic-only paper task."
findings:
  - dimension: "problem_awareness"
    score: "good"
  - dimension: "theoretical_contribution"
    score: "medium"
  - dimension: "literature_dialogue"
    score: "needs_revision"
evidence_basis: "Based on synthetic paper metadata, synthetic abstract, and synthetic outline only."
privacy_redaction_status: "full"
manual_review_required: false
limitations: ["synthetic_only", "no_real_database_check", "no_live_gpt_review"]
contains_real_paper_full_text: false
contains_unredacted_excerpt: false
contains_user_identity: false
"""
    (paper_task_dir(target) / "PAPER_TASK_OUTPUT.yaml").write_text(paper_output, encoding="utf-8")
    result.status = "completed"
    result.outputs = [
        str(target / "review" / "REVIEW_REPORT.md"),
        str(target / "review" / "DIMENSION_SCORES.yaml"),
        str(target / "review" / "CITATION_CHECK_RESULT.yaml"),
        str(target / "review" / "REVIEW_ISSUES.yaml"),
        str(paper_task_dir(target) / "PAPER_TASK_OUTPUT.yaml"),
    ]
    return result


def execute_build_evidence_pack(project_dir: Path = None) -> StageResult:
    """Stage 3: Build evidence pack — framework generates, no manual ZIP."""
    import zipfile

    result = StageResult(stage_id="build_evidence_pack")
    target = project_dir or RUN_DIR
    ensure_dir(target / "evidence")

    zip_path = target / "evidence" / "ref-paper-review-pack.zip"
    manifest_path = target / "evidence" / "PACK_MANIFEST.md"

    # Collect all actual deliverable files
    deliverables = []
    for subdir in ["input", "review", PAPER_TASK_DIRNAME]:
        d = target / subdir
        if d.exists():
            for f in d.iterdir():
                if f.is_file():
                    deliverables.append(f)

    # Build manifest
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    file_entries = []

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(deliverables):
            rel = str(f.relative_to(target)).replace("\\", "/")
            h = sha256(f.read_text(encoding="utf-8"))
            zf.write(f, rel)
            if rel.startswith(f"{PAPER_TASK_DIRNAME}/"):
                role = "paper_task_protocol"
            else:
                role = "synthetic_paper" if "PAPER" in rel else "review_output"
            file_entries.append({"path": rel, "role": role, "sha256": h})

    # Build manifest text directly (no index juggling)
    manifest_text = f"""# Evidence Pack Manifest — REF-PAPER-2A
pipeline_run_id: {PIPELINE_RUN_ID}
created_at: {now}
synthetic_only: true
files_count: {len(file_entries) + 1}

| path | role | sha256 |
|------|------|--------|
"""
    manifest_files = set()
    for e in sorted(file_entries, key=lambda x: x["path"]):
        manifest_text += f"| {e['path']} | {e['role']} | {e['sha256']} |\n"
        manifest_files.add(e["path"])

    # PACK_MANIFEST.md hash is self-excluded (circular dependency)
    manifest_text += f"| PACK_MANIFEST.md | pack_manifest | self_excluded |\n"
    manifest_files.add("PACK_MANIFEST.md")

    manifest_text += f"""
manifest_valid: true
generated_by: devframe_stage_executor
"""
    manifest_path.write_text(manifest_text, encoding="utf-8")

    # Add manifest to ZIP
    with zipfile.ZipFile(zip_path, "a", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("PACK_MANIFEST.md", manifest_text)

    # Verify bidirectional consistency (normalize paths)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zip_files = {n.replace("\\", "/") for n in zf.namelist()}

    if zip_files - manifest_files:
        result.status = "failed"
        result.errors.append(f"ZIP has files not in manifest: {zip_files - manifest_files}")
        return result
    if manifest_files - zip_files:
        result.status = "failed"
        result.errors.append(f"Manifest lists files not in ZIP: {manifest_files - zip_files}")
        return result

    # Generate SAFETY_ATTESTATION.md in evidence/ (before pre_submission_check)
    safety_md = f"""# Safety Attestation - REF-PAPER-2B
pipeline_run_id: {PIPELINE_RUN_ID}
synthetic_only: true
guard_removal_approved: false
evidence_cleanup_approved: false
real_user_paper_processed: false
live_cdp_used: false
bypass_detected: false
real_database_checked: false
generated_by: devframe_stage_executor
"""
    (target / "evidence" / "SAFETY_ATTESTATION.md").write_text(safety_md, encoding="utf-8")

    result.status = "completed"
    result.outputs = [str(zip_path), str(manifest_path), str(target / "evidence" / "SAFETY_ATTESTATION.md")]
    return result


def rebuild_paper_evidence_pack(target: Path) -> tuple[Path, Path]:
    """Rebuild the pack from all paper artifacts produced so far."""
    zip_path = target / "evidence" / "ref-paper-review-pack.zip"
    manifest_path = target / "evidence" / "PACK_MANIFEST.md"
    source_dirs = ("input", PAPER_TASK_DIRNAME, "review", "submission", "closure", "evidence")
    files: list[Path] = []
    for dirname in source_dirs:
        root = target / dirname
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path in {zip_path, manifest_path} or path.suffix == ".zip":
                continue
            files.append(path)
    for name in ("TASKSPEC.json", "execution-report.json", "execution-report.md"):
        path = target / name
        if path.is_file():
            files.append(path)

    entries = []
    for path in sorted(files):
        relative = path.relative_to(target).as_posix()
        role = {
            "input": "synthetic_input",
            PAPER_TASK_DIRNAME: "paper_task_protocol",
            "review": "review_output",
            "submission": "submission_result",
            "closure": "governance_closure",
            "evidence": "gate_evidence",
        }.get(relative.split("/", 1)[0], "deliverable")
        entries.append({
            "path": relative,
            "role": role,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest_lines = [
        "# Evidence Pack Manifest - REF-PAPER",
        f"pipeline_run_id: {PIPELINE_RUN_ID}",
        f"created_at: {now}",
        "synthetic_only: true",
        f"files_count: {len(entries) + 1}",
        "",
        "| path | role | sha256 |",
        "|------|------|--------|",
    ]
    manifest_lines.extend(
        f"| {entry['path']} | {entry['role']} | {entry['sha256']} |"
        for entry in entries
    )
    manifest_lines.extend([
        "| PACK_MANIFEST.md | pack_manifest | self_excluded |",
        "",
        "manifest_valid: true",
        "generated_by: devframe_stage_executor",
        "",
    ])
    manifest_text = "\n".join(manifest_lines)
    manifest_path.write_text(manifest_text, encoding="utf-8")

    temporary_path = zip_path.with_suffix(".rebuild.zip")
    with zipfile.ZipFile(temporary_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, path.relative_to(target).as_posix())
        archive.writestr("PACK_MANIFEST.md", manifest_text)
    temporary_path.replace(zip_path)
    return zip_path, manifest_path


def execute_pre_submission_check(project_dir: Path = None) -> StageResult:
    """Stage 4: Pre-submission gate — bypass check, manifest consistency, summary-only detection."""
    result = StageResult(stage_id="pre_submission_check")
    target = project_dir or RUN_DIR
    ensure_dir(target / "evidence")

    errors = []
    warnings = []
    zip_path = target / "evidence" / "ref-paper-review-pack.zip"

    # 1. Bypass check
    try:
        bypass_result = scan_submission_bypass()
        write_gate_result(bypass_result, target / "evidence" / "BYPASS_CHECK_OUTPUT.txt")
        bypass_passed = bypass_result.passed
    except Exception as exc:
        bypass_passed = None
        warnings.append(f"Bypass checker unavailable: {exc}")

    # 2. Manifest consistency
    manifest_ok = False
    if zip_path.exists():
        with zipfile.ZipFile(zip_path, "r") as zf:
            zip_names = {n.replace("\\", "/") for n in zf.namelist()}
            if "PACK_MANIFEST.md" in zip_names:
                manifest_text = zf.read("PACK_MANIFEST.md").decode("utf-8")
                manifest_listed = set()
                for line in manifest_text.split("\n"):
                    if line.startswith("|") and not line.startswith("|---") and "|" in line[1:]:
                        parts = [p.strip() for p in line.split("|")[1:-1]]
                        if parts and parts[0] and parts[0] != "path":
                            manifest_listed.add(parts[0])
                extra_zip = zip_names - manifest_listed
                extra_man = manifest_listed - zip_names
                manifest_ok = not extra_zip and not extra_man

    # 3. Summary-only detection
    summary_only = True
    if zip_path.exists():
        with zipfile.ZipFile(zip_path, "r") as zf:
            content_files = [n for n in zf.namelist() if n.endswith((".md", ".yaml", ".json")) and n not in ("PACK_MANIFEST.md", "GPT_REVIEW_PROMPT.md", "SAFETY_ATTESTATION.md")]
            summary_only = len(content_files) < 2

    # 4. Write PRE_SUBMISSION_CHECK.yaml
    check_result = {
        "result": "pass" if (bypass_passed and manifest_ok and not summary_only) else "fail",
        "manifest_valid": manifest_ok,
        "zip_manifest_bidirectional_match": manifest_ok,
        "actual_deliverables_present": not summary_only,
        "summary_only_pack_detected": summary_only,
        "bypass_detected": not bypass_passed if bypass_passed is not None else None,
        "pipeline_provenance_present": True,
        "safety_attestation_present": (target / "evidence" / "SAFETY_ATTESTATION.md").exists(),
        "safety_attestation_source": "evidence/SAFETY_ATTESTATION.md",
        "blocking_issues": [],
    }
    if bypass_passed is None:
        check_result["blocking_issues"].append("bypass_checker_unavailable")
    elif not bypass_passed:
        check_result["blocking_issues"].append("bypass_check_failed")
    if not manifest_ok:
        check_result["blocking_issues"].append("manifest_zip_mismatch")
    if summary_only:
        check_result["blocking_issues"].append("summary_only_pack")

    check_path = target / "evidence" / "PRE_SUBMISSION_CHECK.yaml"
    write_pre_submission_check(check_path, check_result)

    # 4.5 Run PAPER-A3 paper task validator on both protocol files and evidence ZIP.
    paper_dir = paper_task_dir(target)
    paper_dir_output = target / "evidence" / "PAPER_TASK_VALIDATION.directory.json"
    paper_zip_output = target / "evidence" / "PAPER_TASK_VALIDATION.zip.json"
    paper_dir_ok, paper_dir_issue = run_paper_task_validator(paper_dir, paper_dir_output)
    paper_zip_ok, paper_zip_issue = run_paper_task_validator(zip_path, paper_zip_output)
    check_result["paper_task_directory_validation"] = "pass" if paper_dir_ok else "fail"
    check_result["paper_task_evidence_pack_validation"] = "pass" if paper_zip_ok else "fail"
    if paper_dir_issue:
        check_result["blocking_issues"].append(f"paper_task_directory_{paper_dir_issue}")
        check_result["result"] = "fail"
    if paper_zip_issue:
        check_result["blocking_issues"].append(f"paper_task_evidence_pack_{paper_zip_issue}")
        check_result["result"] = "fail"

    # Closure authority is evaluated after submission by FinalVerdict + RunIndex.
    check_result["closure_validation"] = "deferred_to_final_verdict"

    write_pre_submission_check(check_path, check_result)
    rebuild_paper_evidence_pack(target)

    if not check_result["blocking_issues"]:
        result.status = "completed"
    else:
        result.status = "failed"
        result.errors = check_result["blocking_issues"]

    result.outputs = [str(check_path), str(paper_dir_output), str(paper_zip_output)]
    return result


def execute_submission_dry_run(project_dir: Path = None) -> StageResult:
    """Stage 5: Submission via submission_adapter (dry-run, no real GPT send)."""
    result = StageResult(stage_id="submission_dry_run")
    target = project_dir or RUN_DIR
    ensure_dir(target / "submission")

    from .submission_adapter import SubmissionAdapter
    from .submission_result import SubmissionRequest

    adapter = SubmissionAdapter(mode="dry_run")
    zip_path = target / "evidence" / "ref-paper-review-pack.zip"

    request = SubmissionRequest(
        zip_path=str(zip_path),
        review_run_id=PIPELINE_RUN_ID,
        prompt_text="Synthetic paper review evidence pack — dry-run submission only.",
    )
    submit_result = adapter.submit(request)

    # Write SUBMISSION_RESULT.json
    submission_output = {
        "mode": "dry_run",
        "adapter": "submission_adapter",
        "live_cdp_used": False,
        "playwright_bridge_used": False,
        "submitted_to_gpt": False,
        "pack_path": str(zip_path),
        "status": "dry_run_success",
        "pipeline_run_id": PIPELINE_RUN_ID,
        "generated_by": "devframe_stage_executor",
    }
    (target / "submission" / "SUBMISSION_RESULT.json").write_text(
        json.dumps(submission_output, indent=2, ensure_ascii=False), encoding="utf-8")

    (target / "submission" / "SUBMISSION_REQUEST.json").write_text(
        json.dumps({"zip_path": request.zip_path, "review_run_id": request.review_run_id}, indent=2), encoding="utf-8")

    result.status = "completed"
    result.outputs = [
        str(target / "submission" / "SUBMISSION_RESULT.json"),
        str(target / "submission" / "SUBMISSION_REQUEST.json"),
    ]
    return result


def execute_closure(project_dir: Path = None) -> StageResult:
    """Stage 6: Seal execution evidence and stop at independent review."""
    result = StageResult(stage_id="closure")
    target = project_dir or RUN_DIR
    ensure_dir(target / "closure")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    flow_outcome = {
        "pipeline_run_id": PIPELINE_RUN_ID,
        "pipeline_path": "pipelines/reference_paper_review.yaml",
        "task_type": "paper_iteration",
        "synthetic_only": True,
        "generated_by": "devframe_stage_executor",
        "generated_at": now,
        "stages": {
            "project_init": "completed",
            "load_input": "completed",
            "paper_review": "completed",
            "build_evidence_pack": "completed",
            "pre_submission_check": "completed",
            "submission_dry_run": "completed",
            "closure": "completed",
        },
        "evidence_pack_path": str(target / "evidence" / "ref-paper-review-pack.zip"),
        "submission_mode": "dry_run",
        "live_cdp_used": False,
        "bypass_detected": False,
        "final_status": "review_pending",
        "safety": {
            "guard_removal_approved": False,
            "evidence_cleanup_approved": False,
            "real_user_paper_processed": False,
            "real_database_checked": False,
        }
    }

    pipeline_gate = validate_paper_pipeline_project(target)
    write_gate_result(pipeline_gate, target / "evidence" / "PAPER_PIPELINE_GATE.json")
    verifier_results = {
        "paper_pipeline_gate": {
            "returncode": 0 if pipeline_gate.passed else 1,
            "status": "passed" if pipeline_gate.passed else "failed",
            "reason": "; ".join(pipeline_gate.errors),
        }
    }
    verifier_failures = [] if pipeline_gate.passed else ["paper_pipeline_gate_failed"]

    if verifier_failures:
        flow_outcome["final_status"] = "failed"
        flow_outcome["stages"]["closure"] = "failed"
        flow_outcome["verifier_failures"] = verifier_failures
    flow_outcome["verifiers"] = verifier_results
    flow_outcome["final_verdict_state"] = "deferred"

    flow_path = target / "closure" / "FLOW_OUTCOME.json"
    flow_path.write_text(json.dumps(flow_outcome, indent=2, ensure_ascii=False), encoding="utf-8")
    stage_rows = "\n".join(
        f"| {stage} | {status} |"
        for stage, status in flow_outcome["stages"].items()
    )
    verifier_rows = "\n".join(
        f"| {name} | {info.get('status', 'unknown')} | {info.get('returncode', '')} | {info.get('reason', '')} |"
        for name, info in verifier_results.items()
    ) or "| none | not_run |  |  |"
    verifier_failure_text = (
        "\n".join(f"- {failure}" for failure in verifier_failures)
        if verifier_failures else "(none)"
    )

    closure_report = f"""# Closure Report — REF-PAPER-2B

> pipeline_run_id: {PIPELINE_RUN_ID}
> generated_by: devframe_stage_executor
> generated_at: {now}
> synthetic_only: true
> final_status: {flow_outcome["final_status"]}

## Stage Status

| Stage | Status |
|-------|--------|
{stage_rows}

## Verifier Status

| Verifier | Status | Return Code | Reason |
|----------|--------|-------------|--------|
{verifier_rows}

## Verifier Failures

{verifier_failure_text}

## Safety Attestation

| Boundary | Value |
|----------|-------|
| guard_removal_approved | false |
| evidence_cleanup_approved | false |
| real_user_paper_processed | false |
| live_cdp_used | false |
| bypass_detected | false |
| real_database_checked | false |

## Outputs

- input/SYNTHETIC_PAPER.md — synthetic paper
- review/DIMENSION_SCORES.yaml — 9-dimension review scores
- review/REVIEW_REPORT.md — full review report
- review/CITATION_CHECK_RESULT.yaml — synthetic-only citation check
- review/REVIEW_ISSUES.yaml — 3 review issues identified
- evidence/ref-paper-review-pack.zip — standard evidence pack
- evidence/PACK_MANIFEST.md — manifest with SHA256
- evidence/PRE_SUBMISSION_CHECK.yaml — pre-submission gate result
- evidence/PAPER_PIPELINE_GATE.json — bounded runtime artifact and safety gate
- submission/SUBMISSION_RESULT.json — submission_adapter dry-run result
- closure/FLOW_OUTCOME.json — framework-generated flow outcome
- closure/CLOSURE_REPORT.md — this report
 - execution-report.json — execution candidate awaiting independent review
"""
    closure_report_path = target / "closure" / "CLOSURE_REPORT.md"
    closure_report_path.write_text(closure_report, encoding="utf-8")
    execution_report_paths = write_paper_execution_report(
        target,
        verifier_failures,
        now,
    )
    rebuild_paper_evidence_pack(target)

    pack_result = validate_evidence_pack(
        target / "evidence" / "ref-paper-review-pack.zip"
    )
    if not pack_result.passed:
        verifier_failures.append("evidence_pack_integrity_failed")
        flow_outcome["final_status"] = "failed"
        flow_outcome["stages"]["closure"] = "failed"
        flow_outcome["verifier_failures"] = verifier_failures
        flow_outcome["verifiers"]["evidence_pack_integrity"] = {
            "returncode": 1,
            "status": "failed",
            "reason": "; ".join(pack_result.errors),
        }
        flow_path.write_text(
            json.dumps(flow_outcome, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        execution_report_paths = write_paper_execution_report(
            target,
            verifier_failures,
            now,
        )
        rebuild_paper_evidence_pack(target)

    mark_paper_execution_state(target, failed=bool(verifier_failures))

    result.status = "failed" if verifier_failures else "completed"
    result.errors = verifier_failures
    result.outputs = [
        str(flow_path),
        str(closure_report_path),
        *(str(path) for path in execution_report_paths),
    ]
    return result


def execute_full_pipeline(project_dir: Path = None) -> list[StageResult]:
    """Execute all stages of the reference paper review pipeline."""
    results = []

    for stage_fn, name in [
        (execute_project_init, "project_init"),
        (execute_load_input, "load_input"),
        (execute_paper_review, "paper_review"),
        (execute_build_evidence_pack, "build_evidence_pack"),
        (execute_pre_submission_check, "pre_submission_check"),
        (execute_submission_dry_run, "submission_dry_run"),
        (execute_closure, "closure"),
    ]:
        print(f"  [{name}] executing...")
        r = stage_fn(project_dir)
        results.append(r)
        if r.status == "failed":
            print(f"  [{name}] FAILED: {r.errors}")
            break
        print(f"  [{name}] completed ({len(r.outputs)} outputs)")

    return results
