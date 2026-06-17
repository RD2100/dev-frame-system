"""
Vault Scanner (A4)
Recursively scans a directory to discover Obsidian .md files with valid
YAML frontmatter. Returns structured discovery results.
"""
import hashlib
from pathlib import Path
from typing import Any

import yaml


def _extract_frontmatter_fast(md_path: Path) -> dict[str, Any] | None:
    """Quickly extract YAML frontmatter without full validation.

    Returns parsed frontmatter dict or None if missing/malformed.
    """
    try:
        text = md_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    if not text.startswith("---"):
        return None

    # Find closing fence
    end = text.find("\n---", 3)
    if end == -1:
        return None

    raw_yaml = text[4:end]  # skip opening "---\n"
    try:
        metadata = yaml.safe_load(raw_yaml)
    except yaml.YAMLError:
        return None

    if not isinstance(metadata, dict):
        return None

    return metadata


def _file_checksum(path: Path) -> str:
    """Compute SHA-256 checksum of a file."""
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest()[:16]


def scan_vault(
    vault_dir: str | Path,
    max_depth: int = 10,
    include_types: set[str] | None = None,
    exclude_confidentiality: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Scan an Obsidian vault directory and discover .md files with frontmatter.

    Args:
        vault_dir: Root directory to scan.
        max_depth: Maximum directory depth for recursive scanning.
        include_types: If set, only include notes with these 'type' values.
        exclude_confidentiality: If set, exclude notes with these confidentiality values.

    Returns:
        List of discovered source records:
        [
            {
                "path": "<absolute path>",
                "relative_path": "<relative to vault_dir>",
                "checksum": "<sha256[:16]>",
                "metadata": { ... frontmatter fields ... },
                "discovered": True,
            },
            ...
        ]
    """
    vault_root = Path(vault_dir).resolve()
    if not vault_root.is_dir():
        raise FileNotFoundError(f"Vault directory not found: {vault_dir}")

    if exclude_confidentiality is None:
        exclude_confidentiality = {"sensitive"}

    discovered = []

    for md_file in sorted(vault_root.rglob("*.md")):
        # Check depth
        rel = md_file.relative_to(vault_root)
        if len(rel.parts) > max_depth + 1:  # +1 for filename
            continue

        metadata = _extract_frontmatter_fast(md_file)
        if metadata is None:
            continue

        # Filter by type
        note_type = metadata.get("type", "")
        if include_types and note_type not in include_types:
            continue

        # Filter by confidentiality
        conf = metadata.get("confidentiality", "public")
        if conf in exclude_confidentiality:
            continue

        discovered.append({
            "path": str(md_file),
            "relative_path": str(rel),
            "checksum": _file_checksum(md_file),
            "metadata": metadata,
            "discovered": True,
        })

    return discovered


def scan_bibtex_files(bib_path: str | Path) -> list[dict[str, Any]]:
    """Scan a .bib file and return discovered reference records.

    Args:
        bib_path: Path to the .bib file.

    Returns:
        List of discovered reference records with checksums.
    """
    from ai_workflow_hub.context_layer.parsers.bibtex_parser import parse_bibtex_file

    path = Path(bib_path)
    if not path.exists():
        raise FileNotFoundError(f"BibTeX file not found: {bib_path}")

    records = parse_bibtex_file(path)

    # Add discovery metadata
    results = []
    for rec in records:
        results.append({
            "path": str(path),
            "checksum": _file_checksum(path),
            "metadata": rec["metadata"],
            "source_path": rec["source_path"],
            "discovered": True,
        })

    return results
