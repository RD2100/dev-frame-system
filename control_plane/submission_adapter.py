"Submission Adapter — dry-run interface, no real CDP."
from __future__ import annotations
from .submission_result import SubmissionRequest, SubmissionResult, dry_run_result


class SubmissionAdapter:
    def __init__(self, mode: str = "dry_run"):
        if mode not in ("dry_run",):
            raise ValueError(f"Unsupported mode: {mode}. Only dry_run is available.")
        self.mode = mode

    def submit(self, request: SubmissionRequest) -> SubmissionResult:
        if self.mode != "dry_run":
            raise RuntimeError("Only dry_run mode is supported in G3")
        return dry_run_result(request)

    def can_submit(self) -> bool:
        return self.mode == "dry_run"


def create_adapter() -> SubmissionAdapter:
    return SubmissionAdapter(mode="dry_run")
