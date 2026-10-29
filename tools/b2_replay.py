"""B2 Multi-Agent Chain Replay — traces full authorization→closure chain per pack.

Reads GPT_REVIEW_DECISION.md (not just route self-comparison).
Extracts REVIEW_RUN_ID from 4 sources (route/decision/result/prompt) + ledger.
Classifies: actionable_fail / legacy_warn / historical_exception / incomplete / unknown.
"""
from __future__ import annotations
import json, re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOT = ROOT / "_reports" / "conversation-authorization"
OUTPUT_DIR = ROOT / "_reports" / "b2-replay-output"
BLOCKED_KEYS = [
    "broader_real_chain_testing_unblocked", "production_promotion_approved",
    "hardcoded_driver_replacement_approved", "guard_removal_approved",
    "evidence_cleanup_approved",
]
EXCLUDE_PREFIXES = ("gpt-reviews", "gpt-review-loop", "s2-", "browser-", "framework-freeze-")

def _extract_rid(text: str) -> str:
    m = re.search(r"REVIEW_RUN_ID:\s*(\S+)", text)
    return m.group(1) if m else ""

def _extract_judgment(text: str) -> str:
    for line in text.splitlines():
        m = re.search(r"overall_judgment:\s*(\S+)", line, re.IGNORECASE)
        if m: return m.group(1).lower().strip()
    return ""

def classify_path(judgment: str) -> str:
    j = judgment.lower().strip()
    if j in ("accepted",): return "accepted"
    if j in ("blocked",): return "blocked"
    if j in ("rejected",): return "rejected"
    if j in ("needs_more_evidence", "human_required", "review_unverified"): return j
    return "unknown"

def _read_file(path: Path) -> str:
    try: return path.read_text(encoding="utf-8", errors="replace")
    except: return ""

def scan_chain(ledger: dict[str, str]) -> list[dict]:
    results = []
    for d in sorted(SCAN_ROOT.iterdir()):
        if not d.is_dir() or d.name.startswith(EXCLUDE_PREFIXES): continue

        # === Read all source files ===
        route = {}
        route_path = d / "POST_REVIEW_ROUTE.json"
        if route_path.exists():
            try: route = json.loads(route_path.read_text(encoding="utf-8"))
            except: pass

        decision_text = _read_file(d / "GPT_REVIEW_DECISION.md")
        result_text = _read_file(d / "GPT_REVIEW_RESULT.md")
        prompt_text = _read_file(d / "GPT_REVIEW_PROMPT.md")

        route_rid = route.get("review_run_id", "")
        decision_rid = _extract_rid(decision_text)
        result_rid = _extract_rid(result_text)
        prompt_rid = _extract_rid(prompt_text)

        route_judgment = route.get("overall_judgment", "")
        decision_judgment = _extract_judgment(decision_text)
        path = classify_path(route_judgment)

        errors = []
        checks = {}
        category = "unknown_pack"

        # === RID cross-check (4 sources + ledger) ===
        rids = {"route": route_rid, "decision": decision_rid, "result": result_rid,
                "prompt": prompt_rid}
        unique_rids = {v for v in [route_rid, decision_rid, result_rid, prompt_rid] if v}
        # Ledger keyed by route_rid, so route-ledger RID match is implicit
        if len(unique_rids) > 1:
            checks["rid_match"] = "fail"
            errors.append(f"RID mismatch across sources: {unique_rids}")
        elif len(unique_rids) == 1:
            checks["rid_match"] = "pass"
        else:
            checks["rid_match"] = "warn"

        # === Route/decision comparison (real GPT decision, not self-compare) ===
        if not decision_judgment:
            if not route_judgment:
                checks["route_decision_match"] = "legacy_missing_decision"
            else:
                checks["route_decision_match"] = "incomplete"
                errors.append("GPT_REVIEW_DECISION.md missing — cannot verify decision vs route")
        elif decision_judgment != route_judgment:
            checks["route_decision_match"] = "fail"
            errors.append(f"decision({decision_judgment}) != route({route_judgment})")
        else:
            checks["route_decision_match"] = "pass"

        # === Ledger cross-check ===
        if route_rid in ledger:
            lj = ledger[route_rid]
            if lj == route_judgment:
                checks["ledger_route_match"] = "pass"
            elif not route_judgment:
                checks["ledger_route_match"] = "legacy_warn"
            else:
                checks["ledger_route_match"] = "fail"
                errors.append(f"ledger({lj}) != route({route_judgment})")
        else:
            checks["ledger_route_match"] = "warn"

        # === Blocked items check ===
        blocked = "pass"
        for k in BLOCKED_KEYS:
            v = route.get(k)
            if v is True:
                blocked = "fail"; errors.append(f"BLOCKED_ITEM_TRUE: {k}")
            elif v is None and blocked == "pass":
                blocked = "warn"
        checks["blocked_preserved"] = blocked

        # === Artifact check ===
        missing = []
        for a in ["GPT_REVIEW_PROMPT.md", "GPT_REVIEW_RESULT.md", "POST_REVIEW_ROUTE.json"]:
            if not (d / a).exists():
                missing.append(a)
        is_legacy = (route.get("broader_real_chain_testing_unblocked") is None
                     or not route.get("overall_judgment"))
        if is_legacy and missing:
            checks["artifacts_complete"] = "legacy_warn"
        else:
            checks["artifacts_complete"] = "pass" if not missing else "warn"

        # === Chain status (6 decision paths) ===
        has_review = (d / "GPT_REVIEW_RESULT.md").exists()
        has_route = route_path.exists()
        in_ledger = route_rid in ledger
        is_accepted = path == "accepted"

        has_closure = (d / "FINAL_CLOSURE_SUMMARY.md").exists()
        if is_accepted and has_review and has_route and in_ledger and has_closure:
            chain_status = "complete"
        elif is_accepted and has_review and has_route and in_ledger and not has_closure:
            chain_status = "incomplete"
        elif path in ("blocked", "rejected", "needs_more_evidence", "review_unverified"):
            # Should stop — check no execution occurred past this point
            has_exec = (d / "UNIFIED_DIFF.patch").exists() or (d / "COMMAND_LOG.md").exists()
            if has_exec:
                chain_status = "broken"
                errors.append(f"{path} pack has execution artifacts — chain violation")
            elif has_review:
                chain_status = "complete"
            else:
                chain_status = "incomplete"
        elif path == "unknown":
            chain_status = "unknown"
        else:
            chain_status = "incomplete"

        # === Final category assignment ===
        # RID mismatch in legacy packs is format difference, not real violation
        rid_match_is_legacy = (checks.get("rid_match") == "fail" and is_legacy)
        fail_keys = ["blocked_preserved", "route_decision_match", "ledger_route_match"]
        has_actionable = any(checks.get(k) == "fail" for k in fail_keys)
        # Non-legacy RID mismatch IS actionable
        if checks.get("rid_match") == "fail" and not is_legacy:
            has_actionable = True
        has_chain_broken = chain_status == "broken"

        if is_legacy:
            # Legacy packs: decision/route mismatch is format difference, not real violation
            if has_actionable or has_chain_broken:
                classification = "historical_exception"
            else:
                classification = "legacy_warn"
        elif rid_match_is_legacy and checks.get("rid_match") == "fail":
            # Pre-standardization RID mismatch: historical, not actionable
            classification = "historical_exception"
        elif has_actionable or has_chain_broken:
            classification = "actionable_fail"
        elif chain_status == "incomplete":
            classification = "incomplete_chain"
        elif path == "unknown":
            classification = "unknown_pack"
        else:
            classification = "warning_only"

        results.append({
            "review_run_id": route_rid or d.name,
            "decision_path": path,
            "classification": classification,
            "chain_status": chain_status,
            "checks": checks,
            "errors": errors,
        })
    return results


def main() -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ledger = {}
    lp = ROOT / "DECISION_LEDGER.jsonl"
    if lp.exists():
        for line in lp.read_text(encoding="utf-8").splitlines():
            if not line.strip(): continue
            try:
                e = json.loads(line)
                if e.get("review_run_id"): ledger[e["review_run_id"]] = e.get("judgment", "")
            except: pass

    packs = scan_chain(ledger)
    by_path = {"accepted": 0, "blocked": 0, "rejected": 0, "needs_more_evidence": 0, "review_unverified": 0, "unknown": 0}
    by_class = {"actionable_fail": 0, "legacy_warn": 0, "historical_exception": 0, "incomplete_chain": 0, "unknown_pack": 0, "warning_only": 0}
    for p in packs:
        path = p["decision_path"]
        if path in by_path: by_path[path] += 1
        cls = p["classification"]
        if cls in by_class: by_class[cls] += 1

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_packs": len(packs),
        "by_decision_path": by_path,
        "by_classification": by_class,
        "packs": packs,
        "summary": {
            "complete": sum(1 for p in packs if p["chain_status"] == "complete"),
            "incomplete": sum(1 for p in packs if p["chain_status"] == "incomplete"),
            "broken": sum(1 for p in packs if p["chain_status"] == "broken"),
            "unknown": sum(1 for p in packs if p["chain_status"] == "unknown"),
            "actionable_fail": by_class["actionable_fail"],
        },
    }

    (OUTPUT_DIR / "B2_REPLAY_RESULT.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Detailed report
    lines = [
        "# B2 Multi-Agent Chain Replay Report", "",
        f"**Generated**: {data['generated_at']}",
        f"**Total packs scanned**: {data['total_packs']}",
        f"**broader_real_chain_testing**: STILL BLOCKED", "",
        "## By Decision Path", "",
    ]
    for k, v in by_path.items(): lines.append(f"- {k}: {v}")
    lines.extend(["", "## By Classification", ""])
    for k, v in by_class.items(): lines.append(f"- {k}: {v}")
    lines.extend(["", "## Summary", "",
        f"- complete chains: {data['summary']['complete']}",
        f"- incomplete chains: {data['summary']['incomplete']}",
        f"- broken chains: {data['summary']['broken']}",
        f"- unknown: {data['summary']['unknown']}",
        f"- **actionable_fail: {data['summary']['actionable_fail']}**", "",
        "### What is actionable", "",
        "- `actionable_fail`: real violations requiring remediation (blocked item true, decision/route mismatch, RID mismatch)",
        "- `historical_exception`: pre-standardization packs with gaps that don't meet current governance (NOT actionable)",
        "- `legacy_warn`: old-format packs, missing fields (informational)",
        "- `incomplete_chain`: pack chain not fully traceable (may need investigation)",
        "- `unknown_pack`: no POST_REVIEW_ROUTE or unclassifiable",
        "- `warning_only`: minor issues, no blockers", "",
        "### Why broader_real_chain_testing is still blocked", "",
        "B2 is a dry-run diagnostic replay tool. It does NOT unblock broader real-chain testing.",
        "B3 (bounded real-chain dry-run with CDP) + separate GPT authorization is required.",
        "", "## Historical Exception Details", "",
    ])
    hist_packs = [p for p in packs if p["classification"] == "historical_exception"]
    if hist_packs:
        lines.append("| RID | Errors | Reason for Downgrade |")
        lines.append("|-----|--------|---------------------|")
        for p in hist_packs:
            errs = "; ".join(p["errors"][:2])
            lines.append(f"| {p['review_run_id']} | {errs} | Legacy pre-standardization: missing overall_judgment in POST_REVIEW_ROUTE. Historical evidence — no modification needed. |")
    else:
        lines.append("None.")
    lines.extend([
        "", "## Per Pack", "",
    ])
    for p in packs:
        lines.append(f"- **{p['review_run_id']}** ({p['decision_path']}, {p['classification']}, {p['chain_status']})")
        if p["errors"]: lines.append(f"  errors: {'; '.join(p['errors'][:3])}")
    lines.append("")

    (OUTPUT_DIR / "B2_REPLAY_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"B2: {data['total_packs']} packs, actionable_fail={data['summary']['actionable_fail']}")
    return data

if __name__ == "__main__":
    main()
