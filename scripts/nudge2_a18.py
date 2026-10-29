"""nudge2_a18.py — Second nudge to get remaining A18 limitations."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

CHAT_ID = "6a297e5f-c9c8-83a8-b413-a8fc414e0e85"
OUTPUT = r"D:\dev-frame-opencode\ai-workflow-hub\GPT_REVIEW_A18_ZIP_full.txt"
NUDGE = "Please continue listing the remaining limitations and provide the 'Next acceptance' and 'Brief rationale' sections."

async def main():
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
    target = None
    for ctx in browser.contexts:
        for page in ctx.pages:
            if CHAT_ID in page.url:
                target = page
                break
    if not target:
        print("ERROR: Tab not found")
        await browser.close()
        return

    baseline = await target.evaluate(
        "() => document.querySelectorAll('[data-message-author-role=\"assistant\"]').length"
    )
    print(f"Baseline: {baseline}")

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
    await target.keyboard.insert_text(NUDGE)
    await asyncio.sleep(1)

    send_btn = await target.query_selector('[data-testid="send-button"]')
    if send_btn:
        disabled = await send_btn.get_attribute("disabled")
        if disabled:
            for w in range(15):
                await asyncio.sleep(1)
                disabled = await send_btn.get_attribute("disabled")
                if not disabled:
                    break
        await send_btn.click()
        print("Send clicked")

    print("Polling...")
    await asyncio.sleep(5)
    for i in range(60):
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
                print(f"Captured ({len(reply)} chars)")
                with open(OUTPUT, "w", encoding="utf-8") as f:
                    f.write(reply)
                print(reply)
                await browser.close()
                return
            else:
                print(f"  Short ({len(reply)} chars)")
        if i % 15 == 14:
            print(f"  Waiting... ({(i+1)*2}s)")

    print("TIMEOUT")
    await browser.close()

asyncio.run(main())
