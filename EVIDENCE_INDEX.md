# Evidence Index

REVIEW_RUN_ID: g0-bootstrap-skeleton-v1-20260605

## 当前状态

G0-G8A、H1-H6、T1-T3 阶段已完成。evidence packs 随各阶段生成，存放于 `evidence_packs/` 目录。

## Evidence Pack 登记

| REVIEW_RUN_ID | 阶段 | 类型 | 状态 | 文件数 | SHA256 |
|---------------|------|------|------|--------|--------|
| g0-bootstrap-v1 | G0 | bootstrap | completed | 14 | — |
| g1-schema-design-v1 | G1 | schema | completed | — | — |
| g2-runner-skeleton-v1 | G2 | runner | completed | — | — |
| g3-submission-adapter-v1 | G3 | adapter | completed | — | — |
| g4-runner-adapter-cli-v1 | G4 | integration | completed | — | — |
| g5-cdp-adapter-v1 | G5 | adapter | accepted_with_evidence_limitation | — | — |
| g6-playwright-bridge-v1 | G6 | bridge | accepted_with_evidence_limitation | — | — |
| g7-mechanical-cdp-v1 | G7 | pilot | accepted | — | — |
| g8-bounded-gpt-review-v1 | G8 | pilot | accepted_with_audit_note | — | — |
| g8a-context-handoff-v1 | G8A | protocol | accepted | — | — |
| h1-productization-v1 | H1 | productization | accepted_with_evidence_limitation | — | — |
| h2-integration-v1 | H2 | design | accepted | — | — |
| h3-paper-template-v1 | H3 | template | accepted | — | — |
| h4-archive-governance-v1 | H4 | governance | accepted | — | — |
| h6-guard-retirement-v1 | H6 | design | accepted | — | — |
| t1-context-sync-v1 | T1 | automation | accepted | — | — |
| t2-live-bootstrap-v1 | T2 | pilot | accepted_with_evidence_limitation | — | — |
| t3-handoff-file-attach-v1 | T3 | protocol | accepted | — | — |

## 证据目录

```
evidence_packs/
  g0-bootstrap-skeleton-v1-20260605/
  g1-schema-design-v1/
  g2-runner-skeleton-v1/
  ...
```

## 规则

- 所有 evidence packs 必须包含 PACK_MANIFEST.md 和 VALIDATION_RESULT.json
- SHA256 必须覆盖 pack 中所有文件（排除自引用文件）
- 证据包不得包含敏感信息
- 历史证据只追加，不删除
- evidence_cleanup_approved: false（permanently blocked）
