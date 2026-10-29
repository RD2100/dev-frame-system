# oracle-pack-review

为指定任务生成 GPT 可复审 evidence pack。

```bash
python tools/oracle_s2_review_pack.py
```

## 功能
1. 收集 S2 执行证据（run artifacts, reports, reviewer-index, evidence-index, test-output, git status）
2. 复制核心源码文件
3. 运行 git status / git diff --stat 生成只读证据
4. 生成完整 evidence pack 目录结构
5. 打包为 zip

## 输出
- `_reports/s2-gpt-review-evidence-pack/` 目录
- `s2-gpt-review-evidence-pack.zip`
- `GPT_REVIEW_PROMPT.md`
- `PACK_MANIFEST.md`
- `MISSING_FILES.md`
- `EVIDENCE_CONFLICTS.md`

## 安全
- 不得修改源码
- 不得执行下一阶段（S3）
- 不得伪造证据
- 不得忽略 evidence pack 缺失项（必须写入 MISSING_FILES.md）

## Framework Freeze Status
**正式能力** — 已验证可用。
