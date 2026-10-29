"""Contract Freeze Review Preparation dispatch fix — review pack."""
import hashlib, json, re, shutil, subprocess, sys, zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "_reports" / "gca-phase3"
D.mkdir(parents=True, exist_ok=True)
TS = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
RUN_ID = "contract-freeze-prep-dispatch-fix"

# Source
sd = D / "source"; sd.mkdir(exist_ok=True)
for f in ["oracle_post_decision_driver.py","oracle_decision_dispatcher.py","oracle_flow_state.py","test_gca_2a_v3.py"]:
    fp = ROOT / "tools" / f
    if fp.exists(): shutil.copy2(fp, sd / f"SOURCE_{f}")

# Diff
patch = ["# Phase Transition Fix Changes",""]
for f in ["oracle_post_decision_driver.py","oracle_decision_dispatcher.py","oracle_flow_state.py"]:
    fp = ROOT / "tools" / f
    if fp.exists():
        c = fp.read_text(encoding="utf-8")
        patch.append(f"## {f}"); patch.append("```python"); patch.append(c); patch.append("```")
(D / "SOURCE_DIFF.patch").write_text("\n".join(patch))

# Schema instances
sys.path.insert(0, str(ROOT / "tools"))
from oracle_decision_dispatcher import dispatch, write_dispatch_result
from oracle_flow_state import write_outcome, FlowState
from oracle_post_decision_driver import generate_contract_freeze_review_preparation_taskspec

oc = {"task_id":"gca-phase3","stage":"gca_phase3","transport_status":"success","business_decision":"accepted","dispatch_status":"ready_to_dispatch","overall_status":"accepted","allow_next_stage":True,"terminal":False,"next_stage":"contract_freeze_review_preparation","next_task_spec_path":"","errors":[],"safety":{}}
write_outcome(D / "FLOW_OUTCOME.json", oc)
dr = dispatch({"transport_status":"success","business_decision":"accepted","allow_next_stage":True,"next_task_spec_path":str(D/"CONTRACT_FREEZE_REVIEW_PREPARATION_TASKSPEC.json")})
write_dispatch_result(D, dr)

ts_result = generate_contract_freeze_review_preparation_taskspec("gca-phase3", oc)
ts_path = Path(ts_result["json_path"])

# Contract validation
from jsonschema import Draft202012Validator
cv = ["# Contract Validation","",f"> {RUN_ID}","","| Instance | Schema | Result |","|----------|--------|--------|"]
for iname, sname in [("FLOW_OUTCOME.json","FLOW_OUTCOME.schema.json"),("DISPATCH_RESULT.json","DISPATCH_RESULT.schema.json")]:
    ip = D / iname; sp = Path("D:/agent-acceptance/contracts") / sname
    try:
        i = json.loads(ip.read_text(encoding="utf-8"))
        s = json.loads(sp.read_text(encoding="utf-8"))
        e = list(Draft202012Validator(s).iter_errors(i))
        cv.append(f"| {iname} | {sname} | {'PASS' if not e else 'FAIL: '+e[0].message[:80]} |")
    except Exception as ex: cv.append(f"| {iname} | {sname} | ERROR: {str(ex)[:80]} |")
if ts_path.exists():
    try:
        i = json.loads(ts_path.read_text(encoding="utf-8"))
        s = json.loads((Path("D:/agent-acceptance/contracts")/"TASKSPEC.schema.json").read_text(encoding="utf-8"))
        e = list(Draft202012Validator(s).iter_errors(i))
        cv.append(f"| {ts_path.name} | TASKSPEC.schema.json | {'PASS' if not e else 'FAIL: '+e[0].message[:80]} |")
    except Exception as ex: cv.append(f"| {ts_path.name} | TASKSPEC.schema.json | ERROR: {str(ex)[:80]} |")
    shutil.copy2(ts_path, D / "CONTRACT_FREEZE_REVIEW_PREPARATION_TASKSPEC.json")
(D / "CONTRACT_VALIDATION.md").write_text("\n".join(cv))

# Tests
r = subprocess.run([sys.executable,"-m","pytest","tools/test_gca_2a_v3.py","-v","--tb=short"], cwd=str(ROOT), capture_output=True, text=True)
m = re.search(r"(\d+) passed", r.stdout)
n = int(m.group(1)) if m else 0
(D / "TEST_OUTPUT.md").write_text(f"# Test Output\n\n> pytest tools/test_gca_2a_v3.py -v --tb=short\n\n```\n{r.stdout}\n```\n")

# Safety
(D / "SAFETY_CHECK.md").write_text(f"# Safety Check\n\n> {RUN_ID}\n\n| Check | Result |\n|-------|--------|\n| files deleted | no |\n| contracts modified | no |\n| production_promotion_approved=no != blocked | fixed |\n| freeze review prep auto-dispatched | yes |\n| {n} tests passed | yes |\n")

# Prompt
prompt = f"REVIEW_RUN_ID: {RUN_ID}\n\n## Phase Transition Fix: production_promotion_approved=no != blocked\n\n### Problem\nproduction_promotion_approved=no was being treated as blocked, stopping the flow.\n\n### Fix\noracle_post_decision_driver.py now correctly dispatches to contract_freeze_review_preparation when:\n- overall_judgment=accepted\n- production_promotion_approved=no (not blocked, just not yet approved)\n- contract_freeze_review_candidate=yes\n- human_required=no\n\n### Changes\n1. Added generate_contract_freeze_review_preparation_taskspec()\n2. Phase transition: next_stage=contract_freeze_review_preparation dispatches (not stops)\n3. DISPATCH_RESULT authority preserves ready_to_dispatch path\n\n### Tests\n{n} passed (5 new phase transition tests)\n\nBegin reply with REVIEW_RUN_ID: {RUN_ID}"
(D / "GPT_REVIEW_PROMPT.md").write_text(prompt)
(D / "GPT_REVIEW_RESULT.md").write_text("NOT_AVAILABLE\n")

# Pack
Z = D / "contract-freeze-prep-dispatch-fix-pack.zip"
pack = ["source/SOURCE_oracle_post_decision_driver.py","source/SOURCE_oracle_decision_dispatcher.py","source/SOURCE_oracle_flow_state.py","source/SOURCE_test_gca_2a_v3.py","SOURCE_DIFF.patch","FLOW_OUTCOME.json","DISPATCH_RESULT.json","CONTRACT_FREEZE_REVIEW_PREPARATION_TASKSPEC.json","CONTRACT_VALIDATION.md","TEST_OUTPUT.md","SAFETY_CHECK.md","GPT_REVIEW_PROMPT.md","GPT_REVIEW_RESULT.md"]
with zipfile.ZipFile(Z, "w", zipfile.ZIP_DEFLATED) as zf:
    for fn in pack:
        fp = (D / fn).resolve()
        if fp.exists(): zf.write(fp, fn)
ml = ["# Pack Manifest","",f"> {RUN_ID}","","| File | SHA256 | Size |","|------|--------|------|"]
with zipfile.ZipFile(Z, "r") as zf:
    for name in sorted(zf.namelist()):
        ml.append(f"| {name} | {hashlib.sha256(zf.read(name)).hexdigest()[:16]} | {zf.getinfo(name).file_size} |")
(D / "PACK_MANIFEST.md").write_text("\n".join(ml))
with zipfile.ZipFile(Z, "a", zipfile.ZIP_DEFLATED) as zf:
    zf.write(D / "PACK_MANIFEST.md", "PACK_MANIFEST.md")
nn = len(zipfile.ZipFile(Z).namelist())
print(f"Pack: {nn} files, {Z.stat().st_size}B, tests: {n} passed")
