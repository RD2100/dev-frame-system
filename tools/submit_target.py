"SubmitTarget data model and shadow config loader."
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class SubmitTarget:
    conversation_id: str = ""
    cdp_host: str = "localhost"
    cdp_port: int = 9222
    file_input_selector: str = 'input[type="file"]'
    editor_selector: str = 'div[contenteditable="true"].ProseMirror'
    send_button_selector: str = 'button[data-testid="send-button"]'
    poll_wait_seconds: int = 60
    max_poll_attempts: int = 3


def load_config(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate_config(config: dict) -> list[str]:
    errors = []
    required = ["conversations", "cdp", "selectors"]
    for key in required:
        if key not in config:
            errors.append(f"Missing required key: {key}")
    return errors


def from_config(config: dict) -> SubmitTarget:
    return SubmitTarget(
        conversation_id=config.get("conversations", {}).get("active", ""),
        cdp_host=config.get("cdp", {}).get("host", "localhost"),
        cdp_port=config.get("cdp", {}).get("port", 9222),
        file_input_selector=config.get("selectors", {}).get("file_input", 'input[type="file"]'),
        editor_selector=config.get("selectors", {}).get("editor", 'div[contenteditable="true"].ProseMirror'),
        send_button_selector=config.get("selectors", {}).get("send_button", 'button[data-testid="send-button"]'),
        poll_wait_seconds=config.get("timing", {}).get("poll_wait_seconds", 60),
        max_poll_attempts=config.get("timing", {}).get("max_poll_attempts", 3),
    )


def diff_hardcoded(config: dict):
    target = from_config(config)
    hardcoded = {
        "conversation_id": "HARDCODED_IN_SCRIPTS",
        "cdp_host": "localhost",
        "cdp_port": 9222,
        "file_input_selector": 'input[type="file"]',
        "editor_selector": 'div[contenteditable="true"].ProseMirror',
        "send_button_selector": 'button[data-testid="send-button"]',
        "poll_wait_seconds": 60,
        "max_poll_attempts": 3,
    }
    print("=== Parity Report: Config vs Hardcoded ===")
    matches = 0
    diffs = 0
    for key, hc_val in hardcoded.items():
        cfg_val = getattr(target, key, "N/A")
        match = str(cfg_val) == str(hc_val)
        status = "MATCH" if match else "DIFF"
        print(f"  {key}: config={cfg_val} | hardcoded={hc_val} | {status}")
        if match:
            matches += 1
        else:
            diffs += 1
    print(f"Matches: {matches}, Diffs: {diffs}")
    return diffs == 0


if __name__ == "__main__":
    import sys
    config_path = sys.argv[1] if len(sys.argv) > 1 else "tools/submit_config.example.json"
    cfg = load_config(config_path)
    errors = validate_config(cfg)
    if errors:
        print("Validation errors:", errors)
        sys.exit(1)
    target = from_config(cfg)
    print(f"Loaded: {target}")
    diff_hardcoded(cfg)
