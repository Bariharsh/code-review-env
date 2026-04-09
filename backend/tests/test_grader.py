import unittest
from dataclasses import asdict

from backend.env.environment import CodeReviewEnvironment, aggregate_breakdowns
from backend.env.grader import HALLUCINATED_FIX_PENALTY, grade_action, normalize_text, signal_matches
from backend.env.models import CodeReviewTask, ReviewAction, ReviewRubric, RewardState, ScoreBreakdown


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

        self.assertEqual(reward.breakdown.fix, 0.0001)
        self.assertEqual(reward.breakdown.hallucinated_fix_penalty, HALLUCINATED_FIX_PENALTY)


class AggregateBreakdownTests(unittest.TestCase):
    def test_cumulative_total_stays_strictly_below_one(self) -> None:
        rewards = [
            RewardState(score=0.3, verdict="full_match", breakdown=ScoreBreakdown(total=0.3)),
            RewardState(score=0.3, verdict="full_match", breakdown=ScoreBreakdown(total=0.3)),
            RewardState(score=0.4, verdict="full_match", breakdown=ScoreBreakdown(total=0.4)),
        ]

        breakdown = aggregate_breakdowns(rewards)

        self.assertEqual(breakdown.total, 0.999)
        self.assertGreater(breakdown.total, 0.0)
        self.assertLess(breakdown.total, 1.0)

    def test_cumulative_breakdown_serialization_avoids_zero_components(self) -> None:
        rewards = [
            RewardState(
                score=0.001,
                verdict="wrong",
                breakdown=ScoreBreakdown(
                    bug_detected=0.0001,
                    explanation=0.0001,
                    fix=0.0001,
                    structure_bonus=0.0001,
                    irrelevant_penalty=-0.0001,
                    hallucinated_fix_penalty=-0.0001,
                    total=0.001,
                ),
            )
            for _ in range(3)
        ]

        payload = aggregate_breakdowns(rewards).to_dict()

        self.assertEqual(payload["bug_detected"], 0.0003)
        self.assertEqual(payload["structure_bonus"], 0.0003)
        self.assertEqual(payload["irrelevant_penalty"], -0.0003)
        self.assertEqual(payload["hallucinated_fix_penalty"], -0.0003)

    def test_raw_environment_state_has_no_boundary_scores_after_episode(self) -> None:
        env = CodeReviewEnvironment()
        observation = env.reset("easy-even-check")

        env.step(ReviewAction(type=observation.expected_action_type, content="n % 2 == 1"))
        observation = env.state().observation
        self.assertIsNotNone(observation)
        env.step(ReviewAction(type=observation.expected_action_type, content="false for even inputs"))
        observation = env.state().observation
        self.assertIsNotNone(observation)
        env.step(ReviewAction(type=observation.expected_action_type, content="def is_even(n: int) -> bool:\n    return n % 2 == 0\n"))

        def walk(obj):
            if isinstance(obj, dict):
                for value in obj.values():
                    yield from walk(value)
            elif isinstance(obj, list):
                for value in obj:
                    yield from walk(value)
            elif isinstance(obj, float):
                yield obj

        payload = asdict(env.state())
        floats = list(walk(payload))

        self.assertNotIn(0.0, floats)
        self.assertNotIn(1.0, floats)
        self.assertNotIn(-0.0, floats)


if __name__ == "__main__":
    unittest.main()
