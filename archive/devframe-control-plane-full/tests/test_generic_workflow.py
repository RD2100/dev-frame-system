"""Test control-plane workflow, registry, and CLI modules."""
import sys
from pathlib import Path
CTRL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CTRL / "scripts"))

class TestWorkflowRegistry:
    def test_registry_has_entries(self):
        from workflow_registry import REGISTRY
        assert len(REGISTRY) >= 4
    
    def test_generic_workflow_pipeline(self):
        from generic_workflow import PIPELINE
        assert len(PIPELINE) >= 3
    
    def test_run_history(self):
        from run_history import log, tail
        assert callable(log); assert callable(tail)
    
    def test_artifacts(self):
        from workflow_artifacts import save, list_runs, latest
        assert callable(save); assert callable(list_runs)

class TestCLI:
    def test_cli_importable(self):
        sys.path.insert(0, str(CTRL))
        import devframe_cli
        assert hasattr(devframe_cli, "main")

    def test_run_history_logs_and_tails(self):
        from run_history import log, tail
        r = log("cli-test", "PASS", "test run")
        assert r["status"] == "PASS"
        entries = tail(5)
        assert len(entries) >= 1
        assert any(e["workflow"] == "cli-test" for e in entries)

    def test_artifacts_save_and_list(self):
        from workflow_artifacts import save, list_runs
        result = save("cli-test", {"status": "ok"})
        assert "artifacts" in result or "cli-test" in result
        assert len(list_runs()) >= 1
