"""B1 Broader Real-Chain Multi-Pack Replay — dry-run historical pack scanner."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOT = ROOT / "_reports" / "conversation-authorization"
OUTPUT_DIR = ROOT / "_reports" / "b1-replay-output"

EXCLUDE_PREFIXES = ("gpt-reviews", "gpt-review-loop", "s2-", "browser-", "framework-freeze-")
BLOCKED_KEYS = [
    "broader_real_chain_testing_unblocked",
    "production_promotion_approved",
    "hardcoded_driver_replacement_approved",
    "guard_removal_approved",
    "evidence_cleanup_approved",
]


def classify(judgment: str) -> str:
    j = judgment.lower().strip()
    if j in ("accepted",): return "accepted"
    if j in ("blocked",): return "blocked"
    if j in ("rejected",): return "rejected"
    if j in ("needs_more_evidence", "human_required", "review_unverified"): return j
    return "unknown"


def scan_packs(ledger_path: Path | None = None) -> list[dict]:
    """Scan packs. If ledger_path provided, cross-check against DECISION_LEDGER."""
    # Load ledger if available
    ledger_entries: dict[str, str] = {}
    if ledger_path and ledger_path.exists():
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line: continue
            try:
                e = json.loads(line)
                rid = e.get("review_run_id", "")
                if rid: ledger_entries[rid] = e.get("judgment", "")
            except Exception:
                pass

    results = []
    for d in sorted(SCAN_ROOT.iterdir()):
        if not d.is_dir(): continue
        if d.name.startswith(EXCLUDE_PREFIXES): continue
        route_path = d / "POST_REVIEW_ROUTE.json"
        if not route_path.exists():
            results.append({"path": str(d.relative_to(ROOT)), "review_run_id": "unknown",
                            "category": "unknown", "checks": {},
                            "errors": ["no POST_REVIEW_ROUTE.json"]})
            continue
        try:
            route = json.loads(route_path.read_text(encoding="utf-8"))
        except Exception:
            results.append({"path": str(d.relative_to(ROOT)), "review_run_id": "unknown",
                            "category": "unknown", "checks": {},
                            "errors": ["malformed POST_REVIEW_ROUTE.json"]})
            continue

        rid = route.get("review_run_id", "unknown")
        judgment = route.get("overall_judgment", "pending")
        category = classify(judgment)

        checks = {}
        errors = []

        # Check blocked items (3-tier: pass/fail for explicit_true, warn for missing)
        blocked_status = "pass"
        for k in BLOCKED_KEYS:
            v = route.get(k)
            if v is True:
                blocked_status = "fail"
                errors.append(f"blocked item EXPLICIT TRUE: {k}")
            elif v is None:
                if blocked_status == "pass": blocked_status = "warn"
        checks["blocked_items_preserved"] = blocked_status

        # Determine if this is a pre-standardization pack (missing blocked_items fields in route)
        is_legacy = route.get("broader_real_chain_testing_unblocked") is None

        # Cross-check with ledger
        if rid in ledger_entries:
            ledger_judgment = ledger_entries[rid]
            route_judgment = route.get("overall_judgment", "")
            if ledger_judgment == route_judgment:
                checks["route_ledger_match"] = "pass"
            elif route_judgment == "":
                # Missing overall_judgment in route — legacy or incomplete pack
                checks["route_ledger_match"] = "legacy_warn"
                errors.append(f"legacy: missing route judgment, ledger={ledger_judgment}")
            else:
                checks["route_ledger_match"] = "fail"
                errors.append(f"route/ledger mismatch: route={route_judgment}, ledger={ledger_judgment}")
        else:
            checks["route_ledger_match"] = "warn" if ledger_path else "unknown"

        # Check artifacts
        artifacts = ["SAFETY_CHECK.md", "PACK_MANIFEST.md", "VALIDATION_RESULT.json"]
        missing = [a for a in artifacts if not (d / a).exists()]
        if is_legacy and missing:
            checks["artifacts_complete"] = "legacy_warn"
        else:
            checks["artifacts_complete"] = "warn" if missing else "pass"
        if missing and not is_legacy:
            errors.append(f"missing: {', '.join(missing)}")

        # Check manifest valid
        val_path = d / "VALIDATION_RESULT.json"
        if val_path.exists():
            try:
                val = json.loads(val_path.read_text(encoding="utf-8"))
                checks["manifest_valid"] = "pass" if val.get("validation_verdict") == "passed" else "fail"
            except Exception:
                checks["manifest_valid"] = "fail"
        elif is_legacy:
            checks["manifest_valid"] = "legacy_warn"
        else:
            checks["manifest_valid"] = "unknown"

        results.append({
            "path": str(d.relative_to(ROOT)),
            "review_run_id": rid,
            "category": category,
            "checks": checks,
            "errors": errors,
        })

    return results


def generate_output(packs: list[dict]) -> dict:
    by_cat = {"accepted": 0, "blocked": 0, "rejected": 0,
              "needs_more_evidence": 0, "review_unverified": 0, "unknown": 0}
    for p in packs:
        cat = p["category"]
        if cat in by_cat: by_cat[cat] += 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_packs_scanned": len(packs),
        "by_category": by_cat,
        "packs": packs,
        "summary": {
            "pass_count": sum(1 for p in packs if p["checks"].get("blocked_items_preserved") == "pass"),
            "warn_count": sum(1 for p in packs if p.get("errors")),
            "fail_count": sum(1 for p in packs if p["checks"].get("blocked_items_preserved") == "fail"),
            "aborted": False,
        },
    }


def main() -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ledger = ROOT / "DECISION_LEDGER.jsonl"
    packs = scan_packs(ledger_path=ledger)
    data = generate_output(packs)

    (OUTPUT_DIR / "B1_REPLAY_RESULT.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = ["# B1 Multi-Pack Replay Report", "",
             f"Generated: {data['generated_at']}",
             f"Packs scanned: {data['total_packs_scanned']}",
             "",
             "## By Category", ""]
    for cat, count in data["by_category"].items():
        lines.append(f"- {cat}: {count}")
    lines.extend(["", "## Per Pack", ""])
    for p in packs:
        lines.append(f"- **{p['review_run_id']}** ({p['category']})")
        for ck, cv in p["checks"].items():
            lines.append(f"  - {ck}: {cv}")
        if p["errors"]:
            lines.append(f"  - errors: {', '.join(p['errors'])}")
    lines.append("")

    (OUTPUT_DIR / "B1_REPLAY_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"B1 replay: {data['total_packs_scanned']} packs, "
          f"pass={data['summary']['pass_count']}, "
          f"warn={data['summary']['warn_count']}, "
          f"fail={data['summary']['fail_count']}")
    return data


if __name__ == "__main__":
    main()
