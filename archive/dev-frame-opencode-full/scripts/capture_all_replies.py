"""capture_all_replies.py — Capture all assistant messages with multiple methods."""
import asyncio
from playwright.async_api import async_playwright

CHAT_ID = "6a297e5f-c9c8-83a8-b413-a8fc414e0e85"
OUTPUT = r"D:\dev-frame-opencode\ai-workflow-hub\GPT_REVIEW_A16B_ZIP.txt"


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
        await browser.close()
        return
    await target.bring_to_front()
    await asyncio.sleep(2)

    # Get all assistant messages
    msgs = await target.evaluate("""
        () => {
            const all = document.querySelectorAll('[data-message-author-role="assistant"]');
            return Array.from(all).map((m, i) => ({
                idx: i,
                len: (m.innerText || '').length,
                preview: (m.innerText || '').substring(0, 150),
            }));
        }
    """)
    for m in msgs:
        print(f"msg[{m['idx']}]: {m['len']} chars | {m['preview'][:100]}")

    # Get last message with full details
    last = await target.evaluate("""
        () => {
            const all = document.querySelectorAll('[data-message-author-role="assistant"]');
            const last = all[all.length - 1];
            if (!last) return {innerText: '', textContent: '', markdown: ''};
            const md = last.querySelector('.markdown');
            return {
                innerText: last.innerText || '',
                textContent: last.textContent || '',
                markdown: md ? (md.innerText || '') : '',
            };
        }
    """)

    print(f"\nLast innerText ({len(last['innerText'])} chars):")
    print(last['innerText'][:2000])
    print(f"\nLast markdown ({len(last['markdown'])} chars):")
    print(last['markdown'][:2000])

    # Save the best version
    best = last['markdown'] if len(last['markdown']) > len(last['innerText']) else last['innerText']
    if len(best) > 100:
        with open(OUTPUT, "w", encoding="utf-8") as f:
            f.write(best)
        print(f"\nSaved {len(best)} chars to {OUTPUT}")

    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
