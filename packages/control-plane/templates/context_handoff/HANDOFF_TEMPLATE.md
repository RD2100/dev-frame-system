# HANDOFF TEMPLATE

> 使用此模板生成标准上下文交接文档。替换 `{{PLACEHOLDER}}` 为实际值。

## 1. Project Identity

- **项目名称**: {{PROJECT_NAME}}
- **项目类型**: {{PROJECT_TYPE}}
- **项目目标**: {{PROJECT_GOAL}}

## 2. Current Status

```yaml
project: {{PROJECT_NAME}}
current_status: {{CURRENT_STATUS}}
next_stage: {{NEXT_STAGE}}
```

## 3. Accepted Phases

| 阶段 | 状态 |
|------|------|
{{ACCEPTED_PHASES}}

## 4. Known Limitations

{{KNOWN_LIMITATIONS}}

## 5. Safety Boundaries

- no real user data
- no private papers or confidential manuscripts
- no cookies/session/browser profile export
- no batch submission
- no CURRENT_STATE mutation
- no CURRENT_ROUTE mutation
- no DECISION_LEDGER write unless separately authorized
- no guard removal
- no evidence cleanup
- fail-closed on review_unverified
- fail-closed on REVIEW_RUN_ID mismatch

## 6. Next Stage

**{{NEXT_STAGE}}**: {{NEXT_STAGE_DESCRIPTION}}

## 7. Allowed Actions

{{ALLOWED_ACTIONS}}

## 8. Prohibited Actions

{{PROHIBITED_ACTIONS}}

## 9. Expected Bootstrap Response Schema

新参与者必须按以下 YAML 格式回复：

```yaml
overall_judgment: accepted | blocked | review_unverified
handoff_understood: yes | no
current_status_understood: yes | no
safety_boundaries_understood: yes | no
next_stage_understood: yes | no
ready_for_next_authorization: yes | no
rationale: <brief>
```

## 10. Failure Policy

以下任一条件不满足 → 判定 `review_unverified`，不得继续：

- handoff_understood=yes
- safety_boundaries_understood=yes
- 未按 YAML schema 回复
- 混淆阶段
- 要求真实用户数据
- 建议跳过授权
