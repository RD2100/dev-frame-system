"""Submit S2 evidence pack prompt to ChatGPT via pyautogui.

Usage (in a REAL terminal, not agent):
    python tools/chatgpt_submit.py

Prerequisites:
    - Firefox or Chrome open at https://chat.openai.com
    - Logged in
    - Click into the ChatGPT message box
    - Manually upload s2-gpt-review-evidence-pack.zip
    - Then press Enter in THIS terminal
"""
import pyautogui
import pyperclip
import os
import time

PROMPT = os.path.join(
    os.path.dirname(__file__), "..",
    "_reports", "s2-gpt-review-evidence-pack", "GPT_REVIEW_PROMPT.md",
)
PROMPT = os.path.abspath(PROMPT)

# Copy prompt
with open(PROMPT, "r", encoding="utf-8") as f:
    pyperclip.copy(f.read())
print("[OK] Prompt copied to clipboard")
print(f"[OK] Zip ready: s2-gpt-review-evidence-pack.zip")
print()
print("Manual steps:")
print("  1. Switch to ChatGPT browser tab")
print("  2. Upload zip (drag or click paperclip)")
print("  3. Click into the message input box")
print()
input("Press ENTER when ready — I will paste prompt and submit...")

# Paste
pyautogui.hotkey("ctrl", "v")
time.sleep(0.3)
print("[OK] Pasted")

# Submit
pyautogui.press("enter")
print("[OK] Submitted!")
print()
print("Wait for GPT reply, then save to:")
print("  _reports/gpt-reviews/s2-gpt-review-result.md")
