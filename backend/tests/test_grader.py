import unittest

from backend.env.grader import HALLUCINATED_FIX_PENALTY, grade_action, normalize_text, signal_matches
from backend.env.models import CodeReviewTask, ReviewAction, ReviewRubric


class SignalMatchesTests(unittest.TestCase):
    def test_regex_signals_do_not_fall_back_to_token_matching(self) -> None:
        text = "This review mentions foo s bar in prose, but not the actual regex match."

        matched = signal_matches(text, normalize_text(text), r"re:foo\s+bar")

        self.assertFalse(matched)

    def test_regex_signals_match_when_the_pattern_matches(self) -> None:
        text = "This review contains foo   bar exactly once."

        matched = signal_matches(text, normalize_text(text), r"re:foo\s+bar")

        self.assertTrue(matched)

    def test_plain_signals_still_use_keyword_token_fallback(self) -> None:
        text = "The auth check is missing before the update runs."

        matched = signal_matches(text, normalize_text(text), "missing auth check")

        self.assertTrue(matched)


class FixScoringTests(unittest.TestCase):
    def test_unrelated_fix_does_not_earn_change_bonus_credit(self) -> None:
        task = CodeReviewTask(
            task_id="test-fix",
            difficulty="easy",
            title="Broken even check",
            code="def is_even(n: int) -> bool:\n    return n % 2 == 1\n",
            rubric=ReviewRubric(
                explanation="The modulo comparison is reversed.",
                bug_keywords=["n % 2 == 1"],
                explanation_keywords=["returns true for odd numbers"],
                fix_keywords=["n % 2 == 0"],
                reference_fix="def is_even(n: int) -> bool:\n    return n % 2 == 0\n",
            ),
        )

        reward = grade_action(
            task,
            ReviewAction(
                type="fix",
                content="const total = 42;\nif (total) {\n  throw new Error('wrong stack');\n}\n",
            ),
            "fix_code",
            2,
        )

        self.assertEqual(reward.breakdown.fix, 0.0)
        self.assertEqual(reward.breakdown.hallucinated_fix_penalty, HALLUCINATED_FIX_PENALTY)


if __name__ == "__main__":
    unittest.main()
