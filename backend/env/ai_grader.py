"""AI-powered grading using Gemini to evaluate code reviews intelligently."""
from __future__ import annotations

import json
import os
import re
from typing import Any

try:
    from google import genai
except ImportError:
    genai = None

from .models import CodeReviewTask, RewardState


GRADING_PROMPT = """You are an expert code review grader. Given a piece of buggy code, the expected explanation, and a student's review, evaluate how well the student identified the bug and suggested a fix.

BUGGY CODE:
{code}

EXPECTED EXPLANATION:
{expected_explanation}

STUDENT'S REVIEW:
{student_review}

Score the review on this scale:
- 1.0 = The review correctly identifies the core bug AND suggests the right fix direction
- 0.5 = The review partially identifies the issue OR mentions the fix but misses key details
- 0.0 = The review completely misses the actual bug

Respond with ONLY valid JSON, no markdown, no code fences:
{{"score": <0.0 or 0.5 or 1.0>, "verdict": "<full_match or partial_match or wrong>", "rationale": "<1-2 sentence explanation of your grading>", "matched_signals": ["<key concepts the student got right>"], "missing_signals": ["<key concepts the student missed>"]}}"""


def ai_grade_review(task: CodeReviewTask, review: str) -> RewardState | None:
    """Use Gemini to intelligently grade a review. Returns None if AI is unavailable."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not genai or not api_key:
        return None

    try:
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")
        client = genai.Client(api_key=api_key)

        prompt = GRADING_PROMPT.format(
            code=task.code,
            expected_explanation=task.expected_output.explanation,
            student_review=review,
        )

        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )

        raw = response.text.strip()
        # Strip markdown code fences if present
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

        result = json.loads(raw)

        score = float(result.get("score", 0.0))
        if score not in (0.0, 0.5, 1.0):
            score = round(score * 2) / 2  # snap to nearest 0.0/0.5/1.0

        verdict_map = {1.0: "full_match", 0.5: "partial_match", 0.0: "wrong"}

        return RewardState(
            score=score,
            verdict=verdict_map.get(score, "wrong"),
            matched_keywords=result.get("matched_signals", []),
            missing_keywords=result.get("missing_signals", []),
            partial_keywords=[],
            semantic_overlap=score,
            rationale=result.get("rationale", "AI-evaluated review."),
        )
    except Exception as exc:
        print(f"[WARN] AI grading failed, falling back to keyword grading: {exc}")
        return None
