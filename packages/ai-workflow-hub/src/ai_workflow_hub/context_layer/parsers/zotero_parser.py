"""
Zotero JSON Parser
Parses Zotero reference JSON files, validates against schema.
"""
import json
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "domains" / "paper" / "contracts" / "zotero_reference_metadata.schema.json"
)


def _load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def parse_zotero_reference(json_path: str | Path) -> dict[str, Any]:
    """Parse a Zotero reference JSON file and return a normalized record.

    Returns:
        {
            "metadata": { ... validated fields (without local_pdf_ref) ... },
            "source_path": "<original file path>"
        }

    Raises jsonschema.ValidationError if data fails schema validation.
    """
    path = Path(json_path)
    data = json.loads(path.read_text(encoding="utf-8"))

    # Strip internal/comment fields before validation
    clean = {k: v for k, v in data.items() if not k.startswith("_")}

    # Validate against schema
    schema = _load_schema()
    jsonschema.validate(instance=clean, schema=schema)

    return {
        "metadata": clean,
        "source_path": str(json_path),
    }


def parse_multiple(json_paths: list[str | Path]) -> list[dict[str, Any]]:
    """Parse multiple Zotero reference JSON files. Returns list of normalized records."""
    results = []
    for path in json_paths:
        results.append(parse_zotero_reference(path))
    return results
