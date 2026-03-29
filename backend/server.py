from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from dataclasses import asdict
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

from backend.baseline.run_agent import generate_review
from backend.env.environment import CodeReviewEnvironment
from backend.env.models import ReviewAction
from backend.env.tasks import load_tasks


BACKEND_ROOT = Path(__file__).resolve().parent
DATA_PATH = BACKEND_ROOT / "data" / "samples.json"
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
DIST_ROOT = FRONTEND_ROOT / "dist"


def build_environment() -> CodeReviewEnvironment:
    return CodeReviewEnvironment(data_path=DATA_PATH)


def list_task_summaries() -> list[dict[str, str]]:
    tasks = load_tasks(DATA_PATH)
    return [
        {
            "task_id": task.task_id,
            "difficulty": task.difficulty,
            "title": task.title,
        }
        for task in tasks
    ]


def reset_task(task_id: str) -> dict[str, Any]:
    env = build_environment()
    observation = env.reset(task_id=task_id)
    return {
        "observation": asdict(observation),
        "state": env.state().to_dict(),
    }


def grade_task(task_id: str, review: str) -> dict[str, Any]:
    env = build_environment()
    observation = env.reset(task_id=task_id)
    next_observation, reward, done, info = env.step(ReviewAction(review=review))
    return {
        "submitted_review": review,
        "initial_observation": asdict(observation),
        "observation": asdict(next_observation),
        "reward": reward,
        "done": done,
        "info": info,
        "state": env.state().to_dict(),
    }


def run_baseline(task_id: str) -> dict[str, Any]:
    env = build_environment()
    observation = env.reset(task_id=task_id)
    review_text, backend = generate_review(observation)
    next_observation, reward, done, info = env.step(ReviewAction(review=review_text))
    return {
        "submitted_review": review_text,
        "backend": backend,
        "observation": asdict(next_observation),
        "reward": reward,
        "done": done,
        "info": info,
        "state": env.state().to_dict(),
    }


class CodeReviewSiteHandler(BaseHTTPRequestHandler):
    server_version = "CodeReviewEnvHTTP/0.1"

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
            except KeyError:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Unknown task id.")
            return

        if self.try_serve_frontend_asset(path):
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

        if path == "/api/review":
            task_id = str(payload.get("task_id", "")).strip()
            review = str(payload.get("review", "")).strip()
            if not task_id:
                self.send_error_json(HTTPStatus.BAD_REQUEST, "`task_id` is required.")
                return
            if not review:
                self.send_error_json(HTTPStatus.BAD_REQUEST, "`review` is required.")
                return
            try:
                self.send_json(grade_task(task_id, review))
            except KeyError:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Unknown task id.")
            return

        if path == "/api/baseline-review":
            task_id = str(payload.get("task_id", "")).strip()
            if not task_id:
                self.send_error_json(HTTPStatus.BAD_REQUEST, "`task_id` is required.")
                return
            try:
                self.send_json(run_baseline(task_id))
            except KeyError:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Unknown task id.")
            except Exception as exc:
                print(f"[ERROR] baseline-review failed: {exc}")
                self.send_error_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    f"AI review failed: {exc}",
                )
            return

        self.send_error_json(HTTPStatus.NOT_FOUND, "Not found.")

    def serve_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error_json(HTTPStatus.NOT_FOUND, "File not found.")
            return

        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def serve_frontend_index(self) -> None:
        index_path = DIST_ROOT / "index.html"
        if not index_path.exists():
            self.send_missing_frontend_message()
            return
        self.serve_file(index_path)

    def try_serve_frontend_asset(self, request_path: str) -> bool:
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

    def send_missing_frontend_message(self) -> None:
        message = (
            "<!doctype html><html><body style=\"font-family: sans-serif; padding: 2rem;\">"
            "<h1>Frontend build not found</h1>"
            "<p>Run <code>npm install</code> and <code>npm run build</code> inside "
            "<code>code-review-env/frontend</code>, then refresh this page.</p>"
            "</body></html>"
        ).encode("utf-8")
        self.send_response(HTTPStatus.SERVICE_UNAVAILABLE)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(message)))
        self.end_headers()
        self.wfile.write(message)

    def read_json(self) -> dict[str, Any]:
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
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_error_json(self, status: HTTPStatus, message: str) -> None:
        self.send_json({"error": message}, status=status)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[web] {self.address_string()} - {format % args}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Code Review Environment website.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on.")
    return parser.parse_args()


def main() -> None:
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
