export const SOLVED_THRESHOLD = 0.85;
export const TASK_SESSION_STORAGE_KEY = "cr_task_sessions_v1";

export const phaseOrder = ["identify_bug", "explain_issue", "fix_code"];

export const phaseLabels = {
  identify_bug: "Identify Bug",
  explain_issue: "Explain Impact",
  fix_code: "Submit Fix",
};

export const phaseDescriptions = {
  identify_bug: "Call out the main defect, vulnerability, or failure mode.",
  explain_issue: "Explain why the issue matters in production or security terms.",
  fix_code: "Provide corrected code that resolves the root cause.",
};

export function emptyBreakdown() {
  return {
    bug_detected: 0,
    explanation: 0,
    fix: 0,
    structure_bonus: 0,
    irrelevant_penalty: 0,
    hallucinated_fix_penalty: 0,
    total: 0,
  };
}

export function emptyEvaluation() {
  return {
    reward: null,
    done: false,
    currentStep: null,
    stepHistory: [],
    cumulativeBreakdown: emptyBreakdown(),
    info: null,
  };
}

export function normalizeEvaluation(value) {
  return {
    reward: value?.reward ?? null,
    done: value?.done ?? false,
    currentStep: value?.currentStep ?? null,
    stepHistory: Array.isArray(value?.stepHistory) ? value.stepHistory : [],
    cumulativeBreakdown: value?.cumulativeBreakdown ?? emptyBreakdown(),
    info: value?.info ?? null,
  };
}

export function uniqueEpisodeSignals(stepHistory, field) {
  const seen = new Set();
  for (const record of stepHistory ?? []) {
    for (const keyword of record?.reward?.[field] ?? []) {
      seen.add(keyword);
    }
  }
  return [...seen];
}

export function formatReward(value) {
  return value == null ? "—" : Number(value).toFixed(2);
}

export function formatVerdict(value) {
  return value ? value.replaceAll("_", " ") : "evaluated";
}

export function clampPercent(value, max) {
  if (!max) return "0%";
  return `${Math.max(0, Math.min(100, (value / max) * 100))}%`;
}

export function listOrFallback(values, fallback) {
  return values && values.length > 0 ? values : [fallback];
}

export function summarizeRecord(record) {
  return `${phaseLabels[record.phase]}: ${record.reward.feedback || record.reward.rationale}`;
}

export function summarizeEpisode(stepHistory) {
  if (!stepHistory.length) {
    return "Start the workflow by identifying the bug, then explain the impact, then submit a fix.";
  }
  return stepHistory.map((record) => summarizeRecord(record)).join("\n\n");
}

export function historyPreview(record, limit = 160) {
  const text = record?.action?.content?.trim() ?? "";
  if (text.length <= limit) {
    return text;
  }
  return `${text.slice(0, limit).trim()}...`;
}

export function historyFeedbackPreview(record, limit = 120) {
  const feedback = (record?.reward?.feedback || record?.reward?.rationale || "").trim();
  if (feedback.length <= limit) {
    return feedback;
  }
  return `${feedback.slice(0, limit).trim()}...`;
}

export function taskScore(snapshot) {
  return snapshot?.evaluation?.cumulativeBreakdown?.total ?? snapshot?.environmentState?.cumulative_reward ?? 0;
}
