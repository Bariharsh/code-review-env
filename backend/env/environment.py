from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .grader import grade_action
from .models import (
    EXPECTED_ACTION_BY_PHASE,
    PHASE_SEQUENCE,
    CodeReviewObservation,
    CodeReviewTask,
    EnvironmentState,
    ReviewAction,
    RewardState,
    ScoreBreakdown,
    StepPhase,
    StepRecord,
)
from .tasks import get_task_by_id, load_tasks


PHASE_PROMPTS: dict[StepPhase, str] = {
    "identify_bug": "Step 1 of 3: identify the core bug or vulnerability in the code.",
    "explain_issue": "Step 2 of 3: explain why the issue matters, including its risk or behavioral impact.",
    "fix_code": "Step 3 of 3: submit the corrected code or patch the relevant snippet.",
}


def aggregate_breakdowns(rewards: Iterable[RewardState]) -> ScoreBreakdown:
    """Aggregate multiple step rewards into a single transparent score view."""

    breakdown = ScoreBreakdown()
    for reward in rewards:
        breakdown.bug_detected = round(breakdown.bug_detected + reward.breakdown.bug_detected, 3)
        breakdown.explanation = round(breakdown.explanation + reward.breakdown.explanation, 3)
        breakdown.fix = round(breakdown.fix + reward.breakdown.fix, 3)
        breakdown.structure_bonus = round(breakdown.structure_bonus + reward.breakdown.structure_bonus, 3)
        breakdown.irrelevant_penalty = round(
            breakdown.irrelevant_penalty + reward.breakdown.irrelevant_penalty,
            3,
        )
        breakdown.hallucinated_fix_penalty = round(
            breakdown.hallucinated_fix_penalty + reward.breakdown.hallucinated_fix_penalty,
            3,
        )
        breakdown.total = round(breakdown.total + reward.breakdown.total, 3)
    return breakdown


class CodeReviewEnvironment:
    """A multi-step code review environment with deterministic reward shaping."""

    def __init__(self, data_path: str | Path | None = None, max_steps: int = len(PHASE_SEQUENCE)) -> None:
        self.tasks = load_tasks(data_path)
        self.max_steps = max(1, min(max_steps, len(PHASE_SEQUENCE)))
        self._task_cursor = 0
        self._current_task: CodeReviewTask | None = None
        self._state = EnvironmentState(max_steps=self.max_steps)

    @property
    def current_task(self) -> CodeReviewTask | None:
        """Expose the current task in a read-only way."""

        return self._current_task

    def _phase_for_step(self, step_count: int) -> StepPhase:
        """Return the active phase for the current step count."""

        return PHASE_SEQUENCE[min(step_count, self.max_steps - 1)]

    def _build_prompt(self, task: CodeReviewTask, phase: StepPhase) -> str:
        """Create a task-specific prompt for the current phase."""

        expected_type = EXPECTED_ACTION_BY_PHASE[phase]
        guidance = {
            "identify_bug": "Name the primary bug, security issue, or faulty behavior directly.",
            "explain_issue": "Focus on why the issue is risky, incorrect, or costly in production.",
            "fix_code": "Provide a corrected version of the code, not just a prose description.",
        }[phase]
        return f"{PHASE_PROMPTS[phase]} {guidance} Expected action type: {expected_type}. Scenario: {task.title}."

    def _build_observation(self, task: CodeReviewTask, step_count: int) -> CodeReviewObservation:
        """Create the observation for the current step."""

        phase = self._phase_for_step(step_count)
        return CodeReviewObservation(
            task_id=task.task_id,
            difficulty=task.difficulty,
            title=task.title,
            code=task.code,
            prompt=self._build_prompt(task, phase),
            phase=phase,
            expected_action_type=EXPECTED_ACTION_BY_PHASE[phase],
            step_index=step_count,
            remaining_steps=max(self.max_steps - step_count, 0),
        )

    def _build_terminal_observation(self, task: CodeReviewTask, step_count: int) -> CodeReviewObservation:
        """Return a terminal observation after the last step."""

        final_phase = PHASE_SEQUENCE[self.max_steps - 1]
        return CodeReviewObservation(
            task_id=task.task_id,
            difficulty=task.difficulty,
            title=task.title,
            code=task.code,
            prompt="Episode complete. Review the score breakdown and reset to try again.",
            phase=final_phase,
            expected_action_type=EXPECTED_ACTION_BY_PHASE[final_phase],
            step_index=step_count,
            remaining_steps=0,
        )

    def reset(self, task_id: str | None = None) -> CodeReviewObservation:
        """Start a new episode and return the initial observation."""

        if task_id is not None:
            task = get_task_by_id(self.tasks, task_id)
        else:
            task = self.tasks[self._task_cursor % len(self.tasks)]
            self._task_cursor += 1

        observation = self._build_observation(task, 0)
        self._current_task = task
        self._state = EnvironmentState(
            task_id=task.task_id,
            step_count=0,
            max_steps=self.max_steps,
            done=False,
            cumulative_reward=0.001,
            observation=observation,
            last_reward=None,
            history=[],
        )
        return observation

    def replay(self, task_id: str, actions: Iterable[ReviewAction]) -> EnvironmentState:
        """Replay an action history to reconstruct state without server-side sessions."""

        self.reset(task_id=task_id)
        for action in actions:
            self.step(action)
        return self.state()

    def step(self, action: ReviewAction) -> tuple[CodeReviewObservation, float, bool, dict[str, Any]]:
        """Grade the current phase, advance the episode, and return a Gym-style tuple."""

        if self._current_task is None or self._state.observation is None:
            raise RuntimeError("Call reset() before step().")
        if self._state.done:
            raise RuntimeError("Episode is done. Call reset() before stepping again.")

        current_observation = self._state.observation
        reward_state = grade_action(
            self._current_task,
            action,
            current_observation.phase,
            self._state.step_count,
        )

        record = StepRecord(
            step_index=self._state.step_count,
            phase=current_observation.phase,
            prompt=current_observation.prompt,
            action=action,
            reward=reward_state,
        )

        next_step_count = self._state.step_count + 1
        done = next_step_count >= self.max_steps
        next_observation = (
            self._build_terminal_observation(self._current_task, next_step_count)
            if done
            else self._build_observation(self._current_task, next_step_count)
        )

        history = [*self._state.history, record]
        cumulative_reward = round(self._state.cumulative_reward + reward_state.score, 3)
        cumulative_reward = min(max(cumulative_reward, 0.001), 0.999)
        cumulative_breakdown = aggregate_breakdowns(item.reward for item in history)

        self._state = EnvironmentState(
            task_id=self._current_task.task_id,
            step_count=next_step_count,
            max_steps=self.max_steps,
            done=done,
            cumulative_reward=cumulative_reward,
            observation=next_observation,
            last_reward=reward_state,
            history=history,
        )

        info = {
            "task_id": self._current_task.task_id,
            "difficulty": self._current_task.difficulty,
            "category": self._current_task.category,
            "language": self._current_task.language,
            "score_details": reward_state.to_dict(),
            "step_evaluation": reward_state.to_dict(),
            "step_history": [item.to_dict() for item in history],
            "cumulative_breakdown": cumulative_breakdown.to_dict(),
            "expected_explanation": self._current_task.rubric.explanation,
            "reference_fix": self._current_task.rubric.reference_fix,
            "grading_backend": "deterministic_v2",
        }
        return next_observation, reward_state.score, done, info

    def state(self) -> EnvironmentState:
        """Return the current typed environment state."""

        return self._state

    def task_ids(self) -> list[str]:
        """Return all available task ids."""

        return [task.task_id for task in self.tasks]

    def close(self) -> None:
        """Release current task state."""

        self._current_task = None
