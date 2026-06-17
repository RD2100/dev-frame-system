"Bootstrap a new conversation with handoff document. Dry-run only."
from __future__ import annotations
from dataclasses import dataclass
from .handoff_generator import generate_handoff
from .handoff_verifier import parse_bootstrap_reply, is_handoff_verified


@dataclass
class BootstrapResult:
    target: str = "new-conversation"
    handoff_generated: bool = False
    handoff_length: int = 0
    submitted: bool = False
    reply_received: bool = False
    reply_parsed: dict = None
    handoff_verified: bool = False
    mode: str = "dry_run"

    def __post_init__(self):
        if self.reply_parsed is None:
            self.reply_parsed = {}


def run_bootstrap(target: str = "new-conversation", dry_run: bool = True) -> BootstrapResult:
    result = BootstrapResult(target=target, mode="dry_run" if dry_run else "live")

    handoff_text = generate_handoff(target)
    result.handoff_generated = True
    result.handoff_length = len(handoff_text)

    if dry_run:
        # Simulate a valid bootstrap reply
        simulated_reply = """overall_judgment: accepted
handoff_understood: true
current_status_understood: true
safety_boundaries_understood: true
next_stage_understood: true
ready_for_next_authorization: true
rationale: "Dry-run simulated bootstrap reply"
"""
        result.submitted = True
        result.reply_received = True
        result.reply_parsed = parse_bootstrap_reply(simulated_reply)
        result.handoff_verified = is_handoff_verified(result.reply_parsed)

    return result
