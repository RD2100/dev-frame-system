"CDP Adapter — interface, safety guards, dry-run fallback. No real Playwright/GPT."
from __future__ import annotations
from enum import Enum
from .submission_result import SubmissionRequest, SubmissionResult, dry_run_result


class AdapterMode(str, Enum):
    DRY_RUN = "dry_run"
    NOT_CONFIGURED = "not_configured"
    UNAVAILABLE = "unavailable"


class CdpAdapter:
    def __init__(self, mode: AdapterMode = AdapterMode.DRY_RUN):
        self.mode = mode

    def submit(self, request: SubmissionRequest) -> SubmissionResult:
        if self.mode == AdapterMode.DRY_RUN:
            return dry_run_result(request)
        if self.mode == AdapterMode.NOT_CONFIGURED:
            return SubmissionResult(
                success=False, review_run_id=request.review_run_id,
                mode="not_configured",
                detail="CDP not configured — set CDP_HOST and CDP_PORT",
            )
        if self.mode == AdapterMode.UNAVAILABLE:
            return SubmissionResult(
                success=False, review_run_id=request.review_run_id,
                mode="unavailable",
                detail="CDP unavailable — Chrome not running on configured port",
            )
        return SubmissionResult(success=False, detail=f"Unknown mode: {self.mode}")

    def health_check(self) -> bool:
        return self.mode == AdapterMode.DRY_RUN

    def can_submit(self) -> bool:
        return self.mode == AdapterMode.DRY_RUN

    def safety_attestation(self) -> dict:
        return {
            "no_real_cdp": True,
            "no_playwright": True,
            "no_gpt_submission": True,
            "no_state_mutation": True,
            "mode": self.mode.value,
        }


def create_adapter(mode: str = "dry_run") -> CdpAdapter:
    return CdpAdapter(AdapterMode(mode))
