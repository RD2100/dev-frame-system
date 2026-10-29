#!/usr/bin/env python3
"""
oracle_chatgpt_cdp_handoff.py — Chrome CDP Runtime handoff for ChatGPT.

Launches an independent Chrome instance with a dedicated profile,
connects Playwright over CDP, opens ChatGPT, pastes the GPT review prompt,
and pauses for manual confirmation before submitting.

Usage:
  python tools/oracle_chatgpt_cdp_handoff.py
  python tools/oracle_chatgpt_cdp_handoff.py --port 9223

Fallback chain:
  1. CDP Chrome  → connect_over_cdp → paste prompt → handoff
  2. CDP fallback → try next port
  3. Chromium persistent context → paste → handoff
  4. Handoff-only (prompt copy + manual instructions)
"""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import textwrap
import time
import urllib.request
from pathlib import Path

# ── Constants ──────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_ZIP = ROOT / "s2-gpt-review-evidence-pack.zip"
PROMPT_PATH = ROOT / "_reports" / "s2-gpt-review-evidence-pack" / "GPT_REVIEW_PROMPT.md"
PROFILE_DIR = ROOT / ".chrome-cdp-profile"
HANDOFF_DIR = ROOT / "_reports" / "browser-cdp-handoff"
GPT_REVIEW_DIR = ROOT / "_reports" / "gpt-reviews"
TARGET_URL_FILE = HANDOFF_DIR / "TARGET_CHATGPT_URL.txt"
DEFAULT_CHATGPT_URL = "https://chatgpt.com/"

VALID_CHATGPT_DOMAINS = {"chatgpt.com", "chat.openai.com"}

CHROME_CANDIDATES = [
    Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
    Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
]
CDP_START_PORT = 9222
CDP_MAX_PORT = 9225


# ── File checks ─────────────────────────────────────────────────────
def check_prerequisites():
    """Verify required files exist. Returns (ok: bool, errors: list)."""
    errors = []
    if not EVIDENCE_ZIP.exists():
        errors.append(f"EVIDENCE_ZIP not found: {EVIDENCE_ZIP}")
    if not PROMPT_PATH.exists():
        errors.append(f"PROMPT not found: {PROMPT_PATH}")
    return len(errors) == 0, errors


# ── Target URL ──────────────────────────────────────────────────────

def resolve_target_url() -> tuple[str | None, str]:
    """
    Read TARGET_CHATGPT_URL.txt and validate.
    Returns (url: str | None, status: str).
    status: 'valid' | 'invalid_domain' | 'missing_file' | 'empty'
    """
    if not TARGET_URL_FILE.exists():
        return None, "missing_file"

    raw = TARGET_URL_FILE.read_text(encoding="utf-8").strip()
    if not raw or raw.startswith("<") or raw in ("CHANGE_ME", "TARGET_URL_HERE"):
        return None, "empty"

    from urllib.parse import urlparse
    parsed = urlparse(raw)
    domain = parsed.hostname or ""
    # Extract base domain (e.g. "chatgpt.com" from "chatgpt.com" or "www.chatgpt.com")
    base_domain = ".".join(domain.split(".")[-2:]) if domain.count(".") >= 1 else domain

    if base_domain not in VALID_CHATGPT_DOMAINS:
        return None, "invalid_domain"

    return raw, "valid"


# ── Prompt handling ──────────────────────────────────────────────────
def read_prompt():
    return PROMPT_PATH.read_text(encoding="utf-8")


def copy_prompt_to_clipboard(prompt_text: str) -> str:
    """Copy prompt to clipboard. Returns method used."""
    # Method 1: pyperclip
    try:
        import pyperclip
        pyperclip.copy(prompt_text)
        return "pyperclip"
    except Exception:
        pass

    # Method 2: Write fallback file
    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    fallback = HANDOFF_DIR / "PROMPT_COPY_FALLBACK.txt"
    fallback.write_text(prompt_text, encoding="utf-8")
    return f"file:{fallback}"


# ── Chrome / CDP ────────────────────────────────────────────────────
def find_chrome() -> Path | None:
    """Find Chrome executable."""
    for p in CHROME_CANDIDATES:
        if p.exists():
            return p
    # Try PATH
    found = shutil.which("chrome") or shutil.which("google-chrome") or shutil.which("chromium")
    if found:
        return Path(found)
    return None


def is_port_available(port: int) -> bool:
    """Check if CDP port is available via HTTP."""
    try:
        url = f"http://127.0.0.1:{port}/json/version"
        req = urllib.request.Request(url)
        urllib.request.urlopen(req, timeout=2)
        return True  # Port is available with CDP running
    except Exception:
        return False


def find_available_port() -> int | None:
    """Find first available CDP port."""
    import socket
    for port in range(CDP_START_PORT, CDP_MAX_PORT + 1):
        # First check if port is free (no process listening)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", port))
            s.close()
            return port  # Port is free
        except OSError:
            s.close()
    # All ports busy — try CDP_START_PORT anyway
    return CDP_START_PORT


def launch_chrome(chrome_path: Path, port: int) -> subprocess.Popen | None:
    """Launch Chrome with CDP debugging and dedicated profile.
    Returns subprocess.Popen or None on failure."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    args = [
        str(chrome_path),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={PROFILE_DIR.resolve()}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=Translate",
        "--disable-sync",
        "--disable-extensions",
        "--disable-background-networking",
        "--window-size=1280,800",
        CHATGPT_URL,
    ]

    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc
    except FileNotFoundError:
        return None
    except Exception:
        return None


def launch_chrome_with_url(chrome_path: Path, port: int, url: str) -> subprocess.Popen | None:
    """Launch Chrome with CDP and open the specific target URL."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    args = [
        str(chrome_path),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={PROFILE_DIR.resolve()}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=Translate",
        "--disable-sync",
        "--disable-extensions",
        "--disable-background-networking",
        "--window-size=1280,800",
        url,
    ]

    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc
    except FileNotFoundError:
        return None
    except Exception:
        return None


def wait_for_cdp(port: int, timeout: int = 15) -> bool:
    """Wait for CDP endpoint to become available."""
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/json/version"
    while time.time() < deadline:
        try:
            req = urllib.request.Request(url)
            resp = urllib.request.urlopen(req, timeout=2)
            data = json.loads(resp.read())
            if "webSocketDebuggerUrl" in data:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


# ── Playwright CDP ──────────────────────────────────────────────────
def connect_over_cdp(port: int, target_url: str = DEFAULT_CHATGPT_URL) -> dict:
    """Connect Playwright to Chrome over CDP. Opens target URL."""
    from playwright.sync_api import sync_playwright

    status = {"connected": False, "chatgpt_opened": False, "prompt_pasted": False,
              "mode": "cdp-chrome", "error": None, "target_url": target_url}

    cdp_url = f"http://127.0.0.1:{port}"

    try:
        pw = sync_playwright().start()
        browser = pw.chromium.connect_over_cdp(cdp_url)
        status["connected"] = True

        contexts = browser.contexts
        if not contexts:
            context = browser.new_context()
        else:
            context = contexts[0]

        pages = context.pages
        if not pages:
            page = context.new_page()
        else:
            page = pages[0]

        # Navigate to target URL
        page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        status["chatgpt_opened"] = True

        # Try to locate input and paste prompt
        prompt_text = read_prompt()
        try:
            # Wait for page to be interactive
            page.wait_for_load_state("domcontentloaded", timeout=10000)

            # Try common ChatGPT input selectors
            input_selectors = [
                "#prompt-textarea",
                "textarea[placeholder*='Message']",
                "textarea[data-id]",
                "div[contenteditable='true']",
                "p[data-placeholder]",
            ]
            located = False
            for sel in input_selectors:
                try:
                    el = page.wait_for_selector(sel, timeout=3000, state="visible")
                    if el:
                        el.click()
                        time.sleep(0.5)
                        el.fill(prompt_text)
                        located = True
                        status["prompt_pasted"] = True
                        break
                except Exception:
                    continue

            if not located:
                # Fallback: use keyboard to type into body
                page.keyboard.press("Control+a")
                time.sleep(0.2)
                # Use type with clipboard
                try:
                    import pyperclip
                    clipboard_text = pyperclip.paste()
                    if clipboard_text == prompt_text:
                        page.keyboard.press("Control+v")
                        status["prompt_pasted"] = True
                except Exception:
                    status["prompt_pasted"] = "partial"
                    status["error"] = "input_not_located"

        except Exception as e:
            status["prompt_pasted"] = "skipped"
            status["error"] = f"paste_error: {e}"

        # Generate handoff docs before pausing
        browser_info = {
            "contexts": len(browser.contexts),
            "pages": sum(len(c.pages) for c in browser.contexts),
        }
        status["browser_info"] = browser_info

        # Try to detect file input for auto-upload
        status["auto_upload"] = "skipped"
        file_selectors = ["input[type='file']", "input[accept]"]
        for sel in file_selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    status["auto_upload"] = "attempted_not_uploaded"
                    break
            except Exception:
                pass

        # Pause for manual confirmation
        try:
            input(
                "\n" + "=" * 60 + "\n"
                "MANUAL STEP: Upload zip and submit in Chrome.\n"
                "Press Enter here when done (or Ctrl+C to leave browser open)...\n"
            )
        except EOFError:
            print("\nNon-interactive environment detected.")
            print("CDP browser handoff preparation completed.")
            print("Please run manually in a real terminal:")
            print("  python tools/oracle_chatgpt_cdp_handoff.py")

        pw.stop()

    except Exception as e:
        status["connected"] = False
        status["error"] = str(e)

    return status


# ── Chromium fallback ───────────────────────────────────────────────
def connect_via_persistent_context(target_url: str = DEFAULT_CHATGPT_URL) -> dict:
    """Fallback: Playwright persistent Chromium context."""
    from playwright.sync_api import sync_playwright

    status = {"connected": True, "chatgpt_opened": False, "prompt_pasted": False,
              "mode": "cdp-chromium-fallback", "error": None, "target_url": target_url}

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch_persistent_context(
            str(PROFILE_DIR.resolve()),
            headless=False,
            args=["--window-size=1280,800"],
            no_viewport=True,
        )

        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        status["chatgpt_opened"] = True

        prompt_text = read_prompt()
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
            input_selectors = ["#prompt-textarea", "textarea[placeholder*='Message']"]
            for sel in input_selectors:
                try:
                    el = page.wait_for_selector(sel, timeout=3000, state="visible")
                    if el:
                        el.click()
                        time.sleep(0.5)
                        el.fill(prompt_text)
                        status["prompt_pasted"] = True
                        break
                except Exception:
                    continue
            if not status["prompt_pasted"]:
                status["prompt_pasted"] = "partial"
        except Exception:
            status["prompt_pasted"] = "skipped"

        # Pause
        try:
            input("\nMANUAL: Upload zip and submit. Press Enter when done...\n")
        except EOFError:
            print("Non-interactive environment. Run manually:")
            print("  python tools/oracle_chatgpt_cdp_handoff.py")

        browser.close()
        pw.stop()
    except Exception as e:
        status["connected"] = False
        status["error"] = str(e)

    return status


# ── Handoff docs ─────────────────────────────────────────────────────
def generate_handoff_docs(chrome_path: str | None, port: int | None,
                          status: dict, prompt_method: str,
                          target_url: str = DEFAULT_CHATGPT_URL):
    """Generate all handoff documentation."""
    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    GPT_REVIEW_DIR.mkdir(parents=True, exist_ok=True)

    # TARGET_CHATGPT_URL.txt
    TARGET_URL_FILE.write_text(target_url, encoding="utf-8")

    # CDP_HANDOFF.md
    handoff = f"""# CDP Browser Handoff

## Purpose
Use independent Chrome CDP runtime to upload S2 evidence pack to ChatGPT
without using Claude Code computer-use browser control.

## Target ChatGPT URL
Target URL: {target_url}

This script opens the fixed target URL directly. It does not search the sidebar
or guess by conversation title.

## Files
- zip: {EVIDENCE_ZIP.resolve()}
- prompt: {PROMPT_PATH.resolve()}

## Browser Runtime
- chrome path: {chrome_path or 'not found (fallback)'}
- CDP port: {port or 'N/A'}
- profile dir: {PROFILE_DIR.resolve()}
- CDP endpoint: http://127.0.0.1:{port}/json/version

## Status
- mode: {status.get('mode', 'unknown')}
- connected: {status.get('connected', False)}
- chatgpt opened: {status.get('chatgpt_opened', False)}
- prompt pasted: {status.get('prompt_pasted', False)}
- auto upload: {status.get('auto_upload', 'not attempted')}

## Manual Steps
1. Confirm the current page URL matches the target URL shown above.
2. Log in to ChatGPT if needed.
3. Upload s2-gpt-review-evidence-pack.zip.
4. Confirm prompt is pasted in the correct conversation input.
5. Click Send.
6. Save GPT reply to _reports/gpt-reviews/s2-gpt-review-result.md.
7. Return to terminal and press Enter.

## Safety
- Does not use system Chrome profile.
- Does not read cookies from existing profiles.
- Does not bypass login.
- Does not auto-submit the message.
- Does not save credentials.
- Opens target URL directly — does not search sidebar.
"""
    (HANDOFF_DIR / "CDP_HANDOFF.md").write_text(handoff, encoding="utf-8")

    # CHATGPT_UPLOAD_CHECKLIST.md
    checklist = f"""# ChatGPT Upload Checklist

- [ ] TARGET_CHATGPT_URL.txt points to the correct ChatGPT conversation
- [ ] Current browser page URL matches the target URL: {target_url}
- [ ] Prompt was pasted into the correct conversation
- [ ] Correct zip uploaded: s2-gpt-review-evidence-pack.zip
- [ ] GPT_REVIEW_PROMPT.md content pasted into ChatGPT
- [ ] GPT instructed to review only the evidence pack
- [ ] GPT instructed not to trust agent SUCCESS summary
- [ ] GPT asked for: accepted / rejected / blocked / human_required
- [ ] GPT asked whether S3 is allowed
- [ ] User manually confirms before submit
- [ ] GPT reply saved to _reports/gpt-reviews/s2-gpt-review-result.md
- [ ] Do NOT proceed to S3 until GPT reply says accepted and S3 allowed
"""
    (HANDOFF_DIR / "CHATGPT_UPLOAD_CHECKLIST.md").write_text(checklist, encoding="utf-8")

    # CDP_RUNTIME_STATUS.md
    runtime_status = f"""# CDP Runtime Status

| Check | Result | Evidence |
|-------|--------|----------|
| target URL file exists | yes | {TARGET_URL_FILE} |
| target URL valid | yes | {target_url} |
| opened target URL | {"yes" if status.get('chatgpt_opened') else "no"} | {target_url} |
| zip found | {"yes" if EVIDENCE_ZIP.exists() else "no"} | {EVIDENCE_ZIP} |
| prompt found | {"yes" if PROMPT_PATH.exists() else "no"} | {PROMPT_PATH} |
| prompt copied | yes | method: {prompt_method} |
| Chrome CDP launched | {"yes" if status.get('connected') else "no"} | port: {port} |
| Playwright connected | {"yes" if status.get('connected') else "no"} | mode: {status.get('mode', 'unknown')} |
| prompt pasted | {"yes" if status.get('prompt_pasted') is True else "partial/skipped"} | {status.get('prompt_pasted')} |
| auto-submit disabled | yes | safety |
| manual upload required | yes | safety |
"""
    (HANDOFF_DIR / "CDP_RUNTIME_STATUS.md").write_text(runtime_status, encoding="utf-8")

    # GPT_REVIEW_RESULT_SAVE_INSTRUCTIONS.md
    save_instructions = f"""# GPT Review Result Save Instructions

After GPT replies, save the full answer to:

{GPT_REVIEW_DIR.resolve()}/s2-gpt-review-result.md

The saved file must include:
- Overall Judgment: accepted / rejected / blocked / human_required
- Evidence Sufficiency
- Gate-by-Gate Review (all 14 gates from the prompt)
- Fake-Green Risk Assessment
- Scope Violation Check
- Missing Evidence
- Conflicts
- Decision
- Whether S3 is allowed

## Important
Do NOT proceed to S3 until:
1. This file exists at {GPT_REVIEW_DIR.resolve()}/s2-gpt-review-result.md
2. The Overall Judgment is "accepted"
3. S3 is explicitly allowed

If GPT says rejected or blocked, return the evidence pack to the agent for fixes.
"""
    (HANDOFF_DIR / "GPT_REVIEW_RESULT_SAVE_INSTRUCTIONS.md").write_text(
        save_instructions, encoding="utf-8")


# ── Main ────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Chrome CDP Runtime — ChatGPT handoff")
    parser.add_argument("--port", type=int, default=None, help="CDP port (auto-select if not set)")
    parser.add_argument("--handoff-only", action="store_true", help="Skip CDP, generate docs only")
    parser.add_argument("--url", type=str, default=None, help="Override target ChatGPT URL")
    args = parser.parse_args()

    print("=" * 60)
    print("Chrome CDP Runtime — ChatGPT Handoff")
    print("=" * 60)

    # 1. Check prerequisites
    ok, errors = check_prerequisites()
    if not ok:
        print("\nBLOCKED: Missing required files:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print(f"\n[OK] Evidence zip: {EVIDENCE_ZIP}")
    print(f"[OK] Review prompt: {PROMPT_PATH}")

    # 2. Resolve target URL
    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    target_url, url_status = resolve_target_url()
    if args.url:
        target_url = args.url
        url_status = "valid"

    if url_status != "valid":
        print(f"\nBLOCKED_INVALID_OR_MISSING_TARGET_URL")
        print(f"  URL file: {TARGET_URL_FILE}")
        print(f"  Status: {url_status}")
        print(f"  Target URL must be a valid chatgpt.com or chat.openai.com URL.")
        print(f"  Create {TARGET_URL_FILE} with the correct target URL.")
        sys.exit(1)

    print(f"[OK] Target URL: {target_url}")

    # 3. Read and copy prompt
    prompt_text = read_prompt()
    prompt_method = copy_prompt_to_clipboard(prompt_text)
    print(f"[OK] Prompt copied: {prompt_method}")

    GPT_REVIEW_DIR.mkdir(parents=True, exist_ok=True)

    # 4. Handoff-only mode
    if args.handoff_only:
        print("\n[INFO] Handoff-only mode. Generating docs...")
        status = {"connected": False, "chatgpt_opened": False, "prompt_pasted": False,
                  "mode": "handoff-only", "error": "handoff-only mode", "auto_upload": "not attempted",
                  "target_url": target_url}
        generate_handoff_docs(None, None, status, prompt_method, target_url)
        print(f"[OK] Handoff docs: {HANDOFF_DIR}/")
        print(f"\nManual steps:")
        print(f"  1. Open Chrome and go to: {target_url}")
        print(f"  2. Upload: {EVIDENCE_ZIP}")
        print(f"  3. Paste prompt from clipboard or {HANDOFF_DIR}/PROMPT_COPY_FALLBACK.txt")
        print(f"  4. Submit and save reply to {GPT_REVIEW_DIR}/s2-gpt-review-result.md")
        print("\nDone. STATUS: PARTIAL (handoff-only)")
        return

    # 5. Find Chrome
    chrome_path = find_chrome()
    if not chrome_path:
        print("\n[WARN] Chrome not found. Falling back to Chromium persistent context.")
        status = connect_via_persistent_context(target_url)
        generate_handoff_docs(None, None, status, prompt_method, target_url)
        exit_code = 0 if status.get("chatgpt_opened") else 1
        print(f"\nDone. STATUS: {'PARTIAL' if exit_code == 0 else 'BLOCKED'}")
        sys.exit(exit_code)

    print(f"[OK] Chrome: {chrome_path}")

    # 6. Find available port
    port = args.port or find_available_port()
    print(f"[INFO] CDP port: {port}")

    # 7. Launch Chrome (opens target URL as startup page)
    print("[INFO] Launching Chrome with CDP...")
    proc = launch_chrome_with_url(chrome_path, port, target_url)
    if not proc:
        print("[WARN] Chrome launch failed. Falling back to Chromium persistent context.")
        status = connect_via_persistent_context(target_url)
        generate_handoff_docs(str(chrome_path), None, status, prompt_method, target_url)
        print(f"\nDone. STATUS: PARTIAL")
        sys.exit(0)

    # 8. Wait for CDP
    print("[INFO] Waiting for CDP endpoint...")
    if not wait_for_cdp(port, timeout=20):
        print("[WARN] CDP endpoint not available. Falling back to Chromium.")
        status = connect_via_persistent_context(target_url)
        generate_handoff_docs(str(chrome_path), port, status, prompt_method, target_url)
        print(f"\nDone. STATUS: PARTIAL")
        sys.exit(0)

    print(f"[OK] CDP endpoint: http://127.0.0.1:{port}/json/version")

    # 9. Connect Playwright over CDP, open target URL
    print("[INFO] Connecting Playwright over CDP...")
    status = connect_over_cdp(port, target_url)

    # 10. Generate handoff docs
    generate_handoff_docs(str(chrome_path), port, status, prompt_method, target_url)
    print(f"\n[OK] Handoff docs: {HANDOFF_DIR}/")

    # 11. Summary
    print("\n" + "=" * 60)
    print("Handoff Complete")
    print("=" * 60)
    print(f"Target URL: {target_url}")
    print(f"Mode: {status.get('mode', 'unknown')}")
    print(f"ChatGPT: {'opened at target URL' if status.get('chatgpt_opened') else 'not opened'}")
    print(f"Prompt: {'pasted' if status.get('prompt_pasted') is True else status.get('prompt_pasted', 'no')}")
    print(f"Auto-submit: disabled")
    print(f"Manual steps required: upload zip + confirm + submit")
    print(f"\nNext:")
    print(f"  1. Confirm browser URL is: {target_url}")
    print(f"  2. Upload: {EVIDENCE_ZIP}")
    print(f"  3. Confirm prompt is pasted in the correct conversation")
    print(f"  4. Click Send")
    print(f"  5. Save GPT reply to: {GPT_REVIEW_DIR.resolve()}/s2-gpt-review-result.md")


if __name__ == "__main__":
    main()
