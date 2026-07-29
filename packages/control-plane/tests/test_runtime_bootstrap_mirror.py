import hashlib
from pathlib import Path


def test_runtime_bootstrap_contract_mirror_matches_public_template():
    root = Path(__file__).resolve().parents[3]
    names = [
        "INSTANTIATION.md",
        "README.md",
        "capability-inventory.template.md",
        "tool-policy.template.md",
        "governance-manifest.template.md",
        "recall-obsidian-working-plan.template.ps1",
        "checkpoint-obsidian-session.template.ps1",
        "devframe-memory.mcp.json",
        "bootstrap.ps1",
    ]
    for name in names:
        public = root / "templates" / "runtime-bootstrap" / name
        packaged = root / "packages" / "control-plane" / "templates" / "runtime-bootstrap" / name
        assert hashlib.sha256(public.read_bytes()).digest() == hashlib.sha256(packaged.read_bytes()).digest(), name
