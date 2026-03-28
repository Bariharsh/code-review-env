from __future__ import annotations

import re

from .models import CodeReviewTask, RewardState


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "because",
    "by",
    "for",
    "from",
    "has",
    "in",
    "into",
    "is",
    "it",
    "of",
    "or",
    "so",
    "should",
    "that",
    "the",
    "this",
    "to",
    "use",
    "with",
}


def normalize_text(text: str) -> str:
    """Normalize text for deterministic matching."""

    lowered = text.lower()
    cleaned = re.sub(r"[^a-z0-9=_%\s]", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


def keyword_present(normalized_text: str, keyword: str) -> bool:
    normalized_keyword = normalize_text(keyword)
    if normalized_keyword in normalized_text:
        return True

    keyword_tokens = [token for token in normalized_keyword.split() if token not in STOPWORDS]
    review_tokens = set(normalized_text.split())
    return bool(keyword_tokens) and all(token in review_tokens for token in keyword_tokens)


def explanation_overlap(reference: str, review: str) -> float:
    """Compute a light-weight deterministic semantic overlap score."""

    reference_tokens = {
        token
        for token in normalize_text(reference).split()
        if token not in STOPWORDS and len(token) > 2
    }
    review_tokens = {
        token for token in normalize_text(review).split() if token not in STOPWORDS and len(token) > 2
    }

    if not reference_tokens:
        return 0.0

    overlap = reference_tokens & review_tokens
    return round(len(overlap) / len(reference_tokens), 3)


def grade_review(task: CodeReviewTask, review: str) -> RewardState:
    """Assign a deterministic reward based on required keyword groups."""

    normalized_review = normalize_text(review)
    matched_keywords: list[str] = []
    missing_keywords: list[str] = []

    for group in task.expected_output.required_keyword_groups:
        matched_keyword = next(
            (keyword for keyword in group if keyword_present(normalized_review, keyword)),
            None,
        )
        if matched_keyword is None:
            missing_keywords.append(" / ".join(group))
        else:
            matched_keywords.append(matched_keyword)

    partial_hits = [
        keyword
        for keyword in task.expected_output.partial_keywords
        if keyword_present(normalized_review, keyword)
    ]
    semantic_overlap = explanation_overlap(task.expected_output.explanation, review)

    if not missing_keywords:
        return RewardState(
            score=1.0,
            verdict="full_match",
            matched_keywords=matched_keywords,
            missing_keywords=[],
            partial_keywords=partial_hits,
            semantic_overlap=semantic_overlap,
            rationale="All required issue categories were identified.",
        )

    if matched_keywords or partial_hits or semantic_overlap >= 0.35:
        return RewardState(
            score=0.5,
            verdict="partial_match",
            matched_keywords=matched_keywords,
            missing_keywords=missing_keywords,
            partial_keywords=partial_hits,
            semantic_overlap=semantic_overlap,
            rationale="The review found part of the expected issue, but missed a key detail or fix.",
        )

    return RewardState(
        score=0.0,
        verdict="wrong",
        matched_keywords=[],
        missing_keywords=missing_keywords,
        partial_keywords=[],
        semantic_overlap=semantic_overlap,
        rationale="The review did not identify the expected issue.",
    )
