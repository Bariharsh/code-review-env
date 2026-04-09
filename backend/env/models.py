from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


Difficulty = Literal["easy", "medium", "hard"]
Verdict = Literal["full_match", "partial_match", "wrong"]
ActionType = Literal["review", "fix"]
StepPhase = Literal["identify_bug", "explain_issue", "fix_code"]

PHASE_SEQUENCE: tuple[StepPhase, ...] = (
    "identify_bug",
    "explain_issue",
    "fix_code",
)

EXPECTED_ACTION_BY_PHASE: dict[StepPhase, ActionType] = {
    "identify_bug": "review",
    "explain_issue": "review",
    "fix_code": "fix",
}

STRICT_SCORE_MIN = 0.001
STRICT_SCORE_MAX = 0.999
STRICT_SCORE_FIELDS = {"score", "cumulative_reward", "semantic_overlap"}
STRICT_BREAKDOWN_SCORE_FIELDS = {"total"}
STRICT_BREAKDOWN_POSITIVE_FIELDS = {"bug_detected", "explanation", "fix", "structure_bonus"}
STRICT_BREAKDOWN_NEGATIVE_FIELDS = {"irrelevant_penalty", "hallucinated_fix_penalty"}
STRICT_BREAKDOWN_EPSILON = 0.0001


def clamp_strict_score(value: float | int) -> float:
    """Clamp a public-facing score into the validator-safe open interval."""

    numeric = float(value)
    return round(min(max(numeric, STRICT_SCORE_MIN), STRICT_SCORE_MAX), 3)


def sanitize_public_scores(value: Any, *, key: str | None = None, parent_key: str | None = None) -> Any:
    """Recursively clamp score-like fields in serialized payloads."""

    if isinstance(value, dict):
        return {
            child_key: sanitize_public_scores(child_value, key=child_key, parent_key=key)
            for child_key, child_value in value.items()
        }

    if isinstance(value, list):
        return [sanitize_public_scores(item, parent_key=key) for item in value]

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if key in STRICT_SCORE_FIELDS:
            return clamp_strict_score(value)
        if key in STRICT_BREAKDOWN_SCORE_FIELDS and parent_key in {"breakdown", "cumulative_breakdown"}:
            return clamp_strict_score(value)
        if key in STRICT_BREAKDOWN_POSITIVE_FIELDS and parent_key in {"breakdown", "cumulative_breakdown"}:
            numeric = float(value)
            if numeric <= 0:
                return STRICT_BREAKDOWN_EPSILON
            if numeric >= 1:
                return STRICT_SCORE_MAX
            return round(numeric, 4)
        if key in STRICT_BREAKDOWN_NEGATIVE_FIELDS and parent_key in {"breakdown", "cumulative_breakdown"}:
            numeric = float(value)
            if numeric >= 0:
                return -STRICT_BREAKDOWN_EPSILON
            return round(numeric, 4)

    return value


def _string_list(value: Any, field_name: str) -> list[str]:
    """Validate and normalize a list of keyword strings."""

    if not isinstance(value, list):
        raise ValueError(f"`{field_name}` must be an array of strings.")

    normalized: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(f"`{field_name}[{index}]` must be a string.")
        text = item.strip()
        if text:
            normalized.append(text)
    return normalized


def _string_field(data: dict[str, Any], key: str, field_name: str, default: str = "") -> str:
    """Read a string field without silently coercing malformed task data."""

    if key not in data:
        return default

    value = data[key]
    if not isinstance(value, str):
        raise ValueError(f"`{field_name}` must be a string.")
    return value


def _string_list_field(data: dict[str, Any], key: str, field_name: str) -> list[str]:
    """Read a keyword list field when present."""

    if key not in data:
        return []
    return _string_list(data[key], field_name)


def _phase_keyword_field(data: dict[str, Any], base_field: str, aliases: tuple[str, ...]) -> list[str]:
    """Read one phase's keywords from a phase-keyword mapping."""

    for alias in aliases:
        if alias in data:
            return _string_list(data[alias], f"{base_field}.{alias}")
    return []


def _expected_output_keywords(expected_output: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    """Extract phase-aware keywords from the compatibility schema."""

    if "phase_keywords" in expected_output:
        phase_keywords = expected_output["phase_keywords"]
        if not isinstance(phase_keywords, dict):
            raise ValueError("`expected_output.phase_keywords` must be an object.")

        return (
            _phase_keyword_field(phase_keywords, "expected_output.phase_keywords", ("identify_bug", "bug")),
            _phase_keyword_field(phase_keywords, "expected_output.phase_keywords", ("explain_issue", "explanation")),
            _phase_keyword_field(phase_keywords, "expected_output.phase_keywords", ("fix_code", "fix")),
        )

    if "required_keyword_groups" in expected_output and "bug_keywords" not in expected_output and "fix_keywords" not in expected_output:
        raise ValueError(
            "`expected_output.required_keyword_groups` is ambiguous for multi-step grading. "
            "Provide phase-specific `bug_keywords`, `explanation_keywords`, and `fix_keywords` instead."
        )

    bug_keywords = _string_list_field(expected_output, "bug_keywords", "expected_output.bug_keywords")
    explanation_keywords = _string_list_field(
        expected_output,
        "explanation_keywords",
        "expected_output.explanation_keywords",
    )
    if not explanation_keywords and "partial_keywords" in expected_output:
        explanation_keywords = _string_list_field(
            expected_output,
            "partial_keywords",
            "expected_output.partial_keywords",
        )
    fix_keywords = _string_list_field(expected_output, "fix_keywords", "expected_output.fix_keywords")

    if bug_keywords or explanation_keywords or fix_keywords:
        return bug_keywords, explanation_keywords, fix_keywords

    return [], [], []


@dataclass(slots=True)
class ReviewAction:
    """An agent action submitted to the environment."""

    type: ActionType
    content: str

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, field_prefix: str = "action") -> "ReviewAction":
        if "type" not in data:
            raise ValueError(f"`{field_prefix}.type` is required.")

        raw_type = data["type"]
        if not isinstance(raw_type, str):
            raise ValueError(f"`{field_prefix}.type` must be a string.")

        action_type = raw_type.strip().lower()
        if action_type not in {"review", "fix"}:
            raise ValueError(f"`{field_prefix}.type` must be either 'review' or 'fix'.")

        content = data.get("content", "")
        if not isinstance(content, str):
            raise ValueError(f"`{field_prefix}.content` must be a string.")

        return cls(
            type=action_type,
            content=content,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ScoreBreakdown:
    """Weighted reward components for a single step."""

    bug_detected: float = 0.0
    explanation: float = 0.0
    fix: float = 0.0
    structure_bonus: float = 0.0
    irrelevant_penalty: float = 0.0
    hallucinated_fix_penalty: float = 0.0
    total: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return sanitize_public_scores(asdict(self), key="breakdown")


@dataclass(slots=True)
class CodeReviewObservation:
    """What the agent sees at the current step."""

    task_id: str
    difficulty: Difficulty
    title: str
    code: str
    prompt: str
    phase: StepPhase
    expected_action_type: ActionType
    step_index: int = 0
    remaining_steps: int = len(PHASE_SEQUENCE)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RewardState:
    """Detailed reward data returned after grading a step."""

    score: float
    verdict: Verdict
    breakdown: ScoreBreakdown = field(default_factory=ScoreBreakdown)
    matched_keywords: list[str] = field(default_factory=list)
    missing_keywords: list[str] = field(default_factory=list)
    partial_keywords: list[str] = field(default_factory=list)
    semantic_overlap: float = STRICT_SCORE_MIN
    rationale: str = ""
    feedback: str = ""
    phase: StepPhase = "identify_bug"
    expected_action_type: ActionType = "review"
    action_type: ActionType = "review"
    step_index: int = 0

    def to_dict(self) -> dict[str, Any]:
        return sanitize_public_scores(asdict(self))


@dataclass(slots=True)
class StepRecord:
    """Recorded interaction history for a single step."""

    step_index: int
    phase: StepPhase
    prompt: str
    action: ReviewAction
    reward: RewardState

    def to_dict(self) -> dict[str, Any]:
        return sanitize_public_scores(asdict(self))


@dataclass(slots=True)
class EnvironmentState:
    """Current environment state exposed through state()."""

    task_id: str | None = None
    step_count: int = 0
    max_steps: int = len(PHASE_SEQUENCE)
    done: bool = False
    cumulative_reward: float = STRICT_SCORE_MIN
    observation: CodeReviewObservation | None = None
    last_reward: RewardState | None = None
    history: list[StepRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return sanitize_public_scores(asdict(self))


@dataclass(slots=True)
class ReviewRubric:
    """Task-specific signals used by deterministic grading."""

    explanation: str
    bug_keywords: list[str] = field(default_factory=list)
    explanation_keywords: list[str] = field(default_factory=list)
    fix_keywords: list[str] = field(default_factory=list)
    reference_fix: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewRubric":
        if "expected_output" in data:
            expected_output = data["expected_output"]
            if not isinstance(expected_output, dict):
                raise ValueError("`expected_output` must be an object.")

            bug_keywords, explanation_keywords, fix_keywords = _expected_output_keywords(expected_output)
            return cls(
                explanation=_string_field(
                    expected_output,
                    "explanation",
                    "expected_output.explanation",
                    default=_string_field(
                        data,
                        "reference_explanation",
                        "reference_explanation",
                        default=_string_field(data, "explanation", "explanation"),
                    ),
                ),
                bug_keywords=bug_keywords,
                explanation_keywords=explanation_keywords,
                fix_keywords=fix_keywords,
                reference_fix=_string_field(
                    expected_output,
                    "reference_fix",
                    "expected_output.reference_fix",
                    default=_string_field(data, "reference_fix", "reference_fix"),
                ),
            )

        return cls(
            explanation=_string_field(
                data,
                "reference_explanation",
                "reference_explanation",
                default=_string_field(data, "explanation", "explanation"),
            ),
            bug_keywords=_string_list_field(data, "bug_keywords", "bug_keywords"),
            explanation_keywords=_string_list_field(data, "explanation_keywords", "explanation_keywords"),
            fix_keywords=_string_list_field(data, "fix_keywords", "fix_keywords"),
            reference_fix=_string_field(data, "reference_fix", "reference_fix"),
        )


@dataclass(slots=True)
class CodeReviewTask:
    """A single code review task loaded from JSON."""

    task_id: str
    difficulty: Difficulty
    title: str
    code: str
    rubric: ReviewRubric
    category: str = "correctness"
    language: str = "text"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodeReviewTask":
        return cls(
            task_id=str(data["task_id"]),
            difficulty=data["difficulty"],
            title=str(data["title"]),
            code=str(data["code"]),
            rubric=ReviewRubric.from_dict(data),
            category=str(data.get("category", "correctness")),
            language=str(data.get("language", "text")),
        )
