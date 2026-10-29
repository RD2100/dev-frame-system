# HANDOFF G0-G7 → G8 (EXAMPLE)

> 此为合成示例。不含真实用户数据、真实论文、cookies、session 或 browser profile。

## 1. Project Identity

- **项目名称**: DevFrame Control Plane
- **项目类型**: Workflow Integration Layer
- **项目目标**: 将散落的 Agent 工作流组件整合成声明式流水线引擎

## 2. Current Status

```yaml
project: devframe-control-plane
current_status: G0-G7 completed
feature_complete: true
mechanical_cdp_verified: true
real_gpt_review_pilot: not_yet_done
next_stage: G8_bounded_gpt_review_pilot
```

## 3. Accepted Phases

| 阶段 | 状态 |
|------|------|
| G0 Bootstrap | accepted |
| G1 Schema Design | accepted |
| G2 Runner | accepted |
| G3 Adapter | accepted |
| G4 Integration | accepted |
| G5 CDP Adapter | accepted_with_evidence_limitation |
| G6 Playwright Bridge | accepted_with_evidence_limitation |
| G7 Mechanical CDP Pilot | accepted |

## 4. Known Limitations

G5/G6 是 accepted_with_evidence_limitation。功能主线完成，部分 closure pack 存在证据格式不完美。不影响 feature-complete 判断。

## 5. G7 Meaning

G7 是 mechanical CDP pilot（非真实 GPT 审查）：
- CDP connect OK
- page found
- payload injected (SHA256 recorded)
- send button found but NOT clicked
- no GPT reply captured
- no judgment parsed

## 6. What Has NOT Been Done

- no real GPT review pilot
- no actual click-send pilot
- no captured GPT reply
- no parsed GPT judgment

## 7. Safety Boundaries

- no real user data / cookies / session / browser profile
- no CURRENT_STATE / CURRENT_ROUTE / DECISION_LEDGER mutation
- no guard removal / evidence cleanup
- fail-closed on review_unverified / RID mismatch

## 8. Next Phase: G8

Submit exactly 1 synthetic bounded prompt to new clean conversation. Capture GPT reply, compute SHA256, parse judgment. No real user data.

## 9. Expected Response

```yaml
overall_judgment: accepted | blocked | review_unverified
handoff_understood: yes | no
current_status_understood: yes | no
safety_boundaries_understood: yes | no
next_stage_understood: yes | no
ready_for_g8_authorization: yes | no
rationale: <brief>
```

## 10. Failure Policy

handoff_understood≠yes 或 safety_boundaries_understood≠yes → review_unverified，不得继续 G8。
