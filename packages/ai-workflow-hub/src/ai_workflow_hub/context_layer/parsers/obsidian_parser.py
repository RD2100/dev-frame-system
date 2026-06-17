"""
Obsidian Markdown Parser
Parses YAML frontmatter + body from .md files, validates against schema.
"""
import re
from pathlib import Path
from typing import Any

import jsonschema
import yaml

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "domains" / "paper" / "contracts" / "obsidian_note_metadata.schema.json"
)


def _load_schema() -> dict[str, Any]:
    import json
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def parse_frontmatter(md_path: str | Path) -> dict[str, Any]:
    """Extract YAML frontmatter from a Markdown file.

    Returns a dict with the parsed frontmatter fields.
    Raises ValueError if frontmatter is missing or malformed.
    """
    path = Path(md_path)
    text = path.read_text(encoding="utf-8")

    # Match YAML frontmatter between --- fences
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        raise ValueError(f"No valid YAML frontmatter found in: {md_path}")

    raw_yaml = match.group(1)
    try:
        metadata = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in frontmatter of {md_path}: {exc}") from exc

    if not isinstance(metadata, dict):
        raise ValueError(f"Frontmatter must be a YAML mapping in {md_path}")

    return metadata


def parse_body(md_path: str | Path) -> str:
    """Extract the body text after the YAML frontmatter.

    Returns the body as a string (may be empty).
    """
    path = Path(md_path)
    text = path.read_text(encoding="utf-8")

    # Strip the frontmatter block
    match = re.match(r"^---\s*\n.*?\n---\s*\n", text, re.DOTALL)
    if match:
        return text[match.end():]
    return text


def parse_obsidian_note(md_path: str | Path) -> dict[str, Any]:
    """Parse an Obsidian Markdown file and return a normalized record.

    Returns:
        {
            "metadata": { ... validated frontmatter fields ... },
            "body": "... body text ...",
            "source_path": "<original file path>"
        }

    Raises jsonschema.ValidationError if metadata fails schema validation.
    """
    metadata = parse_frontmatter(md_path)
    body = parse_body(md_path)

    # Validate against schema
    schema = _load_schema()
    jsonschema.validate(instance=metadata, schema=schema)

    return {
        "metadata": metadata,
        "body": body,
        "source_path": str(md_path),
    }


def parse_multiple(md_paths: list[str | Path]) -> list[dict[str, Any]]:
    """Parse multiple Obsidian Markdown files. Returns list of normalized records."""
    results = []
    for path in md_paths:
        results.append(parse_obsidian_note(path))
    return results
