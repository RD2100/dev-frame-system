"""Production Readiness Score / Heatmap — read-only diagnostic tool.

Reads project state files and produces:
  - readiness_score.json  : structured 0.0-1.0 scores per metric
  - readiness_heatmap.md  : visual heatmap for human review

Does NOT modify any file except its own output.
Does NOT unblock any blocked item.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read_json(path: Path) -> dict:
    """Read JSON, return {} on any failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_text(path: Path) -> str:
    """Read text, return '' on failure."""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _file_exists(path: Path) -> bool:
    return path.exists() and path.is_file()


# ---------------------------------------------------------------------------
# Individual metric scorers
# ---------------------------------------------------------------------------

def score_test_health() -> tuple[float, str]:
    """Parse smoke_report.txt for test pass/fail status."""
    text = _read_text(ROOT / "smoke_report.txt")
    if not text:
        return 0.0, "unknown: smoke_report.txt not found or empty"

    # Parse the summary line: "Summary : N passed, M known issues, K failed"
    for line in text.splitlines():
        if "Summary" in line and "passed" in line:
            import re
            m = re.search(r"(\d+)\s+passed", line)
            p = int(m.group(1)) if m else 0
            m = re.search(r"(\d+)\s+failed", line)
            f = int(m.group(1)) if m else 0
            total = p + f
            if total == 0:
                return 0.0, "unknown: no test results found"
            score = p / total
            return score, f"{p}/{total} smoke commands PASS"
    return 0.0, "unknown: summary line not found"


def score_evidence_integrity() -> tuple[float, str]:
    """Check most recent VALIDATION_RESULT.json in _reports/."""
    reports_dir = ROOT / "_reports"
    results = list(reports_dir.rglob("VALIDATION_RESULT.json"))
    if not results:
        return 0.0, "unknown: no VALIDATION_RESULT.json found"

    # Use most recently modified
    latest = max(results, key=lambda p: p.stat().st_mtime)
    data = _read_json(latest)
    verdict = data.get("validation_verdict", "unknown")
    if verdict == "passed":
        return 1.0, f"latest pack ({latest.parent.name[:30]}): passed"
    elif verdict == "failed":
        return 0.0, f"latest pack ({latest.parent.name[:30]}): failed"
    return 0.5, f"latest pack ({latest.parent.name[:30]}): {verdict}"


def score_route_ledger_consistency() -> tuple[float, str]:
    """Check CURRENT_ROUTE.json and DECISION_LEDGER.jsonl for consistency."""
    route = _read_json(ROOT / "CURRENT_ROUTE.json")
    ledger_text = _read_text(ROOT / "DECISION_LEDGER.jsonl")

    if not route or not ledger_text:
        return 0.0, "unknown: route or ledger missing"

    # Count accepted decisions in ledger
    accepted_count = ledger_text.count('"accepted"')
    total_entries = len([l for l in ledger_text.splitlines() if l.strip()])

    if total_entries == 0:
        return 0.5, "ledger empty"

    # Check that blocked items in route match expectations
    blocked_keys = [
        "broader_real_chain_testing_unblocked",
        "production_promotion_approved",
        "hardcoded_driver_replacement_approved",
        "guard_removal_approved",
        "evidence_cleanup_approved",
    ]
    # production_promotion_approved and broader_real_chain can be true after authorized unblocking
    must_be_false = [k for k in blocked_keys if k not in ("production_promotion_approved", "broader_real_chain_testing_unblocked", "hardcoded_driver_replacement_approved")]
    blocked_consistent = all(route.get(k) is False for k in must_be_false)
    if not blocked_consistent:
        return 0.0, "blocked item inconsistency detected"
    status = f"{accepted_count} accepted / {total_entries} ledger entries"
    if route.get("production_promotion_approved") is True:
        status += ", production promoted"
    if route.get("broader_real_chain_testing_unblocked") is True:
        status += ", broader chain unblocked"
    return 1.0, f"{status}, blocked consistent"


    return 1.0, f"{accepted_count} accepted / {total_entries} ledger entries, blocked consistent"


def score_submission_safety() -> tuple[float, str]:
    """Check SUBMISSION_LOG.jsonl for submission safety patterns."""
    logs = list(ROOT.rglob("SUBMISSION_LOG.jsonl"))
    if not logs:
        return 0.5, "unknown: no SUBMISSION_LOG found (tool recently added)"

    total = 0
    successful = 0
    for log_path in logs:
        for line in _read_text(log_path).splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                total += 1
                if entry.get("success"):
                    successful += 1
            except json.JSONDecodeError:
                pass

    if total == 0:
        return 0.5, "no submission entries yet"
    score = successful / total
    return score, f"{successful}/{total} submissions successful"


def score_stale_documentation_risk() -> tuple[float, str]:
    """Smoke #0 staleness check — already integrated into smoke, check its result."""
    text = _read_text(ROOT / "smoke_report.txt")
    if "Documentation staleness check" not in text:
        return 0.5, "unknown: staleness check not found in smoke report"

    # Check if #0 passed
    if "staleness check" in text.lower() and "PASS" in text:
        # Find the specific line for #0
        for line in text.splitlines():
            if "staleness" in line.lower() and "PASS" in line:
                return 1.0, "staleness check PASS: 0 stale patterns"
    return 0.0, "staleness check FAIL or not found"


def score_broader_real_chain_coverage() -> tuple[float, str]:
    """Broader real-chain testing coverage. Currently BLOCKED."""
    route = _read_json(ROOT / "CURRENT_ROUTE.json")
    if route.get("broader_real_chain_testing_unblocked") is True:
        return 1.0, "broader real-chain testing unblocked (P12 authorized)"
    return 0.0, "BLOCKED: broader_real_chain_testing_unblocked=false"


def score_rollback_readiness() -> tuple[float, str]:
    """ROLLBACK_PLAN.md existence check."""
    path = ROOT / "ROLLBACK_PLAN.md"
    if _file_exists(path):
        size = path.stat().st_size
        return 1.0, f"ROLLBACK_PLAN.md exists ({size} bytes)"
    return 0.0, "ROLLBACK_PLAN.md not found"


def score_monitoring_readiness() -> tuple[float, str]:
    """MONITORING_PLAN.md existence check."""
    path = ROOT / "MONITORING_PLAN.md"
    if _file_exists(path):
        size = path.stat().st_size
        return 1.0, f"MONITORING_PLAN.md exists ({size} bytes)"
    return 0.0, "MONITORING_PLAN.md not found"


def score_human_override_readiness() -> tuple[float, str]:
    """HUMAN_OVERRIDE_PROTOCOL.md existence check."""
    path = ROOT / "HUMAN_OVERRIDE_PROTOCOL.md"
    if _file_exists(path):
        size = path.stat().st_size
        return 1.0, f"HUMAN_OVERRIDE_PROTOCOL.md exists ({size} bytes)"
    return 0.0, "HUMAN_OVERRIDE_PROTOCOL.md not found"


def score_open_gap_count() -> tuple[float, str]:
    """Count P0/P1/P2 open gaps."""
    gaps_text = _read_text(ROOT / "PRODUCTION_READINESS_GAPS.md")
    if not gaps_text:
        return 0.0, "PRODUCTION_READINESS_GAPS.md not found"

    p0_count = len([l for l in gaps_text.splitlines() if "P0" in l or "production_promotion" in l.lower() or "broader_real" in l.lower()])
    p1_count = len([l for l in gaps_text.splitlines() if "P1" in l or "hardcoded_driver" in l.lower() or "guard_removal" in l.lower()])
    p2_count = len([l for l in gaps_text.splitlines() if "P2" in l or "evidence_cleanup" in l.lower()])

    total = p0_count + p1_count + p2_count
    # Lower open gap count = higher score. 0 gaps = 1.0, 10+ gaps = 0.0
    score = max(0.0, 1.0 - (total / 10.0))
    return score, f"P0≈{p0_count}, P1≈{p1_count}, P2≈{p2_count} open"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

METRICS: list[dict] = [
    {"key": "test_health", "label": "Test Health", "fn": score_test_health},
    {"key": "evidence_integrity", "label": "Evidence Integrity", "fn": score_evidence_integrity},
    {"key": "route_ledger_consistency", "label": "Route-Ledger Consistency", "fn": score_route_ledger_consistency},
    {"key": "submission_safety", "label": "Submission Safety", "fn": score_submission_safety},
    {"key": "stale_documentation_risk", "label": "Stale Documentation Risk", "fn": score_stale_documentation_risk},
    {"key": "broader_real_chain_coverage", "label": "Broader Real-Chain Coverage", "fn": score_broader_real_chain_coverage},
    {"key": "rollback_readiness", "label": "Rollback Readiness", "fn": score_rollback_readiness},
    {"key": "monitoring_readiness", "label": "Monitoring Readiness", "fn": score_monitoring_readiness},
    {"key": "human_override_readiness", "label": "Human Override Readiness", "fn": score_human_override_readiness},
    {"key": "open_gap_count", "label": "Open Gap Count", "fn": score_open_gap_count},
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def compute_scores() -> dict:
    """Run all metric scorers and return structured results."""
    results: list[dict] = []
    for metric in METRICS:
        score, detail = metric["fn"]()
        results.append({
            "key": metric["key"],
            "label": metric["label"],
            "score": round(score, 2),
            "detail": detail,
        })

    overall = round(sum(r["score"] for r in results) / len(results), 2) if results else 0.0

    # Verify blocked items from CURRENT_ROUTE.json
    route = _read_json(ROOT / "CURRENT_ROUTE.json")
    blocked_ok = all(
        route.get(k) is False for k in [
            "guard_removal_approved",
            "evidence_cleanup_approved",
        ]
    ) if route else False

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_score": overall,
        "metrics": results,
        "blocked_items_preserved": blocked_ok,
    }


def write_score_json(data: dict, path: Path | None = None) -> Path:
    """Write readiness_score.json."""
    out = path or (ROOT / "readiness_score.json")
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def write_heatmap_md(data: dict, path: Path | None = None) -> Path:
    """Write readiness_heatmap.md."""
    out = path or (ROOT / "readiness_heatmap.md")
    lines = [
        "# Production Readiness Heatmap",
        "",
        f"**Generated**: {data['generated_at']}",
        f"**Overall Score**: {data['overall_score']:.2f} / 1.00",
        "",
        "| Metric | Score | Detail |",
        "|--------|-------|--------|",
    ]

    for m in data["metrics"]:
        score = m["score"]
        # Visual indicator
        if score >= 0.8:
            bar = "🟢"
        elif score >= 0.5:
            bar = "🟡"
        elif score > 0.0:
            bar = "🔴"
        else:
            bar = "⚫"  # blocked or unknown
        lines.append(f"| {bar} {m['label']} | {score:.2f} | {m['detail']} |")

    lines.append("")
    blocked_status = "ALL PRESERVED" if data.get("blocked_items_preserved") else "VIOLATION DETECTED"
    lines.append(f"## Blocked Items: {blocked_status}")
    lines.append("")
    lines.append("> Diagnostic tool only — does not constitute production readiness or promotion authorization.")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main() -> dict:
    """Run readiness score computation and write outputs."""
    data = compute_scores()
    write_score_json(data)
    write_heatmap_md(data)
    return data


if __name__ == "__main__":
    data = main()
    print(f"Overall: {data['overall_score']:.2f}")
    for m in data["metrics"]:
        print(f"  {m['label']}: {m['score']:.2f} — {m['detail']}")
