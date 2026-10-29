"""submit_a15_resubmit.py — Re-submit A15 ZIP to GPT and capture verdict.

Strategy:
1. Upload ZIP via file input
2. Wait for ZIP to appear as attachment chip in the editor
3. Insert follow-up prompt text
4. Click send button (not Enter key)
5. Poll for GPT response
"""
import asyncio
import sys
from playwright.async_api import async_playwright

ZIP_PATH = sys.argv[1] if len(sys.argv) > 1 else r"D:\dev-frame-opencode\ai-workflow-hub\EVIDENCE_PACK_A15.zip"
OUTPUT_PATH = sys.argv[2] if len(sys.argv) > 2 else r"D:\dev-frame-opencode\ai-workflow-hub\GPT_REVIEW_A15_ZIP.txt"
CHAT_ID = "6a297e5f-c9c8-83a8-b413-a8fc414e0e85"

FOLLOWUP_PROMPT = """I'm re-uploading the evidence ZIP for A15 since the previous upload didn't reach your /mnt/data. Please:

1. Check /mnt/data for EVIDENCE_PACK_A15.zip
2. Unzip and review all files
3. Provide your formal verdict in the same format as A13 and A14:

task_id: PAPER-DECISION-AUDIT-HARDENING-A15
overall_judgment: (accepted / accepted_with_limitations / review_unverified / rejected)
evidence_pack_reviewed: true/false
blocking_issues: (list or "none")
limitations: (numbered list)
next_task_authorized: (task description or "N/A")

The A15 prompt above contains the full review context. The ZIP contains all source files, tests, validation output, and pytest output."""


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
        print("ERROR: Project chat tab not found")
        await browser.close()
        return

    print(f"Found tab: {target.url[:60]}")
    await target.bring_to_front()
    await asyncio.sleep(1)

    # Baseline
    baseline = await target.evaluate(
        "() => document.querySelectorAll('[data-message-author-role=\"assistant\"]').length"
    )
    print(f"Baseline assistant messages: {baseline}")

    # Step 1: Upload ZIP
    print("=== Step 1: Upload ZIP ===")
    file_input = await target.query_selector('input[type="file"]')
    if file_input:
        await file_input.set_input_files(ZIP_PATH)
        print(f"ZIP uploaded via file input: {ZIP_PATH}")
        await asyncio.sleep(3)

        # Dismiss duplicate file modal if present
        modal = await target.query_selector('#modal-duplicate-file')
        if modal:
            print("Duplicate file modal detected, dismissing...")
            btn_modal = await target.query_selector('#modal-duplicate-file button.btn-primary')
            if btn_modal:
                await btn_modal.click()
            else:
                await target.keyboard.press("Escape")
            await asyncio.sleep(2)
            print("Modal dismissed")
    else:
        print("WARNING: No file input found")

    # Step 2: Wait for attachment to appear
    print("=== Step 2: Check attachment ===")
    for attempt in range(10):
        attachment_info = await target.evaluate("""
            () => {
                // Check for file attachment chips/buttons near the editor
                const chips = document.querySelectorAll('[data-testid*="file"], [data-testid*="attachment"]');
                if (chips.length > 0) {
                    return { found: true, count: chips.length, text: chips[0].textContent || '' };
                }
                // Check for any file name display in the composer area
                const composer = document.querySelector('form, [role="form"]');
                if (composer) {
                    const fileEls = composer.querySelectorAll('button, span, div');
                    for (const el of fileEls) {
                        const t = el.textContent || '';
                        if (t.includes('.zip') || t.includes('EVIDENCE')) {
                            return { found: true, count: 1, text: t.substring(0, 100) };
                        }
                    }
                }
                return { found: false, count: 0, text: '' };
            }
        """)
        print(f"  Attempt {attempt+1}: attachment={attachment_info}")
        if attachment_info.get('found'):
            print(f"  Attachment detected: {attachment_info.get('text', '')[:80]}")
            break
        await asyncio.sleep(1)
    else:
        print("  WARNING: Attachment not detected in UI, but continuing...")

    # Step 3: Click editor and insert text
    print("=== Step 3: Insert prompt text ===")
    editor = await target.query_selector("#prompt-textarea")
    if not editor:
        editor = await target.query_selector('[contenteditable="true"][role="textbox"]')

    if not editor:
        print("ERROR: Text editor not found")
        await browser.close()
        return

    await editor.click(force=True)
    await asyncio.sleep(0.5)

    # Clear any existing text
    await target.keyboard.press("Control+A")
    await asyncio.sleep(0.1)
    await target.keyboard.press("Backspace")
    await asyncio.sleep(0.2)

    # Insert text via CDP native insertText
    await target.keyboard.insert_text(FOLLOWUP_PROMPT)
    print(f"Prompt inserted ({len(FOLLOWUP_PROMPT)} chars)")
    await asyncio.sleep(1)

    # Step 4: Click send button
    print("=== Step 4: Click send button ===")
    send_btn = await target.query_selector('[data-testid="send-button"]')
    if send_btn:
        disabled = await send_btn.get_attribute("disabled")
        print(f"  Send button found, disabled={disabled}")
        if disabled:
            # Wait for button to become enabled (attachment may still be processing)
            for w in range(15):
                await asyncio.sleep(1)
                disabled = await send_btn.get_attribute("disabled")
                if not disabled:
                    print(f"  Send button enabled after {w+1}s")
                    break
            else:
                print("  WARNING: Send button stayed disabled, trying click anyway")

        await send_btn.click()
        print("  Send button clicked!")
    else:
        print("  Send button not found, trying Enter key...")
        await editor.click(force=True)
        await asyncio.sleep(0.3)
        await target.keyboard.press("Enter")
        print("  Enter pressed")

    # Step 5: Verify message was sent
    print("=== Step 5: Verify and wait for response ===")
    await asyncio.sleep(3)

    user_msgs = await target.evaluate(
        "() => document.querySelectorAll('[data-message-author-role=\"user\"]').length"
    )
    print(f"  User messages after send: {user_msgs}")

    # Poll for response
    print("=== Step 6: Polling for GPT response ===")
    for i in range(150):
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
            await asyncio.sleep(5)
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
                print(reply[:5000])
                await browser.close()
                return
            else:
                print(f"  Reply too short ({len(reply)} chars), waiting...")
        elif i % 15 == 14:
            print(f"  Waiting... ({(i+1)*2}s, msgs={count}, stop={stop_vis})")

    print("TIMEOUT waiting for GPT response")
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
