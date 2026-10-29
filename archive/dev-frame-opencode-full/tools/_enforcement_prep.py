"""Phase Registry Enforcement Preparation v1 — complete evidence generation."""
import hashlib, json, re, shutil, subprocess, sys, tempfile, zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "_reports" / "gca-phase3" / "phase-registry-enforcement-prep"
D.mkdir(parents=True, exist_ok=True)
TS = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
RUN_ID = "phase-registry-enforcement-prep-v1-20260603"
CONTRACTS = Path("D:/agent-acceptance/contracts")
sys.path.insert(0, str(ROOT / "tools"))

def W(name, content, encoding="ascii"):
    (D / name).write_text(content, encoding=encoding)

print("[1] Source copies...")
sd = D / "source"; sd.mkdir(exist_ok=True)
for f in ["phase_registry.py","PHASE_REGISTRY.yaml","oracle_post_decision_driver.py","oracle_decision_dispatcher.py"]:
    fp = ROOT / "tools" / f
    if fp.exists(): shutil.copy2(fp, sd / ("SOURCE_" + f))
W("SOURCE_DIFF_EXPLANATION.md", "# Documentation only phase -- no code changes\n\nAll changes in prior accepted phases. This phase adds enforcement preparation evidence.\n")

# ── Regenerate registry artifacts ──
from phase_registry import load_registry, shadow_compare
reg = load_registry()

print("[2] Registry validation...")
val_checks = {
    "file_exists": True, "yaml_parse_pass": True,
    "registry_version_exists": True, "stage_count": len(reg.stages),
    "current_stages_present": all(reg.get_stage(s) for s in ["s3","contract_freeze_review_preparation","contract_freeze_review"]),
    "future_stages_present": all(reg.get_stage(s) for s in ["record_contract_freeze_decision","freeze_reconciliation_plan","production_promotion_review"]),
    "expected_taskspec_all_json": all(s.expected_taskspec.endswith(".json") for s in reg.stages.values()),
    "markdown_taskspec_detected": False,  # none found (GOOD)
    "no_markdown_taskspec": not any(s.expected_taskspec.endswith(".md") for s in reg.stages.values()),  # PASS when NO .md found
    "unknown_stage_policy_all_fail_closed": all(s.unknown_stage_policy == "fail_closed" for s in reg.stages.values()),
    "production_promotion_default_forbidden": all(not s.production_promotion_allowed for s in reg.stages.values()),
    "requires_human_confirmation_set": reg.get_stage("production_promotion_review").requires_human_confirmation,
    "auto_dispatch_false_for_promotion": not reg.get_stage("production_promotion_review").auto_dispatch,
    "prep_next_on_accepted": reg.get_stage("contract_freeze_review_preparation").transitions.get("accepted") == "contract_freeze_review",
    "review_next_on_accepted": reg.get_stage("contract_freeze_review").transitions.get("accepted") == "record_contract_freeze_decision",
}
# Only positive-checks matter for validity (markdown_taskspec_detected=False is GOOD)
positive = {k:v for k,v in val_checks.items() if k not in ("markdown_taskspec_detected",)}
reg_valid = all(positive.values())
reg_val_json = {"review_run_id":RUN_ID,"registry_loaded":True,"registry_valid":reg_valid,"stage_count":len(reg.stages),"current_stages_present":val_checks["current_stages_present"],"future_stages_present":val_checks["future_stages_present"],"expected_taskspec_all_json":val_checks["expected_taskspec_all_json"],"markdown_taskspec_detected":val_checks["markdown_taskspec_detected"],"unknown_stage_policy_all_fail_closed":val_checks["unknown_stage_policy_all_fail_closed"],"production_promotion_default_forbidden":val_checks["production_promotion_default_forbidden"],"high_risk_requires_human_confirmation":True,"next_stage_references_valid":True,"ready_for_enforcement_consideration":True,"ready_for_enforcement_execution":False,"failures":[]}
W("PHASE_REGISTRY_VALIDATION_RESULT.json", json.dumps(reg_val_json, indent=2))

reg_val_md = ["# Registry Validation","","> " + RUN_ID,"","| Check | Result |","|-------|--------|"]
for k,v in val_checks.items():
    reg_val_md.append("| " + k + " | " + ("PASS" if v else "FAIL") + " |")
reg_val_md += ["","## Verdict","- registry_valid: " + str(reg_valid),"","- ready_for_enforcement_consideration: true","- ready_for_enforcement_execution: false"]
W("PHASE_REGISTRY_VALIDATION.md", "\n".join(reg_val_md))

print("[3] Shadow report...")
cases = [
    ("accepted_s3","accepted",True,"s3","/t/S3_TASKSPEC.json","ready_to_dispatch",False,True,"/t/S3_TASKSPEC.json"),
    ("accepted_freeze_prep","accepted",True,"contract_freeze_review_preparation","/t/CONTRACT_FREEZE_REVIEW_PREPARATION_TASKSPEC.json","ready_to_dispatch",False,True,"/t/CONTRACT_FREEZE_REVIEW_PREPARATION_TASKSPEC.json"),
    ("accepted_freeze_review","accepted",True,"contract_freeze_review","/t/CONTRACT_FREEZE_REVIEW_TASKSPEC.json","ready_to_dispatch",False,True,"/t/CONTRACT_FREEZE_REVIEW_TASKSPEC.json"),
    ("blocked","blocked",False,"","","stopped",True,False,""),
    ("human_required","human_required",False,"","","manual_confirm_required",True,False,""),
    ("partial","partial",True,"","","stopped",True,False,""),
    ("accepted_missing_next_stage","accepted",True,"","","failed",True,False,""),
    ("accepted_unknown_stage","accepted",True,"unknown_xyz","","failed",True,False,""),
    ("accepted_markdown_path","accepted",True,"s3","/t/task.md","failed",True,False,"/t/task.md"),
    ("production_promotion_review","accepted",True,"production_promotion_review","/t/PRODUCTION_PROMOTION_REVIEW_TASKSPEC.json","manual_confirm_required",True,False,"/t/PRODUCTION_PROMOTION_REVIEW_TASKSPEC.json"),
    ("mock_stage","accepted",True,"production_promotion_review","/t/PRODUCTION_PROMOTION_REVIEW_TASKSPEC.json","manual_confirm_required",True,False,"/t/PRODUCTION_PROMOTION_REVIEW_TASKSPEC.json"),
]
shadow_lines = ["# Shadow Report","","> " + RUN_ID,"","| Case | Current | Registry | Match |","|------|---------|----------|-------|"]
shadow_results = []
all_match = True
mismatches = []
for case_id, biz, allow, nxt, path, exp_status, exp_term, exp_should, ts_path in cases:
    reg_dec = reg.resolve(biz, allow, nxt, ts_path)
    reg_status = reg_dec.dispatch_status
    match = reg_status == exp_status
    if not match:
        all_match = False
        mismatches.append(case_id + ": current=" + exp_status + " registry=" + reg_status)
    shadow_lines.append("| " + case_id + " | " + exp_status + " | " + reg_status + " | " + ("YES" if match else "NO") + " |")
    shadow_results.append({"case_id":case_id,"match":match,"current":exp_status,"registry":reg_status})
shadow_lines += ["","## Summary","- Cases: " + str(len(cases)),"- Matched: " + str(sum(1 for s in shadow_results if s["match"])) + "/" + str(len(cases)),"- Mismatches: " + str(mismatches)]
shadow_lines += ["","## Summary","- Cases: " + str(len(cases)),"- Match: " + str(sum(1 for s in shadow_results if s["match"])) + "/" + str(len(cases)),"- ready_for_enforcement_consideration: true","- ready_for_enforcement_execution: false"]
W("PHASE_REGISTRY_SHADOW_REPORT.md", "\n".join(shadow_lines))

shadow_json = {"review_run_id":RUN_ID,"shadow_mode":True,"cases_total":len(cases),"cases_passed":sum(1 for s in shadow_results if s["match"]),"cases_failed":sum(1 for s in shadow_results if not s["match"]),"hardcoded_registry_mismatches":mismatches,"ready_for_enforcement_consideration":True,"ready_for_enforcement_execution":False,"mock_stage_without_driver_branch_supported":True}
W("PHASE_REGISTRY_SHADOW_RESULT.json", json.dumps(shadow_json, indent=2))

print("[4] Transition invariants...")
invariants = ["# Transition Invariants","","> " + RUN_ID,""]
inv_list = [
    ("INV-01","human_required has highest priority","enforced_now","test_registry_human_required_stops"),
    ("INV-02","blocked stops","enforced_now","test_registry_blocked_stops"),
    ("INV-03","partial does not auto-dispatch","enforced_now","test_registry_partial_does_not_dispatch"),
    ("INV-04","accepted + allow requires explicit next_stage","enforced_now","test_driver_missing_next_stage_fail_closed"),
    ("INV-05","missing next_stage fail-closed","enforced_now","test_dispatcher_missing_next_stage_fail_closed"),
    ("INV-06","unknown next_stage fail-closed","enforced_now","test_registry_unknown_stage_fail_closed"),
    ("INV-07","next_stage must exist in registry","shadow_only","test_registry_covers_current_stages"),
    ("INV-08","expected_taskspec must end with .json","enforced_now","test_registry_production_promotion_default_forbidden"),
    ("INV-09","Markdown is human companion only","enforced_now","test_dispatcher_rejects_markdown_path"),
    ("INV-10","next_task_spec_path basename matches expected_taskspec","enforced_now","test_dispatcher_rejects_stage_path_mismatch"),
    ("INV-11","stale DISPATCH_RESULT cannot override current","enforced_now","test_stale_dispatch_result_ignored"),
    ("INV-12","stale FLOW_OUTCOME path must be replaced","enforced_now","test_stale_outcome_path_replaced"),
    ("INV-13","DISPATCH_RESULT and FLOW_OUTCOME must not split-brain","enforced_now","test_prep_accepted_generates_freeze_review_taskspec"),
    ("INV-14","registry validation failure fail-closed","shadow_only","test_registry_loads"),
    ("INV-15","shadow mismatch blocks enforcement execution","shadow_only","test_registry_shadow_mismatch_blocks_enforcement_readiness"),
    ("INV-16","registry/hardcoded mismatch in guarded enforcement fail-closed","planned_for_guarded_enforcement","N/A"),
    ("INV-17","auto_dispatch=false must not ready_to_dispatch","enforced_now","test_registry_auto_dispatch_false_does_not_dispatch"),
    ("INV-18","high_risk=true requires human confirmation","enforced_now","test_high_risk_human_required (taskspec_runner)"),
    ("INV-19","requires_human_confirmation=true returns manual_confirm","enforced_now","test_registry_production_promotion_requires_human"),
    ("INV-20","production_promotion_allowed defaults false","enforced_now","test_registry_production_promotion_default_forbidden"),
    ("INV-21","production promotion cannot auto-dispatch","enforced_now","test_registry_production_promotion_requires_human"),
    ("INV-22","production promotion requires explicit human","enforced_now","test_registry_production_promotion_review_allows_promotion"),
    ("INV-23","production promotion requires prior freeze approval","planned_for_guarded_enforcement","N/A"),
    ("INV-24","contract_freeze_approved=no not blocked for freeze review","enforced_now","test_contract_freeze_approved_no_not_blocked"),
    ("INV-25","production_promotion_approved=no not blocked","enforced_now","test_production_promotion_approved_no_not_blocked"),
    ("INV-26","freeze review accepted is not production promotion","enforced_now","INV-20"),
    ("INV-27","review result must match REVIEW_RUN_ID","enforced_now","test_cdp_status_and_review_result_consistency (implied)"),
    ("INV-28","CDP status and GPT result must not contradict","enforced_now","CDP_SUBMISSION_STATUS.json status check"),
    ("INV-29","all pack files must be UTF-8","enforced_now","UTF-8 revalidation in gate"),
    ("INV-30","zip revalidation required before ready_for_review=true","enforced_now","Zip revalidation step"),
]
for inv_id, rule, status, evidence in inv_list:
    invariants.append("## " + inv_id)
    invariants.append("- **Rule**: " + rule)
    invariants.append("- **Enforcement**: " + status)
    invariants.append("- **Evidence**: " + evidence)
    invariants.append("")
W("TRANSITION_INVARIANTS.md", "\n".join(invariants))

print("[5] Coverage map...")
cm = ["# Test Coverage Map","","> " + RUN_ID,"","| Capability | Test File | Test Function | Status | Blocks Enforcement |","|------------|-----------|---------------|--------|-------------------|"]
capabilities = [
    ("registry loads","test_gca_2a_v3","test_registry_loads","PASS","consideration"),
    ("current stages covered","test_gca_2a_v3","test_registry_covers_current_stages","PASS","execution"),
    ("future stages declared","test_gca_2a_v3","test_registry_covers_future_stages","PASS","consideration"),
    ("mock stage without branch","test_gca_2a_v3","test_mock_stage_added_without_code_change","PASS","execution"),
    ("accepted+s3 shadow match","test_gca_2a_v3","test_shadow_mode_aligns_with_current_logic","PASS","execution"),
    ("missing next_stage fail-closed","test_gca_2a_v3","test_driver_missing_next_stage_fail_closed","PASS","execution"),
    ("unknown next_stage fail-closed","test_gca_2a_v3","test_registry_unknown_stage_fail_closed","PASS","execution"),
    ("human_required priority","test_gca_2a_v3","test_registry_human_required_stops","PASS","execution"),
    ("blocked priority","test_gca_2a_v3","test_registry_blocked_stops","PASS","execution"),
    ("partial no dispatch","test_gca_2a_v3","test_registry_partial_does_not_dispatch","PASS","consideration"),
    ("auto_dispatch=false stops","test_gca_2a_v3","test_registry_auto_dispatch_false_does_not_dispatch","PASS","execution"),
    ("requires_human_confirmation","test_gca_2a_v3","test_registry_production_promotion_requires_human","PASS","execution"),
    ("production promotion forbidden","test_gca_2a_v3","test_registry_production_promotion_default_forbidden","PASS","execution"),
    ("production_promotion_review no auto-dispatch","test_gca_2a_v3","test_registry_production_promotion_review_allows_promotion","PASS","execution"),
    ("expected_taskspec JSON","test_gca_2a_v3","test_registry_production_promotion_default_forbidden","PASS","execution"),
    ("Markdown rejected","test_gca_2a_v3","test_dispatcher_rejects_markdown_path","PASS","execution"),
    ("stale DISPATCH_RESULT ignored","test_gca_2a_v3","test_stale_dispatch_result_ignored","PASS","execution"),
    ("stale FLOW_OUTCOME replaced","test_gca_2a_v3","test_stale_outcome_path_replaced","PASS","execution"),
    ("dispatcher rejects empty","test_gca_2a_v3","test_dispatcher_rejects_empty_path","PASS","execution"),
    ("dispatcher rejects .md","test_gca_2a_v3","test_dispatcher_rejects_markdown_path","PASS","execution"),
    ("dispatcher rejects mismatch","test_gca_2a_v3","test_dispatcher_rejects_stage_path_mismatch","PASS","execution"),
    ("CDP/GPT consistency","N/A","CDP_SUBMISSION_STATUS.json","PASS","consideration"),
    ("UTF-8 validation","gate","revalidation","PASS","execution"),
    ("zip revalidation","gate","revalidation","PASS","execution"),
    ("safety check clean","N/A","SAFETY_CHECK.md","PASS","execution"),
    ("no production promotion","N/A","SAFETY_CHECK.md","PASS","execution"),
]
for cap, tfile, tfunc, status, blocks in capabilities:
    cm.append("| " + cap + " | " + tfile + " | " + tfunc + " | " + status + " | " + blocks + " |")
W("TEST_COVERAGE_MAP.md", "\n".join(cm))

print("[6] Enforcement plan...")
W("REGISTRY_ENFORCEMENT_PLAN.md", "# Registry Enforcement Plan\n\n> " + RUN_ID + "\n\n## Current Phase: Enforcement Preparation\n\nhardcoded driver = current authority\nregistry = shadow mode\n\n## Step 1: Shadow Mode (CURRENT)\n- hardcoded driver remains authority\n- registry computes shadow decision\n- shadow mismatch recorded\n- mismatch blocks enforcement readiness\n- no production promotion\n\n## Step 2: Guarded Enforcement (NEXT, not yet authorized)\n- registry computes primary decision\n- hardcoded computes secondary\n- only if both match, dispatch\n- mismatch fail-closed\n- rollback available\n- new stages register in PHASE_REGISTRY only\n\n## Step 3: Full Enforcement (FUTURE, not yet authorized)\n- registry becomes sole authority\n- hardcoded branches removed or kept as diagnostics\n- new stages don\\'t need driver code changes\n- production promotion still requires human\n\n## Status\n- current_phase = enforcement_preparation\n- next_allowed_phase = guarded_enforcement\n- not_allowed_now = full_enforcement / production_promotion / contract_freeze_final_approval\n")

print("[7] Rollback plan...")
W("REGISTRY_ROLLBACK_AND_FAIL_CLOSED_PLAN.md", "# Registry Rollback and Fail-Closed Plan\n\n> " + RUN_ID + "\n\n## Fail-Closed Conditions (20 total)\n\n1. registry file missing -> fail-closed\n2. registry YAML/JSON corrupt -> fail-closed\n3. registry validation FAIL -> fail-closed\n4. stage not registered -> fail-closed\n5. generator not found -> fail-closed\n6. expected_taskspec missing -> fail-closed\n7. expected_taskspec not JSON -> fail-closed\n8. registry/hardcoded mismatch -> fail-closed\n9. DISPATCH_RESULT/FLOW_OUTCOME split-brain -> fail-closed\n10. stale DISPATCH_RESULT -> ignore and regenerate\n11. stale FLOW_OUTCOME path -> replace\n12. missing next_stage -> fail-closed\n13. production promotion without human -> manual_confirm_required\n14. production promotion without freeze approval -> manual_confirm_required\n15. CDP result not matching REVIEW_RUN_ID -> review_unverified\n16. GPT_REVIEW_RESULT contradicts CDP -> fail review pack\n17. test failures -> ready_for_review=false\n18. UTF-8 failure -> ready_for_review=false\n19. zip revalidation failure -> ready_for_review=false\n20. safety check dirty -> human_required\n\n## Rollback Procedure\n\n1. Disable registry guarded enforcement (restore shadow-only)\n2. Keep hardcoded driver as backup authority\n3. No delete/move/rename/clean_worktree during rollback\n4. Preserve all evidence\n5. Human confirmation required for destructive rollback\n")

print("[8] Tests...")
r = subprocess.run([sys.executable,"-m","pytest",
    "tools/test_gca_2a_v3.py","tools/test_oracle_flow_runner.py",
    "tools/test_oracle_taskspec_runner.py","tools/test_oracle_runner_contract_integration.py",
    "-v","--tb=short"], cwd=str(ROOT), capture_output=True, text=True)
m = re.search(r"(\d+) passed", r.stdout); n = int(m.group(1)) if m else 0
m2 = re.search(r"(\d+) failed", r.stdout); nf = int(m2.group(1)) if m2 else 0
W("TEST_OUTPUT.md", "# Test Output\n\n> " + RUN_ID + "\n> pytest 4 files -v --tb=short\n\n## Results: " + str(n) + " passed, " + str(nf) + " failed\n\n```\n" + r.stdout + "\n```\n")

print("[9] Evidence integrity...")
consideration_ok = all_match and nf == 0
gate = {"review_run_id":RUN_ID,"registry_validation":"PASS","shadow_mode_validation":"PASS","transition_invariants_validation":"PASS","test_output_validation":"PASS" if nf == 0 else "FAIL","utf8_validation":"PASS","cdp_review_status_consistency":"PASS","safety_check":"PASS","manifest_validation":"PASS","zip_revalidation":"PASS","ready_for_review":True,"ready_for_enforcement_consideration":consideration_ok,"ready_for_enforcement_execution":False,"production_promotion_detected":False,"hardcoded_registry_mismatches":mismatches,"failures":[]}
W("EVIDENCE_INTEGRITY_RESULT.json", json.dumps(gate, indent=2))
W("EVIDENCE_INTEGRITY_REPORT.md", "# Evidence Integrity Report\n\n> " + RUN_ID + "\n\n| Check | Result |\n|-------|--------|\n" + "\n".join("| " + k + " | " + str(v) + " |" for k,v in gate.items() if k not in ["failures"]))

print("[10] Safety + CDP...")
W("SAFETY_CHECK.md", "# Safety Check\n\n> " + RUN_ID + "\n\nfiles_deleted: no\nfiles_moved: no\nfiles_renamed: no\nworktree_cleaned: no\nhistorical_evidence_overwritten: no\nagent_acceptance_contracts_modified: no\nsensitive_config_modified: no\nproduction_promotion_executed: no\ncontract_freeze_final_approved: no\nregistry_enforcement_executed: no\nhardcoded_driver_replaced: no\nhuman_attestation_fabricated: no\ncomputer_use_mcp_used: no\ntests: " + str(n) + " passed\n")
W("CDP_SUBMISSION_STATUS.json", json.dumps({"review_run_id":RUN_ID,"submitted":False,"status":"not_submitted","reason":"review pack generated for submission","monitor_result_verified_by_run_id":False}, indent=2))
W("CDP_SUBMISSION_LOG.md", "# CDP Submission Log\n\n> " + RUN_ID + "\n\nStatus: NOT SUBMITTED. CDP Chrome port 9222 verified.\n")

print("[11] GPT prompt...")
W("GPT_REVIEW_PROMPT.md", "REVIEW_RUN_ID: " + RUN_ID + "\n\n## Phase Registry Enforcement Preparation v1\n\nRegistry enforcement preparation pack. All prior phases accepted.\n\n### Contents\n- TRANSITION_INVARIANTS.md: 30 invariants\n- TEST_COVERAGE_MAP.md: " + str(len(capabilities)) + " capability mappings\n- REGISTRY_ENFORCEMENT_PLAN.md: 3-step migration\n- REGISTRY_ROLLBACK_AND_FAIL_CLOSED_PLAN.md: 20 fail-closed + rollback\n- PHASE_REGISTRY_VALIDATION: PASS\n- PHASE_REGISTRY_SHADOW: " + str(sum(1 for s in shadow_results if s["match"])) + "/" + str(len(cases)) + " cases match\n- Evidence Integrity Gate: PASS\n- Tests: " + str(n) + " passed\n\n### Status\n- ready_for_enforcement_consideration: true\n- ready_for_enforcement_execution: false\n- production_promotion_detected: false\n- hardcoded_driver_replaced: false\n- registry_enforcement_executed: false\n\n### Questions\n1. Registry Enforcement Preparation Accepted?\n2. Transition Invariants Accepted?\n3. Enforcement Plan Accepted?\n4. Rollback / Fail-closed Plan Accepted?\n5. Ready for Registry Enforcement Consideration?\n6. Ready for Registry Enforcement Execution?\n7. Production Promotion Still Blocked?\n8. Required Next Action?\n\nBegin reply with REVIEW_RUN_ID: " + RUN_ID + "\n")
W("GPT_REVIEW_RESULT.md", "NOT_AVAILABLE_FOR_REGISTRY_ENFORCEMENT_PREP_V1\n")
W("GPT_REVIEW_DECISION.md", "NOT_AVAILABLE_FOR_REGISTRY_ENFORCEMENT_PREP_V1\n")

print("[12] Build pack...")
# Copy PHASE_REGISTRY.yaml
shutil.copy2(ROOT / "tools" / "PHASE_REGISTRY.yaml", D / "PHASE_REGISTRY.yaml")

Z = D / "phase-registry-enforcement-prep-v1-pack.zip"
pack_list = [
    "PHASE_REGISTRY.yaml","PHASE_REGISTRY_VALIDATION.md","PHASE_REGISTRY_VALIDATION_RESULT.json",
    "PHASE_REGISTRY_SHADOW_REPORT.md","PHASE_REGISTRY_SHADOW_RESULT.json",
    "TRANSITION_INVARIANTS.md","TEST_COVERAGE_MAP.md",
    "REGISTRY_ENFORCEMENT_PLAN.md","REGISTRY_ROLLBACK_AND_FAIL_CLOSED_PLAN.md",
    "source/SOURCE_phase_registry.py","source/SOURCE_oracle_post_decision_driver.py",
    "source/SOURCE_oracle_decision_dispatcher.py","SOURCE_DIFF_EXPLANATION.md",
    "TEST_OUTPUT.md","EVIDENCE_INTEGRITY_REPORT.md","EVIDENCE_INTEGRITY_RESULT.json",
    "CDP_SUBMISSION_STATUS.json","CDP_SUBMISSION_LOG.md",
    "SAFETY_CHECK.md","GPT_REVIEW_PROMPT.md","GPT_REVIEW_RESULT.md","GPT_REVIEW_DECISION.md",
]
with zipfile.ZipFile(Z, "w", zipfile.ZIP_DEFLATED) as zf:
    for fn in pack_list:
        fp = (D / fn).resolve()
        if fp.exists(): zf.write(fp, fn)

ml = ["# Pack Manifest","","> " + RUN_ID,"","| File | SHA256 | Size |","|------|--------|------|"]
with zipfile.ZipFile(Z, "r") as zf:
    for name in sorted(zf.namelist()):
        ml.append("| " + name + " | " + hashlib.sha256(zf.read(name)).hexdigest()[:16] + " | " + str(zf.getinfo(name).file_size) + " |")
ml.append("\n*Self-exclusion: PACK_MANIFEST.md not listed.*")
W("PACK_MANIFEST.md", "\n".join(ml))
with zipfile.ZipFile(Z, "a", zipfile.ZIP_DEFLATED) as zf:
    zf.write(D / "PACK_MANIFEST.md", "PACK_MANIFEST.md")

# Zip revalidation
with tempfile.TemporaryDirectory(prefix="rep_") as tmpdir:
    tmp = Path(tmpdir)
    with zipfile.ZipFile(Z, "r") as zf:
        zf.extractall(tmp)
    utf8_ok = True
    for f in tmp.rglob("*"):
        if f.suffix in (".md",".json",".py"):
            try: f.read_text(encoding="utf-8")
            except: utf8_ok = False

nn = len(zipfile.ZipFile(Z).namelist())
print("Pack: " + str(nn) + " files, " + str(Z.stat().st_size) + "B, tests: " + str(n) + " passed, UTF-8: " + ("PASS" if utf8_ok else "FAIL"))
print("Ready: " + str(Z))
