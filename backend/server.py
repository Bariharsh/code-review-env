from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.baseline.run_agent import run_episode_data
from backend.custom_review import review_custom_code
from backend.env.ai_grader import ai_second_opinion
from backend.env.environment import CodeReviewEnvironment
from backend.env.models import ReviewAction
from backend.env.tasks import load_tasks


BACKEND_ROOT = Path(__file__).resolve().parent
DATA_PATH = BACKEND_ROOT / "data" / "samples.json"
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
DIST_ROOT = FRONTEND_ROOT / "dist"
CORS_ALLOW_ORIGIN = "*"
CORS_ALLOW_METHODS = "GET, POST, OPTIONS"
CORS_ALLOW_HEADERS = "Content-Type"


def build_environment() -> CodeReviewEnvironment:
    """Create a fresh environment instance."""

    return CodeReviewEnvironment(data_path=DATA_PATH)


def list_task_summaries() -> list[dict[str, str]]:
    """Return the metadata needed by the frontend task list."""

    tasks = load_tasks(DATA_PATH)
    return [
        {
            "task_id": task.task_id,
            "difficulty": task.difficulty,
            "title": task.title,
            "category": task.category,
            "language": task.language,
        }
        for task in tasks
    ]


def task_metadata(task_id: str) -> dict[str, str]:
    """Return summary metadata for one task."""

    task = next(task for task in load_tasks(DATA_PATH) if task.task_id == task_id)
    return {
        "task_id": task.task_id,
        "difficulty": task.difficulty,
        "title": task.title,
        "category": task.category,
        "language": task.language,
    }


def reset_task(task_id: str) -> dict[str, Any]:
    """Reset the environment for a task."""

    env = build_environment()
    observation = env.reset(task_id=task_id)
    return {
        "task": task_metadata(task_id),
        "observation": observation.to_dict(),
        "state": env.state().to_dict(),
    }


def parse_history(payload: dict[str, Any]) -> list[ReviewAction]:
    """Parse a step history from the request payload."""

    raw_history = payload.get("history", [])
    if not isinstance(raw_history, list):
        raise ValueError("`history` must be an array.")

    actions: list[ReviewAction] = []
    for index, item in enumerate(raw_history):
        if not isinstance(item, dict):
            raise ValueError(f"`history[{index}]` must be an object.")
        action_payload = item.get("action", item)
        if not isinstance(action_payload, dict):
            raise ValueError(f"`history[{index}].action` must be an object.")
        action = ReviewAction.from_dict(action_payload, field_prefix=f"history[{index}].action")
        if not action.content.strip():
            raise ValueError(f"`history[{index}]` is missing content.")
        actions.append(action)
    return actions


def replay_history(env: CodeReviewEnvironment, task_id: str, history: list[ReviewAction]) -> None:
    """Replay prior actions to recover the current multi-step state."""

    env.reset(task_id=task_id)
    for action in history:
        env.step(action)


def grade_step(task_id: str, action: ReviewAction, history: list[ReviewAction]) -> dict[str, Any]:
    """Grade one step after replaying the submitted history."""

    env = build_environment()
    replay_history(env, task_id, history)
    current_observation = env.state().observation
    if current_observation is None:
        raise RuntimeError("Environment did not return an observation.")
    if env.state().done:
        raise ValueError("Episode already completed for this history.")

    next_observation, reward, done, info = env.step(action)
    return {
        "task": task_metadata(task_id),
        "submitted_action": action.to_dict(),
        "submitted_review": action.content if action.type == "review" else "",
        "submitted_fixed_code": action.content if action.type == "fix" else "",
        "current_observation": current_observation.to_dict(),
        "observation": next_observation.to_dict(),
        "reward": reward,
        "done": done,
        "info": info,
        "state": env.state().to_dict(),
    }


def grade_task(task_id: str, review: str, history: list[ReviewAction]) -> dict[str, Any]:
    """Compatibility wrapper for review-mode submissions."""

    return grade_step(task_id, ReviewAction(type="review", content=review), history)


def grade_fix_task(task_id: str, fixed_code: str, history: list[ReviewAction]) -> dict[str, Any]:
    """Compatibility wrapper for fix-mode submissions."""

    return grade_step(task_id, ReviewAction(type="fix", content=fixed_code), history)


def run_baseline(task_id: str) -> dict[str, Any]:
    """Run the multi-step baseline agent on one task."""

    result = run_episode_data(task_id=task_id, data_path=DATA_PATH, max_steps=3)
    result["task"] = task_metadata(task_id)
    return result


def get_second_opinion(task_id: str, review: str) -> dict[str, Any]:
    """Get an optional AI critique of the user's reasoning."""

    env = build_environment()
    env.reset(task_id=task_id)
    if env.current_task is None:
        raise RuntimeError("Task not loaded.")
    critique = ai_second_opinion(env.current_task, review)
    return {"second_opinion": critique}


class CodeReviewSiteHandler(BaseHTTPRequestHandler):
    """Serve the frontend and a small JSON API."""

    server_version = "CodeReviewEnvHTTP/0.2"

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path in {"/", "/index.html"}:
            self.serve_frontend_index()
            return

        if path == "/api/health":
            self.send_json({"status": "ok"})
            return

        if path == "/api/tasks":
            self.send_json({"tasks": list_task_summaries()})
            return

        if path.startswith("/api/tasks/"):
            task_id = unquote(path.removeprefix("/api/tasks/"))
            try:
                self.send_json(reset_task(task_id))
            except (KeyError, StopIteration):
                self.send_error_json(HTTPStatus.NOT_FOUND, "Unknown task id.")
            return

        if self.try_serve_frontend_asset(path):
            return

        if self.try_serve_frontend_route(path):
            return

        self.send_error_json(HTTPStatus.NOT_FOUND, "Not found.")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            payload = self.read_json()
        except ValueError as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return

        if path == "/api/step":
            self.handle_step(payload)
            return

        if path == "/api/review":
            self.handle_review(payload)
            return

        if path == "/api/grade-fix":
            self.handle_fix(payload)
            return

        if path == "/api/baseline-review":
            self.handle_baseline(payload)
            return

        if path == "/api/second-opinion":
            self.handle_second_opinion(payload)
            return

        if path == "/api/custom-review":
            self.handle_custom_review(payload)
            return

        self.send_error_json(HTTPStatus.NOT_FOUND, "Not found.")

    def handle_step(self, payload: dict[str, Any]) -> None:
        """Handle a generic multi-step environment action."""

        task_id = str(payload.get("task_id", "")).strip()
        action_payload = payload.get("action")
        if not task_id:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "`task_id` is required.")
            return
        if not isinstance(action_payload, dict):
            self.send_error_json(HTTPStatus.BAD_REQUEST, "`action` is required.")
            return

        try:
            history = parse_history(payload)
            action = ReviewAction.from_dict(action_payload, field_prefix="action")
            if not action.content.strip():
                raise ValueError("`action.content` is required.")
            self.send_json(grade_step(task_id, action, history))
        except (KeyError, StopIteration):
            self.send_error_json(HTTPStatus.NOT_FOUND, "Unknown task id.")
        except ValueError as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except RuntimeError as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

    def handle_review(self, payload: dict[str, Any]) -> None:
        """Handle a review-phase submission."""

        task_id = str(payload.get("task_id", "")).strip()
        review = str(payload.get("review", "")).strip()
        if not task_id:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "`task_id` is required.")
            return
        if not review:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "`review` is required.")
            return

        try:
            history = parse_history(payload)
            self.send_json(grade_task(task_id, review, history))
        except (KeyError, StopIteration):
            self.send_error_json(HTTPStatus.NOT_FOUND, "Unknown task id.")
        except ValueError as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

    def handle_fix(self, payload: dict[str, Any]) -> None:
        """Handle a fix-phase submission."""

        task_id = str(payload.get("task_id", "")).strip()
        fixed_code = str(payload.get("fixed_code", "")).strip()
        if not task_id:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "`task_id` is required.")
            return
        if not fixed_code:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "`fixed_code` is required.")
            return

        try:
            history = parse_history(payload)
            self.send_json(grade_fix_task(task_id, fixed_code, history))
        except (KeyError, StopIteration):
            self.send_error_json(HTTPStatus.NOT_FOUND, "Unknown task id.")
        except ValueError as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

    def handle_baseline(self, payload: dict[str, Any]) -> None:
        """Run the full baseline flow for one task."""

        task_id = str(payload.get("task_id", "")).strip()
        if not task_id:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "`task_id` is required.")
            return

        try:
            self.send_json(run_baseline(task_id))
        except (KeyError, StopIteration):
            self.send_error_json(HTTPStatus.NOT_FOUND, "Unknown task id.")
        except ValueError as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            print(f"[ERROR] baseline-review failed: {exc!r}")
            self.send_error_json(HTTPStatus.BAD_GATEWAY, "AI review failed.")

    def handle_second_opinion(self, payload: dict[str, Any]) -> None:
        """Request an AI auditor critique."""

        task_id = str(payload.get("task_id", "")).strip()
        review = str(payload.get("review", "")).strip()
        if not task_id or not review:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "task_id and review are required.")
            return

        try:
            self.send_json(get_second_opinion(task_id, review))
        except (KeyError, StopIteration):
            self.send_error_json(HTTPStatus.NOT_FOUND, "Unknown task id.")
        except ValueError as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            print(f"[ERROR] second-opinion failed: {exc!r}")
            self.send_error_json(HTTPStatus.BAD_GATEWAY, "Second opinion unavailable.")

    def handle_custom_review(self, payload: dict[str, Any]) -> None:
        """Review a user-submitted code snippet with the AI reviewer."""

        code = str(payload.get("code", "")).rstrip()
        title = str(payload.get("title", "")).strip()
        language = str(payload.get("language", "")).strip()
        focus = str(payload.get("focus", "")).strip()

        if not code.strip():
            self.send_error_json(HTTPStatus.BAD_REQUEST, "`code` is required.")
            return

        try:
            self.send_json(review_custom_code(code, title=title, language=language, focus=focus))
        except ValueError as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            print(f"[ERROR] custom-review failed: {exc!r}")
            self.send_error_json(HTTPStatus.BAD_GATEWAY, "Custom review unavailable.")

    def serve_file(self, path: Path) -> None:
        """Serve a static asset."""

        if not path.exists() or not path.is_file():
            self.send_error_json(HTTPStatus.NOT_FOUND, "File not found.")
            return

        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_cors_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def serve_frontend_index(self) -> None:
        """Serve the built frontend."""

        index_path = DIST_ROOT / "index.html"
        if not index_path.exists():
            self.send_missing_frontend_message()
            return
        self.serve_file(index_path)

    def try_serve_frontend_asset(self, request_path: str) -> bool:
        """Serve a frontend asset if it exists."""

        if not DIST_ROOT.exists():
            return False

        relative_path = request_path.removeprefix("/")
        if not relative_path:
            return False

        file_path = (DIST_ROOT / relative_path).resolve()
        if not file_path.is_relative_to(DIST_ROOT.resolve()):
            self.send_error_json(HTTPStatus.FORBIDDEN, "Forbidden path.")
            return True

        if file_path.exists() and file_path.is_file():
            self.serve_file(file_path)
            return True

        return False

    def try_serve_frontend_route(self, request_path: str) -> bool:
        """Serve a built Astro route like /reviewer via its index.html file."""

        if not DIST_ROOT.exists():
            return False

        relative_path = request_path.strip("/")
        if not relative_path:
            return False

        candidates = [
            (DIST_ROOT / relative_path / "index.html").resolve(),
            (DIST_ROOT / f"{relative_path}.html").resolve(),
        ]
        dist_root = DIST_ROOT.resolve()

        for candidate in candidates:
            if not candidate.is_relative_to(dist_root):
                self.send_error_json(HTTPStatus.FORBIDDEN, "Forbidden path.")
                return True
            if candidate.exists() and candidate.is_file():
                self.serve_file(candidate)
                return True

        return False

    def send_missing_frontend_message(self) -> None:
        """Return a helpful message when the built frontend is absent."""

        message = (
            "<!doctype html><html><body style=\"font-family: sans-serif; padding: 2rem;\">"
            "<h1>Frontend build not found</h1>"
            "<p>Run <code>npm install</code> and <code>npm run build</code> inside "
            "<code>frontend</code>, then refresh this page.</p>"
            "</body></html>"
        ).encode("utf-8")
        self.send_response(HTTPStatus.SERVICE_UNAVAILABLE)
        self.send_cors_headers()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(message)))
        self.end_headers()
        self.wfile.write(message)

    def read_json(self) -> dict[str, Any]:
        """Read a JSON request body."""

        content_length = self.headers.get("Content-Length")
        if content_length is None:
            raise ValueError("Missing Content-Length header.")

        try:
            length = int(content_length)
        except ValueError as exc:
            raise ValueError("Invalid Content-Length header.") from exc

        raw_body = self.rfile.read(length)
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Request body must be valid JSON.") from exc

        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object.")
        return payload

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        """Write a JSON response."""

        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_cors_headers(self) -> None:
        """Allow browser clients on another origin to call the API."""

        self.send_header("Access-Control-Allow-Origin", CORS_ALLOW_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", CORS_ALLOW_METHODS)
        self.send_header("Access-Control-Allow-Headers", CORS_ALLOW_HEADERS)

    def send_error_json(self, status: HTTPStatus, message: str) -> None:
        """Write a JSON error response."""

        self.send_json({"error": message}, status=status)

    def log_message(self, message_format: str, *args: Any) -> None:
        """Keep server logs compact."""

        print(f"[web] {self.address_string()} - {message_format % args}")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the HTTP server."""

    parser = argparse.ArgumentParser(description="Run the Code Review Environment website.")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on.")
    return parser.parse_args()


def main() -> None:
    """Server entrypoint."""

    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), CodeReviewSiteHandler)
    print(f"Serving Code Review Environment at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
