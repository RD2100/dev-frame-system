"""capture_all_a18.py — Capture ALL assistant messages to find A18 verdict."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

CHAT_ID = "6a297e5f-c9c8-83a8-b413-a8fc414e0e85"
OUTPUT = r"D:\dev-frame-opencode\ai-workflow-hub\GPT_REVIEW_A18_ZIP.txt"

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

    # Check generating status
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

    # Get ALL messages with metadata
    msgs = await target.evaluate("""
        () => {
            const user_msgs = document.querySelectorAll('[data-message-author-role="user"]');
            const asst_msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
            const results = {
                user_count: user_msgs.length,
                asst_count: asst_msgs.length,
                stop_visible: false,
                last_asst: '',
                all_asst_lengths: [],
                page_title: document.title,
            };
            // Check stop button
            const btns = document.querySelectorAll('button');
            for (const b of btns) {
                const t = b.textContent || '';
                const al = b.getAttribute('aria-label') || '';
                if (t.includes('Stop') || al.includes('Stop')) results.stop_visible = true;
            }
            // Get all assistant message lengths and last one content
            for (let i = 0; i < asst_msgs.length; i++) {
                const md = asst_msgs[i].querySelector('.markdown');
                const txt = md ? md.innerText : asst_msgs[i].innerText;
                results.all_asst_lengths.push(txt.length);
                if (i === asst_msgs.length - 1) results.last_asst = txt;
            }
            // Get last user message
            if (user_msgs.length > 0) {
                const last_user = user_msgs[user_msgs.length - 1];
                const umd = last_user.querySelector('.markdown');
                results.last_user = umd ? umd.innerText : last_user.innerText;
            }
            return results;
        }
    """)

    print(f"User messages: {msgs['user_count']}")
    print(f"Assistant messages: {msgs['asst_count']}")
    print(f"Stop visible: {msgs['stop_visible']}")
    print(f"All asst lengths: {msgs['all_asst_lengths']}")
    print(f"Page title: {msgs['page_title']}")
    print(f"Last user msg (first 200): {msgs.get('last_user', '')[:200]}")
    print(f"Last asst msg ({len(msgs['last_asst'])} chars):")
    print(msgs['last_asst'][:2000])

    # If generating, wait more
    if msgs['stop_visible']:
        print("\nGPT still generating, waiting...")
        for i in range(60):
            await asyncio.sleep(2)
            stop = await target.evaluate("""
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
            if not stop:
                print(f"  Done after {(i+1)*2}s")
                break
            if i % 10 == 9:
                print(f"  Still waiting... {(i+1)*2}s")

        # Recapture
        msgs2 = await target.evaluate("""
            () => {
                const asst_msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
                const results = { asst_count: asst_msgs.length, all_asst_lengths: [], last_asst: '' };
                for (let i = 0; i < asst_msgs.length; i++) {
                    const md = asst_msgs[i].querySelector('.markdown');
                    const txt = md ? md.innerText : asst_msgs[i].innerText;
                    results.all_asst_lengths.push(txt.length);
                    if (i === asst_msgs.length - 1) results.last_asst = txt;
                }
                return results;
            }
        """)
        print(f"\nAfter wait - Assistant messages: {msgs2['asst_count']}")
        print(f"All asst lengths: {msgs2['all_asst_lengths']}")
        print(f"Last asst ({len(msgs2['last_asst'])} chars):")
        print(msgs2['last_asst'][:3000])

        if len(msgs2['last_asst']) > 100:
            with open(OUTPUT, "w", encoding="utf-8") as f:
                f.write(f"# GPT Review — A18 PAPER-CLI-RUNTIME-E2E\n")
                f.write(f"# Captured via CDP ({len(msgs2['last_asst'])} chars)\n\n")
                f.write(msgs2['last_asst'])
            print(f"\nSaved to {OUTPUT}")

    await browser.close()

asyncio.run(main())
