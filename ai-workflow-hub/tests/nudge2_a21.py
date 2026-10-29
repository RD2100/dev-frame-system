"""nudge2_a21.py — Second nudge to get full A21 verdict."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_PATH = r"D:\dev-frame-opencode\ai-workflow-hub\GPT_REVIEW_A21_ZIP_FULL.txt"
CHAT_ID = "6a297e5f-c9c8-83a8-b413-a8fc414e0e85"
NUDGE_MSG = "Your previous response was truncated. Please continue from where you left off. Provide the remaining limitations, the next acceptance ID, and the brief rationale. Do NOT repeat what you already said."

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
        print("ERROR: Chat tab not found")
        await browser.close()
        return

    print(f"Found tab: {target.url[:60]}")
    await target.bring_to_front()

    baseline = await target.evaluate(
        "() => document.querySelectorAll('[data-message-author-role=\"assistant\"]').length"
    )
    print(f"Baseline assistant messages: {baseline}")

    editor = await target.query_selector("#prompt-textarea")
    if not editor:
        editor = await target.query_selector('[contenteditable="true"][role="textbox"]')
    if not editor:
        print("ERROR: Editor not found")
        await browser.close()
        return

    await editor.click(force=True)
    await asyncio.sleep(0.3)
    await target.keyboard.press("Control+A")
    await asyncio.sleep(0.1)
    await target.keyboard.press("Backspace")
    await asyncio.sleep(0.2)
    await target.keyboard.insert_text(NUDGE_MSG)
    print(f"Nudge inserted")
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
    else:
        await target.keyboard.press("Enter")

    print("Polling...")
    for i in range(90):
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
        if i % 15 == 14:
            print(f"  Waiting... ({(i+1)*2}s, msgs={count}, stop={stop_vis})")

    print("TIMEOUT")
    await browser.close()

asyncio.run(main())
