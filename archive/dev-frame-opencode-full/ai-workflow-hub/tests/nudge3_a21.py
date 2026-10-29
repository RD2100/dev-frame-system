"""nudge3_a21.py — Third nudge: get next acceptance + rationale."""
import asyncio
from playwright.async_api import async_playwright

OUTPUT_PATH = r"D:\dev-frame-opencode\ai-workflow-hub\GPT_REVIEW_A21_ZIP_FINAL.txt"
CHAT_ID = "6a297e5f-c9c8-83a8-b413-a8fc414e0e85"
NUDGE_MSG = "Your response was again truncated. Please provide ONLY: (1) the remaining limitations text, (2) next acceptance ID, (3) brief rationale. Keep it concise."

async def main():
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
    target = None
    for ctx in browser.contexts:
        for page in ctx.pages:
            if CHAT_ID in page.url:
                target = page; break
    if not target:
        print("ERROR: tab not found"); await browser.close(); return
    await target.bring_to_front()
    baseline = await target.evaluate(
        "() => document.querySelectorAll('[data-message-author-role=\"assistant\"]').length")
    print(f"Baseline: {baseline}")

    editor = await target.query_selector("#prompt-textarea") or \
             await target.query_selector('[contenteditable="true"][role="textbox"]')
    if not editor:
        print("ERROR: editor not found"); await browser.close(); return
    await editor.click(force=True)
    await asyncio.sleep(0.3)
    await target.keyboard.press("Control+A")
    await target.keyboard.press("Backspace")
    await asyncio.sleep(0.2)
    await target.keyboard.insert_text(NUDGE_MSG)
    await asyncio.sleep(1)

    send_btn = await target.query_selector('[data-testid="send-button"]')
    if send_btn:
        disabled = await send_btn.get_attribute("disabled")
        if disabled:
            for w in range(15):
                await asyncio.sleep(1)
                disabled = await send_btn.get_attribute("disabled")
                if not disabled: break
        await send_btn.click()
    else:
        await target.keyboard.press("Enter")
    print("Sent")

    for i in range(90):
        await asyncio.sleep(2)
        count = await target.evaluate(
            "() => document.querySelectorAll('[data-message-author-role=\"assistant\"]').length")
        stop_vis = await target.evaluate("""
            () => { for (const b of document.querySelectorAll('button')) {
                if ((b.textContent||'').includes('Stop') || (b.getAttribute('aria-label')||'').includes('Stop')) return true;
            } return false; }""")
        if count > baseline and not stop_vis:
            await asyncio.sleep(5)
            reply = await target.evaluate("""
                () => { const msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
                    if (!msgs.length) return '';
                    const last = msgs[msgs.length-1];
                    const md = last.querySelector('.markdown');
                    return md ? md.innerText : last.innerText; }""")
            if len(reply) > 50:
                print(f"Captured ({len(reply)} chars)")
                with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
                    f.write(reply)
                print("---RESPONSE---")
                print(reply[:5000])
                await browser.close(); return
        if i % 15 == 14:
            print(f"  Wait ({(i+1)*2}s, msgs={count})")
    print("TIMEOUT"); await browser.close()

asyncio.run(main())
