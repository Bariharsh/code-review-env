from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


Difficulty = Literal["easy", "medium", "hard"]
Verdict = Literal["full_match", "partial_match", "wrong"]


@dataclass(slots=True)
class ReviewAction:
    """Agent action: a free-form code review."""

    review: str


@dataclass(slots=True)
class CodeReviewObservation:
    """What the agent sees at each step."""

    task_id: str
    difficulty: Difficulty
    title: str
    code: str
    prompt: str = "Review this code and find issues."
    step_index: int = 0


@dataclass(slots=True)
class RewardState:
    """Reward details returned after grading a review."""

    score: float
    verdict: Verdict
    matched_keywords: list[str] = field(default_factory=list)
    missing_keywords: list[str] = field(default_factory=list)
    partial_keywords: list[str] = field(default_factory=list)
    semantic_overlap: float = 0.0
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EnvironmentState:
    """Current environment state exposed through state()."""

    task_id: str | None = None
    step_count: int = 0
    max_steps: int = 1
    done: bool = False
    observation: CodeReviewObservation | None = None
    last_reward: RewardState | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExpectedOutput:
    """Task-specific grading expectations."""

    explanation: str
    required_keyword_groups: list[list[str]] = field(default_factory=list)
    partial_keywords: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExpectedOutput":
        return cls(
            explanation=str(data.get("explanation", "")),
            required_keyword_groups=[
                [str(keyword) for keyword in group]
                for group in data.get("required_keyword_groups", [])
            ],
            partial_keywords=[str(keyword) for keyword in data.get("partial_keywords", [])],
        )


@dataclass(slots=True)
class CodeReviewTask:
    """A single code review task loaded from JSON."""

    task_id: str
    difficulty: Difficulty
    title: str
    code: str
    expected_output: ExpectedOutput

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodeReviewTask":
        return cls(
            task_id=str(data["task_id"]),
            difficulty=data["difficulty"],
            title=str(data["title"]),
            code=str(data["code"]),
            expected_output=ExpectedOutput.from_dict(data["expected_output"]),
        )
