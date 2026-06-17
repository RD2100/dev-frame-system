---
note_id: mem-retrieval-architecture-decisions
type: project_memory
project_id: edu-policy-research-2026
title: Retrieval Architecture Design Decisions
chapter: methodology
status: active
tags: [architecture, retrieval, design decisions]
confidentiality: public
---

Key architecture decisions for the retrieval pipeline:

1. Metadata weight 0.4 + keyword weight 0.6 — chosen based on Lee (2021) validation results
2. Chinese bigram tokenization — simple but effective for CJK text without jieba dependency
3. Top-k default of 5 — balances comprehensiveness with context window limits
4. Privacy filter runs BEFORE retrieval — fail-closed approach ensures sensitive data never enters scoring
