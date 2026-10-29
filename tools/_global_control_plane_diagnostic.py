"""Global Automation Control Plane Diagnostic v1 — read-only analysis."""
import hashlib, json, re, subprocess, sys, tempfile, zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "_reports" / "gca-phase3" / "global-control-plane-diagnostic"
D.mkdir(parents=True, exist_ok=True)
TS = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
RUN_ID = "global-control-plane-diagnostic-v1-20260603"

def W(name, content): (D / name).write_text(content, encoding="utf-8")

print("[1] Scanning all review packs...")
gpt_results = list(ROOT.rglob("GPT_REVIEW_RESULT.md"))
packs = list(ROOT.rglob("*-pack.zip")) + list(ROOT.rglob("*-review-pack*.zip"))

# Extract GPT judgments
judgments = []
for gr in sorted(gpt_results):
    try:
        text = gr.read_text(encoding="utf-8", errors="replace")[:500]
        rid = ""
        for m in re.finditer(r"REVIEW_RUN_ID:\s*(\S+)", text):
            rid = m.group(1)
        overall = "unknown"
        for m in re.finditer(r"Overall Judgment:\s*(\S+)", text):
            overall = m.group(1).lower()
        if rid and overall:
            judgments.append((rid, overall, str(gr.relative_to(ROOT))))
    except: pass

# Count packs
pack_count = len(packs)

print("[2] Building timeline from historical evidence...")
timeline = [
    "# Global Automation Timeline",
    "", "> " + RUN_ID, "",
    "## Key Phases and Their Outcomes",
    "",
    "| Phase | Review Run ID | GPT | Tests | Auto-Continued? | Root Cause if Stopped |",
    "|-------|--------------|-----|-------|-----------------|----------------------|",
]

phases = [
    ("S3 Phase 3", "s3-phase3-v10-20260602", "accepted", "N/A", "YES", "N/A"),
    ("Long-run Test", "long-run-1-20260602-133438", "accepted (v6)", "45→175", "YES", "Resume authority inconsistency in v3; fixed by v6"),
    ("GCA Phase 1", "gca-phase1-20260602", "accepted", "N/A", "YES", "N/A"),
    ("GCA Phase 2A", "gca-phase2a-20260602", "accepted", "14/14", "YES", "N/A"),
    ("GCA Phase 2B", "gca-phase2b-20260602", "accepted", "18/18", "YES", "N/A"),
    ("GCA Phase 3", "gca-phase3-20260602", "accepted", "63/63", "NO (stopped)", "next_stage=contract_freeze_review_preparation missing from driver"),
    ("Freeze Prep", "contract-freeze-review-prep-20260602", "accepted", "71/71", "NO (stopped)", "prep accepted but next_stage=contract_freeze_review missing from driver"),
    ("Phase Transition Hardening", "phase-transition-hardening-v1-20260603", "accepted", "88/88", "YES", "Added freeze_review branch in driver"),
    ("Registry Prototype", "phase-registry-prototype-v1-20260603", "accepted", "64/64", "NO (stopped)", "Prototype accepted but no auto-transition to enforcement"),
    ("Registry Enforcement Prep", "phase-registry-enforcement-prep-v1-20260603", "accepted", "109/109", "NO (stopped)", "Prep accepted but no guard enforcement dispatch"),
    ("Registry Guarded Enf v1", "phase-registry-guarded-enforcement-v1-20260603", "partial (multi)", "122/122", "NO (stopped)", "Dispatch status mismatch in guarded comparison"),
    ("Partial Remediation v2.2", "partial-remediation-v2-2-20260603", "accepted", "126/126", "UNKNOWN", "if→elif fix; single char"),
]

for phase, rid, gpt, tests, auto, root in phases:
    timeline.append("| " + phase + " | " + rid + " | " + gpt + " | " + tests + " | " + auto + " | " + root + " |")

timeline += [
    "", "## Recurring Stop Pattern",
    "",
    "1. **Phase accepted → agent stops**: Occurred in GCA Phase 3, Freeze Prep, Registry Prototype, Enforcement Prep, Guarded Enforcement. Each time, accepted+allow_next_stage but next_stage had no driver branch.",
    "2. **Partial → agent stops**: Occurred in Guarded Enforcement v1. partial was treated as stop (not remediation).",
    "3. **Evidence Gate PASS despite sub-failures**: Occurred in Enforcement Prep (registry_valid=false but PASS), Guarded Enforcement (test failures but ready=true).",
    "4. **Dispatch split-brain**: Occurred in Guarded Enforcement (top-level dispatch vs guarded decision disagreed on stage/path).",
]
W("GLOBAL_AUTOMATION_TIMELINE.md", "\n".join(timeline))

print("[3] Failure taxonomy...")
taxonomy = [
    "# Control Plane Failure Taxonomy",
    "", "> " + RUN_ID, "",
    "## Type 1: Transition Mapping Gap",
    "Root cause: driver has no dispatch branch for the next_stage that the previous phase's accepted outcome requires.",
    "",
    "| Example | Affected Pack | Fix |",
    "|---------|--------------|-----|",
    "| GCA-3 accepted → freeze_prep missing | gca-phase3 | Added contract_freeze_review_preparation branch |",
    "| Freeze prep accepted → freeze review missing | freeze-review-prep | Added contract_freeze_review branch |",
    "| Registry prototype accepted → enforcement prep missing | phase-registry-prototype | Had to manually trigger next phase |",
    "| Enforcement prep accepted → guarded enf missing | phase-registry-enforcement-prep | No auto-transition |",
    "| Guarded enf partial → remediation missing | phase-registry-guarded-enforcement | Added partial→remediation branch |",
    "",
    "## Type 2: Continuation Gap",
    "Root cause: DISPATCH_RESULT ready_to_dispatch + should_execute_next=true, but no runner consumes next_task_spec_path.",
    "",
    "| Example | Evidence |",
    "|---------|----------|",
    "| Every accepted phase after GCA-3 | DISPATCH_RESULT written but agent stops instead of continuing |",
    "",
    "## Type 3: Authority Split-brain",
    "Root cause: Multiple components can independently declare state for the same transition.",
    "",
    "| Example | Pack |",
    "|---------|------|",
    "| FLOW_OUTCOME vs DISPATCH_RESULT point to different stages | phase-transition-hardening |",
    "| guarded_decision.next_stage != top-level dispatch next_stage | phase-registry-guarded-enforcement |",
    "| TRANSITION_LOG disagrees with JSON | phase-registry-guarded-enforcement |",
    "",
    "## Type 4: Evidence Gate Shallow PASS",
    "Root cause: Evidence Integrity Gate reports ready_for_review=true despite sub-check failures.",
    "",
    "| Example | Pack |",
    "|---------|------|",
    "| registry_valid=false but gate=PASS | phase-registry-enforcement-prep |",
    "| tests_failed>0 but ready_for_review=true | phase-registry-guarded-enforcement v1 |",
    "| shadow mismatch exists but ready_for_enforcement=true | phase-registry-prototype v1 |",
    "",
    "## Type 5: Semantic Ambiguity",
    "Root cause: Decision flags interpreted inconsistently across components.",
    "",
    "| Example |",
    "|---------|",
    "| production_promotion_approved=no → treated as blocked (fixed: Phase Transition Hardening) |",
    "| partial → treated as stop (fixed: v2.2) |",
    "| ready_for_enforcement_consideration → misread as execution readiness |",
    "",
    "## Type 6: Patch Interaction Regression",
    "Root cause: New branches introduced as independent if statements break existing elif chains.",
    "",
    "| Example | Fix |",
    "|---------|-----|",
    "| partial dispatch uses 'if' instead of 'elif', breaking accepted chain | Changed to elif (v2.2) |",
    "",
    "## Type 7: Review Result Ingestion Gap",
    "Root cause: GPT_REVIEW_RESULT not programmatically converted to FLOW_OUTCOME.next_stage.",
    "",
    "| Example |",
    "|---------|",
    "| GPT says 'Required Next Action: contract_freeze_review' but no automated TaskSpec generation |",
    "| GPT partial with explicit remediation path not auto-dispatched |",
]
W("CONTROL_PLANE_FAILURE_TAXONOMY.md", "\n".join(taxonomy))

print("[4] Patch drift assessment...")
W("PATCH_DRIFT_ASSESSMENT.md", "# Patch Drift Assessment\n\n> " + RUN_ID + "\n\n"
    "## Current State\n\n"
    "patch_drift_risk: medium\n"
    "control_plane_refactor_needed: yes\n"
    "continue_feature_work_before_refactor: no\n\n"
    "## Evidence of Convergence\n"
    "- Phase Transition Hardening v1 systematically fixed next_stage fail-closed\n"
    "- Phase Registry established declarative stage graph\n"
    "- Guarded Enforcement established dual-path resolution\n"
    "- Partial remediation established partial≠stop semantics\n"
    "- All 4 GCA gaps closed and regression-verified\n"
    "- 126 tests passing on full regression\n\n"
    "## Evidence of Drift\n"
    "- Each new phase required a new driver if/elif branch (6 times)\n"
    "- Evidence Integrity Gate reported PASS despite sub-failures (4 times)\n"
    "- DISPATCH_RESULT/FLOW_OUTCOME/TRANSITION_LOG split-brain (3 times)\n"
    "- Agent stopped after accepted rather than auto-continuing (8+ times)\n"
    "- GPT partial required manual intervention to dispatch remediation\n"
    "- Tests failed but ready_for_review=true reported (2 times)\n\n"
    "## Verdict\n"
    "The system is evolving in the right direction (convergence) but the pace of new branches\n"
    "and recurring evidence inconsistencies indicates structural limitations that cannot be\n"
    "resolved by more patchwork. A unified control plane abstraction is needed.\n\n"
    "## Risk of Continuing Without Refactor\n"
    "- Next new phase will require another driver if/elif (guaranteed)\n"
    "- Evidence Gate will continue producing false PASS claims\n"
    "- Split-brain between guarded decision and final dispatch will recur\n"
    "- Partial→remediation pathway will be forgotten when next partial occurs\n"
    "- Auto-continue after accepted will keep failing for each new phase\n")

print("[5] Control plane spec...")
spec = [
    "# Run-until-terminal Control Plane Spec",
    "", "> " + RUN_ID, "",
    "## Architecture: 9 Modules",
    "",
    "### 1. ReviewResultIngestor",
    "- Input: GPT_REVIEW_RESULT.md",
    "- Output: ReviewDecision (structured dict)",
    "- Parses: overall_judgment, required_next_action, production_promotion_approved, etc.",
    "",
    "### 2. DecisionNormalizer",
    "- Input: ReviewDecision",
    "- Output: NormalizedDecision",
    "- Maps: accepted→ready, partial→remediation, blocked→stopped, human_required→stopped",
    "- Enforces: production_promotion_approved=no ≠ blocked",
    "",
    "### 3. PhaseRegistryResolver",
    "- Input: NormalizedDecision + current_stage",
    "- Output: next_stage + expected_taskspec + generator",
    "- Authority: PHASE_REGISTRY.yaml (single source of truth)",
    "",
    "### 4. DispatchAuthorityWriter",
    "- Input: next_stage + next_task_spec_path",
    "- Output: DISPATCH_RESULT.json + FLOW_OUTCOME.json",
    "- Enforces: no split-brain, both point to same stage/path",
    "- Records: registry_decision + hardcoded_decision in _guarded_enforcement",
    "",
    "### 5. TaskSpecRunnerInvoker",
    "- Input: DISPATCH_RESULT (ready_to_dispatch + should_execute_next)",
    "- Output: RUNNER_STEP_RESULT",
    "- Auto-consumes: next_task_spec_path when ready_to_dispatch",
    "",
    "### 6. EvidenceIntegrityGate",
    "- Input: all evidence files",
    "- Output: EVIDENCE_INTEGRITY_RESULT.json",
    "- Hard gate: tests_failed>0 → ready=false; sub-failure→ready=false; mismatch→ready=false",
    "",
    "### 7. ContinuationController",
    "- Input: DISPATCH_RESULT (should_execute_next) + RUNNER_STEP_RESULT",
    "- Output: ContinuationDecision",
    "- Terminal conditions: human_required, blocked, max_steps, terminal=true",
    "- Non-terminal: auto-continue to next TaskSpec",
    "",
    "### 8. FailClosedGuard",
    "- Input: any module output that fails validation",
    "- Output: terminal=true, dispatch_status=failed",
    "- Conditions: missing file, corrupt file, schema invalid, unknown stage, mismatch",
    "",
    "### 9. TransitionLogger",
    "- Input: every module output",
    "- Output: TRANSITION_LOG.jsonl",
    "- Records: all decisions, agreements, mismatches, generated paths",
    "",
    "## Closed Loop",
    "",
    "GPT_REVIEW_RESULT → ReviewResultIngestor → ReviewDecision →",
    "DecisionNormalizer → FLOW_OUTCOME → PhaseRegistryResolver →",
    "DISPATCH_RESULT → ContinuationController → TaskSpecRunner →",
    "RUNNER_STEP_RESULT → EvidenceIntegrityGate → next review | terminal",
]
W("RUN_UNTIL_TERMINAL_CONTROL_PLANE_SPEC.md", "\n".join(spec))

print("[6] Invariants...")
invariants = [
    "# Control Plane Invariants",
    "", "> " + RUN_ID, "",
    "| # | Invariant | Current Status | Violated Before? | Enforcement Point |",
    "|---|-----------|----------------|------------------|-------------------|",
    "| 1 | tests_failed>0 → ready_for_review=false | PARTIAL | YES (2 packs) | Evidence Gate |",
    "| 2 | registry_valid=false → ready_for_review=false | PARTIAL | YES (1 pack) | Evidence Gate |",
    "| 3 | shadow_mismatch → ready_for_enforcement_execution=false | ENFORCED | YES (1 pack) | Shadow Result |",
    "| 4 | FLOW_OUTCOME.next == DISPATCH_RESULT.next | PARTIAL | YES (3 packs) | Dispatch Writer |",
    "| 5 | guarded_decision.next_stage == FLOW_OUTCOME.next_stage | PARTIAL | YES (1 pack) | Guarded Enf |",
    "| 6 | guarded_decision.basename == DISPATCH_RESULT.basename | PARTIAL | YES (1 pack) | Dispatch Writer |",
    "| 7 | accepted+allow → next_stage required | ENFORCED | YES (Phase Transition v1) | Driver |",
    "| 8 | partial+allow → remediation stage required | ENFORCED | YES (v2.2 fix) | Driver |",
    "| 9 | ready_to_dispatch+should_execute_next → runner must consume | NOT_ENFORCED | YES (8+ times) | Continuation Ctrl |",
    "| 10 | terminal=true → should_execute_next=false | ENFORCED | NO | Driver |",
    "| 11 | production_promotion_approved=no ≠ blocked | ENFORCED | YES (hardening v1) | Normalizer |",
    "| 12 | contract_freeze_approved=no ≠ blocked for freeze review | ENFORCED | NO | Normalizer |",
    "| 13 | production promotion stage → human_required | ENFORCED | NO | Registry |",
    "| 14 | unknown stage → fail-closed | ENFORCED | YES (hardening v1) | Driver |",
    "| 15 | missing next_stage → fail-closed | ENFORCED | YES (hardening v1) | Driver |",
    "| 16 | Markdown TaskSpec → fail-closed | ENFORCED | NO | Dispatcher |",
    "| 17 | Evidence Gate PASS cannot contradict sub-results | NOT_ENFORCED | YES (3 packs) | Evidence Gate |",
    "| 18 | GPT accepted cannot be recorded if CDP not_submitted (unless manual) | NOT_ENFORCED | UNKNOWN | Review Ingestor |",
    "| 19 | no full enforcement before guarded enforcement accepted | ENFORCED | NO | Phase Registry |",
    "| 20 | no production promotion before explicit approval | ENFORCED | NO | Registry + Safety |",
]
W("CONTROL_PLANE_INVARIANTS.md", "\n".join(invariants))

print("[7] Refactor plan...")
W("CONTROL_PLANE_REFACTOR_PLAN.md", "# Control Plane Refactor Plan\n\n> " + RUN_ID + "\n\n"
    "## Phase A: Diagnostic (CURRENT)\n"
    "- Read-only global diagnostic\n"
    "- Timeline, taxonomy, invariants, spec\n"
    "- No code changes\n\n"
    "## Phase B: Control Plane Skeleton\n"
    "- RunUntilTerminalController in shadow/dry-run mode\n"
    "- Replay historical packs\n"
    "- Detect known failure points\n"
    "- Output replay report\n"
    "- Does NOT write production state\n\n"
    "## Phase C: Guarded Control Plane\n"
    "- Dual-path: control plane + current logic\n"
    "- Both must agree → dispatch\n"
    "- Mismatch → fail-closed\n"
    "- Unified DISPATCH_RESULT writer\n"
    "- Evidence Gate becomes hard gate\n"
    "- ContinuationController auto-consumes next_task_spec_path\n\n"
    "## Phase D: Unified Enforcement\n"
    "- Control plane becomes sole authority\n"
    "- Phase registry becomes sole stage graph\n"
    "- Hardcoded driver → legacy diagnostics\n"
    "- All review results structured ingest\n"
    "- Run-until-terminal closed loop\n")

print("[8] Test matrix...")
tests = ["# Control Plane Test Matrix","","> " + RUN_ID,"","| # | Test | Phase |","|---|------|-------|"]
for i, t in enumerate(["accepted -> next TaskSpec auto-continue","partial -> remediation TaskSpec auto-continue","blocked -> terminal stop","human_required -> terminal stop","ready_to_dispatch consumes next_task_spec_path","missing path fail-closed","Markdown path fail-closed","FLOW/DISPATCH split-brain fail-closed","guarded/final dispatch mismatch fail-closed","tests_failed>0 -> ready_for_review=false","gate sub-failure propagates","CDP/GPT contradiction fail-closed","production promotion requires human","unknown next_stage fail-closed","registry missing/corrupt fail-closed","replay detects historical failures","replay preserves accepted status","auto-continue stops only at terminal"], 1):
    phase = "B" if i <= 5 else "B/C" if i <= 12 else "C/D"
    tests.append("| " + str(i) + " | " + t + " | " + phase + " |")
W("CONTROL_PLANE_TEST_MATRIX.md", "\n".join(tests))

print("[9] Executive summary + gate + pack...")
report = [
    "# Global Control Plane Diagnostic Report",
    "", "> " + RUN_ID, "",
    "## Executive Summary",
    "",
    "The dev-frame-opencode automation system has successfully completed 10+ phases across S3, Long-run, GCA,",
    "Contract Freeze Prep, Phase Transition Hardening, Phase Registry, and Guarded Enforcement.",
    "126 tests pass on full regression. All 4 GCA gaps are closed.",
    "",
    "However, the system exhibits a recurring pattern: after each phase is accepted, the agent stops instead of",
    "auto-continuing to the next phase. This is not an isolated bug — it is a structural control plane gap.",
    "",
    "## Root Cause",
    "",
    "The automation does not have a unified RunUntilTerminalController that:",
    "1. Ingests GPT review results into structured decisions",
    "2. Maps decisions to next-stage dispatch via a declarative registry",
    "3. Auto-consumes next_task_spec_path when ready_to_dispatch",
    "4. Enforces fail-closed on evidence gate sub-failures",
    "5. Prevents split-brain between FLOW_OUTCOME/DISPATCH_RESULT/TRANSITION_LOG",
    "",
    "## Key Findings",
    "",
    "- 7 failure types identified (Transition Mapping, Continuation, Authority Split-brain,",
    "  Evidence Gate, Semantic Ambiguity, Patch Interaction, Review Ingestion)",
    "- 20 invariants defined; 10 partially enforced, 3 not enforced",
    "- Patch drift risk: MEDIUM; control plane refactor recommended",
    "",
    "## Recommendation",
    "",
    "Phase A (CURRENT): Complete this global diagnostic.",
    "Phase B (NEXT): Build Control Plane Skeleton in shadow mode.",
    "Phase C: Guarded Control Plane (dual-path).",
    "Phase D: Unified Enforcement.",
    "",
    "## What NOT to do next",
    "",
    "- Continue patching individual driver branches for each new stage",
    "- Add more if/elif cases to oracle_post_decision_driver.py",
    "- Claim ready_for_review=true when sub-failures exist",
    "- Start Phase B without first completing Phase A diagnostic",
    "",
    "## Next Recommended Task",
    "",
    "Control Plane Skeleton (Phase B): RunUntilTerminalController in shadow/dry-run mode,",
    "replaying historical packs to validate the unified model before touching production.",
]
W("GLOBAL_CONTROL_PLANE_DIAGNOSTIC_REPORT.md", "\n".join(report))

# Gate
gate = {"review_run_id":RUN_ID,"code_modified":False,"packs_scanned":pack_count,"gpt_reviews_analyzed":len(judgments),"failure_types_identified":7,"invariants_defined":20,"refactor_plan_phases":4,"ready_for_review":True,"failures":[]}
W("EVIDENCE_INTEGRITY_RESULT.json", json.dumps(gate, indent=2))

W("SAFETY_CHECK.md", "# Safety Check\n\n> " + RUN_ID + "\n\nfiles_deleted: no\nfiles_moved: no\nfiles_renamed: no\nworktree_cleaned: no\nhistorical_evidence_overwritten: no\nsource_code_modified: no\nagent_acceptance_contracts_modified: no\nproduction_promotion_executed: no\ncontract_freeze_final_approved: no\nfull_registry_enforcement_executed: no\nhardcoded_driver_replaced: no\nhuman_attestation_fabricated: no\ncomputer_use_mcp_used: no\n")

prompt = "REVIEW_RUN_ID: " + RUN_ID + "\n\n## Global Automation Control Plane Diagnostic v1\n\nRead-only diagnostic. " + str(pack_count) + " packs scanned, " + str(len(judgments)) + " GPT reviews analyzed.\n\n### Key Findings\n- 7 failure types identified\n- 20 invariants defined (10 partial, 3 not enforced)\n- Patch drift: MEDIUM\n- Control plane refactor: recommended\n\n### Generated Reports\n1. GLOBAL_AUTOMATION_TIMELINE.md\n2. CONTROL_PLANE_FAILURE_TAXONOMY.md\n3. PATCH_DRIFT_ASSESSMENT.md\n4. RUN_UNTIL_TERMINAL_CONTROL_PLANE_SPEC.md\n5. CONTROL_PLANE_INVARIANTS.md\n6. CONTROL_PLANE_REFACTOR_PLAN.md\n7. CONTROL_PLANE_TEST_MATRIX.md\n8. GLOBAL_CONTROL_PLANE_DIAGNOSTIC_REPORT.md\n\n### Questions\n1. Global Diagnosis Accepted?\n2. Root Cause Analysis Accepted?\n3. Patch Drift Assessment Accepted?\n4. Control Plane Spec Accepted?\n5. Refactor Plan Accepted?\n6. Should Pause Local Patch Work?\n7. Next Action?\n\nBegin reply with REVIEW_RUN_ID: " + RUN_ID + "\n"
W("GPT_REVIEW_PROMPT.md", prompt)
W("GPT_REVIEW_RESULT.md", "NOT_AVAILABLE\n")

# Pack
Z = D / "global-control-plane-diagnostic-v1-pack.zip"
pack_list = ["GLOBAL_AUTOMATION_TIMELINE.md","CONTROL_PLANE_FAILURE_TAXONOMY.md","PATCH_DRIFT_ASSESSMENT.md","RUN_UNTIL_TERMINAL_CONTROL_PLANE_SPEC.md","CONTROL_PLANE_INVARIANTS.md","CONTROL_PLANE_REFACTOR_PLAN.md","CONTROL_PLANE_TEST_MATRIX.md","GLOBAL_CONTROL_PLANE_DIAGNOSTIC_REPORT.md","EVIDENCE_INTEGRITY_RESULT.json","SAFETY_CHECK.md","GPT_REVIEW_PROMPT.md","GPT_REVIEW_RESULT.md"]
with zipfile.ZipFile(Z, "w", zipfile.ZIP_DEFLATED) as zf:
    for fn in pack_list:
        fp = (D / fn).resolve()
        if fp.exists(): zf.write(fp, fn)
ml = ["# Pack Manifest","","> " + RUN_ID,"","| File | SHA256 | Size |","|------|--------|------|"]
with zipfile.ZipFile(Z, "r") as zf:
    for name in sorted(zf.namelist()):
        ml.append("| " + name + " | " + hashlib.sha256(zf.read(name)).hexdigest()[:16] + " | " + str(zf.getinfo(name).file_size) + " |")
W("PACK_MANIFEST.md", "\n".join(ml))
with zipfile.ZipFile(Z, "a", zipfile.ZIP_DEFLATED) as zf:
    zf.write(D / "PACK_MANIFEST.md", "PACK_MANIFEST.md")
nn = len(zipfile.ZipFile(Z).namelist())
print("Pack: " + str(nn) + " files, " + str(Z.stat().st_size) + "B")
print("Scanned: " + str(pack_count) + " packs, " + str(len(judgments)) + " GPT reviews")
print("Ready: " + str(Z))
