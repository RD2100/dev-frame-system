import asyncio
import json
import sys
from playwright.async_api import async_playwright

BUNDLE_DIR = r"D:\dev-frame-system\review-bundle-phase1b-round2"
ZIP_PATH = r"D:\dev-frame-system\review-bundle-phase1b-round2.zip"
CONVO_URL = "https://chatgpt.com/c/6a475842-60a0-83e8-bbc3-c60475917c2d"


async def find_chatgpt_page(pages):
    for page in pages:
        if "chatgpt.com/c/" in page.url or "chat.openai.com/c/" in page.url:
            return page
    return None


async def upload_and_send(page):
    with open(f"{BUNDLE_DIR}/question.txt", encoding="utf-8") as fh:
        question = fh.read()

    file_input = await page.query_selector('input[type="file"]')
    if file_input:
        await file_input.set_input_files(ZIP_PATH)
        print("  [OK] file uploaded")
    else:
        attach = await page.query_selector('button[aria-label="Attach files"]')
        if attach:
            await attach.click()
            await asyncio.sleep(1)
            file_input = await page.query_selector('input[type="file"]')
            if file_input:
                await file_input.set_input_files(ZIP_PATH)
                print("  [OK] file uploaded via attach")
            else:
                print("  [WARN] no file input after attach click")
        else:
            print("  [WARN] no file input found")

    await asyncio.sleep(2)

    # Read question from file and inject via JS
    with open(f"{BUNDLE_DIR}/question.txt", encoding="utf-8") as fh:
        question = fh.read()

    # Use page.evaluate with a function to avoid string escaping issues
    result = await page.evaluate("""(text) => {
        const editor = document.querySelector('[contenteditable="true"]');
        if (!editor) return 'no_editor';
        editor.focus();
        editor.innerHTML = '';
        const lines = text.split('\\n');
        for (const line of lines) {
            const p = document.createElement('p');
            p.textContent = line || ' ';
            editor.appendChild(p);
        }
        editor.dispatchEvent(new Event('input', { bubbles: true }));
        editor.dispatchEvent(new Event('change', { bubbles: true }));
        return 'content_set:' + editor.innerText.substring(0, 80);
    }""", question)
    print(f"  [OK] editor content set: {result}")

    await asyncio.sleep(2)

    for sel in [
        'button[data-testid="send-button"]',
        'button[aria-label*="Send"]',
        'button[aria-label*="send"]',
        'button[aria-label*="发送"]',
    ]:
        btn = await page.query_selector(sel)
        if btn:
            await btn.click()
            print(f"  [OK] clicked send: {sel}")
            return True

    await page.keyboard.press("Enter")
    print("  [OK] sent via Enter")
    return True


async def poll_for_reply(page, baseline, max_checks=36, interval=10):
    import time
    for i in range(max_checks):
        await asyncio.sleep(interval)
        msg_count = await page.evaluate("""() => {
            // Count assistant messages
            const msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
            return msgs.length;
        }""")
        elapsed = (i + 1) * interval
        print(f"  poll {i+1}/{max_checks}: {elapsed}s elapsed, assistant msgs={msg_count} (baseline={baseline})")
        if msg_count > baseline:
            print(f"  [OK] new assistant message detected")
            return True
    return False


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        ctx = browser.contexts[0]
        pages = ctx.pages

        chatgpt_page = await find_chatgpt_page(pages)
        if not chatgpt_page:
            chatgpt_page = pages[-1] if pages else await ctx.new_page()
            await chatgpt_page.goto(CONVO_URL)

        print(f"Page: {chatgpt_page.url}")

        # Count baseline assistant messages
        baseline = await chatgpt_page.evaluate("""() => {
            const msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
            return msgs.length;
        }""")
        print(f"Baseline assistant messages: {baseline}")

        await upload_and_send(chatgpt_page)
        print("Starting poll for ChatGPT reply...")
        got_reply = await poll_for_reply(chatgpt_page, baseline)
        if not got_reply:
            print("No new reply within timeout")
        print(f"Final page: {chatgpt_page.url}")


if __name__ == "__main__":
    asyncio.run(main())
