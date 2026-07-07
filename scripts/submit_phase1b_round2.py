import asyncio
import argparse
import os
from pathlib import Path

from playwright.async_api import async_playwright

DEFAULT_BUNDLE_DIR = "review-bundle-phase1b-round2"
DEFAULT_ZIP_PATH = "review-bundle-phase1b-round2.zip"
BUNDLE_DIR_ENV = "SUBMIT_BUNDLE_DIR"
ZIP_PATH_ENV = "SUBMIT_ZIP_PATH"
CONVO_URL_ENV = "SUBMIT_CONVERSATION_URL"
CDP_ENDPOINT_ENV = "SUBMIT_CDP_ENDPOINT"


def parse_args():
    env_cdp_endpoint = os.environ.get(CDP_ENDPOINT_ENV)
    parser = argparse.ArgumentParser(
        description="Upload a review bundle to an existing ChatGPT browser session."
    )
    parser.add_argument(
        "--bundle-dir",
        default=os.environ.get(BUNDLE_DIR_ENV, DEFAULT_BUNDLE_DIR),
        help=f"Bundle directory. Defaults to ${BUNDLE_DIR_ENV} or {DEFAULT_BUNDLE_DIR}.",
    )
    parser.add_argument(
        "--zip-path",
        default=os.environ.get(ZIP_PATH_ENV, DEFAULT_ZIP_PATH),
        help=f"Bundle zip path. Defaults to ${ZIP_PATH_ENV} or {DEFAULT_ZIP_PATH}.",
    )
    parser.add_argument(
        "--conversation-url",
        default=os.environ.get(CONVO_URL_ENV),
        help=f"ChatGPT conversation URL. Defaults to ${CONVO_URL_ENV}.",
    )
    parser.add_argument(
        "--cdp-endpoint",
        default=env_cdp_endpoint,
        required=not env_cdp_endpoint,
        help=f"Browser CDP endpoint. Defaults to ${CDP_ENDPOINT_ENV}.",
    )
    args = parser.parse_args()
    args.bundle_dir = Path(args.bundle_dir)
    args.zip_path = Path(args.zip_path)
    return args


async def find_chatgpt_page(pages):
    for page in pages:
        if "chatgpt.com/c/" in page.url or "chat.openai.com/c/" in page.url:
            return page
    return None


async def upload_and_send(page, bundle_dir, zip_path):
    question = (bundle_dir / "question.txt").read_text(encoding="utf-8")

    file_input = await page.query_selector('input[type="file"]')
    if file_input:
        await file_input.set_input_files(str(zip_path))
        print("  [OK] file uploaded")
    else:
        attach = await page.query_selector('button[aria-label="Attach files"]')
        if attach:
            await attach.click()
            await asyncio.sleep(1)
            file_input = await page.query_selector('input[type="file"]')
            if file_input:
                await file_input.set_input_files(str(zip_path))
                print("  [OK] file uploaded via attach")
            else:
                print("  [WARN] no file input after attach click")
        else:
            print("  [WARN] no file input found")

    await asyncio.sleep(2)

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
    args = parse_args()
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(args.cdp_endpoint)
        ctx = browser.contexts[0]
        pages = ctx.pages

        chatgpt_page = await find_chatgpt_page(pages)
        if not chatgpt_page:
            if not args.conversation_url:
                raise RuntimeError(
                    "No ChatGPT conversation page found. Pass --conversation-url "
                    f"or set ${CONVO_URL_ENV}."
                )
            chatgpt_page = pages[-1] if pages else await ctx.new_page()
            await chatgpt_page.goto(args.conversation_url)

        print(f"Page: {chatgpt_page.url}")

        # Count baseline assistant messages
        baseline = await chatgpt_page.evaluate("""() => {
            const msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
            return msgs.length;
        }""")
        print(f"Baseline assistant messages: {baseline}")

        await upload_and_send(chatgpt_page, args.bundle_dir, args.zip_path)
        print("Starting poll for ChatGPT reply...")
        got_reply = await poll_for_reply(chatgpt_page, baseline)
        if not got_reply:
            print("No new reply within timeout")
        print(f"Final page: {chatgpt_page.url}")


if __name__ == "__main__":
    asyncio.run(main())
