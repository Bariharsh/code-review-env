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


@dataclass(slots=True)
class ReviewAction:
    """An agent action submitted to the environment."""

    type: ActionType
    content: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewAction":
        action_type = str(data.get("type", "review")).strip().lower() or "review"
        if action_type not in {"review", "fix"}:
            action_type = "review"
        return cls(
            type=action_type,
            content=str(data.get("content", "")),
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
        return asdict(self)


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
    semantic_overlap: float = 0.0
    rationale: str = ""
    feedback: str = ""
    phase: StepPhase = "identify_bug"
    expected_action_type: ActionType = "review"
    action_type: ActionType = "review"
    step_index: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StepRecord:
    """Recorded interaction history for a single step."""

    step_index: int
    phase: StepPhase
    prompt: str
    action: ReviewAction
    reward: RewardState

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EnvironmentState:
    """Current environment state exposed through state()."""

    task_id: str | None = None
    step_count: int = 0
    max_steps: int = len(PHASE_SEQUENCE)
    done: bool = False
    cumulative_reward: float = 0.0
    observation: CodeReviewObservation | None = None
    last_reward: RewardState | None = None
    history: list[StepRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
            required_groups = [
                keyword
                for group in expected_output.get("required_keyword_groups", [])
                for keyword in group
            ]
            partial_keywords = [str(keyword) for keyword in expected_output.get("partial_keywords", [])]
            return cls(
                explanation=str(expected_output.get("explanation", "")),
                bug_keywords=required_groups[: max(1, len(required_groups) // 2)],
                explanation_keywords=partial_keywords,
                fix_keywords=required_groups[max(1, len(required_groups) // 2) :],
                reference_fix=str(expected_output.get("reference_fix", "")),
            )

        return cls(
            explanation=str(data.get("reference_explanation", data.get("explanation", ""))),
            bug_keywords=[str(keyword) for keyword in data.get("bug_keywords", [])],
            explanation_keywords=[str(keyword) for keyword in data.get("explanation_keywords", [])],
            fix_keywords=[str(keyword) for keyword in data.get("fix_keywords", [])],
            reference_fix=str(data.get("reference_fix", "")),
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
