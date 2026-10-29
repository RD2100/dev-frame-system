# Submission Adapter

## 当前阶段：G3 — Dry-Run Only

Submission Adapter 为未来 CDP/GPT 提交提供接口层。G3 仅实现 dry-run 模式。

## 接口

```python
from control_plane.submission_adapter import create_adapter
from control_plane.submission_result import SubmissionRequest

adapter = create_adapter()
request = SubmissionRequest(
    review_run_id="my-review-v1",
    zip_path="/path/to/pack.zip",
    prompt_text="GPT review prompt",
    conversation_id="6a223019",
)
result = adapter.submit(request)
# result.success == True (dry-run)
# result.mode == "dry_run"
```

## 数据流

```
SubmissionRequest → SubmissionAdapter.submit() → SubmissionResult
                                                      ↓
                                            dry_run: deterministic success
                                            live (G4+): CDP/Playwright
```

## G3 限制

- 无 CDP 连接
- 无 Playwright
- 无真实 GPT 提交
- 无状态修改
- `mode` 仅支持 `dry_run`
