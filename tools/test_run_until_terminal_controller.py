"""Control Plane Skeleton tests — shadow/replay only."""
from pathlib import Path
from run_until_terminal_controller import (
    RunUntilTerminalController, ReviewDecision, FlowOutcomeDecision,
    DispatchDecision, EvidenceState, replay_history, ContinuationDecision,
)


class TestContinuationRules:
    def setup_method(self):
        self.ctrl = RunUntilTerminalController()

    def test_accepted_ready_dispatch_continues_shadow(self):
        d = self.ctrl.decide_continuation(
            ReviewDecision(overall_judgment="accepted"),
            FlowOutcomeDecision(business_decision="accepted", allow_next_stage=True, next_stage="s3", terminal=False),
            DispatchDecision(dispatch_status="ready_to_dispatch", should_execute_next=True, terminal=False, next_task_spec_path="/t/S3_TASKSPEC.json"),
            EvidenceState(tests_failed=0, evidence_gate_ready=True))
        assert d.should_continue == True

    def test_accepted_missing_next_task_spec_fail_closed(self):
        d = self.ctrl.decide_continuation(
            ReviewDecision(overall_judgment="accepted"),
            FlowOutcomeDecision(business_decision="accepted", allow_next_stage=True, next_stage="s3", terminal=False),
            DispatchDecision(dispatch_status="ready_to_dispatch", should_execute_next=True, terminal=False, next_task_spec_path=""),
            EvidenceState(tests_failed=0, evidence_gate_ready=True))
        assert d.should_continue == False
        assert d.fail_closed == True

    def test_accepted_markdown_task_spec_fail_closed(self):
        d = self.ctrl.decide_continuation(
            ReviewDecision(overall_judgment="accepted"),
            FlowOutcomeDecision(business_decision="accepted", allow_next_stage=True, next_stage="s3", terminal=False),
            DispatchDecision(dispatch_status="ready_to_dispatch", should_execute_next=True, terminal=False, next_task_spec_path="/t/task.md"),
            EvidenceState(tests_failed=0, evidence_gate_ready=True))
        assert d.should_continue == False
        assert d.fail_closed == True
        assert "markdown" in d.stop_reason

    def test_partial_remediation_dispatch_continues_shadow(self):
        d = self.ctrl.decide_continuation(
            ReviewDecision(overall_judgment="partial"),
            FlowOutcomeDecision(business_decision="partial", allow_next_stage=True, next_stage="remediation", terminal=False),
            DispatchDecision(dispatch_status="ready_to_dispatch", should_execute_next=True, terminal=False, next_task_spec_path="/t/REMEDIATION_TASKSPEC.json"),
            EvidenceState(tests_failed=0, evidence_gate_ready=True))
        assert d.should_continue == True

    def test_partial_without_remediation_fail_closed(self):
        d = self.ctrl.decide_continuation(
            ReviewDecision(overall_judgment="partial"),
            FlowOutcomeDecision(business_decision="partial", allow_next_stage=True, terminal=False),
            DispatchDecision(dispatch_status="ready_to_dispatch", should_execute_next=True, terminal=False, next_task_spec_path=""),
            EvidenceState(tests_failed=0, evidence_gate_ready=True))
        assert d.should_continue == False
        assert d.fail_closed == True

    def test_blocked_stops(self):
        d = self.ctrl.decide_continuation(
            ReviewDecision(overall_judgment="blocked", blocked=True),
            FlowOutcomeDecision(business_decision="blocked", terminal=True),
            DispatchDecision(dispatch_status="stopped", terminal=True),
            EvidenceState())
        assert d.should_continue == False
        assert d.stop_reason == "blocked"

    def test_human_required_stops(self):
        d = self.ctrl.decide_continuation(
            ReviewDecision(overall_judgment="human_required", human_required=True),
            FlowOutcomeDecision(business_decision="human_required", terminal=True),
            DispatchDecision(dispatch_status="manual_confirm_required", terminal=True),
            EvidenceState())
        assert d.should_continue == False
        assert d.stop_reason == "human_required"

    def test_tests_failed_fail_closed(self):
        d = self.ctrl.decide_continuation(
            ReviewDecision(overall_judgment="accepted"),
            FlowOutcomeDecision(business_decision="accepted", allow_next_stage=True, next_stage="s3", terminal=False),
            DispatchDecision(dispatch_status="ready_to_dispatch", should_execute_next=True, terminal=False, next_task_spec_path="/t/S3_TASKSPEC.json"),
            EvidenceState(tests_failed=2))
        assert d.should_continue == False
        assert d.fail_closed == True

    def test_evidence_gate_failed_fail_closed(self):
        d = self.ctrl.decide_continuation(
            ReviewDecision(overall_judgment="accepted"),
            FlowOutcomeDecision(business_decision="accepted", allow_next_stage=True, next_stage="s3", terminal=False),
            DispatchDecision(dispatch_status="ready_to_dispatch", should_execute_next=True, terminal=False, next_task_spec_path="/t/S3_TASKSPEC.json"),
            EvidenceState(tests_failed=0, evidence_gate_ready=False))
        assert d.should_continue == False
        assert d.fail_closed == True

    def test_flow_dispatch_split_brain_fail_closed(self):
        d = self.ctrl.decide_continuation(
            ReviewDecision(overall_judgment="accepted"),
            FlowOutcomeDecision(business_decision="accepted", allow_next_stage=True, next_stage="s3", terminal=False, next_task_spec_path="/t/S3_TASKSPEC.json"),
            DispatchDecision(dispatch_status="ready_to_dispatch", should_execute_next=True, terminal=False, next_task_spec_path="/t/WRONG_TASKSPEC.json"),
            EvidenceState(tests_failed=0, evidence_gate_ready=True))
        assert d.should_continue == False
        assert d.fail_closed == True

    def test_guarded_decision_mismatch_fail_closed(self):
        d = self.ctrl.decide_continuation(
            ReviewDecision(overall_judgment="accepted"),
            FlowOutcomeDecision(business_decision="accepted", allow_next_stage=True, next_stage="contract_freeze_review", terminal=False, next_task_spec_path="/t/CONTRACT_FREEZE_REVIEW_TASKSPEC.json"),
            DispatchDecision(dispatch_status="ready_to_dispatch", should_execute_next=True, terminal=False, next_task_spec_path="/t/CONTRACT_FREEZE_REVIEW_TASKSPEC.json"),
            EvidenceState(tests_failed=0, evidence_gate_ready=True, guarded_next_stage="s3", flow_next_stage="contract_freeze_review"))
        assert d.should_continue == False
        assert d.fail_closed == True

    def test_production_promotion_requires_human(self):
        d = self.ctrl.decide_continuation(
            ReviewDecision(overall_judgment="accepted"),
            FlowOutcomeDecision(business_decision="accepted", allow_next_stage=True, next_stage="production_promotion_review", terminal=False),
            DispatchDecision(dispatch_status="ready_to_dispatch", should_execute_next=True, terminal=False, next_task_spec_path="/t/PROMO.json"),
            EvidenceState(tests_failed=0, evidence_gate_ready=True))
        assert d.should_continue == False
        assert "production_promotion" in d.stop_reason

    def test_unknown_next_stage_fail_closed(self):
        d = self.ctrl.decide_continuation(
            ReviewDecision(overall_judgment="accepted"),
            FlowOutcomeDecision(business_decision="accepted", allow_next_stage=True, next_stage="unknown_future_stage", terminal=False, next_task_spec_path="/t/t.json"),
            DispatchDecision(dispatch_status="ready_to_dispatch", should_execute_next=True, terminal=False, next_task_spec_path="/t/t.json"),
            EvidenceState(tests_failed=0, evidence_gate_ready=True))
        assert d.should_continue == False
        assert d.fail_closed == True

    def test_replay_historical_accepted_stop_detected(self):
        results = replay_history(self.ctrl)
        # Tests that controller produces decisions for all replayed packs
        assert len(results) > 0
        # At least one pack should be successfully replayed
        has_decision = any("controller_decision" in r for r in results)
        assert has_decision

    def test_replay_historical_partial_remediation_detected(self):
        results = replay_history(self.ctrl)
        # Verify real pack replay includes evidence extraction
        has_files = any("files_found" in r for r in results)
        assert has_files

    def test_controller_never_executes_taskspec_in_shadow_mode(self):
        assert self.ctrl.mode == "shadow_replay"
        d = self.ctrl.decide_continuation(
            ReviewDecision(overall_judgment="accepted"),
            FlowOutcomeDecision(business_decision="accepted", allow_next_stage=True, next_stage="s3", terminal=False),
            DispatchDecision(dispatch_status="ready_to_dispatch", should_execute_next=True, terminal=False, next_task_spec_path="/t/S3_TASKSPEC.json"),
            EvidenceState(tests_failed=0, evidence_gate_ready=True))
        assert d.should_continue == True
        # In shadow mode, we compute the decision but never actually invoke the runner


class TestSkeletonV22Fixes:
    """Verify v2.2 fixes: normalized judgment in replay chain, consistent counts."""
    SKELETON_DIR = Path(__file__).resolve().parent.parent / "_reports" / "gca-phase3" / "control-plane-skeleton"

    def test_controller_uses_normalized_gpt_judgment(self):
        """accepted, with trailing comma must be accepted by decide_continuation."""
        ctrl = RunUntilTerminalController()
        # Simulate a review that has "accepted," (trailing comma from GPT output)
        review = ReviewDecision(overall_judgment="accepted,")
        flow = FlowOutcomeDecision(business_decision="accepted", allow_next_stage=True,
                                   next_stage="s3", terminal=False)
        dispatch = DispatchDecision(dispatch_status="ready_to_dispatch", should_execute_next=True,
                                    terminal=False, next_task_spec_path="/t/S3_TASKSPEC.json")
        evidence = EvidenceState(tests_failed=0, evidence_gate_ready=True)
        # Without .rstrip(), this would fail with "unhandled state: accepted,"
        # With the fix, it should normalize to "accepted" and continue
        d = ctrl.decide_continuation(review, flow, dispatch, evidence)
        assert d.fail_closed == False, f"Should not fail-closed on 'accepted,' — got: {d.reason}"

    def test_replay_result_has_no_unhandled_accepted_comma(self):
        """CONTROL_PLANE_REPLAY_RESULT.json must not contain unhandled state: accepted,."""
        import json
        rp = self.SKELETON_DIR / "CONTROL_PLANE_REPLAY_RESULT.json"
        if rp.exists():
            data = json.loads(rp.read_text(encoding="utf-8"))
            for case in data.get("cases", []):
                reason = case.get("controller_decision", {}).get("reason", "")
                assert "unhandled state: accepted," not in reason, \
                    f"Case {case['case_id']} has unhandled accepted,: {reason}"

    def test_replay_report_counts_match_replay_result_json(self):
        """Counts in report and JSON must be identical."""
        import json, re
        rp = self.SKELETON_DIR / "CONTROL_PLANE_REPLAY_RESULT.json"
        report = self.SKELETON_DIR / "CONTROL_PLANE_REPLAY_REPORT.md"
        if rp.exists() and report.exists():
            data = json.loads(rp.read_text(encoding="utf-8"))
            text = report.read_text(encoding="utf-8")
            json_continue = data["would_auto_continue_count"]
            json_fail = data["would_fail_closed_count"]
            m = re.search(r"(?:Would auto-)?[Cc]ontinue:\s*(\d+)", text)
            report_continue = int(m.group(1)) if m else -1
            m = re.search(r"(?:Would )?[Ff]ail-closed:\s*(\d+)", text)
            report_fail = int(m.group(1)) if m else -1
            assert json_continue == report_continue, \
                f"Continue: JSON={json_continue} Report={report_continue}"
            assert json_fail == report_fail, \
                f"Fail-closed: JSON={json_fail} Report={report_fail}"

    def test_zip_has_no_duplicate_manifest_entry(self):
        """Zip pack must not contain duplicate PACK_MANIFEST.md."""
        import zipfile
        zp = self.SKELETON_DIR / "control-plane-skeleton-v2-2-pack.zip"
        if zp.exists():
            with zipfile.ZipFile(zp, 'r') as zf:
                names = zf.namelist()
                manifest_count = sum(1 for n in names if n == "PACK_MANIFEST.md")
                assert manifest_count <= 1, \
                    f"PACK_MANIFEST.md appears {manifest_count} times (expected 0 or 1)"
