# Architecture

## DevFrame Control Plane 架构

```
┌─────────────────────────────────────────┐
│           Pipeline YAML Spec            │
│   (声明式：阶段、依赖、证据要求)           │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│         Pipeline Runner (G2+)           │
│   authorize → evidence → CDP → review   │
└────┬──────────┬──────────┬──────────────┘
     │          │          │
┌────▼──┐ ┌────▼──┐ ┌────▼──────────┐
│ State │ │Evidence│ │Submission     │
│Machine│ │Builder │ │Adapter (G3+)  │
└───────┘ └───────┘ └───────────────┘
     │          │          │
┌────▼──┐ ┌────▼──┐ ┌────▼──────────┐
│Review │ │Ledger │ │Recovery       │
│Parser │ │Writer │ │Manager        │
└───────┘ └───────┘ └───────────────┘
```

## 组件说明

| 组件 | 职责 | 实现阶段 |
|------|------|----------|
| Pipeline Spec | YAML 格式定义流水线 | G1 |
| Pipeline Runner | 主执行引擎 | G2+ |
| State Machine | CURRENT_ROUTE 不变式检查 | G1 |
| Evidence Builder | 封装 review_pack_flow | G2+ |
| Submission Adapter | 封装 CDP/Playwright | G3+ |
| Review Parser | 解析 GPT 审查结果 | G2+ |
| Ledger Writer | DECISION_LEDGER 追加 | G2+ |
| Recovery Manager | 异常恢复 | G3+ |

## 分层设计

1. **定义层** (G1)：Schema + 规格文档
2. **执行层** (G2+)：Runner + State Machine + Evidence Builder
3. **通信层** (G3+)：CDP Adapter + Recovery Manager
