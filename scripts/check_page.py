"""check_page.py — Check GPT page state."""
import asyncio
from playwright.async_api import async_playwright

CHAT_ID = "6a297e5f-c9c8-83a8-b413-a8fc414e0e85"


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

    user_msgs = await target.evaluate(
        "() => document.querySelectorAll('[data-message-author-role=\"user\"]').length"
    )
    asst_msgs = await target.evaluate(
        "() => document.querySelectorAll('[data-message-author-role=\"assistant\"]').length"
    )
    print(f"User messages: {user_msgs}")
    print(f"Assistant messages: {asst_msgs}")

    editor_text = await target.evaluate("""
        () => {
            const ed = document.querySelector('#prompt-textarea');
            if (ed) return ed.textContent || ed.value || ed.innerText || '(empty)';
            const ce = document.querySelector('[contenteditable="true"][role="textbox"]');
            if (ce) return ce.textContent || ce.innerText || '(empty)';
            return '(no editor found)';
        }
    """)
    print(f"Editor ({len(editor_text)} chars): {editor_text[:500]}")

    last_user = await target.evaluate("""
        () => {
            const msgs = document.querySelectorAll('[data-message-author-role="user"]');
            if (msgs.length === 0) return '(none)';
            return msgs[msgs.length - 1].innerText;
        }
    """)
    print(f"Last user msg ({len(last_user)} chars): {last_user[:500]}")

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
    print(f"Stop button: {stop_vis}")

    modal = await target.evaluate("""
        () => {
            const m = document.querySelector('[role="dialog"]');
            return m ? m.textContent.substring(0, 300) : '(none)';
        }
    """)
    print(f"Modal: {modal[:300]}")

    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
