# oracle-handoff-only

CDP 不可用时的半自动 handoff 模式。

```bash
python tools/oracle_chatgpt_cdp_handoff.py --handoff-only
```

## 功能
1. 检查 evidence pack zip 和 GPT_REVIEW_PROMPT.md 是否存在
2. 将 prompt 内容复制到剪贴板（优先 pyperclip，fallback 写入文件）
3. 打开 evidence pack 所在文件夹
4. 输出手动上传清单

## 输出
- `_reports/browser-cdp-handoff/CDP_HANDOFF.md`
- `_reports/browser-cdp-handoff/CHATGPT_UPLOAD_CHECKLIST.md`
- `_reports/browser-cdp-handoff/PROMPT_COPY_FALLBACK.txt`（如剪贴板不可用）

## 安全
- 仅检查文件、复制 prompt、打开文件夹
- 不操作浏览器
- 不自动提交
- 不修改任何文件

## Framework Freeze Status
**正式能力（fallback）** — 已验证可用。
