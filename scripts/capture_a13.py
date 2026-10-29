"""capture_a13.py — Capture latest GPT assistant message for A13."""
import asyncio
from playwright.async_api import async_playwright

CHAT_ID = "6a297e5f-c9c8-83a8-b413-a8fc414e0e85"
OUTPUT = r"D:\dev-frame-opencode\ai-workflow-hub\GPT_REVIEW_A13_ZIP.txt"


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
    await asyncio.sleep(2)

    # Wait for generation to finish
    for i in range(30):
        stop_vis = await target.evaluate("""
            () => {
                const btns = document.querySelectorAll("button");
                for (const b of btns) {
                    const t = b.textContent || "";
                    const al = b.getAttribute("aria-label") || "";
                    if (t.includes("Stop") || al.includes("Stop")) return true;
                }
                return false;
            }
        """)
        if not stop_vis:
            break
        print(f"  GPT still generating... ({(i+1)*2}s)")
        await asyncio.sleep(2)

    reply = await target.evaluate("""
        () => {
            const msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
            if (msgs.length === 0) return "";
            return msgs[msgs.length - 1].innerText;
        }
    """)
    count = await target.evaluate(
        '() => document.querySelectorAll(\'[data-message-author-role="assistant"]\').length'
    )
    print(f"Total assistant messages: {count}")
    print(f"Response length: {len(reply)} chars")
    print("---RESPONSE---")
    print(reply)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(reply)
    print(f"\nSaved to {OUTPUT}")
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
