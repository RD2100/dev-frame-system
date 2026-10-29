"""Firefox + PyAutoGUI: paste prompt into ChatGPT and submit.

Usage:
    python tools/oracle_firefox_chatgpt.py

Prerequisites:
    - Firefox open at https://chat.openai.com
    - Logged in to ChatGPT
    - Manually upload s2-gpt-review-evidence-pack.zip first
    - Then press Enter in THIS terminal, and the script pastes + submits
"""
import pyautogui
import pyperclip
import time
import os

PROMPT_FILE = os.path.join(
    os.path.dirname(__file__), "..",
    "_reports", "s2-gpt-review-evidence-pack", "GPT_REVIEW_PROMPT.md",
)
PROMPT_FILE = os.path.abspath(PROMPT_FILE)

if not os.path.exists(PROMPT_FILE):
    print(f"ERROR: {PROMPT_FILE} not found")
    exit(1)

with open(PROMPT_FILE, "r", encoding="utf-8") as f:
    prompt = f.read()

pyperclip.copy(prompt)
print("Prompt copied to clipboard.")

print("""
=== Manual steps before continuing ===
1. Make sure Firefox is focused and on ChatGPT chat page
2. Upload s2-gpt-review-evidence-pack.zip (drag-and-drop or click paperclip)
3. Click into the ChatGPT message input box
=========================================
""")

input("Press Enter when ready to paste + submit...")

# Paste
pyautogui.hotkey("ctrl", "v")
time.sleep(0.3)
print("Pasted.")

# Submit
pyautogui.press("enter")
print("Submitted!")

print("""
=== Next ===
Wait for GPT reply, then save it to:
  _reports/gpt-reviews/s2-gpt-review-result.md
""")
