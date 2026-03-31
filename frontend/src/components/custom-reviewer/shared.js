export const reviewerLanguageOptions = [
  { value: "auto", label: "Auto Detect" },
  { value: "python", label: "Python" },
  { value: "javascript", label: "JavaScript" },
  { value: "typescript", label: "TypeScript" },
  { value: "react", label: "React" },
  { value: "html", label: "HTML" },
  { value: "sql", label: "SQL" },
  { value: "go", label: "Go" },
  { value: "java", label: "Java" },
  { value: "text", label: "Other" },
];

export const reviewerGoalPresets = [
  {
    label: "Security Audit",
    description: "Look for unsafe input handling, auth issues, and data exposure risks.",
    value: "Review this for security issues, unsafe input handling, auth problems, and sensitive data exposure risks.",
  },
  {
    label: "Bug Risk",
    description: "Prioritize correctness issues, edge cases, and likely runtime failures.",
    value: "Review this for correctness problems, edge cases, missing validation, and likely runtime bugs.",
  },
  {
    label: "Performance",
    description: "Spot wasteful work, scaling concerns, and unnecessary re-renders.",
    value: "Review this for performance issues, unnecessary work, scaling risks, and inefficient patterns.",
  },
  {
    label: "Maintainability",
    description: "Focus on clarity, structure, readability, and long-term upkeep.",
    value: "Review this for maintainability, readability, duplication, and design choices that will be harder to evolve.",
  },
];

export function emptyCustomReviewResult() {
  return {
    backend: "",
    summary: "",
    overall_verdict: "needs_changes",
    risk_level: "medium",
    strengths: [],
    findings: [],
    suggested_changes: [],
    improved_code: "",
  };
}

export function severityLabel(value) {
  return (value || "medium").replaceAll("_", " ");
}

export function backendLabel(value) {
  if (value === "gemini") return "Gemini";
  if (value === "openai") return "OpenAI";
  if (value === "heuristic") return "Fallback reviewer";
  return value || "Reviewer";
}

export function languageLabel(value) {
  const option = reviewerLanguageOptions.find((entry) => entry.value === value);
  if (option) return option.label;
  if (!value) return "Auto Detect";
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function verdictLabel(value) {
  if (value === "strong") return "Strong";
  if (value === "mixed") return "Mixed";
  return "Needs changes";
}

export function computeCodeStats(code) {
  const normalized = (code || "").replace(/\r\n/g, "\n");
  const lines = normalized.trim() ? normalized.split("\n") : [];
  return {
    lineCount: lines.length,
    nonEmptyLineCount: lines.filter((line) => line.trim()).length,
    charCount: normalized.length,
  };
}

export function getPrimaryFinding(result) {
  return result?.findings?.[0] ?? null;
}

export function getPriorityAction(result) {
  const primaryFinding = getPrimaryFinding(result);
  if (primaryFinding?.recommendation) return primaryFinding.recommendation;
  if (result?.suggested_changes?.length) return result.suggested_changes[0];
  return "Review the summary and start with the highest-risk area first.";
}

export function demoSnippet() {
  return {
    language: "python",
    focus: "Please review this for security issues and suggest a safer version.",
    code: [
      "import sqlite3",
      "",
      "def find_user(conn: sqlite3.Connection, username: str):",
      "    query = f\"SELECT id, username, is_admin FROM users WHERE username = '{username}'\"",
      "    return conn.execute(query).fetchone()",
    ].join("\n"),
  };
}
