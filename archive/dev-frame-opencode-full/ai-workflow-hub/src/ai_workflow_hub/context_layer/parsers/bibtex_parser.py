"""
BibTeX Parser (A4)
Parses Better BibTeX .bib files, maps entries to ZoteroReferenceMetadata schema.
No external bibtex library required — uses regex-based parsing.
"""
import re
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "domains" / "paper" / "contracts" / "zotero_reference_metadata.schema.json"
)

# Mapping from BibTeX entry types to schema item_type enum values
ENTRY_TYPE_MAP = {
    "article": "journal_article",
    "book": "book",
    "inbook": "book_section",
    "incollection": "book_section",
    "inproceedings": "conference_paper",
    "conference": "conference_paper",
    "phdthesis": "thesis",
    "mastersthesis": "thesis",
    "techreport": "report",
    "misc": "journal_article",
}

# LaTeX special character replacements for basic decoding
LATEX_REPLACEMENTS = {
    r"\'{a}": "á", r"\'{e}": "é", r"\'{i}": "í", r"\'{o}": "ó", r"\'{u}": "ú",
    r'\"{a}': "ä", r'\"{e}': "ë", r'\"{i}': "ï", r'\"{o}': "ö", r'\"{u}': "ü",
    r"\^{a}": "â", r"\^{e}": "ê", r"\^{i}": "î", r"\^{o}": "ô", r"\^{u}": "û",
    r"\c{c}": "ç", r"\~{n}": "ñ",
    r"\'{A}": "Á", r"\'{E}": "É", r"\'{O}": "Ó",
    r'\"{A}': "Ä", r'\"{O}': "Ö", r'\"{U}': "Ü",
    r"\&": "&", r"\%": "%", r"\#": "#", r"\_": "_",
}

# Stop words for author parsing
AUTHOR_STOP = {"jr", "sr", "iii", "iv", "von", "de", "del", "la", "le", "van"}


def _load_schema() -> dict[str, Any]:
    import json
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _strip_latex(text: str) -> str:
    """Remove LaTeX formatting from a string."""
    result = text
    # Apply known replacements FIRST (before stripping braces)
    for latex, plain in LATEX_REPLACEMENTS.items():
        result = result.replace(latex, plain)
    # Remove remaining braces
    result = result.replace("{", "").replace("}", "")
    # Remove remaining backslash commands (e.g. \textit already de-braced)
    result = re.sub(r"\\[a-zA-Z]+\s*", "", result)
    return result.strip()


def _normalize_authors(author_str: str) -> list[str]:
    """Parse BibTeX author field into a list of 'Last, First' strings."""
    # Split by ' and ' (case-insensitive)
    parts = re.split(r"\s+and\s+", author_str, flags=re.IGNORECASE)
    authors = []
    for part in parts:
        part = _strip_latex(part.strip())
        if not part:
            continue
        # Already in 'Last, First' format
        if "," in part:
            authors.append(part)
        else:
            # 'First Last' -> 'Last, First'
            words = part.split()
            if len(words) >= 2:
                last = words[-1]
                first = " ".join(words[:-1])
                authors.append(f"{last}, {first}")
            else:
                authors.append(part)
    return authors


def _extract_tags(text: str) -> list[str]:
    """Parse BibTeX keywords field into a tag list."""
    tags = []
    for tag in re.split(r"[,;]", text):
        tag = _strip_latex(tag.strip().lower())
        if tag and tag not in AUTHOR_STOP:
            tags.append(tag)
    return tags


def _split_bibtex_entries(text: str) -> list[str]:
    """Split a .bib file into individual entry strings."""
    entries = []
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "@":
            if depth == 0 and start is not None:
                entries.append(text[start:i])
            start = i
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                entries.append(text[start:i + 1])
                start = None
    if start is not None and depth == 0:
        entries.append(text[start:])
    return entries


def _parse_entry(raw: str) -> dict[str, Any] | None:
    """Parse a single BibTeX entry into a dict."""
    # Match entry type and citekey
    header = re.match(r"@(\w+)\s*\{\s*([^,]*),", raw)
    if not header:
        return None

    entry_type = header.group(1).lower()
    citekey = header.group(2).strip()

    if entry_type in ("comment", "string", "preamble"):
        return None

    # Extract field = {value} or field = "value" pairs
    fields: dict[str, str] = {}
    # Use regex to find field assignments
    pattern = re.compile(
        r'(\w+)\s*=\s*(?:\{((?:[^{}]|\{[^{}]*\})*)\}|"((?:[^"\\]|\\.)*)"|(\d+))',
        re.DOTALL,
    )
    for m in pattern.finditer(raw[header.end():]):
        key = m.group(1).lower()
        value = m.group(2) or m.group(3) or m.group(4) or ""
        fields[key] = value

    return {"entry_type": entry_type, "citekey": citekey, "fields": fields}


def parse_bibtex_entry(raw: str) -> dict[str, Any] | None:
    """Parse a single BibTeX entry and return a normalized record.

    Returns None for non-reference entries (@comment, @string, @preamble).
    Returns a dict matching ZoteroReferenceMetadata schema on success.
    """
    parsed = _parse_entry(raw)
    if parsed is None:
        return None

    item_type = ENTRY_TYPE_MAP.get(parsed["entry_type"], "journal_article")
    fields = parsed["fields"]

    year_str = fields.get("year", "0")
    try:
        year = int(re.search(r"\d{4}", year_str).group()) if re.search(r"\d{4}", year_str) else 0
    except (AttributeError, ValueError):
        year = 0

    record: dict[str, Any] = {
        "citekey": parsed["citekey"],
        "title": _strip_latex(fields.get("title", "")),
        "authors": _normalize_authors(fields.get("author", "")),
        "year": year,
        "item_type": item_type,
        "confidentiality": "public",  # Default for BibTeX entries
    }

    # Optional fields
    if "journal" in fields or "booktitle" in fields:
        record["publication"] = _strip_latex(fields.get("journal") or fields.get("booktitle", ""))
    if "doi" in fields:
        record["doi"] = fields["doi"]
    if "url" in fields:
        record["url"] = fields["url"]
    if "keywords" in fields or "tags" in fields:
        tag_str = fields.get("keywords") or fields.get("tags", "")
        record["tags"] = _extract_tags(tag_str)

    return record


def parse_bibtex_file(bib_path: str | Path) -> list[dict[str, Any]]:
    """Parse a .bib file and return a list of validated normalized records.

    Each record is validated against zotero_reference_metadata.schema.json.
    Invalid entries are skipped (not raised).

    Returns:
        List of {"metadata": {...}, "source_path": "<path>"} dicts.
    """
    path = Path(bib_path)
    text = path.read_text(encoding="utf-8")
    schema = _load_schema()

    results = []
    for raw_entry in _split_bibtex_entries(text):
        record = parse_bibtex_entry(raw_entry)
        if record is None:
            continue
        try:
            jsonschema.validate(instance=record, schema=schema)
        except jsonschema.ValidationError:
            # Skip invalid entries silently
            continue
        results.append({
            "metadata": record,
            "source_path": str(bib_path),
        })

    return results
