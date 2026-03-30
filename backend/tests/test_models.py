import unittest

from backend.env.models import ReviewAction, ReviewRubric


class ReviewActionTests(unittest.TestCase):
    def test_invalid_action_type_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, r"`action.type` must be either 'review' or 'fix'."):
            ReviewAction.from_dict({"type": "ship-it", "content": "Looks good."})

    def test_null_action_content_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, r"`action.content` must be a string."):
            ReviewAction.from_dict({"type": "review", "content": None})


class ReviewRubricTests(unittest.TestCase):
    def test_expected_output_supports_phase_aware_keywords(self) -> None:
        rubric = ReviewRubric.from_dict(
            {
                "expected_output": {
                    "explanation": "The query is unsafe.",
                    "phase_keywords": {
                        "identify_bug": ["sql injection"],
                        "explain_issue": ["user input changes the query"],
                        "fix_code": ["parameterized query"],
                    },
                    "reference_fix": "cursor.execute(query, (username,))",
                }
            }
        )

        self.assertEqual(rubric.bug_keywords, ["sql injection"])
        self.assertEqual(rubric.explanation_keywords, ["user input changes the query"])
        self.assertEqual(rubric.fix_keywords, ["parameterized query"])

    def test_ambiguous_required_keyword_groups_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, r"expected_output\.required_keyword_groups"):
            ReviewRubric.from_dict(
                {
                    "expected_output": {
                        "explanation": "The query is unsafe.",
                        "required_keyword_groups": [["sql injection"], ["parameterized query"]],
                        "partial_keywords": ["unsafe query"],
                        "reference_fix": "cursor.execute(query, (username,))",
                    }
                }
            )


if __name__ == "__main__":
    unittest.main()
