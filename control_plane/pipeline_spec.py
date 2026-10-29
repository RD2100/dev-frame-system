"Load and validate pipeline YAML against JSON schema."
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"


def load_schema(name: str) -> dict[str, Any]:
    with open(SCHEMA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def load_pipeline(path: str | Path) -> dict[str, Any]:
    import yaml
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_pipeline(pipeline: dict[str, Any]) -> list[str]:
    errors = []
    required = ["pipeline_id", "version", "stages"]
    for key in required:
        if key not in pipeline:
            errors.append(f"Missing required key: {key}")
    if "stages" in pipeline and not isinstance(pipeline["stages"], list):
        errors.append("stages must be a list")
    if "stages" in pipeline:
        for i, stage in enumerate(pipeline["stages"]):
            if "id" not in stage:
                errors.append(f"Stage {i}: missing 'id'")
            if "type" not in stage:
                errors.append(f"Stage {i}: missing 'type'")
    return errors


def get_stage_sequence(pipeline: dict[str, Any]) -> list[str]:
    return [s.get("id", f"stage_{i}") for i, s in enumerate(pipeline["stages"])]
