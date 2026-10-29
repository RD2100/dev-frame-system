#!/usr/bin/env python3
"""Submit remediation execution report to GPT via CDP."""
import asyncio, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ZIP_PATH = ROOT / "_reports" / "smoke-timeout-remediation-evidence" / "smoke-timeout-diagnosis-remediation-v1-20260604.zip"
CDP_URL = "http://localhost:9222"

PROMPT = """# 修复执行报告

REVIEW_RUN_ID: smoke-timeout-diagnosis-remediation-v1-20260604

## 执行结果：全线绿色

按你授权的范围（仅修改 test_go_dispatch.py 的 patch 配置），执行了最小修复：

### 修改内容
在 `test_fix_loop_multi_round_through_graph` 中补全 3 个缺失的 mock：
- `plan_auditor_node` → `{"status": "running", "plan_audit_passed": True}`
- `human_gate_node` → `{"status": "running"}`
- `reviewer_node` → `{"review_result": "pass"}`

### 验证结果
| Step | Tests | Result |
|------|-------|--------|
| 1. Targeted | test_fix_loop_multi_round_through_graph | 1 passed in 0.49s |
| 2. Full file | test_go_dispatch.py | 77 passed in 2.84s |
| 3. Core state | All ai-workflow-hub tests | 464 passed, 1 skipped in 30.80s |
| 4. Smoke test | Full cross-project | 3/3 PASS |

### 约束遵守
- ✅ 未修改任何生产源码（src/）
- ✅ 未跳过/删除/xfail 测试
- ✅ 未延长 timeout
- ✅ 未推进任何 blocked 下一阶段

## 请求确认
修复完成，全绿。请确认执行结果，并指导下一步。

```yaml
REVIEW_RUN_ID: smoke-timeout-diagnosis-remediation-v1-20260604
remediation_confirmed: true | false
smoke_test_verified: true | false
overall_judgment: accepted | blocked
next_action_suggestion: <建议下一步>
```
"""

async def submit():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        print(f"[OK] Connected to CDP at {CDP_URL}")
        target_page = None
        for context in browser.contexts:
            for page in context.pages:
                if "/c/6a212fda-6c04-83a8-82fa-0fa036f762f9" in page.url:
                    target_page = page
                    break
        if not target_page:
            print("ERROR: ChatGPT page not found")
            return
        await target_page.bring_to_front()
        await asyncio.sleep(1)
        file_input = await target_page.query_selector('input[type="file"]')
        if file_input:
            await file_input.set_input_files(str(ZIP_PATH))
            print(f"[OK] ZIP uploaded")
            await asyncio.sleep(3)
        input_el = await target_page.query_selector('div[contenteditable="true"].ProseMirror')
        if input_el:
            await input_el.click()
            await asyncio.sleep(0.5)
            await target_page.evaluate(f"navigator.clipboard.writeText({json.dumps(PROMPT)})")
            await asyncio.sleep(0.5)
            await target_page.keyboard.press("Control+v")
            await asyncio.sleep(1)
        send_btn = await target_page.query_selector('button[data-testid="send-button"]')
        if send_btn:
            await send_btn.click()
            print("[OK] Submitted!")
        await asyncio.sleep(2)
        print("[DONE]")

if __name__ == "__main__":
    asyncio.run(submit())
