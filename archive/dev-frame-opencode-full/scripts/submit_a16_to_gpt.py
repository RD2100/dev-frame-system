"""submit_a16_to_gpt.py — Submit A16 evidence to GPT via CDP."""
import asyncio
import json
import sys
import urllib.request
from pathlib import Path
from playwright.async_api import async_playwright

ZIP_PATH = sys.argv[1] if len(sys.argv) > 1 else r"D:\dev-frame-opencode\ai-workflow-hub\EVIDENCE_PACK_A16.zip"
PROMPT_PATH = sys.argv[2] if len(sys.argv) > 2 else r"D:\dev-frame-opencode\ai-workflow-hub\GPT_REVIEW_PROMPT_A16.md"
OUTPUT_PATH = sys.argv[3] if len(sys.argv) > 3 else r"D:\dev-frame-opencode\ai-workflow-hub\GPT_REVIEW_A16_ZIP.txt"
CHAT_ID = "6a2e02e2-5ff8-83ee-8718-95ff5ac4242f"


def _cdp_endpoint() -> str:
    with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))["webSocketDebuggerUrl"]


async def main():
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(_cdp_endpoint())

    target = None
    for ctx in browser.contexts:
        for page in ctx.pages:
            if CHAT_ID in page.url:
                target = page
                break
    if not target:
        print("ERROR: Chat tab not found")
        await browser.close()
        return

    print(f"Found tab: {target.url[:60]}")
    await target.bring_to_front()
    await asyncio.sleep(1)

    baseline = await target.evaluate(
        "() => document.querySelectorAll('[data-message-author-role=\"assistant\"]').length"
    )
    print(f"Baseline assistant messages: {baseline}")

    # Step 1: Upload ZIP
    print("=== Upload ZIP ===")
    file_input = await target.query_selector('input[type="file"]')
    if file_input:
        await file_input.set_input_files(ZIP_PATH)
        print(f"ZIP uploaded: {ZIP_PATH}")
        await asyncio.sleep(3)
        # Dismiss duplicate modal
        modal = await target.query_selector('#modal-duplicate-file')
        if modal:
            print("Dismissing duplicate modal...")
            btn = await target.query_selector('#modal-duplicate-file button.btn-primary')
            if btn:
                await btn.click()
            else:
                await target.keyboard.press("Escape")
            await asyncio.sleep(2)
    else:
        print("WARNING: No file input found")

    # Step 2: Check attachment
    print("=== Check attachment ===")
    for a in range(10):
        info = await target.evaluate("""
            () => {
                const chips = document.querySelectorAll('[data-testid*="file"], [data-testid*="attachment"]');
                if (chips.length > 0) return { found: true, count: chips.length };
                const form = document.querySelector('form, [role="form"]');
                if (form) {
                    for (const el of form.querySelectorAll('button, span, div')) {
                        if ((el.textContent || '').includes('.zip')) return { found: true, count: 1 };
                    }
                }
                return { found: false, count: 0 };
            }
        """)
        if info.get("found"):
            print(f"  Attachment detected (attempt {a+1})")
            break
        await asyncio.sleep(1)

    # Step 3: Insert prompt text
    print("=== Insert prompt ===")
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        prompt = f.read()

    editor = await target.query_selector("#prompt-textarea")
    if not editor:
        editor = await target.query_selector('[contenteditable="true"][role="textbox"]')
    if not editor:
        print("ERROR: Editor not found")
        await browser.close()
        return

    await editor.click(force=True)
    await asyncio.sleep(0.5)
    await target.keyboard.press("Control+A")
    await asyncio.sleep(0.1)
    await target.keyboard.press("Backspace")
    await asyncio.sleep(0.2)
    await target.keyboard.insert_text(prompt)
    print(f"Prompt inserted ({len(prompt)} chars)")
    await asyncio.sleep(1)

    # Step 4: Click send
    print("=== Send ===")
    send_btn = await target.query_selector('[data-testid="send-button"]')
    if send_btn:
        disabled = await send_btn.get_attribute("disabled")
        if disabled:
            for w in range(15):
                await asyncio.sleep(1)
                disabled = await send_btn.get_attribute("disabled")
                if not disabled:
                    print(f"  Button enabled after {w+1}s")
                    break
        await send_btn.click()
        print("  Send button clicked!")
    else:
        await target.keyboard.press("Enter")
        print("  Enter pressed (fallback)")

    # Step 5: Poll for response
    print("=== Polling ===")
    await asyncio.sleep(3)
    user_msgs = await target.evaluate(
        "() => document.querySelectorAll('[data-message-author-role=\"user\"]').length"
    )
    print(f"  User messages: {user_msgs}")

    for i in range(150):
        await asyncio.sleep(2)
        count = await target.evaluate(
            "() => document.querySelectorAll('[data-message-author-role=\"assistant\"]').length"
        )
        stop_vis = await target.evaluate("""
            () => {
                const btns = document.querySelectorAll('button');
                for (const b of btns) {
                    const t = b.textContent || '';
                    const al = b.getAttribute('aria-label') || '';
                    if (t.includes('Stop') || al.includes('Stop')) return true;
                }
                return false;
            }
        """)
        if count > baseline and not stop_vis:
            await asyncio.sleep(5)
            reply = await target.evaluate("""
                () => {
                    const msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
                    if (msgs.length === 0) return '';
                    const last = msgs[msgs.length - 1];
                    const md = last.querySelector('.markdown');
                    return md ? md.innerText : last.innerText;
                }
            """)
            if len(reply) > 100:
                print(f"Response captured ({len(reply)} chars)")
                with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
                    f.write(reply)
                print(f"Saved to {OUTPUT_PATH}")
                print("---RESPONSE---")
                print(reply[:5000])
                await browser.close()
                return
            else:
                print(f"  Reply short ({len(reply)} chars), waiting...")
        elif i % 15 == 14:
            print(f"  Waiting... ({(i+1)*2}s, msgs={count}, stop={stop_vis})")

    print("TIMEOUT")
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
