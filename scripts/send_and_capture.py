"""send_and_capture.py — Click send button and capture response."""
import asyncio
from playwright.async_api import async_playwright

CHAT_ID = "6a297e5f-c9c8-83a8-b413-a8fc414e0e85"
OUTPUT = r"D:\dev-frame-opencode\ai-workflow-hub\GPT_REVIEW_A15_ZIP.txt"


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
        print("Tab not found")
        return
    await target.bring_to_front()
    await asyncio.sleep(1)

    # Try clicking the send button
    send_btn = await target.query_selector('[data-testid="send-button"]')
    if send_btn:
        await send_btn.click()
        print("Clicked send button via data-testid")
    else:
        # Find send button by aria-label
        btns = await target.query_selector_all("button")
        found = False
        for b in btns:
            label = await b.get_attribute("aria-label") or ""
            if "send" in label.lower():
                await b.click()
                print(f"Clicked send button: {label}")
                found = True
                break
        if not found:
            # Try Enter in editor
            editor = await target.query_selector("#prompt-textarea")
            if editor:
                await editor.click(force=True)
                await asyncio.sleep(0.5)
                await target.keyboard.press("Enter")
                print("Pressed Enter")

    await asyncio.sleep(3)

    user_msgs = await target.evaluate(
        "() => document.querySelectorAll('[data-message-author-role=\"user\"]').length"
    )
    asst_msgs = await target.evaluate(
        "() => document.querySelectorAll('[data-message-author-role=\"assistant\"]').length"
    )
    print(f"Messages: user={user_msgs}, assistant={asst_msgs}")

    # Wait for response
    baseline = asst_msgs
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
            await asyncio.sleep(3)
            reply = await target.evaluate("""
                () => {
                    const msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
                    if (msgs.length === 0) return '';
                    return msgs[msgs.length - 1].innerText;
                }
            """)
            if len(reply) > 100:
                print(f"Response captured ({len(reply)} chars)")
                with open(OUTPUT, "w", encoding="utf-8") as f:
                    f.write(reply)
                print(f"Saved to {OUTPUT}")
                print("---RESPONSE---")
                print(reply[:3000])
                await browser.close()
                return
        elif i % 10 == 9:
            print(f"  Waiting... ({(i+1)*2}s, msgs={count}, stop={stop_vis})")

    print("TIMEOUT waiting for response")
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
