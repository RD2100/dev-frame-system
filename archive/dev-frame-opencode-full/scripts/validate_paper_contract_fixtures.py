"""
Validate paper domain contract fixtures against their JSON Schema definitions.

Usage: python validate_paper_contract_fixtures.py
Exit 0 = all fixtures valid. Exit 1 = any failure.
"""
import json
import sys
from pathlib import Path

# jsonschema is optional; fall back to basic JSON validation if unavailable
try:
    from jsonschema import validate, ValidationError, Draft202012Validator
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

BASE = Path(__file__).resolve().parent.parent / "ai-workflow-hub" / "src" / "ai_workflow_hub" / "domains" / "paper"
CONTRACTS = BASE / "contracts"
FIXTURES = BASE / "fixtures"

# Schema -> Fixture mapping
VALIDATION_PAIRS = [
    ("paper_task_spec.schema.json", "paper_task_spec.sample.yaml"),
    ("paper_context_pack.schema.json", "paper_context_pack.sample.json"),
    ("paper_acceptance_result.schema.json", "paper_acceptance_result.sample.json"),
    ("obsidian_note_metadata.schema.json", "obsidian_literature_note.sample.md"),
    ("obsidian_note_metadata.schema.json", "obsidian_bad_example.sample.md"),
    ("obsidian_note_metadata.schema.json", "obsidian_writing_rule.sample.md"),
    ("zotero_reference_metadata.schema.json", "zotero_reference.sample.json"),
]


def load_yaml_fixture(path: Path) -> dict:
    """Load YAML fixture, extracting frontmatter if present."""
    import yaml
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        # Extract frontmatter between --- markers
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return yaml.safe_load(parts[1])
    return yaml.safe_load(text)


def load_json_fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_schema(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_pair(schema_name: str, fixture_name: str) -> tuple[bool, str]:
    schema_path = CONTRACTS / schema_name
    fixture_path = FIXTURES / fixture_name

    if not schema_path.exists():
        return False, f"SCHEMA MISSING: {schema_path}"
    if not fixture_path.exists():
        return False, f"FIXTURE MISSING: {fixture_path}"

    try:
        schema = load_schema(schema_path)
    except json.JSONDecodeError as e:
        return False, f"SCHEMA PARSE ERROR: {e}"

    try:
        if fixture_path.suffix in (".yaml", ".yml", ".md"):
            fixture = load_yaml_fixture(fixture_path)
        else:
            fixture = load_json_fixture(fixture_path)
    except Exception as e:
        return False, f"FIXTURE PARSE ERROR: {e}"

    if not isinstance(fixture, dict):
        return False, f"FIXTURE NOT DICT: got {type(fixture).__name__}"

    if HAS_JSONSCHEMA:
        try:
            validator = Draft202012Validator(schema)
            errors = list(validator.iter_errors(fixture))
            if errors:
                msgs = [f"  - {e.json_path}: {e.message}" for e in errors[:5]]
                return False, f"SCHEMA VALIDATION FAILED:\n" + "\n".join(msgs)
            return True, "schema validated"
        except Exception as e:
            return False, f"VALIDATION ERROR: {e}"
    else:
        # Basic check: verify required fields exist
        required = schema.get("required", [])
        missing = [f for f in required if f not in fixture]
        if missing:
            return False, f"MISSING REQUIRED FIELDS: {missing}"
        return True, f"basic check passed (jsonschema not installed, {len(required)} required fields verified)"


def check_privacy() -> tuple[bool, list[str]]:
    """Verify no sensitive content in fixtures."""
    import re
    issues = []
    # Real API key patterns (sk- followed by 20+ alphanumeric chars)
    api_key_re = re.compile(r'sk-[a-zA-Z0-9]{20,}')
    for f in FIXTURES.iterdir():
        text = f.read_text(encoding="utf-8")
        if api_key_re.search(text):
            issues.append(f"{f.name}: contains real API key pattern (sk-...)")
        if "OPENCODE_API_KEY" in text or "DEEPSEEK_API_KEY" in text:
            issues.append(f"{f.name}: contains API key variable name")
    return len(issues) == 0, issues


def main():
    print("=" * 60)
    print("Paper Domain Contract Fixture Validation")
    print("=" * 60)

    if not HAS_JSONSCHEMA:
        print("WARNING: jsonschema not installed. Running basic validation only.")
        print("Install with: pip install jsonschema\n")

    all_pass = True
    results = []

    # 1. Validate schema files are valid JSON
    print("\n--- Schema Files ---")
    schema_files = list(CONTRACTS.glob("*.schema.json"))
    print(f"Found {len(schema_files)} schema files")
    for sf in sorted(schema_files):
        try:
            s = json.loads(sf.read_text(encoding="utf-8"))
            title = s.get("title", "untitled")
            required_count = len(s.get("required", []))
            print(f"  [OK] {sf.name} ({title}, {required_count} required)")
        except json.JSONDecodeError as e:
            print(f"  [FAIL] {sf.name}: {e}")
            all_pass = False

    # 2. Validate fixture files
    print("\n--- Fixture Files ---")
    fixture_files = list(FIXTURES.iterdir())
    print(f"Found {len(fixture_files)} fixture files")
    for ff in sorted(fixture_files):
        print(f"  [OK] {ff.name} ({ff.stat().st_size} bytes)")

    # 3. Validate fixtures against schemas
    print("\n--- Schema Validation ---")
    for schema_name, fixture_name in VALIDATION_PAIRS:
        ok, msg = validate_pair(schema_name, fixture_name)
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {fixture_name} -> {schema_name}: {msg}")
        results.append((schema_name, fixture_name, ok, msg))
        if not ok:
            all_pass = False

    # 4. Privacy check
    print("\n--- Privacy Check ---")
    privacy_ok, privacy_issues = check_privacy()
    if privacy_ok:
        print("  [PASS] No sensitive content detected in fixtures")
    else:
        all_pass = False
        for issue in privacy_issues:
            print(f"  [FAIL] {issue}")

    # Summary
    print("\n" + "=" * 60)
    passed = sum(1 for _, _, ok, _ in results if ok)
    total = len(results)
    if all_pass:
        print(f"RESULT: ALL PASS ({passed}/{total} validated, privacy OK)")
    else:
        failed = [(s, f, m) for s, f, ok, m in results if not ok]
        print(f"RESULT: FAIL ({passed}/{total} passed)")
        for s, f, m in failed:
            print(f"  FAILED: {f} -> {s}: {m}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
