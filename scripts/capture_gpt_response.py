"""capture_gpt_response.py — Capture the latest GPT response from the chat tab."""
import asyncio
from playwright.async_api import async_playwright

CHAT_ID = "6a297e5f-c9c8-83a8-b413-a8fc414e0e85"
OUTPUT_PATH = r"D:\dev-frame-opencode\GPT_REVIEW_A10_ZIP.txt"

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
        return

    await target.bring_to_front()
    await asyncio.sleep(1)

    # Get total messages
    count = await target.evaluate(
        "() => document.querySelectorAll('[data-message-author-role=\"assistant\"]').length"
    )
    print(f"Total assistant messages: {count}")

    # Check if stop button visible
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
    print(f"Stop button visible: {stop_vis}")

    if stop_vis:
        print("GPT is still generating... waiting 30s")
        await asyncio.sleep(30)

    # Capture latest response
    reply = await target.evaluate("""
        () => {
            const msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
            if (msgs.length === 0) return '';
            return msgs[msgs.length - 1].innerText;
        }
    """)

    print(f"Response length: {len(reply)} chars")
    if reply:
        print("---RESPONSE---")
        print(reply[:5000])

        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            f.write(reply)
        print(f"\nSaved to {OUTPUT_PATH}")
    else:
        print("ERROR: No response captured")

    await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
