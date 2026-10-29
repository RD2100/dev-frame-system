#!/usr/bin/env python3
"""v6: v5 artifacts + gate files added to zip. Minimal fix."""
import hashlib, json, re, sys, tempfile, zipfile
from pathlib import Path

RUN_DIR = Path("D:/dev-frame-opencode/_reports/long-run-test/runs/long-run-1-20260602-133438")
V5_ZIP = RUN_DIR / "long-run-review-pack-v5.zip"
V6_ZIP = RUN_DIR / "long-run-review-pack-v6.zip"

gate_report = RUN_DIR / "EVIDENCE_INTEGRITY_REPORT.md"
gate_result = RUN_DIR / "EVIDENCE_INTEGRITY_RESULT.json"

print(f"gate_report: {gate_report.exists()} ({gate_report.stat().st_size}B)")
print(f"gate_result: {gate_result.exists()} ({gate_result.stat().st_size}B)")

# Show gate result content
gr = json.loads(gate_result.read_text(encoding="utf-8"))
print(f"Gate: schema={gr['schema_validation']}, cross={gr['cross_artifact_consistency']}, zip={gr['zip_revalidation']}")

# Build v6: copy v5 files (skip old manifest) + add gate files
with zipfile.ZipFile(V6_ZIP, "w", zipfile.ZIP_DEFLATED) as out:
    with zipfile.ZipFile(V5_ZIP, "r") as zin:
        for item in zin.infolist():
            if item.filename != "PACK_MANIFEST.md":
                out.writestr(item, zin.read(item.filename))
    out.write(gate_report, "EVIDENCE_INTEGRITY_REPORT.md")
    out.write(gate_result, "EVIDENCE_INTEGRITY_RESULT.json")

# Regenerate manifest from v6 zip contents
with zipfile.ZipFile(V6_ZIP, "r") as zf:
    v6_names = sorted(zf.namelist())

lines = [
    "# Pack Manifest - Long-run Review Pack v6", "",
    "> REVIEW_RUN_ID: long-run-1-20260602-133438", "",
    "| File | SHA256 (first 16) | Size |",
    "|------|--------------------|------|",
]
for fn in v6_names:
    fp = RUN_DIR / fn
    if fp.exists():
        h = hashlib.sha256(fp.read_bytes()).hexdigest()[:16]
        s = fp.stat().st_size
    else:
        h, s = "N/A", 0
    lines.append(f"| {fn} | {h} | {s} |")
RUN_DIR.joinpath("PACK_MANIFEST.md").write_text("\n".join(lines), encoding="utf-8")

# Add manifest to v6 zip
with zipfile.ZipFile(V6_ZIP, "a", zipfile.ZIP_DEFLATED) as zf:
    zf.write(RUN_DIR / "PACK_MANIFEST.md", "PACK_MANIFEST.md")

# Verify v6
with zipfile.ZipFile(V6_ZIP, "r") as zf:
    final = set(zf.namelist())
print(f"\nv6: {len(final)} files, {V6_ZIP.stat().st_size}B")
print(f"  gate_report: {'EVIDENCE_INTEGRITY_REPORT.md' in final}")
print(f"  gate_result: {'EVIDENCE_INTEGRITY_RESULT.json' in final}")

# Revalidation
with tempfile.TemporaryDirectory(prefix="lrev6_") as tmpdir:
    tmp = Path(tmpdir)
    with zipfile.ZipFile(V6_ZIP, "r") as zf:
        zf.extractall(tmp)

    # Verify gate result
    gr2 = json.loads((tmp / "EVIDENCE_INTEGRITY_RESULT.json").read_text(encoding="utf-8"))
    print(f"\nZip revalidation:")
    print(f"  schema: {gr2['schema_validation']}")
    print(f"  cross:  {gr2['cross_artifact_consistency']}")
    print(f"  zip:    {gr2.get('zip_revalidation', 'N/A')}")
    print(f"  ready:  {gr2['ready_for_review']}")

    # Verify manifest completeness
    mtext = (tmp / "PACK_MANIFEST.md").read_text(encoding="utf-8")
    manifest_files = set()
    for m in re.finditer(r"^\|\s*([^\s|]+)\s*\|", mtext, re.MULTILINE):
        name = m.group(1).strip()
        if name not in ("File",) and not name.startswith("-"):
            manifest_files.add(name)
    extracted = set(str(f.relative_to(tmp)).replace("\\", "/") for f in tmp.rglob("*") if f.is_file())
    extra = manifest_files - extracted
    missing = extracted - manifest_files
    print(f"  manifest extra: {extra if extra else 'none'}")
    print(f"  manifest missing: {missing if missing else 'none'}")

    # Verify resume contract points to BEFORE
    rc = json.loads((tmp / "resume_output" / "RUNNER_CONTRACT.json").read_text(encoding="utf-8"))
    print(f"\nResume contract check:")
    print(f"  input_outcome_path = {Path(rc['input_outcome_path']).name}")
    print(f"  -> is BEFORE: {Path(rc['input_outcome_path']).name == 'FLOW_OUTCOME_RESUME_BEFORE.json'}")

print("\nv6 COMPLETE - ready for GPT review")
print(f"  {V6_ZIP}")
