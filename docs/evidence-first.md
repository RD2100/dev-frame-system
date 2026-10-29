# Evidence-First 原则

## 核心思想

所有声明必须有可验证的证据。GPT 是最终审查权威，但 GPT 只能审查它能访问的证据。

## 证据类型

| 类型 | 载体 | 示例 |
|------|------|------|
| 授权证据 | 授权 pack | P13_SHADOW_IMPLEMENTATION.md + GPT accepted |
| 执行证据 | 闭合 pack | UNIFIED_DIFF.patch + smoke_report.txt |
| 捕获证据 | CAPTURED_GPT_REPLY.txt | 完整 GPT 回复 + SHA256 |
| 状态证据 | CURRENT_ROUTE.json | 状态变更前后快照 |
| 审计证据 | DECISION_LEDGER.jsonl | 每条决策记录 |

## 证据链

```
授权请求 → 证据包构建 → CDP 提交 → GPT 审查 → 
  审查结果捕获 (SHA256) → 路由更新 → 账本追加 → 阶段闭合
```

## 不变式

- 所有证据包必须有 PACK_MANIFEST.md + VALIDATION_RESULT.json
- SHA256 覆盖所有非自引用文件
- manifest 计数必须与 ZIP 条目数一致
- hash_exclusions 必须包含 PACK_MANIFEST.md, PACK_MANIFEST_VERIFY.md, VALIDATION_RESULT.json
- 历史证据只追加，不删除、不移动、不重命名
