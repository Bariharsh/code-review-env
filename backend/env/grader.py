from __future__ import annotations

import re
from typing import Iterable

from .models import (
    EXPECTED_ACTION_BY_PHASE,
    ReviewAction,
    CodeReviewTask,
    RewardState,
    ScoreBreakdown,
    StepPhase,
    STRICT_SCORE_MAX,
    STRICT_SCORE_MIN,
    clamp_strict_score,
)


BUG_WEIGHT = 0.25
EXPLANATION_WEIGHT = 0.25
FIX_WEIGHT = 0.34
IRRELEVANT_PENALTY = -0.2
HALLUCINATED_FIX_PENALTY = -0.3
MAX_STRUCTURE_BONUS = 0.05
MIN_REWARD = STRICT_SCORE_MIN
MAX_REWARD = STRICT_SCORE_MAX

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
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
    "on",
    "or",
    "so",
    "that",
    "the",
    "this",
    "to",
    "with",
}

REASONING_MARKERS = {
    "because",
    "causes",
    "causing",
    "creates",
    "leads",
    "means",
    "results",
    "therefore",
    "which makes",
    "so that",
}


def normalize_text(text: str) -> str:
    """Normalize free-form text for deterministic matching."""

    lowered = text.lower()
    cleaned = re.sub(r"[^a-z0-9_=%><./()\-\s]", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


def explanation_overlap(reference: str, review: str) -> float:
    """Compute a deterministic lexical overlap score."""

    reference_tokens = {
        token
        for token in normalize_text(reference).split()
        if token not in STOPWORDS and len(token) > 2
    }
    review_tokens = {
        token
        for token in normalize_text(review).split()
        if token not in STOPWORDS and len(token) > 2
    }

    if not reference_tokens:
        return 0.0

    overlap = reference_tokens & review_tokens
    return round(len(overlap) / len(reference_tokens), 3)


def compile_signal_pattern(signal: str) -> re.Pattern[str]:
    """Compile a keyword or regex signal into a reusable pattern."""

    stripped = signal.strip()
    if stripped.startswith("re:"):
        return re.compile(stripped[3:], re.IGNORECASE | re.DOTALL)

    escaped = re.escape(stripped)
    flexible_spaces = escaped.replace(r"\ ", r"\s+")
    return re.compile(flexible_spaces, re.IGNORECASE | re.DOTALL)


def signal_matches(text: str, normalized_text: str, signal: str) -> bool:
    """Return True when a signal matches either raw or normalized text."""

    stripped_signal = signal.strip()
    pattern = compile_signal_pattern(signal)
    if pattern.search(text):
        return True

    if stripped_signal.startswith("re:"):
        return False

    normalized_signal = normalize_text(stripped_signal)
    if not normalized_signal:
        return False

    if normalized_signal in normalized_text:
        return True

    keyword_tokens = [token for token in normalized_signal.split() if token not in STOPWORDS]
    review_tokens = set(normalized_text.split())
    return bool(keyword_tokens) and all(token in review_tokens for token in keyword_tokens)


def collect_signal_matches(text: str, signals: Iterable[str]) -> tuple[list[str], list[str]]:
    """Collect matched and missing signals from a candidate response."""

    normalized_text = normalize_text(text)
    matched: list[str] = []
    missing: list[str] = []

    for signal in signals:
        if signal_matches(text, normalized_text, signal):
            matched.append(signal)
        else:
            missing.append(signal)

    return matched, missing


def keyword_target(signal_count: int) -> int:
    """Return how many strong hits are needed for full credit in one category."""

    if signal_count <= 0:
        return 1
    if signal_count <= 2:
        return 1
    return 2


def keyword_coverage(matched_count: int, signal_count: int) -> float:
    """Convert matched signal counts into a partial-credit coverage score."""

    target = keyword_target(signal_count)
    return min(matched_count / target, 1.0)


def has_reasoning_language(text: str) -> bool:
    """Check whether the explanation explicitly describes cause and effect."""

    normalized = normalize_text(text)
    return any(marker in normalized for marker in REASONING_MARKERS)


def is_structured_submission(action: ReviewAction) -> bool:
    """Reward responses that are clear and organized."""

    content = action.content.strip()
    if not content:
        return False

    if action.type == "fix":
        return "\n" in content and any(token in content for token in ("return", "if ", "const ", "def ", "SELECT", "set"))

    sentence_like_chunks = re.split(r"[.!?\n]+", content)
    non_empty_chunks = [chunk for chunk in sentence_like_chunks if chunk.strip()]
    has_list_format = bool(re.search(r"(?m)^\s*(?:[-*]|\d+\.)\s+", content))
    return has_list_format or len(non_empty_chunks) >= 2


def looks_like_code_submission(text: str) -> bool:
    """Heuristic for whether a fix action resembles code instead of prose."""

    return any(token in text for token in ("def ", "return", "{", "}", "=>", "SELECT", "if ", "useEffect", "for "))


def has_meaningful_change(original_code: str, candidate_code: str) -> bool:
    """Detect whether a submitted fix changes the original code materially."""

    return normalize_text(original_code) != normalize_text(candidate_code)


def phase_weight(phase: StepPhase) -> float:
    """Return the maximum positive score for a phase."""

    if phase == "identify_bug":
        return BUG_WEIGHT
    if phase == "explain_issue":
        return EXPLANATION_WEIGHT
    return FIX_WEIGHT


def phase_signals(task: CodeReviewTask, phase: StepPhase) -> tuple[list[str], str]:
    """Return the signals and reference text for the active phase."""

    if phase == "identify_bug":
        return task.rubric.bug_keywords, task.rubric.explanation
    if phase == "explain_issue":
        return task.rubric.explanation_keywords, task.rubric.explanation
    return task.rubric.fix_keywords, task.rubric.reference_fix or task.rubric.explanation


def phase_overlap_coverage(phase: StepPhase, overlap: float) -> float:
    """Translate lexical overlap into soft partial credit."""

    if phase == "identify_bug":
        return min(overlap / 0.45, 1.0) * 0.75
    if phase == "explain_issue":
        return min(overlap / 0.40, 1.0) * 0.85
    return min(overlap / 0.55, 1.0) * 0.60


def positive_phase_score(
    task: CodeReviewTask,
    action: ReviewAction,
    phase: StepPhase,
) -> tuple[float, list[str], list[str], float]:
    """Score the active phase before bonuses and penalties."""

    signals, reference_text = phase_signals(task, phase)
    matched, missing = collect_signal_matches(action.content, signals)
    overlap = explanation_overlap(reference_text, action.content)

    coverage = max(
        keyword_coverage(len(matched), len(signals)),
        phase_overlap_coverage(phase, overlap),
    )

    if phase == "explain_issue" and has_reasoning_language(action.content):
        coverage = min(1.0, coverage + 0.20)

    if (
        phase == "fix_code"
        and coverage > 0.0
        and looks_like_code_submission(action.content)
        and has_meaningful_change(task.code, action.content)
    ):
        coverage = min(1.0, coverage + 0.10)

    return round(phase_weight(phase) * coverage, 3), matched, missing, overlap


def structure_bonus(action: ReviewAction, positive_score: float, phase: StepPhase) -> float:
    """Give a small reward bump to well-structured answers without exceeding the phase cap."""

    if positive_score <= 0.0 or not is_structured_submission(action):
        return 0.0

    remaining_room = max(phase_weight(phase) - positive_score, 0.0)
    return round(min(MAX_STRUCTURE_BONUS, remaining_room), 3)


def irrelevant_penalty(
    action: ReviewAction,
    expected_action_type: str,
    positive_score: float,
    overlap: float,
    matched_keywords: list[str],
) -> float:
    """Penalize off-topic or mode-mismatched responses."""

    if action.type != expected_action_type:
        return IRRELEVANT_PENALTY

    if not action.content.strip():
        return IRRELEVANT_PENALTY

    if positive_score > 0.0 or matched_keywords or overlap >= 0.18:
        return 0.0

    return IRRELEVANT_PENALTY


def hallucinated_fix_penalty(
    task: CodeReviewTask,
    action: ReviewAction,
    phase: StepPhase,
    positive_score: float,
    overlap: float,
    matched_keywords: list[str],
) -> float:
    """Penalize fix attempts that change code but do not align with the rubric."""

    if phase != "fix_code" or action.type != "fix":
        return 0.0

    if not looks_like_code_submission(action.content):
        return 0.0

    if not has_meaningful_change(task.code, action.content):
        return 0.0

    if positive_score > 0.0 or matched_keywords or overlap >= 0.15:
        return 0.0

    return HALLUCINATED_FIX_PENALTY


def verdict_for_score(total_score: float, phase: StepPhase) -> str:
    """Map a step reward to a verdict label."""

    possible_positive = phase_weight(phase)
    if possible_positive <= 0:
        return "wrong"

    ratio = max(total_score, 0.0) / possible_positive
    if ratio >= 0.85:
        return "full_match"
    if ratio >= 0.35:
        return "partial_match"
    return "wrong"


def build_feedback(
    phase: StepPhase,
    matched_keywords: list[str],
    missing_keywords: list[str],
    penalties: list[str],
) -> tuple[str, str]:
    """Build concise rationale and learner-facing feedback."""

    phase_names = {
        "identify_bug": "bug identification",
        "explain_issue": "risk explanation",
        "fix_code": "fix validation",
    }
    phase_name = phase_names[phase]

    if matched_keywords:
        rationale = f"Strong {phase_name} signals detected: {', '.join(matched_keywords[:3])}."
    else:
        rationale = f"The response did not provide strong enough {phase_name} signals."

    feedback_parts: list[str] = []
    if matched_keywords:
        feedback_parts.append(f"Matched: {', '.join(matched_keywords[:3])}.")
    if missing_keywords:
        feedback_parts.append(f"Missing: {', '.join(missing_keywords[:3])}.")
    if penalties:
        feedback_parts.append("Penalties: " + ", ".join(penalties) + ".")

    feedback = " ".join(feedback_parts) if feedback_parts else rationale
    return rationale, feedback


def grade_action(task: CodeReviewTask, action: ReviewAction, phase: StepPhase, step_index: int) -> RewardState:
    """Grade one environment step with partial credit and reward shaping."""

    expected_action_type = EXPECTED_ACTION_BY_PHASE[phase]
    matched_keywords: list[str] = []
    missing_keywords: list[str] = []
    overlap = 0.0
    positive_score = 0.0

    if action.type == expected_action_type:
        positive_score, matched_keywords, missing_keywords, overlap = positive_phase_score(task, action, phase)
    else:
        _, missing_keywords = collect_signal_matches(action.content, phase_signals(task, phase)[0])
        reference_text = phase_signals(task, phase)[1]
        overlap = explanation_overlap(reference_text, action.content)

    structure = structure_bonus(action, positive_score, phase)
    irrelevant = irrelevant_penalty(action, expected_action_type, positive_score, overlap, matched_keywords)
    hallucinated = hallucinated_fix_penalty(task, action, phase, positive_score, overlap, matched_keywords)

    penalties: list[str] = []
    if irrelevant < 0:
        penalties.append("irrelevant_or_wrong_mode")
    if hallucinated < 0:
        penalties.append("hallucinated_fix")

    EPS = 0.0001
    breakdown = ScoreBreakdown(
        bug_detected=max(EPS, positive_score) if phase == "identify_bug" else EPS,
        explanation=max(EPS, positive_score) if phase == "explain_issue" else EPS,
        fix=max(EPS, positive_score) if phase == "fix_code" else EPS,
        structure_bonus=max(EPS, structure),
        irrelevant_penalty=irrelevant if irrelevant != 0 else -EPS,
        hallucinated_fix_penalty=hallucinated if hallucinated != 0 else -EPS,
    )
    raw_total = positive_score + structure + irrelevant + hallucinated
    breakdown.total = clamp_strict_score(raw_total)

    rationale, feedback = build_feedback(phase, matched_keywords, missing_keywords, penalties)
    verdict = verdict_for_score(breakdown.total, phase)

    return RewardState(
        score=breakdown.total,
        verdict=verdict,
        breakdown=breakdown,
        matched_keywords=matched_keywords,
        missing_keywords=missing_keywords,
        partial_keywords=matched_keywords[:1] if verdict == "partial_match" else [],
        semantic_overlap=clamp_strict_score(overlap),
        rationale=rationale,
        feedback=feedback,
        phase=phase,
        expected_action_type=expected_action_type,
        action_type=action.type,
        step_index=step_index,
    )
