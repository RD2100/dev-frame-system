"""submit_a7_to_gpt.py — Submit A7 evidence pack to GPT via CDP."""
import asyncio
from playwright.async_api import async_playwright

ZIP_PATH = r"D:\dev-frame-opencode\EVIDENCE_PACK_A12.zip"
PROMPT_PATH = r"D:\dev-frame-opencode\GPT_REVIEW_PROMPT_A12.md"
OUTPUT_PATH = r"D:\dev-frame-opencode\GPT_REVIEW_A12_ZIP.txt"
CHAT_ID = "6a297e5f-c9c8-83a8-b413-a8fc414e0e85"


async def main():
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222")

    # Find project chat tab
    target = None
    for ctx in browser.contexts:
        for page in ctx.pages:
            if CHAT_ID in page.url:
                target = page
                break
    if not target:
        print("ERROR: Project chat tab not found")
        return

    print(f"Found tab: {target.url[:60]}")
    await target.bring_to_front()
    await asyncio.sleep(1)

    # Baseline: count assistant messages
    baseline = await target.evaluate(
        "() => document.querySelectorAll('[data-message-author-role=\"assistant\"]').length"
    )
    print(f"Baseline assistant messages: {baseline}")

    # Upload ZIP
    file_input = await target.query_selector('input[type="file"]')
    if file_input:
        await file_input.set_input_files(ZIP_PATH)
        print("ZIP uploaded via file input")
        await asyncio.sleep(2)
    else:
        print("WARNING: No file input found, trying attach button...")
        # Try attach button + file chooser
        try:
            async with target.expect_file_chooser(timeout=5000) as fc:
                btn = await target.query_selector('[data-testid="file-upload-button"]')
                if btn:
                    await btn.click()
                else:
                    # Generic paperclip
                    btns = await target.query_selector_all("button")
                    for b in btns:
                        label = await b.get_attribute("aria-label") or ""
                        if "attach" in label.lower() or "file" in label.lower():
                            await b.click()
                            break
            chooser = await fc.value
            await chooser.set_files(ZIP_PATH)
            print("ZIP uploaded via file chooser")
            await asyncio.sleep(2)
        except Exception as e:
            print(f"Could not upload ZIP: {e}")

    # Read and type prompt
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        prompt = f.read()

    editor = await target.query_selector("#prompt-textarea")
    if not editor:
        editor = await target.query_selector('[contenteditable="true"][role="textbox"]')

    if not editor:
        print("ERROR: Text editor not found")
        await browser.close()
        return

    await editor.click()
    await asyncio.sleep(0.5)
    await target.keyboard.press("Control+A")
    await asyncio.sleep(0.1)
    await target.keyboard.type(prompt, delay=5)
    print(f"Prompt typed ({len(prompt)} chars)")
    await asyncio.sleep(1)
    await target.keyboard.press("Enter")
    print("Submitted! Waiting for response...")

    # Poll for response
    for i in range(120):
        await asyncio.sleep(2)
        count = await target.evaluate(
            "() => document.querySelectorAll('[data-message-author-role=\"assistant\"]').length"
        )
        # Check stop button
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
                with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
                    f.write(reply)
                print(f"Saved to {OUTPUT_PATH}")
                print("---RESPONSE---")
                print(reply[:3000])
                break
            else:
                print(f"  Reply too short ({len(reply)} chars), waiting...")
        elif i % 10 == 9:
            print(f"  Waiting... ({(i+1)*2}s, msgs={count}, stop={stop_vis})")
    else:
        print("TIMEOUT waiting for GPT response")

    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
