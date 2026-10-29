"Submission data structures — dry-run only, no real CDP."
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SubmissionRequest:
    zip_path: str = ""
    prompt_text: str = ""
    conversation_id: str = ""
    review_run_id: str = ""


@dataclass
class SubmissionResult:
    success: bool = False
    review_run_id: str = ""
    captured_reply_length: int = 0
    captured_reply_sha256: str = ""
    parsed_judgment: str = "pending"
    mode: str = "dry_run"
    detail: str = ""


def dry_run_result(request: SubmissionRequest) -> SubmissionResult:
    return SubmissionResult(
        success=True,
        review_run_id=request.review_run_id,
        captured_reply_length=0,
        captured_reply_sha256="dry_run_no_capture",
        parsed_judgment="dry_run_pending",
        mode="dry_run",
        detail=f"Simulated submission for {request.review_run_id} — no CDP, no GPT",
    )
