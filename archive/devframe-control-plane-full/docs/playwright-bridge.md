# Playwright Bridge

## G6 — Optional Playwright Import + Safety Flag

Bridge connects Control Plane to real CDP/Playwright. G6 implements the safety layer. Actual live submission is G7 (separate pilot).

## Modes

| Mode | Health Check | Submit | Playwright Required |
|------|-------------|--------|-------------------|
| disabled | blocked | blocked | No |
| dry_run | ready | deterministic success | No |
| live | requires: safety_flag + conv_id + playwright | placeholder (G7) | Yes |

## Safety

- Playwright import is optional (try/except)
- Live mode requires explicit safety_flag=True
- No real GPT submission in tests
- Bridge disabled by default

## Usage

```python
from control_plane.playwright_bridge import BridgeConfig, BridgeMode, submit_via_bridge
config = BridgeConfig(mode=BridgeMode.DRY_RUN)
result = submit_via_bridge(request, config)
```
