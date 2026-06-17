"Pipeline Runner — parse YAML, validate, dry-run stage sequence."
from __future__ import annotations
import sys
from pathlib import Path
from .pipeline_spec import load_pipeline, validate_pipeline, get_stage_sequence


def dry_run(pipeline_path: str | Path, with_submission: bool = False) -> int:
    try:
        pipeline = load_pipeline(pipeline_path)
    except Exception as e:
        print(f"ERROR: Cannot load pipeline: {e}")
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

    if with_submission:
        from .submission_adapter import create_adapter
        from .submission_result import SubmissionRequest
        adapter = create_adapter()

    for i, sid in enumerate(stages):
        stage = pipeline["stages"][i]
        stype = stage.get("type", "unknown")
        depends = stage.get("depends_on", "none")
        gpt = "GPT" if stage.get("requires_gpt_acceptance") else "no-review"
        print(f"  {i+1}. {sid} [{stype}] depends={depends} review={gpt}")
        if with_submission and stage.get("requires_gpt_acceptance"):
            req = SubmissionRequest(review_run_id=f"{pipeline_id}-{sid}-v1")
            result = adapter.submit(req)
            print(f"    -> submission dry-run: success={result.success}, mode={result.mode}")

    print(f"DRY-RUN COMPLETE — all stages valid. submission={'on' if with_submission else 'off'}")
    return 0


def run_cli():
    if "--pipeline" not in sys.argv:
        print("Usage: python -m control_plane.run --pipeline <path> [--dry-run] [--with-submission]")
        sys.exit(1)
    idx = sys.argv.index("--pipeline")
    path = sys.argv[idx + 1]
    with_sub = "--with-submission" in sys.argv
    return dry_run(path, with_submission=with_sub)


if __name__ == "__main__":
    sys.exit(run_cli())
