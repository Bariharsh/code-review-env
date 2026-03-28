from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from .grader import grade_review
from .models import CodeReviewObservation, EnvironmentState, ReviewAction
from .tasks import get_task_by_id, load_tasks


class CodeReviewEnvironment:
    """A simple one-turn review environment with optional multi-step support."""

    def __init__(self, data_path: str | Path | None = None, max_steps: int = 1) -> None:
        self.tasks = load_tasks(data_path)
        self.max_steps = max(1, max_steps)
        self._task_cursor = 0
        self._current_task = None
        self._state = EnvironmentState(max_steps=self.max_steps)

    def reset(self, task_id: str | None = None) -> CodeReviewObservation:
        """Start a new episode and return the initial observation."""

        if task_id is not None:
            task = get_task_by_id(self.tasks, task_id)
        else:
            task = self.tasks[self._task_cursor % len(self.tasks)]
            self._task_cursor += 1

        observation = CodeReviewObservation(
            task_id=task.task_id,
            difficulty=task.difficulty,
            title=task.title,
            code=task.code,
            step_index=0,
        )

        self._current_task = task
        self._state = EnvironmentState(
            task_id=task.task_id,
            step_count=0,
            max_steps=self.max_steps,
            done=False,
            observation=observation,
            last_reward=None,
        )
        return observation

    def step(self, action: ReviewAction) -> tuple[CodeReviewObservation, float, bool, dict[str, Any]]:
        """Grade the agent review and return a Gym-style step tuple."""

        if self._current_task is None or self._state.observation is None:
            raise RuntimeError("Call reset() before step().")
        if self._state.done:
            raise RuntimeError("Episode is done. Call reset() before stepping again.")

        reward_state = grade_review(self._current_task, action.review)
        next_step_count = self._state.step_count + 1
        done = next_step_count >= self.max_steps

        observation = replace(self._state.observation, step_index=next_step_count)
        self._state = EnvironmentState(
            task_id=self._current_task.task_id,
            step_count=next_step_count,
            max_steps=self.max_steps,
            done=done,
            observation=observation,
            last_reward=reward_state,
        )

        info = {
            "task_id": self._current_task.task_id,
            "difficulty": self._current_task.difficulty,
            "score_details": reward_state.to_dict(),
            "expected_explanation": self._current_task.expected_output.explanation,
        }
        return observation, reward_state.score, done, info

    def state(self) -> EnvironmentState:
        """Return the current typed environment state."""

        return self._state

    def task_ids(self) -> list[str]:
        return [task.task_id for task in self.tasks]

    def close(self) -> None:
        self._current_task = None
