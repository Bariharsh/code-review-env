from __future__ import annotations

import json
from pathlib import Path

from .models import CodeReviewTask


DEFAULT_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "samples.json"


def validate_task(task: CodeReviewTask) -> None:
    """Validate that a loaded task is rich enough for the upgraded grader."""

    if not task.code.strip():
        raise ValueError(f"Task {task.task_id} must include code.")
    if not task.rubric.explanation.strip():
        raise ValueError(f"Task {task.task_id} must include a reference explanation.")
    if not task.rubric.bug_keywords:
        raise ValueError(f"Task {task.task_id} must include bug_keywords.")
    if not task.rubric.explanation_keywords:
        raise ValueError(f"Task {task.task_id} must include explanation_keywords.")
    if not task.rubric.fix_keywords:
        raise ValueError(f"Task {task.task_id} must include fix_keywords.")


def load_tasks(data_path: str | Path | None = None) -> list[CodeReviewTask]:
    """Load review tasks from disk and validate the upgraded schema."""

    resolved_path = Path(data_path) if data_path is not None else DEFAULT_DATA_PATH
    with resolved_path.open("r", encoding="utf-8") as handle:
        raw_tasks = json.load(handle)

    tasks = [CodeReviewTask.from_dict(item) for item in raw_tasks]
    if not tasks:
        raise ValueError("At least one task is required.")

    task_ids = [task.task_id for task in tasks]
    if len(task_ids) != len(set(task_ids)):
        raise ValueError("Task ids must be unique.")

    for task in tasks:
        validate_task(task)

    return tasks


def get_task_by_id(tasks: list[CodeReviewTask], task_id: str) -> CodeReviewTask:
    """Look up a task by id."""

    for task in tasks:
        if task.task_id == task_id:
            return task
    raise KeyError(f"Unknown task_id: {task_id}")
