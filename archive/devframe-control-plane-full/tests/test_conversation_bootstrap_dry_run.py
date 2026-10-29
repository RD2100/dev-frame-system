import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from control_plane.conversation_bootstrap import run_bootstrap, BootstrapResult


def test_run_bootstrap_dry_run_returns_result():
    result = run_bootstrap(target="new-conversation", dry_run=True)
    assert isinstance(result, BootstrapResult)
    assert result.mode == "dry_run"
    assert result.handoff_generated is True
    assert result.handoff_length > 500
    assert result.submitted is True
    assert result.reply_received is True
    assert result.handoff_verified is True


def test_run_bootstrap_dry_run_parses_reply():
    result = run_bootstrap(target="test-target", dry_run=True)
    assert result.reply_parsed["handoff_understood"] is True
    assert result.reply_parsed["overall_judgment"] == "accepted"
