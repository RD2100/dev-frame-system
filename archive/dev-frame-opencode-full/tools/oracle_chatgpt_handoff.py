# tools/oracle_chatgpt_handoff.py
"""Semi-automated ChatGPT handoff for Oracle-style S2 evidence pack review.

Usage:
    python tools/oracle_chatgpt_handoff.py          # full semi-auto flow
    python tools/oracle_chatgpt_handoff.py --check  # non-interactive: verify all assets ready
"""

from playwright.sync_api import sync_playwright
import os
import sys
import pyperclip
import webbrowser

# ── config ──────────────────────────────────────────────
EVIDENCE_PACK_ZIP = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "s2-gpt-review-evidence-pack.zip")
)
PROMPT_FILE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..",
        "_reports", "s2-gpt-review-evidence-pack", "GPT_REVIEW_PROMPT.md",
    )
)
CHATGPT_URL = "https://chat.openai.com/"
REVIEW_OUTPUT_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..",
        "_reports", "gpt-reviews",
    )
)
# ────────────────────────────────────────────────────────

STATUS = {
    "zip_exists": False,
    "prompt_exists": False,
    "prompt_copied": False,
    "browser_opened": False,
    "folder_opened": False,
    "playwright_launched": False,
    "human_confirmed": False,
}


def check_mode():
    """Non-interactive check: verify all assets ready, skip browser + input."""
    print("=== Oracle S2 Handoff — Check Mode ===\n")

    # 1. zip exists
    if os.path.exists(EVIDENCE_PACK_ZIP):
        STATUS["zip_exists"] = True
        size_kb = os.path.getsize(EVIDENCE_PACK_ZIP) / 1024
        print(f"[PASS] Evidence pack zip found: {EVIDENCE_PACK_ZIP} ({size_kb:.1f} KB)")
    else:
        print(f"[FAIL] Evidence pack zip NOT found: {EVIDENCE_PACK_ZIP}")

    # 2. prompt exists
    if os.path.exists(PROMPT_FILE):
        STATUS["prompt_exists"] = True
        print(f"[PASS] GPT_REVIEW_PROMPT.md found: {PROMPT_FILE}")
    else:
        print(f"[FAIL] GPT_REVIEW_PROMPT.md NOT found: {PROMPT_FILE}")

    # 3. prompt to clipboard
    if STATUS["prompt_exists"]:
        try:
            with open(PROMPT_FILE, "r", encoding="utf-8") as f:
                pyperclip.copy(f.read())
            STATUS["prompt_copied"] = True
            print("[PASS] Prompt copied to clipboard.")
        except Exception as e:
            print(f"[FAIL] Failed to copy prompt: {e}")
    else:
        print("[SKIP] Prompt copy skipped (file missing).")

    # 4. open browser
    try:
        webbrowser.open(CHATGPT_URL)
        STATUS["browser_opened"] = True
        print(f"[PASS] Browser opened: {CHATGPT_URL}")
    except Exception as e:
        print(f"[FAIL] Browser open failed: {e}")

    # 5. open folder
    evidence_folder = os.path.dirname(EVIDENCE_PACK_ZIP)
    try:
        webbrowser.open(evidence_folder)
        STATUS["folder_opened"] = True
        print(f"[PASS] Evidence pack folder opened: {evidence_folder}")
    except Exception as e:
        print(f"[FAIL] Folder open failed: {e}")

    # 6. ensure review output dir
    os.makedirs(REVIEW_OUTPUT_DIR, exist_ok=True)
    print(f"[INFO] Review output dir ready: {REVIEW_OUTPUT_DIR}")

    # 7. summary
    all_ready = all([
        STATUS["zip_exists"],
        STATUS["prompt_exists"],
        STATUS["prompt_copied"],
        STATUS["browser_opened"],
        STATUS["folder_opened"],
    ])
    print(f"\n=== Check Result: {'ALL READY' if all_ready else 'BLOCKED'} ===")
    print("Next step: run `python tools/oracle_chatgpt_handoff.py` in a terminal to complete upload.")
    return all_ready


def full_mode():
    """Full semi-automated flow with Playwright and human input wait."""
    print("=== Oracle S2 Handoff — Full Mode ===\n")

    # 1. check files
    if not os.path.exists(EVIDENCE_PACK_ZIP):
        raise FileNotFoundError(f"Evidence pack zip not found: {EVIDENCE_PACK_ZIP}")
    STATUS["zip_exists"] = True
    print(f"[OK] Evidence pack zip: {EVIDENCE_PACK_ZIP}")

    if not os.path.exists(PROMPT_FILE):
        raise FileNotFoundError(f"GPT_REVIEW_PROMPT.md not found: {PROMPT_FILE}")
    STATUS["prompt_exists"] = True
    print(f"[OK] GPT_REVIEW_PROMPT.md: {PROMPT_FILE}")

    # 2. copy prompt to clipboard
    with open(PROMPT_FILE, "r", encoding="utf-8") as f:
        prompt_text = f.read()
    pyperclip.copy(prompt_text)
    STATUS["prompt_copied"] = True
    print("[OK] Prompt copied to clipboard.")

    # 3. open ChatGPT in system browser
    webbrowser.open(CHATGPT_URL)
    STATUS["browser_opened"] = True
    print(f"[OK] Browser opened: {CHATGPT_URL}")

    # 4. open evidence pack folder
    evidence_folder = os.path.dirname(EVIDENCE_PACK_ZIP)
    webbrowser.open(evidence_folder)
    STATUS["folder_opened"] = True
    print(f"[OK] Folder opened: {evidence_folder}")

    # 5. ensure review output dir
    os.makedirs(REVIEW_OUTPUT_DIR, exist_ok=True)

    print("\n" + "=" * 50)
    print("Manual steps required:")
    print(f"  1. Upload: {EVIDENCE_PACK_ZIP}")
    print(f"  2. Paste prompt (already in clipboard)")
    print(f"  3. Submit and wait for GPT reply")
    print(f"  4. Save reply to: {REVIEW_OUTPUT_DIR}/s2-gpt-review-result.md")
    print("=" * 50 + "\n")

    # 6. Playwright Chromium
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(CHATGPT_URL)
        STATUS["playwright_launched"] = True
        print("[OK] Playwright Chromium launched. Please log in if needed.")

        # 7. wait for human
        try:
            input("\n完成上传和粘贴 prompt 后，按回车结束 Playwright...")
            STATUS["human_confirmed"] = True
        except EOFError:
            print("\nNon-interactive environment detected.")
            print("Browser handoff preparation completed.")
            print("Please run this script manually in a terminal to upload and submit.")
        finally:
            browser.close()

    # 8. final summary
    print("\n=== Handoff Summary ===")
    print(f"  zip found:       {'yes' if STATUS['zip_exists'] else 'no'}")
    print(f"  prompt found:    {'yes' if STATUS['prompt_exists'] else 'no'}")
    print(f"  prompt copied:   {'yes' if STATUS['prompt_copied'] else 'no'}")
    print(f"  browser opened:  {'yes' if STATUS['browser_opened'] else 'no'}")
    print(f"  folder opened:   {'yes' if STATUS['folder_opened'] else 'no'}")
    print(f"  playwright:      {'yes' if STATUS['playwright_launched'] else 'no'}")
    print(f"  human confirmed: {'yes' if STATUS['human_confirmed'] else 'no'}")
    outcome = "PARTIAL PASS" if STATUS["human_confirmed"] else "PARTIAL PASS (auto ok, human pending)"
    print(f"\nResult: {outcome}")
    print("Remember: save GPT reply to _reports/gpt-reviews/s2-gpt-review-result.md")


if __name__ == "__main__":
    if "--check" in sys.argv or "-c" in sys.argv:
        ok = check_mode()
        sys.exit(0 if ok else 1)
    else:
        full_mode()
