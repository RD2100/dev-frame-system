"""Pipeline runner: parse YAML, validate, and dry-run stage sequence."""
from __future__ import annotations

import sys
from pathlib import Path

from .pipeline_spec import get_stage_sequence, load_pipeline, validate_pipeline


def dry_run(pipeline_path: str | Path, with_submission: bool = False) -> int:
    try:
        pipeline = load_pipeline(pipeline_path)
    except Exception as exc:
        print(f"ERROR: Cannot load pipeline: {exc}")
        return 1

    errors = validate_pipeline(pipeline)
    if errors:
        print("VALIDATION ERRORS:")
        for err in errors:
            print(f"  - {err}")
        return 1

    stages = get_stage_sequence(pipeline)
    pipeline_id = pipeline.get("pipeline_id", "unknown")
    print(f"Pipeline: {pipeline_id}")
    print(f"Stages: {len(stages)}")

    adapter = None
    if with_submission:
        from .submission_adapter import create_adapter
        adapter = create_adapter()

    for index, stage_id in enumerate(stages):
        stage = pipeline["stages"][index]
        stage_type = stage.get("type", "unknown")
        depends = stage.get("depends_on", "none")
        review = "GPT" if stage.get("requires_gpt_acceptance") else "no-review"
        print(f"  {index + 1}. {stage_id} [{stage_type}] depends={depends} review={review}")
        if adapter and stage.get("requires_gpt_acceptance"):
            from .submission_result import SubmissionRequest
            req = SubmissionRequest(review_run_id=f"{pipeline_id}-{stage_id}-v1")
            result = adapter.submit(req)
            print(f"    -> submission dry-run: success={result.success}, mode={result.mode}")

    print(f"DRY-RUN COMPLETE: all stages valid. submission={'on' if with_submission else 'off'}")
    return 0


def run_cli() -> int:
    if "--pipeline" not in sys.argv:
        print("Usage: python -m control_plane.run --pipeline <path> [--dry-run] [--with-submission]")
        return 1
    index = sys.argv.index("--pipeline")
    path = sys.argv[index + 1]
    with_submission = "--with-submission" in sys.argv
    return dry_run(path, with_submission=with_submission)


if __name__ == "__main__":
    sys.exit(run_cli())
