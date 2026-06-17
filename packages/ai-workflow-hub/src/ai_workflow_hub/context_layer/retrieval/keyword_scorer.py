"""
Keyword Scorer
Extracts keywords from the task spec and scores sources by keyword
frequency in body text (Obsidian) or title (Zotero).

No vector DB or embeddings — pure keyword/FTS-based matching.
"""
import re
from collections import Counter
from typing import Any


# Chinese stop words (minimal set for academic context)
_STOP_WORDS_ZH = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些",
    "但", "而", "与", "及", "对", "为", "以", "中", "等", "从", "被", "把",
    "将", "所", "之", "其", "并", "能", "可以", "可能", "需要",
}

# English stop words (minimal)
_STOP_WORDS_EN = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "and", "but", "or", "nor", "not", "so", "yet", "both", "either",
    "neither", "each", "every", "all", "any", "few", "more", "most", "other",
    "some", "such", "no", "only", "own", "same", "than", "too", "very",
    "just", "because", "this", "that", "these", "those", "it", "its",
}

ALL_STOP_WORDS = _STOP_WORDS_ZH | _STOP_WORDS_EN


def extract_keywords(
    task_spec: dict[str, Any],
    min_length: int = 2,
    max_keywords: int = 20,
) -> list[str]:
    """Extract task-relevant keywords from the task spec.

    Combines keywords from:
    - chapter (章节名)
    - section (小节名)
    - constraints (约束条件)
    - acceptance_criteria (验收标准)
    - tags from task context

    Returns deduplicated keywords sorted by frequency, excluding stop words.
    """
    text_parts: list[str] = []

    # Collect text from relevant task spec fields
    for field in ["chapter", "section", "task_type", "paper_type"]:
        val = task_spec.get(field)
        if val:
            text_parts.append(str(val))

    for field in ["constraints", "acceptance_criteria"]:
        items = task_spec.get(field, [])
        if isinstance(items, list):
            text_parts.extend(str(item) for item in items)

    full_text = " ".join(text_parts)

    # Tokenize: split on whitespace and punctuation, keep CJK characters as unigrams/bigrams
    tokens: list[str] = []

    # Extract Chinese character sequences (2+ chars)
    cjk_pattern = re.compile(r"[\u4e00-\u9fff]{2,}")
    for match in cjk_pattern.finditer(full_text):
        word = match.group()
        if word not in ALL_STOP_WORDS:
            tokens.append(word)
        # Also extract bigrams for partial matching
        for i in range(len(word) - 1):
            bigram = word[i:i + 2]
            if bigram not in ALL_STOP_WORDS:
                tokens.append(bigram)

    # Extract English/alphanumeric words (2+ chars)
    alpha_pattern = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{1,}")
    for match in alpha_pattern.finditer(full_text):
        word = match.group().lower()
        if word not in ALL_STOP_WORDS and len(word) >= min_length:
            tokens.append(word)

    # Count and return top keywords
    counter = Counter(tokens)
    top_keywords = [kw for kw, _ in counter.most_common(max_keywords)]
    return top_keywords


def score_keywords(
    source: dict[str, Any],
    keywords: list[str],
) -> float:
    """Score a source by keyword matching in its text content.

    For Obsidian notes: searches in body text.
    For Zotero references: searches in title + tags.

    Returns:
        Keyword score in [0.0, 1.0].
    """
    if not keywords:
        return 0.5  # neutral if no keywords

    meta = source.get("metadata", {})
    is_zotero = "citekey" in meta

    # Build searchable text
    if is_zotero:
        searchable = " ".join([
            meta.get("title", ""),
            " ".join(meta.get("tags", [])),
            " ".join(meta.get("authors", [])),
        ]).lower()
    else:
        searchable = source.get("body", "").lower()

    if not searchable:
        return 0.0

    # Count keyword hits
    hits = 0
    for kw in keywords:
        kw_lower = kw.lower()
        # Count occurrences (capped at 5 per keyword to avoid over-weighting)
        count = min(searchable.count(kw_lower), 5)
        if count > 0:
            hits += min(count / 5.0, 1.0)

    # Normalize by number of keywords
    raw_score = hits / len(keywords)
    return min(1.0, max(0.0, raw_score))
