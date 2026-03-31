import unittest
from http import HTTPStatus
from unittest.mock import patch

from backend import server


class HandlerDouble:
    def __init__(self) -> None:
        self.responses: list[tuple[str, HTTPStatus, object]] = []

    def send_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        self.responses.append(("json", status, payload))

    def send_error_json(self, status: HTTPStatus, message: str) -> None:
        self.responses.append(("error", status, message))


class ServerHandlerTests(unittest.TestCase):
    def test_handle_step_rejects_unknown_action_type(self) -> None:
        handler = HandlerDouble()

        server.CodeReviewSiteHandler.handle_step(
            handler,
            {
                "task_id": "easy-even-check",
                "action": {"type": "ship-it", "content": "Looks fine to me."},
            },
        )

        self.assertEqual(
            handler.responses,
            [("error", HTTPStatus.BAD_REQUEST, "`action.type` must be either 'review' or 'fix'.")],
        )

    def test_handle_second_opinion_returns_not_found_for_unknown_task(self) -> None:
        handler = HandlerDouble()

        with patch("backend.server.get_second_opinion", side_effect=KeyError("missing")):
            server.CodeReviewSiteHandler.handle_second_opinion(
                handler,
                {"task_id": "missing-task", "review": "This looks unsafe."},
            )

        self.assertEqual(
            handler.responses,
            [("error", HTTPStatus.NOT_FOUND, "Unknown task id.")],
        )

    def test_handle_baseline_sanitizes_internal_errors(self) -> None:
        handler = HandlerDouble()

        with patch("backend.server.run_baseline", side_effect=RuntimeError("provider token expired")), patch("builtins.print"):
            server.CodeReviewSiteHandler.handle_baseline(
                handler,
                {"task_id": "easy-even-check"},
            )

        self.assertEqual(
            handler.responses,
            [("error", HTTPStatus.BAD_GATEWAY, "AI review failed.")],
        )

    def test_handle_second_opinion_sanitizes_internal_errors(self) -> None:
        handler = HandlerDouble()

        with patch("backend.server.get_second_opinion", side_effect=RuntimeError("provider timeout")), patch("builtins.print"):
            server.CodeReviewSiteHandler.handle_second_opinion(
                handler,
                {"task_id": "easy-even-check", "review": "This looks unsafe."},
            )

        self.assertEqual(
            handler.responses,
            [("error", HTTPStatus.BAD_GATEWAY, "Second opinion unavailable.")],
        )

    def test_handle_custom_review_requires_code(self) -> None:
        handler = HandlerDouble()

        server.CodeReviewSiteHandler.handle_custom_review(
            handler,
            {"language": "python", "focus": "security"},
        )

        self.assertEqual(
            handler.responses,
            [("error", HTTPStatus.BAD_REQUEST, "`code` is required.")],
        )

    def test_handle_custom_review_sanitizes_internal_errors(self) -> None:
        handler = HandlerDouble()

        with patch("backend.server.review_custom_code", side_effect=RuntimeError("provider timeout")), patch("builtins.print"):
            server.CodeReviewSiteHandler.handle_custom_review(
                handler,
                {"code": "print('hello')", "language": "python"},
            )

        self.assertEqual(
            handler.responses,
            [("error", HTTPStatus.BAD_GATEWAY, "Custom review unavailable.")],
        )


if __name__ == "__main__":
    unittest.main()
