from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.env.environment import CodeReviewEnvironment
from backend.env.models import CodeReviewObservation, ReviewAction

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None


def build_prompt(observation: CodeReviewObservation) -> str:
    return (
        f"{observation.prompt}\n\n"
        f"Task: {observation.title}\n"
        f"Difficulty: {observation.difficulty}\n\n"
        "Code:\n"
        f"{observation.code}\n\n"
        "Explain the bug or risk, and suggest a fix."
    )


def extract_response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", "")
    if output_text:
        return output_text.strip()

    parts: list[str] = []
    for item in getattr(response, "output", []):
        for content in getattr(item, "content", []):
            text_value = getattr(content, "text", None)
            if text_value:
                parts.append(str(text_value))
    return "\n".join(parts).strip()


def mock_review(observation: CodeReviewObservation) -> str:
    code = observation.code

    if "n % 2 == 1" in code:
        return (
            "The function is incorrect for even checks: `n % 2 == 1` identifies odd numbers, "
            "so the condition is reversed. It should compare the modulo result to 0 instead."
        )

    if "ranked = sorted(scores)" in code and "return ranked[:3]" in code:
        return (
            "This logic returns the lowest scores, not the top scores, because the list is sorted "
            "in ascending order and the first three items are returned. Sort in descending order "
            "or take the last three values."
        )

    if "SELECT id, username, is_admin FROM users" in code and "{username}" in code:
        return (
            "This code is vulnerable to SQL injection because user input is interpolated directly "
            "into the query with an f-string. Use a parameterized query with placeholders and pass "
            "the username as a bound parameter."
        )

    return (
        "There may be a correctness or security issue here. Review the control flow, data handling, "
        "and any direct use of user input."
    )


def should_use_openai() -> bool:
    return bool(OpenAI and os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_MODEL"))


def openai_review(observation: CodeReviewObservation) -> str:
    if OpenAI is None:
        raise RuntimeError("The openai package is not installed.")

    model = os.environ["OPENAI_MODEL"]
    client = OpenAI()
    response = client.responses.create(model=model, input=build_prompt(observation))
    return extract_response_text(response)


def generate_review(observation: CodeReviewObservation) -> tuple[str, str]:
    if should_use_openai():
        return openai_review(observation), "openai"
    return mock_review(observation), "mock"


def run_episode(env: CodeReviewEnvironment, task_id: str) -> None:
    observation = env.reset(task_id=task_id)
    review_text, backend = generate_review(observation)
    _, reward, done, info = env.step(ReviewAction(review=review_text))

    print(f"Task: {observation.task_id} ({observation.difficulty})")
    print(f"Backend: {backend}")
    print("AI output:")
    print(review_text)
    print(f"Reward score: {reward:.1f}")
    print(f"Done: {done}")
    print(f"Verdict: {info['score_details']['verdict']}")
    print("-" * 60)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the baseline code review agent.")
    parser.add_argument(
        "--task-id",
        help="Run a single task by id. If omitted, all tasks run sequentially.",
    )
    parser.add_argument(
        "--data-path",
        help="Optional path to a custom samples.json file.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=1,
        help="Optional max steps for the environment. Default is 1.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env = CodeReviewEnvironment(data_path=args.data_path, max_steps=args.max_steps)

    if args.task_id:
        run_episode(env, args.task_id)
        return

    for task_id in env.task_ids():
        run_episode(env, task_id)


if __name__ == "__main__":
    main()
