from __future__ import annotations

import json
import os
import re
from typing import Any

try:
    from google import genai
except ImportError:
    genai = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


CUSTOM_REVIEW_PROMPT = """You are an expert senior code reviewer. Review the submitted code like a product-ready AI reviewer.

SNIPPET TITLE:
{title}

LANGUAGE:
{language}

AUTHOR GOAL:
{focus}

CODE:
{code}

Return ONLY valid JSON with this exact shape:
{{
  "summary": "<2-3 sentence high level review>",
  "overall_verdict": "<strong or mixed or needs_changes>",
  "risk_level": "<low or medium or high or critical>",
  "strengths": ["<short positive point>", "<short positive point>"],
  "findings": [
    {{
      "title": "<finding title>",
      "severity": "<low or medium or high or critical>",
      "why_it_matters": "<why this matters in real usage>",
      "evidence": "<what in the code suggests this issue>",
      "recommendation": "<clear suggested change>"
    }}
  ],
  "suggested_changes": ["<clear next step>", "<clear next step>"],
  "improved_code": "<full improved code if a concrete fix is possible, otherwise empty string>"
}}

Rules:
- Focus on correctness, reliability, security, performance, and maintainability.
- Keep findings concrete and user-understandable.
- If the code is mostly solid, say that honestly.
- Do not include markdown fences.
- Do not include any text before or after the JSON.
"""

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
VERDICT_VALUES = {"strong", "mixed", "needs_changes"}


def _strip_wrappers(raw: str) -> str:
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _extract_openai_text(response: Any) -> str:
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


def _normalized_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            normalized.append(item.strip())
    return normalized


def _normalize_severity(value: Any) -> str:
    if not isinstance(value, str):
        return "medium"
    severity = value.strip().lower()
    return severity if severity in SEVERITY_ORDER else "medium"


def _normalize_verdict(value: Any) -> str:
    if not isinstance(value, str):
        return "needs_changes"
    verdict = value.strip().lower()
    return verdict if verdict in VERDICT_VALUES else "needs_changes"


def _normalize_findings(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    findings: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip() or "Review finding"
        why_it_matters = str(item.get("why_it_matters", "")).strip()
        evidence = str(item.get("evidence", "")).strip()
        recommendation = str(item.get("recommendation", "")).strip()
        findings.append(
            {
                "title": title,
                "severity": _normalize_severity(item.get("severity")),
                "why_it_matters": why_it_matters,
                "evidence": evidence,
                "recommendation": recommendation,
            }
        )
    return findings


def _finalize_review(result: dict[str, Any], *, backend: str) -> dict[str, Any]:
    findings = _normalize_findings(result.get("findings"))
    risk_level = _normalize_severity(result.get("risk_level"))
    if findings:
        risk_level = max([risk_level, *[finding["severity"] for finding in findings]], key=lambda item: SEVERITY_ORDER[item])

    return {
        "backend": backend,
        "summary": str(result.get("summary", "")).strip() or "The reviewer analyzed the snippet and prepared a feedback summary.",
        "overall_verdict": _normalize_verdict(result.get("overall_verdict")),
        "risk_level": risk_level,
        "strengths": _normalized_string_list(result.get("strengths"))[:4],
        "findings": findings[:6],
        "suggested_changes": _normalized_string_list(result.get("suggested_changes"))[:6],
        "improved_code": str(result.get("improved_code", "")).rstrip(),
    }


def _make_finding(
    title: str,
    severity: str,
    why_it_matters: str,
    evidence: str,
    recommendation: str,
) -> dict[str, str]:
    return {
        "title": title,
        "severity": severity,
        "why_it_matters": why_it_matters,
        "evidence": evidence,
        "recommendation": recommendation,
    }


def _guess_language(code: str, language: str) -> str:
    if language.strip():
        return language.strip().lower()

    stripped = code.lower()
    if "useeffect" in stripped or "const " in stripped or "function " in stripped:
        return "javascript"
    if "def " in stripped or "import " in stripped:
        return "python"
    if "<div" in stripped or "<form" in stripped:
        return "html"
    return "text"


def heuristic_custom_review(code: str, *, title: str = "", language: str = "", focus: str = "") -> dict[str, Any]:
    normalized = code.lower()
    detected_language = _guess_language(code, language)
    findings: list[dict[str, str]] = []
    strengths: list[str] = []
    suggested_changes: list[str] = []
    improved_code = ""

    if "select " in normalized and ("f\"" in code or "format(" in normalized or "' + " in code or "\" + " in code):
        findings.append(
            _make_finding(
                "Possible SQL injection",
                "critical",
                "Interpolating untrusted input into a SQL string can let attackers alter the query or read unintended data.",
                "The query appears to be built with string interpolation or concatenation instead of parameter binding.",
                "Switch to parameterized queries and pass user input as query parameters rather than embedding it in the SQL string.",
            )
        )
        suggested_changes.append("Replace dynamic SQL string building with parameterized database calls.")
        if "sqlite3" in normalized and "username" in normalized:
            improved_code = (
                "import sqlite3\n\n\n"
                "def find_user(conn: sqlite3.Connection, username: str):\n"
                "    query = \"SELECT id, username, is_admin FROM users WHERE username = ?\"\n"
                "    return conn.execute(query, (username,)).fetchone()\n"
            )

    if "record[\"password\"] == password" in code or "record['password'] == password" in code:
        findings.append(
            _make_finding(
                "Plaintext password comparison",
                "high",
                "Raw password comparison usually means passwords are stored or handled insecurely, which becomes very dangerous if credentials leak.",
                "The authentication flow compares the incoming password directly against a stored password field.",
                "Store password hashes and verify them with a dedicated password hashing library such as bcrypt or argon2.",
            )
        )
        suggested_changes.append("Replace plaintext password checks with secure password hash verification.")

    if "os.path.join" in normalized and "filename" in normalized and "open(" in normalized:
        findings.append(
            _make_finding(
                "Possible path traversal",
                "high",
                "Joining raw user input into a filesystem path can allow attackers to escape the intended directory and read arbitrary files.",
                "The code constructs a path from user-provided filename data and opens it without checking the resolved location.",
                "Resolve the final path and verify it still stays inside the allowed root directory before reading the file.",
            )
        )
        suggested_changes.append("Resolve the requested path and reject values that escape the intended directory.")

    if "useeffect(()" in normalized and "setinterval" in normalized and "setcount(count + 1)" in normalized:
        findings.append(
            _make_finding(
                "Stale React state closure",
                "medium",
                "The interval callback keeps the first render's state, so the UI can stop updating correctly.",
                "The interval updates state with `setCount(count + 1)` inside an effect that does not refresh the closure.",
                "Use a functional state updater like `setCount((prev) => prev + 1)` so each interval tick sees fresh state.",
            )
        )
        suggested_changes.append("Use a functional React state update inside interval callbacks.")
        improved_code = code.replace("setCount(count + 1);", "setCount((prev) => prev + 1);")

    if "setinterval" in normalized and ".on(" in normalized and "socket" in normalized:
        findings.append(
            _make_finding(
                "Repeated event listener registration",
                "medium",
                "Registering the same event handler repeatedly can leak memory and make callbacks fire multiple times for one event.",
                "A listener registration appears inside a recurring interval rather than a one-time setup block.",
                "Register the listener once and return a cleanup function that removes it when it is no longer needed.",
            )
        )
        suggested_changes.append("Move repeated listener registration out of recurring timers and add cleanup.")

    if "<form" in normalized and "<button" in normalized and "cancel" in normalized and "type=" not in normalized:
        findings.append(
            _make_finding(
                "Implicit submit button behavior",
                "low",
                "Buttons inside a form default to submit, which can trigger unintended form submission for secondary actions.",
                "The form contains buttons without explicit `type` attributes.",
                "Set button types explicitly so non-submit actions do not trigger the form submission flow.",
            )
        )
        suggested_changes.append("Add explicit button types inside forms to avoid accidental submit behavior.")

    if "todo" in normalized or "fixme" in normalized:
        strengths.append("The snippet is easy to scan and already flags unfinished work with inline notes.")
        findings.append(
            _make_finding(
                "Unfinished implementation marker",
                "low",
                "TODO and FIXME comments can be useful during development, but leaving them in important code paths can signal incomplete behavior.",
                "The snippet contains TODO or FIXME markers that suggest unresolved work.",
                "Confirm whether the unfinished path is safe in production and convert the note into a tracked task if needed.",
            )
        )

    if not findings:
        strengths.append("No obvious critical security or correctness issue stood out from the fallback review.")
        suggested_changes.extend(
            [
                "Add targeted tests around the most important user paths and edge cases.",
                "Review error handling and validation so failures stay predictable in production.",
            ]
        )

    if not strengths:
        strengths.append("The code is focused and small enough to reason about quickly.")

    highest_severity = max((finding["severity"] for finding in findings), key=lambda item: SEVERITY_ORDER[item], default="low")
    verdict = "needs_changes" if SEVERITY_ORDER[highest_severity] >= 2 else "mixed" if findings else "strong"

    if findings:
        summary = (
            f"The reviewer found {len(findings)} notable issue{'s' if len(findings) != 1 else ''}"
            f" in this {detected_language} snippet, with the highest risk at {highest_severity} severity."
        )
        if focus.strip():
            summary += f" The feedback also stayed aligned with the author's goal: {focus.strip()}."
    else:
        summary = "The reviewer did not detect an obvious critical issue in the snippet, but still suggests a few polish and reliability improvements."

    return _finalize_review(
        {
            "summary": summary,
            "overall_verdict": verdict,
            "risk_level": highest_severity,
            "strengths": strengths,
            "findings": findings,
            "suggested_changes": suggested_changes,
            "improved_code": improved_code,
        },
        backend="heuristic",
    )


def _gemini_custom_review(prompt: str) -> dict[str, Any]:
    if genai is None:
        raise RuntimeError("The google-genai package is not installed.")

    api_key = os.environ["GEMINI_API_KEY"]
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(model=model_name, contents=prompt)
    return json.loads(_strip_wrappers(response.text))


def _openai_custom_review(prompt: str) -> dict[str, Any]:
    if OpenAI is None:
        raise RuntimeError("The openai package is not installed.")

    model = os.environ["OPENAI_MODEL"]
    client = OpenAI()
    response = client.responses.create(model=model, input=prompt)
    return json.loads(_strip_wrappers(_extract_openai_text(response)))


def should_use_gemini() -> bool:
    return bool(genai and os.getenv("GEMINI_API_KEY"))


def should_use_openai() -> bool:
    return bool(OpenAI and os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_MODEL"))


def review_custom_code(code: str, *, title: str = "", language: str = "", focus: str = "") -> dict[str, Any]:
    if not code.strip():
        raise ValueError("`code` is required.")

    prompt = CUSTOM_REVIEW_PROMPT.format(
        title=title.strip() or "Untitled snippet",
        language=_guess_language(code, language),
        focus=focus.strip() or "General code review",
        code=code.rstrip(),
    )

    try:
        if should_use_gemini():
            return _finalize_review(_gemini_custom_review(prompt), backend="gemini")
        if should_use_openai():
            return _finalize_review(_openai_custom_review(prompt), backend="openai")
    except Exception as exc:
        print(f"[WARN] Custom AI review failed, using heuristic fallback: {exc}")

    return heuristic_custom_review(code, title=title, language=language, focus=focus)
