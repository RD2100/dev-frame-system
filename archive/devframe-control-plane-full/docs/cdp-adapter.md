# CDP Adapter

## G5 — Interface + Safety + Dry-Run

CdpAdapter provides the interface layer for future real CDP submission. G5 only implements safety-checked modes without Playwright.

## Modes

| Mode | submit() | health_check() | can_submit() |
|------|----------|---------------|-------------|
| dry_run | deterministic success | true | true |
| not_configured | failure + detail | false | false |
| unavailable | failure + detail | false | false |

## Usage

```python
from control_plane.cdp_adapter import create_adapter
adapter = create_adapter("dry_run")
result = adapter.submit(request)
```

## Safety

- No Playwright import
- No real CDP connection
- No GPT submission
- No state mutation
- All modes except dry_run return safe failure
