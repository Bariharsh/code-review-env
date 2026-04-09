from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.env.environment import CodeReviewEnvironment, aggregate_breakdowns
from backend.env.models import CodeReviewObservation, ReviewAction, StepRecord, clamp_strict_score

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from google import genai
except ImportError:
    genai = None


MOCK_BASELINE_ACTIONS: dict[str, dict[str, str]] = {
    "easy-even-check": {
        "identify_bug": "The parity check is reversed because `n % 2 == 1` identifies odd numbers rather than even numbers.",
        "explain_issue": "Even numbers produce `0` when divided by 2, so this function returns the wrong boolean result for every even input.",
        "fix_code": "def is_even(n: int) -> bool:\n    return n % 2 == 0\n",
    },
    "medium-inefficient-sorting": {
        "identify_bug": "This uses a bubble-sort style nested loop to rank users, creating an O(n^2) performance problem just to fetch the top three.",
        "explain_issue": "The double loop does unnecessary comparisons across the full list, so latency grows quickly as the dataset gets larger.",
        "fix_code": "def top_three(users: list[dict]) -> list[dict]:\n    return sorted(users, key=lambda user: user[\"score\"], reverse=True)[:3]\n",
    },
    "hard-sql-injection": {
        "identify_bug": "The query is vulnerable to SQL injection because it builds SQL with an f-string and untrusted username input.",
        "explain_issue": "An attacker can alter the WHERE clause by injecting SQL into `username`, which can expose or change unintended records.",
        "fix_code": "import sqlite3\n\n\ndef find_user(conn: sqlite3.Connection, username: str):\n    query = \"SELECT id, username, is_admin FROM users WHERE username = ?\"\n    return conn.execute(query, (username,)).fetchone()\n",
    },
    "hard-insecure-authentication": {
        "identify_bug": "This authentication flow compares plaintext passwords directly instead of verifying a secure password hash.",
        "explain_issue": "Plaintext password storage or comparison is dangerous because a database leak immediately exposes reusable credentials.",
        "fix_code": "import bcrypt\n\n\ndef authenticate(username: str, password: str, users: dict[str, dict[str, bytes]]) -> bool:\n    record = users.get(username)\n    if not record:\n        return False\n    return bcrypt.checkpw(password.encode(\"utf-8\"), record[\"password_hash\"])\n",
    },
    "medium-react-stale-closure": {
        "identify_bug": "The interval callback has a stale closure over `count`, so it keeps using the initial render's value.",
        "explain_issue": "Because the effect dependency array is empty, the callback repeatedly computes `count + 1` from the same captured state and the counter stalls.",
        "fix_code": "import { useState, useEffect } from 'react';\n\nfunction Timer() {\n  const [count, setCount] = useState(0);\n\n  useEffect(() => {\n    const id = setInterval(() => {\n      setCount((prev) => prev + 1);\n    }, 1000);\n    return () => clearInterval(id);\n  }, []);\n\n  return <div>{count}</div>;\n}\n",
    },
    "medium-listener-memory-leak": {
        "identify_bug": "The function keeps registering the same `message` listener inside `setInterval`, which leaks listeners over time.",
        "explain_issue": "Every second adds another callback, so memory usage grows and one socket message triggers the handler multiple times.",
        "fix_code": "function subscribe(socket, onMessage) {\n  socket.on(\"message\", onMessage);\n  return () => socket.off(\"message\", onMessage);\n}\n",
    },
    "hard-python-path-traversal": {
        "identify_bug": "This endpoint has a path traversal vulnerability because it joins untrusted `filename` input directly into the filesystem path.",
        "explain_issue": "Attackers can use `../` segments to escape the uploads directory and read arbitrary server files if the resolved path is never checked.",
        "fix_code": "from fastapi import FastAPI, HTTPException\nfrom pathlib import Path\n\napp = FastAPI()\nUPLOAD_ROOT = Path('/var/www/uploads').resolve()\n\n@app.get('/download')\ndef download_file(filename: str):\n    candidate = (UPLOAD_ROOT / filename).resolve()\n    if not candidate.is_relative_to(UPLOAD_ROOT):\n        raise HTTPException(status_code=400, detail='invalid filename')\n    return candidate.read_text()\n",
    },
    "medium-sql-n-plus-one": {
        "identify_bug": "This creates an N+1 query problem by loading authors first and then querying each author's books inside the list comprehension.",
        "explain_issue": "The number of database round trips grows with the number of authors, which makes the endpoint slower and more expensive at scale.",
        "fix_code": "from myapp.models import Author\n\ndef get_all_books():\n    authors = Author.objects.prefetch_related('book_set')\n    return [author.book_set.all() for author in authors]\n",
    },
    "easy-html-button-type": {
        "identify_bug": "The cancel button is missing an explicit type, so the browser treats it as a submit button by default.",
        "explain_issue": "Inside a form, the default button behavior is submit, which means clicking Cancel can trigger the login form unexpectedly.",
        "fix_code": "<form onsubmit=\"login()\">\n  <input type=\"text\" name=\"user\">\n  <button type=\"button\" class=\"action-btn\" onclick=\"cancel()\">Cancel</button>\n  <button type=\"submit\" class=\"primary-btn\">Login</button>\n</form>\n",
    },
    "hard-react-infinite-loop": {
        "identify_bug": "The component creates an infinite render loop because the effect depends on `width` and also updates `width` on every run.",
        "explain_issue": "Each render schedules another `setWidth`, and `Math.random()` guarantees a fresh value, so the effect never stabilizes.",
        "fix_code": "import { useState, useLayoutEffect } from 'react';\n\nfunction Element() {\n  const [width, setWidth] = useState(0);\n\n  useLayoutEffect(() => {\n      setWidth(100);\n  }, []);\n\n  return <div style={{ width: width }}>Content</div>;\n}\n",
    },
    "hard-go-loop-pointer": {
        "identify_bug": "The code appends `&u`, which is the address of the loop variable rather than the address of each slice element.",
        "explain_issue": "Because the loop variable is reused, every stored pointer ends up referencing the same memory slot and prints the last user repeatedly.",
        "fix_code": "package main\n\nimport \"fmt\"\n\ntype User struct { Name string }\n\nfunc main() {\n\tusers := []User{{Name: \"Alice\"}, {Name: \"Bob\"}}\n\tvar ptrs []*User\n\n\tfor i := range users {\n\t\tptrs = append(ptrs, &users[i])\n\t}\n\n\tfor _, p := range ptrs {\n\t\tfmt.Println(p.Name)\n\t}\n}\n",
    },
}


def build_prompt(observation: CodeReviewObservation, history: list[StepRecord]) -> str:
    """Build a phase-aware prompt for an external model."""

    prior_steps = "\n".join(
        f"- Phase: {record.phase}\n  Action type: {record.action.type}\n  Content: {record.action.content}\n  Reward: {record.reward.score}"
        for record in history
    )
    history_block = prior_steps if prior_steps else "- None yet."

    response_style = (
        "Return corrected code only."
        if observation.expected_action_type == "fix"
        else "Return 1-3 concise sentences focused only on this step."
    )

    return (
        "You are a senior code reviewer acting inside a 3-step training environment.\n"
        f"Current phase: {observation.phase}\n"
        f"Instruction: {observation.prompt}\n"
        f"Expected action type: {observation.expected_action_type}\n"
        f"Code:\n{observation.code}\n\n"
        f"Prior steps:\n{history_block}\n\n"
        f"{response_style}\n"
        "Do not mention the phase names in your answer."
    )


def extract_response_text(response: Any) -> str:
    """Extract text from an OpenAI Responses API object."""

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


def should_use_gemini() -> bool:
    """Check whether Gemini is configured."""

    return bool(genai and os.getenv("GEMINI_API_KEY"))


def should_use_openai() -> bool:
    """Check whether OpenAI is configured."""

    return bool(OpenAI and os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_MODEL"))


def gemini_action(observation: CodeReviewObservation, history: list[StepRecord]) -> str:
    """Generate the next step with Gemini."""

    if genai is None:
        raise RuntimeError("The google-genai package is not installed.")

    api_key = os.environ["GEMINI_API_KEY"]
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model_name,
        contents=build_prompt(observation, history),
    )
    return response.text.strip()


def openai_action(observation: CodeReviewObservation, history: list[StepRecord]) -> str:
    """Generate the next step with OpenAI."""

    if OpenAI is None:
        raise RuntimeError("The openai package is not installed.")

    model = os.environ["OPENAI_MODEL"]
    client = OpenAI()
    response = client.responses.create(model=model, input=build_prompt(observation, history))
    return extract_response_text(response)


def mock_action(observation: CodeReviewObservation) -> str:
    """Return a deterministic baseline action without any external API."""

    task_actions = MOCK_BASELINE_ACTIONS.get(observation.task_id, {})
    if observation.phase in task_actions:
        return task_actions[observation.phase]

    if observation.expected_action_type == "fix":
        return observation.code
    return "There is a correctness or security issue here that needs a targeted fix."


def summarize_review_steps(history: list[StepRecord], max_words: int = 32) -> str:
    """Return a short combined review summary for the UI."""

    review_parts = [
        " ".join(record.action.content.split())
        for record in history
        if record.action.type == "review" and record.action.content.strip()
    ]
    if not review_parts:
        return ""

    summary = " ".join(review_parts)
    words = summary.split()
    if len(words) <= max_words:
        return summary
    return " ".join(words[:max_words]).rstrip(",.;:") + "..."


def generate_action(observation: CodeReviewObservation, history: list[StepRecord]) -> tuple[ReviewAction, str]:
    """Generate the next action for the current phase."""

    if should_use_gemini():
        content = gemini_action(observation, history)
        backend = "gemini"
    elif should_use_openai():
        content = openai_action(observation, history)
        backend = "openai"
    else:
        content = mock_action(observation)
        backend = "mock"

    return ReviewAction(type=observation.expected_action_type, content=content), backend


def run_episode_data(
    task_id: str,
    data_path: str | Path | None = None,
    max_steps: int = 3,
) -> dict[str, Any]:
    """Run the full baseline loop and return structured episode data."""

    env = CodeReviewEnvironment(data_path=data_path, max_steps=max_steps)
    observation = env.reset(task_id=task_id)
    backend = "mock"
    submissions: list[dict[str, Any]] = []
    final_info: dict[str, Any] = {}
    done = False

    while not done:
        action, backend = generate_action(observation, env.state().history)
        observation, reward, done, info = env.step(action)
        submissions.append(
            {
                "action": action.to_dict(),
                "reward": clamp_strict_score(reward),
                "done": done,
                "step_evaluation": info["step_evaluation"],
            }
        )
        final_info = info

    state = env.state()
    cumulative_breakdown = aggregate_breakdowns(record.reward for record in state.history)
    
    if not submissions:
        submissions.append({
            "action": {"type": "review", "content": "Failed to generate action"},
            "reward": clamp_strict_score(0.0),
            "done": True,
            "step_evaluation": {}
        })

    final_action = submissions[-1]["action"] if submissions else {"type": "review", "content": ""}

    return {
        "backend": backend,
        "submitted_action": final_action,
        "submitted_review": summarize_review_steps(state.history),
        "submitted_fixed_code": next(
            (record.action.content for record in reversed(state.history) if record.action.type == "fix"),
            "",
        ),
        "observation": state.observation.to_dict() if state.observation else None,
        "reward": clamp_strict_score(state.cumulative_reward),
        "done": state.done,
        "info": {
            **final_info,
            "step_history": [record.to_dict() for record in state.history],
            "cumulative_breakdown": cumulative_breakdown.to_dict(),
        },
        "state": state.to_dict(),
        "submissions": submissions,
    }


def run_episode(env: CodeReviewEnvironment, task_id: str) -> None:
    """Run one baseline episode and print a detailed transcript."""

    observation = env.reset(task_id=task_id)
    backend = "mock"

    print(f"Task: {observation.task_id} ({observation.difficulty})")
    while not env.state().done:
        action, backend = generate_action(observation, env.state().history)
        observation, reward, done, info = env.step(action)
        print(f"Phase: {info['step_evaluation']['phase']}")
        print(f"Action type: {action.type}")
        print("Submitted content:")
        print(action.content)
        print(f"Reward: {reward:.3f}")
        print(f"Verdict: {info['step_evaluation']['verdict']}")
        print(f"Breakdown: {info['step_evaluation']['breakdown']}")
        print("-" * 60)
        if done:
            break

    summary = aggregate_breakdowns(record.reward for record in env.state().history)
    print(f"Backend: {backend}")
    print(f"Cumulative reward: {env.state().cumulative_reward:.3f}")
    print(f"Cumulative breakdown: {summary.to_dict()}")
    print("=" * 60)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the baseline runner."""

    parser = argparse.ArgumentParser(description="Run the multi-step baseline code review agent.")
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
        default=3,
        help="Maximum steps per episode. Defaults to the full 3-step workflow.",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""

    args = parse_args()
    env = CodeReviewEnvironment(data_path=args.data_path, max_steps=args.max_steps)

    if args.task_id:
        run_episode(env, args.task_id)
        return

    for task_id in env.task_ids():
        run_episode(env, task_id)


if __name__ == "__main__":
    main()
