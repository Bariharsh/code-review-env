import unittest

from backend.custom_review import heuristic_custom_review


class HeuristicCustomReviewTests(unittest.TestCase):
    def test_detects_sql_injection_pattern(self) -> None:
        code = (
            "import sqlite3\n\n"
            "def find_user(conn, username):\n"
            "    query = f\"SELECT * FROM users WHERE username = '{username}'\"\n"
            "    return conn.execute(query).fetchone()\n"
        )

        result = heuristic_custom_review(code, language="python", focus="security review")

        self.assertEqual(result["backend"], "heuristic")
        self.assertTrue(result["findings"])
        self.assertEqual(result["findings"][0]["severity"], "critical")
        self.assertIn("parameterized", result["findings"][0]["recommendation"].lower())


if __name__ == "__main__":
    unittest.main()
