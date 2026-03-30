<script>
  import { onDestroy, onMount } from "svelte";
  import confetti from "canvas-confetti";
  import hljs from "highlight.js/lib/core";
  import python from "highlight.js/lib/languages/python";
  import sql from "highlight.js/lib/languages/sql";
  import javascript from "highlight.js/lib/languages/javascript";
  import xml from "highlight.js/lib/languages/xml";
  import go from "highlight.js/lib/languages/go";

  hljs.registerLanguage("python", python);
  hljs.registerLanguage("sql", sql);
  hljs.registerLanguage("javascript", javascript);
  hljs.registerLanguage("xml", xml);
  hljs.registerLanguage("go", go);

  const SOLVED_THRESHOLD = 0.85;
  const TASK_SESSION_STORAGE_KEY = "cr_task_sessions_v1";
  const phaseOrder = ["identify_bug", "explain_issue", "fix_code"];
  const phaseLabels = {
    identify_bug: "Identify Bug",
    explain_issue: "Explain Impact",
    fix_code: "Submit Fix",
  };
  const phaseDescriptions = {
    identify_bug: "Call out the main defect, vulnerability, or failure mode.",
    explain_issue: "Explain why the issue matters in production or security terms.",
    fix_code: "Provide corrected code that resolves the root cause.",
  };

  function emptyBreakdown() {
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

  function emptyEvaluation() {
    return {
      reward: null,
      done: false,
      currentStep: null,
      stepHistory: [],
      cumulativeBreakdown: emptyBreakdown(),
      info: null,
    };
  }

  let tasks = [];
  let currentTaskId = "";
  let taskMeta = null;
  let observation = null;
  let environmentState = null;
  let reviewText = "";
  let fixCode = "";
  let isBooting = true;
  let isLoadingTask = false;
  let isSubmitting = false;
  let isRunningBaseline = false;
  let isGettingOpinion = false;
  let mode = "review";
  let statusText = "Ready";
  let secondOpinionText = "";
  let backendLabel = "manual";
  let selectedDifficulty = "all";
  let reviewTextareaEl;
  let taskSessions = {};
  let taskStatusById = {};
  let evaluationPanelEl;
  let celebrationState = {
    active: false,
    source: "manual",
    emoji: "",
    title: "",
    detail: "",
    score: "0.00",
    run: 0,
  };
  let celebrationTimerId = 0;
  let emojiShower = [];
  let emojiShowerTimerId = 0;

  let evaluation = emptyEvaluation();
  let typedNarration = "";
  const typingTimers = new Map();

  let sessionStats = { totalScore: 0, solvedTasks: new Set(), reviewsGiven: 0 };

  $: isBusy = isSubmitting || isRunningBaseline || isLoadingTask;
  $: filteredTasks = selectedDifficulty === "all" ? tasks : tasks.filter((task) => task.difficulty === selectedDifficulty);
  $: activeTask = tasks.find((task) => task.task_id === currentTaskId) ?? taskMeta;
  $: highlightedCode = observation ? hljs.highlightAuto(observation.code).value : "";
  $: currentPhase = observation?.phase ?? "identify_bug";
  $: expectedActionType = observation?.expected_action_type ?? "review";
  $: isEpisodeDone = environmentState?.done ?? evaluation.done;
  $: currentStepNumber = observation ? (isEpisodeDone ? observation.step_index : observation.step_index + 1) : 1;
  $: cumulativeBreakdown = evaluation.cumulativeBreakdown ?? emptyBreakdown();
  $: breakdownRows = [
    { key: "bug_detected", label: "Bug Detection", value: cumulativeBreakdown.bug_detected, max: 0.3 },
    { key: "explanation", label: "Explanation", value: cumulativeBreakdown.explanation, max: 0.3 },
    { key: "fix", label: "Fix Correctness", value: cumulativeBreakdown.fix, max: 0.4 },
  ];
  $: latestMatched = evaluation.currentStep?.matched_keywords ?? [];
  $: latestMissing = evaluation.currentStep?.missing_keywords ?? [];
  $: tone = cumulativeBreakdown.total >= SOLVED_THRESHOLD ? "green" : cumulativeBreakdown.total >= 0.45 ? "yellow" : cumulativeBreakdown.total > 0 ? "red" : "neutral";
  $: isResultsMode = isEpisodeDone && evaluation.stepHistory.length > 0;
  $: matchedEpisodeSignals = uniqueEpisodeSignals(evaluation.stepHistory, "matched_keywords");
  $: missingEpisodeSignals = uniqueEpisodeSignals(evaluation.stepHistory, "missing_keywords");
  $: bestStepRecord = evaluation.stepHistory.reduce((best, record) => {
    if (!best) return record;
    return record.reward.breakdown.total > best.reward.breakdown.total ? record : best;
  }, null);
  $: taskStatusById = tasks.reduce((statuses, task) => {
    const snapshot = task.task_id === currentTaskId && observation
      ? {
        observation,
        environmentState,
        evaluation,
      }
      : taskSessions[task.task_id] ?? null;

    const stepHistory = snapshot?.evaluation?.stepHistory ?? [];
    if (!stepHistory.length) {
      statuses[task.task_id] = null;
      return statuses;
    }

    const completed = snapshot?.evaluation?.done ?? snapshot?.environmentState?.done ?? false;
    statuses[task.task_id] = completed
      ? {
        tone: "completed",
        badge: "Completed",
        detail: `Score ${formatReward(taskScore(snapshot))}`,
      }
      : {
        tone: "submitted",
        badge: "Submitted",
        detail: `Step ${Math.min(stepHistory.length, phaseOrder.length)}/${phaseOrder.length} saved`,
      };
    return statuses;
  }, {});

  function stopTyping(key) {
    const job = typingTimers.get(key);
    if (!job) return;
    clearTimeout(job.timeoutId);
    typingTimers.delete(key);
    job.resolve?.();
  }

  function stopAllTyping() {
    for (const key of [...typingTimers.keys()]) {
      stopTyping(key);
    }
  }

  function keepTextareaPinned() {
    if (!reviewTextareaEl) return;
    reviewTextareaEl.scrollTop = reviewTextareaEl.scrollHeight;
  }

  function uniqueEpisodeSignals(stepHistory, field) {
    const seen = new Set();
    for (const record of stepHistory ?? []) {
      for (const keyword of record?.reward?.[field] ?? []) {
        seen.add(keyword);
      }
    }
    return [...seen];
  }

  function animateText(key, text, applyValue, speed = 18) {
    stopTyping(key);
    applyValue("");

    if (!text) {
      return Promise.resolve();
    }

    let index = 0;

    return new Promise((resolve) => {
      const step = () => {
        index += 1;
        applyValue(text.slice(0, index));

        if (index >= text.length) {
          typingTimers.delete(key);
          resolve();
          return;
        }

        const char = text.charAt(index - 1);
        const delay = /[.!?]/.test(char) ? speed * 5 : /[,;:]/.test(char) ? speed * 3 : speed;
        const timeoutId = window.setTimeout(step, delay);
        typingTimers.set(key, { timeoutId, resolve });
      };

      step();
    });
  }

  function typeNarration(text, speed = 18) {
    return animateText("narration", text, (value) => {
      typedNarration = value;
    }, speed);
  }

  function streamReviewText(text, speed = 12) {
    return animateText("review", text, (value) => {
      reviewText = value;
      keepTextareaPinned();
    }, speed);
  }

  function streamSecondOpinion(text, speed = 16) {
    return animateText("second-opinion", text, (value) => {
      secondOpinionText = value;
    }, speed);
  }

  function saveStats() {
    try {
      const data = {
        totalScore: sessionStats.totalScore,
        solvedTasks: [...sessionStats.solvedTasks],
        reviewsGiven: sessionStats.reviewsGiven,
      };
      localStorage.setItem("cr_session", JSON.stringify(data));
    } catch (error) {}
  }

  function loadStats() {
    try {
      const raw = localStorage.getItem("cr_session");
      if (raw) {
        const data = JSON.parse(raw);
        sessionStats = {
          totalScore: data.totalScore || 0,
          solvedTasks: new Set(data.solvedTasks || []),
          reviewsGiven: data.reviewsGiven || 0,
        };
      }
    } catch (error) {}
  }

  function loadTaskSessions() {
    try {
      const raw = localStorage.getItem(TASK_SESSION_STORAGE_KEY);
      taskSessions = raw ? JSON.parse(raw) : {};
    } catch (error) {
      taskSessions = {};
    }
  }

  function saveTaskSessions() {
    try {
      localStorage.setItem(TASK_SESSION_STORAGE_KEY, JSON.stringify(taskSessions));
    } catch (error) {}
  }

  function fireConfetti() {
    confetti({ particleCount: 120, spread: 80, origin: { y: 0.7 }, colors: ["#3b82f6", "#22c55e", "#f59e0b", "#fff"], zIndex: 99999 });
  }

  function scrollScorecardIntoView() {
    if (typeof window === "undefined" || !evaluationPanelEl) return;
    window.requestAnimationFrame(() => {
      evaluationPanelEl?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function clearCelebrationTimer() {
    if (!celebrationTimerId || typeof window === "undefined") return;
    window.clearTimeout(celebrationTimerId);
    celebrationTimerId = 0;
  }

  function clearEmojiShowerTimer() {
    if (!emojiShowerTimerId || typeof window === "undefined") return;
    window.clearTimeout(emojiShowerTimerId);
    emojiShowerTimerId = 0;
  }

  function celebrationCopy(source) {
    return source === "baseline"
      ? {
        emoji: "🤖",
        title: "Baseline completed!",
        detail: "AI walkthrough finished all three steps and staged the scorecard.",
      }
      : {
        emoji: "🎉",
        title: "Yes, completed!",
        detail: "Submission accepted, scored, and ready for the scorecard spotlight.",
      };
  }

  function emojiPoolFor(source) {
    return source === "baseline"
      ? ["🤖", "✨", "🎉", "✅", "🚀", "🏆"]
      : ["🎉", "✅", "✨", "🥳", "🏆", "🚀"];
  }

  function buildEmojiShower(source) {
    const pool = emojiPoolFor(source);
    return Array.from({ length: 26 }, (_, index) => ({
      id: `${Date.now()}-${index}`,
      emoji: pool[Math.floor(Math.random() * pool.length)],
      left: 4 + Math.random() * 92,
      top: Math.round(Math.random() * 24),
      drift: Math.round((Math.random() - 0.5) * 220),
      rotation: Math.round((Math.random() - 0.5) * 260),
      delay: Math.round(Math.random() * 240),
      duration: 1800 + Math.round(Math.random() * 1200),
      size: 22 + Math.round(Math.random() * 18),
    }));
  }

  function launchEmojiShower(source) {
    if (typeof window === "undefined") return;
    clearEmojiShowerTimer();
    emojiShower = buildEmojiShower(source);
    emojiShowerTimerId = window.setTimeout(() => {
      emojiShower = [];
      emojiShowerTimerId = 0;
    }, 3200);
  }

  function launchCompletionCelebration(source, totalScore) {
    if (typeof window === "undefined") return;

    clearCelebrationTimer();
    const copy = celebrationCopy(source);
    celebrationState = {
      active: true,
      source,
      emoji: copy.emoji,
      title: copy.title,
      detail: copy.detail,
      score: formatReward(totalScore),
      run: Date.now(),
    };

    launchEmojiShower(source);
    scrollScorecardIntoView();
    celebrationTimerId = window.setTimeout(() => {
      celebrationState = { ...celebrationState, active: false };
      celebrationTimerId = 0;
    }, 3400);
  }

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
      ...options,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Request failed.");
    return data;
  }

  function resetEvaluation() {
    backendLabel = "manual";
    evaluation = emptyEvaluation();
    secondOpinionText = "";
    typedNarration = "";
    stopAllTyping();
  }

  function normalizeEvaluation(value) {
    return {
      reward: value?.reward ?? null,
      done: value?.done ?? false,
      currentStep: value?.currentStep ?? null,
      stepHistory: Array.isArray(value?.stepHistory) ? value.stepHistory : [],
      cumulativeBreakdown: value?.cumulativeBreakdown ?? emptyBreakdown(),
      info: value?.info ?? null,
    };
  }

  function currentNarration(nextEvaluation = evaluation, nextObservation = observation) {
    if (nextEvaluation?.done) {
      return summarizeEpisode(nextEvaluation.stepHistory ?? []);
    }

    return nextEvaluation?.currentStep?.feedback || nextEvaluation?.currentStep?.rationale || nextObservation?.prompt || "";
  }

  function taskScore(snapshot) {
    return snapshot?.evaluation?.cumulativeBreakdown?.total ?? snapshot?.environmentState?.cumulative_reward ?? 0;
  }

  function persistCurrentTaskSession() {
    if (!currentTaskId || !observation) return;

    taskSessions = {
      ...taskSessions,
      [currentTaskId]: {
        taskMeta,
        observation,
        environmentState,
        reviewText,
        fixCode,
        mode,
        secondOpinionText,
        backendLabel,
        evaluation: normalizeEvaluation(evaluation),
        savedAt: Date.now(),
      },
    };
    saveTaskSessions();
  }

  function clearTaskSession(taskId = currentTaskId) {
    if (!taskId || !taskSessions[taskId]) return;

    const nextSessions = { ...taskSessions };
    delete nextSessions[taskId];
    taskSessions = nextSessions;
    saveTaskSessions();
  }

  function restoreTaskSession(taskId) {
    const snapshot = taskSessions[taskId];
    if (!snapshot?.observation) {
      return false;
    }

    stopAllTyping();
    currentTaskId = taskId;
    taskMeta = snapshot.taskMeta ?? tasks.find((task) => task.task_id === taskId) ?? null;
    observation = snapshot.observation;
    environmentState = snapshot.environmentState ?? null;
    reviewText = snapshot.reviewText ?? "";
    fixCode = snapshot.fixCode ?? snapshot.observation.code ?? "";
    mode = snapshot.mode ?? snapshot.observation.expected_action_type ?? "review";
    secondOpinionText = snapshot.secondOpinionText ?? "";
    backendLabel = snapshot.backendLabel ?? "manual";
    evaluation = normalizeEvaluation(snapshot.evaluation);
    typedNarration = currentNarration(evaluation, observation);

    if (observation?.phase === "fix_code" && !fixCode.trim()) {
      fixCode = observation.code;
    }

    statusText = evaluation.stepHistory.length > 0
      ? evaluation.done
        ? "Restored completed episode."
        : `Restored progress for ${taskMeta?.title ?? taskId}.`
      : "Ready";
    return true;
  }

  function syncModeWithObservation() {
    if (!observation) return;
    mode = observation.expected_action_type;
    if (observation.phase === "fix_code" && !fixCode.trim()) {
      fixCode = observation.code;
    }
  }

  function historyPayload() {
    return evaluation.stepHistory.map((record) => record.action);
  }

  function formatReward(value) {
    return value == null ? "—" : Number(value).toFixed(2);
  }

  function clampPercent(value, max) {
    if (!max) return "0%";
    return `${Math.max(0, Math.min(100, (value / max) * 100))}%`;
  }

  function listOrFallback(values, fallback) {
    return values && values.length > 0 ? values : [fallback];
  }

  function summarizeRecord(record) {
    return `${phaseLabels[record.phase]}: ${record.reward.feedback || record.reward.rationale}`;
  }

  function summarizeEpisode(stepHistory) {
    if (!stepHistory.length) {
      return "Start the workflow by identifying the bug, then explain the impact, then submit a fix.";
    }
    return stepHistory.map((record) => summarizeRecord(record)).join("\n\n");
  }

  function historyPreview(record, limit = 160) {
    const text = record?.action?.content?.trim() ?? "";
    if (text.length <= limit) {
      return text;
    }
    return `${text.slice(0, limit).trim()}...`;
  }

  function historyFeedbackPreview(record, limit = 120) {
    const feedback = (record?.reward?.feedback || record?.reward?.rationale || "").trim();
    if (feedback.length <= limit) {
      return feedback;
    }
    return `${feedback.slice(0, limit).trim()}...`;
  }

  function combinedReviewText() {
    const reviewSteps = evaluation.stepHistory.filter((record) => record.action?.type === "review");
    if (!reviewSteps.length) {
      return reviewText.trim();
    }
    return reviewSteps
      .map((record) => `${phaseLabels[record.phase]}: ${record.action.content}`)
      .join("\n\n");
  }

  function phaseIndex(phase) {
    return phaseOrder.indexOf(phase);
  }

  function isPhaseComplete(phase) {
    return evaluation.stepHistory.some((record) => record.phase === phase);
  }

  function isPhaseUnlocked(phase) {
    if (!observation) return false;
    if (isEpisodeDone) return true;
    return phaseIndex(phase) <= phaseIndex(currentPhase) || isPhaseComplete(phase);
  }

  function handlePhaseClick(phase) {
    if (!observation) return;

    if (!isPhaseUnlocked(phase)) {
      statusText = `Finish ${phaseLabels[currentPhase]} first to unlock ${phaseLabels[phase]}.`;
      return;
    }

    mode = phase === "fix_code" ? "fix" : "review";

    const existingRecord = evaluation.stepHistory.find((record) => record.phase === phase);
    if (existingRecord && phase !== currentPhase) {
      typeNarration(`${phaseLabels[phase]}: ${existingRecord.reward.feedback || existingRecord.reward.rationale}`);
      statusText = `${phaseLabels[phase]} is already complete. Continue with ${phaseLabels[currentPhase]}.`;
      return;
    }

    statusText = `${phaseLabels[phase]} ready`;
  }

  function registerReward(data) {
    sessionStats.reviewsGiven += 1;
    sessionStats.totalScore += data.reward ?? 0;

    const episodeTotal = data.state?.cumulative_reward ?? data.info?.cumulative_breakdown?.total ?? 0;
    const wasSolved = sessionStats.solvedTasks.has(currentTaskId);
    if (data.done && episodeTotal >= SOLVED_THRESHOLD) {
      sessionStats.solvedTasks.add(currentTaskId);
      if (!wasSolved) {
        sessionStats = sessionStats;
        fireConfetti();
      }
    }
    saveStats();
  }

  function applyResponse(data, { source = "manual" } = {}) {
    taskMeta = data.task ?? taskMeta;
    observation = data.observation;
    environmentState = data.state ?? environmentState;
    evaluation = normalizeEvaluation({
      reward: data.reward,
      done: data.done,
      currentStep: data.info?.step_evaluation ?? data.info?.score_details ?? null,
      stepHistory: data.info?.step_history ?? data.state?.history ?? [],
      cumulativeBreakdown: data.info?.cumulative_breakdown ?? emptyBreakdown(),
      info: data.info ?? null,
    });

    backendLabel = data.backend ?? source;

    if (data.submitted_fixed_code) {
      fixCode = data.submitted_fixed_code;
    }
    if (data.done && data.submitted_review) {
      reviewText = data.submitted_review;
    }

    syncModeWithObservation();

    const narrative = currentNarration(evaluation, observation);
    typeNarration(narrative);

    if (!data.done && observation?.phase === "fix_code" && !fixCode.trim()) {
      fixCode = observation.code;
    }

    if (data.done) {
      statusText = `Episode complete: ${formatReward(data.state?.cumulative_reward)} / 1.00`;
      launchCompletionCelebration(source, data.state?.cumulative_reward ?? data.info?.cumulative_breakdown?.total ?? 0);
    } else {
      statusText = `${phaseLabels[observation.phase]} ready`;
    }

    persistCurrentTaskSession();
  }

  async function loadTasks() {
    isBooting = true;
    try {
      const data = await fetchJson("/api/tasks");
      tasks = data.tasks;
      if (tasks.length > 0) {
        currentTaskId = tasks[0].task_id;
        await loadTask(currentTaskId, { preserveInputs: false });
      }
    } catch (error) {
      statusText = "Failed to load tasks.";
    } finally {
      isBooting = false;
    }
  }

  async function loadTask(taskId, { preserveInputs = true, forceReset = false } = {}) {
    if (!taskId) return;
    isLoadingTask = true;
    try {
      if (!forceReset && currentTaskId && currentTaskId !== taskId) {
        persistCurrentTaskSession();
      }

      if (!forceReset && restoreTaskSession(taskId)) {
        return;
      }

      if (forceReset) {
        clearTaskSession(taskId);
      }

      const data = await fetchJson(`/api/tasks/${encodeURIComponent(taskId)}`);
      currentTaskId = data.observation.task_id;
      taskMeta = data.task ?? tasks.find((task) => task.task_id === currentTaskId) ?? null;
      observation = data.observation;
      environmentState = data.state;
      if (!preserveInputs) {
        reviewText = "";
        fixCode = data.observation.code;
      }
      resetEvaluation();
      syncModeWithObservation();
      statusText = "Ready";
      persistCurrentTaskSession();
    } catch (error) {
      statusText = "Failed to load scenario.";
    } finally {
      isLoadingTask = false;
    }
  }

  async function restartCurrentTask() {
    if (!currentTaskId) return;
    statusText = "Restarting scenario...";
    await loadTask(currentTaskId, { preserveInputs: false, forceReset: true });
  }

  async function submitCurrentAction() {
    if (!currentTaskId || !observation) return;
    if (isEpisodeDone) {
      statusText = "This episode is complete. Load another scenario to continue.";
      return;
    }

    const content = mode === "review" ? reviewText.trim() : fixCode.trim();
    if (!content) {
      statusText = mode === "review" ? "Write a review first." : "Write the fixed code first.";
      return;
    }

    isSubmitting = true;
    statusText = `Scoring ${phaseLabels[currentPhase]}...`;

    try {
      const data = await fetchJson("/api/step", {
        method: "POST",
        body: JSON.stringify({
          task_id: currentTaskId,
          action: { type: mode, content },
          history: historyPayload(),
        }),
      });
      registerReward(data);
      applyResponse(data, { source: "manual" });

      if (mode === "review" && !data.done) {
        reviewText = "";
      }
    } catch (error) {
      statusText = "Evaluation failed.";
    } finally {
      isSubmitting = false;
    }
  }

  async function runBaseline() {
    if (!currentTaskId) return;
    isRunningBaseline = true;
    resetEvaluation();
    statusText = "Running AI baseline through all 3 steps...";

    try {
      const data = await fetchJson("/api/baseline-review", {
        method: "POST",
        body: JSON.stringify({ task_id: currentTaskId }),
      });
      if (data.submitted_review) {
        await streamReviewText(data.submitted_review);
      }
      if (data.submitted_fixed_code) {
        fixCode = data.submitted_fixed_code;
      }
      registerReward(data);
      applyResponse(data, { source: data.backend ?? "baseline" });
    } catch (error) {
      statusText = "Baseline run failed.";
    } finally {
      isRunningBaseline = false;
    }
  }

  async function getSecondOpinion() {
    const transcript = combinedReviewText();
    if (!currentTaskId || !transcript) return;

    isGettingOpinion = true;
    statusText = "Consulting auditor AI...";
    secondOpinionText = "";
    stopTyping("second-opinion");

    try {
      const data = await fetchJson("/api/second-opinion", {
        method: "POST",
        body: JSON.stringify({ task_id: currentTaskId, review: transcript }),
      });
      await streamSecondOpinion(data.second_opinion);
      statusText = "Second opinion received";
      persistCurrentTaskSession();
    } catch (error) {
      secondOpinionText = "Failed to get second opinion.";
      statusText = "Auditor error";
    } finally {
      isGettingOpinion = false;
    }
  }

  function clearCurrentInput() {
    if (mode === "review") {
      reviewText = "";
      persistCurrentTaskSession();
      return;
    }
    fixCode = observation?.code ?? "";
    persistCurrentTaskSession();
  }

  onMount(() => {
    loadStats();
    loadTaskSessions();
    loadTasks();
  });

  onDestroy(() => {
    clearCelebrationTimer();
    clearEmojiShowerTimer();
    stopAllTyping();
  });
</script>

<header class="topbar">
  <div class="topbar-left">
    <div class="logo-mark">CR</div>
    <div class="logo-text">
      <span>Code Review</span>
      <span class="logo-sub">OpenEnv Lab</span>
    </div>
  </div>
  <div class="topbar-center">
    <div class="stat"><span class="stat-val">{sessionStats.totalScore.toFixed(2)}</span><span class="stat-lbl">Score</span></div>
    <div class="stat-divider"></div>
    <div class="stat"><span class="stat-val">{sessionStats.solvedTasks.size}<span class="stat-dim">/{tasks.length}</span></span><span class="stat-lbl">Solved</span></div>
    <div class="stat-divider"></div>
    <div class="stat"><span class="stat-val">{sessionStats.reviewsGiven ? ((sessionStats.solvedTasks.size / sessionStats.reviewsGiven) * 100).toFixed(0) : 0}%</span><span class="stat-lbl">Accuracy</span></div>
  </div>
  <div class="topbar-right">
    <span class="status-dot" class:active={isBusy}></span>
    <span class="status-text">{statusText}</span>
  </div>
</header>

{#if celebrationState.active}
  {#key celebrationState.run}
    <div class="completion-banner {celebrationState.source}" aria-live="polite">
      <div class="completion-icon" aria-hidden="true">{celebrationState.emoji}</div>
      <div class="completion-copy">
        <span class="completion-kicker">{celebrationState.source === "baseline" ? "Baseline Run" : "Submission Complete"}</span>
        <strong>{celebrationState.title}</strong>
        <span class="completion-detail">{celebrationState.detail}</span>
      </div>
      <div class="completion-score">
        <span>Score</span>
        <strong>{celebrationState.score}</strong>
      </div>
    </div>
  {/key}
{/if}

{#if emojiShower.length > 0}
  <div class="emoji-shower" aria-hidden="true">
    {#each emojiShower as particle (particle.id)}
      <span
        class="emoji-particle"
        style={`left:${particle.left}%; top:${particle.top}px; font-size:${particle.size}px; --emoji-drift:${particle.drift}px; --emoji-rotate:${particle.rotation}deg; animation-delay:${particle.delay}ms; animation-duration:${particle.duration}ms;`}
      >
        {particle.emoji}
      </span>
    {/each}
  </div>
{/if}

<div class="page-wrapper">
  <aside class="sidebar">
    <div class="sidebar-header">
      <h2 class="section-title">Scenarios</h2>
      <div class="filter-bar">
        {#each ["all", "easy", "medium", "hard"] as level}
          <button class="filter-pill" class:active={selectedDifficulty === level} on:click={() => selectedDifficulty = level}>
            {level === "all" ? "All" : level.charAt(0).toUpperCase() + level.slice(1)}
          </button>
        {/each}
      </div>
    </div>

    <div class="task-list">
      {#each filteredTasks as task}
        {@const sidebarStatus = taskStatusById[task.task_id]}
        <button
          class="task-card"
          class:selected={task.task_id === currentTaskId}
          class:solved={sessionStats.solvedTasks.has(task.task_id)}
          class:has-progress={sidebarStatus}
          on:click={() => loadTask(task.task_id, { preserveInputs: false })}
          disabled={isLoadingTask}
        >
          <div class="task-row">
            <span class="diff-dot {task.difficulty}"></span>
            <span class="task-name">{task.title}</span>
            {#if sessionStats.solvedTasks.has(task.task_id)}
              <span class="solved-check">✓</span>
            {/if}
          </div>
          <span class="task-meta">{task.difficulty} · {task.category} · {task.language}</span>
          {#if sidebarStatus}
            <div class="task-status-row">
              <span class="task-status-badge {sidebarStatus.tone}">{sidebarStatus.badge}</span>
              <span class="task-status-copy">{sidebarStatus.detail}</span>
            </div>
          {/if}
        </button>
      {/each}
    </div>
  </aside>

  <main class="main-content">
    <section class="panel code-panel">
      <div class="panel-header">
        <div>
          <div class="panel-label">Observation</div>
          <h2 class="panel-title">{activeTask?.title ?? "Loading..."}</h2>
        </div>
        {#if observation}
          <div class="badge-row">
            <span class="badge {observation.difficulty}">{observation.difficulty}</span>
            <span class="badge neutral">{activeTask?.language ?? "code"}</span>
          </div>
        {/if}
      </div>

      <div class="phase-strip">
        {#each phaseOrder as phase, index}
          <button
            type="button"
            class="step-pill"
            class:active={currentPhase === phase && !isEpisodeDone}
            class:complete={isPhaseComplete(phase)}
            class:locked={!isPhaseUnlocked(phase)}
            on:click={() => handlePhaseClick(phase)}
            title={isPhaseUnlocked(phase) ? phaseLabels[phase] : `Finish ${phaseLabels[currentPhase]} first`}
          >
            <span class="step-index">{index + 1}</span>
            <span>{phaseLabels[phase]}</span>
          </button>
        {/each}
      </div>

      <div class="prompt-card">
        <div class="prompt-top">
          <div class="prompt-phase">{phaseLabels[currentPhase]}</div>
          <div class="prompt-step">Step {Math.min(currentStepNumber, 3)} / 3</div>
        </div>
        <p>{observation?.prompt ?? "Loading prompt..."}</p>
        <span class="prompt-note">{phaseDescriptions[currentPhase]}</span>
      </div>

      <div class="code-frame">
        <div class="code-toolbar">
          <span class="toolbar-dot red"></span>
          <span class="toolbar-dot yellow"></span>
          <span class="toolbar-dot green"></span>
          <span class="toolbar-filename">{observation?.task_id ?? "snippet"}.txt</span>
        </div>
        <pre class="code-block hljs"><code>{@html highlightedCode || " "}</code></pre>
      </div>
    </section>

    <div class="two-col" class:results-mode={isResultsMode}>
      <section class="panel review-panel" class:results-compact={isResultsMode}>
        <div class="panel-header">
          <div>
            <div class="panel-label">Submission</div>
            <h2 class="panel-title">{isResultsMode ? "Episode Summary" : phaseLabels[currentPhase]}</h2>
          </div>
          {#if !isResultsMode}
            <div class="mode-toggle">
              <button class="mode-btn" class:selected={mode === "review"} on:click={() => mode = "review"}>Review</button>
              <button class="mode-btn" class:selected={mode === "fix"} on:click={() => mode = "fix"}>Fix</button>
            </div>
          {/if}
        </div>

        {#if isResultsMode}
          <div class="results-summary" class:celebrating={celebrationState.active}>
            <div class="results-summary-grid">
              <div class="results-summary-lead">
                <div class="panel-label">Episode Complete</div>
                <h3 class="results-summary-title">{activeTask?.title ?? "Scenario complete"}</h3>
                <p class="results-summary-copy">The score is locked in. Open the captured submissions only when you want details, so the scorecard stays front and center.</p>
                <div class="summary-actions">
                  <button class="btn btn-outline" on:click={runBaseline} disabled={isRunningBaseline}>
                    {isRunningBaseline ? "Running..." : "Run AI Baseline"}
                  </button>
                  <button class="btn btn-outline" on:click={restartCurrentTask} disabled={isBusy}>
                    Restart Task
                  </button>
                </div>
              </div>

              <div class="results-stat-card highlight">
                <span class="results-stat-label">Episode Score</span>
                <strong>{formatReward(cumulativeBreakdown.total)}</strong>
                <small>{evaluation.stepHistory.length}/{phaseOrder.length} steps completed</small>
              </div>

              <div class="results-stat-card">
                <span class="results-stat-label">Signals Hit</span>
                <strong>{matchedEpisodeSignals.length}</strong>
                <small>{matchedEpisodeSignals.slice(0, 2).join(" · ") || "No strong matches yet"}</small>
              </div>

              <div class="results-stat-card">
                <span class="results-stat-label">Best Step</span>
                <strong>{bestStepRecord ? phaseLabels[bestStepRecord.phase] : "—"}</strong>
                <small>{bestStepRecord ? `${formatReward(bestStepRecord.reward.breakdown.total)} step score` : "No scored step yet"}</small>
              </div>

              <div class="results-stat-card">
                <span class="results-stat-label">Open Gaps</span>
                <strong>{missingEpisodeSignals.length}</strong>
                <small>{missingEpisodeSignals[0] ?? "No critical gaps left"}</small>
              </div>
            </div>
            <div class="summary-chip-row">
              <span class="chip chip-green">Completed</span>
              <span class="chip chip-neutral">Score {formatReward(cumulativeBreakdown.total)}</span>
              <span class="chip chip-neutral">{evaluation.stepHistory.length}/{phaseOrder.length} steps</span>
            </div>
          </div>

          <details class="summary-drawer">
            <summary>
              <div class="summary-drawer-title">
                <span>Submission Highlights</span>
                <small>{matchedEpisodeSignals.length} matched signals · {missingEpisodeSignals.length} gaps</small>
              </div>
              <div class="summary-drawer-meta">
                <span>{evaluation.stepHistory.length} scored steps</span>
                <span class="summary-drawer-hint">View details</span>
              </div>
            </summary>
            <div class="summary-list">
              {#each evaluation.stepHistory as record}
                <article class="summary-card">
                  <div class="summary-card-top">
                    <div>
                      <strong>{phaseLabels[record.phase]}</strong>
                      <span>{record.action.type}</span>
                    </div>
                    <div class="summary-score">{formatReward(record.reward.breakdown.total)}</div>
                  </div>
                  <p class="summary-copy">{historyPreview(record)}</p>
                  <p class="summary-feedback">{historyFeedbackPreview(record)}</p>
                </article>
              {/each}
            </div>
          </details>
        {:else}
          <div class="submission-note">
            <div>
              <strong>Expected action:</strong> {expectedActionType}
            </div>
            {#if mode !== expectedActionType}
              <div class="warning-note">This mode can still be submitted, but the grader may penalize it as off-phase.</div>
            {/if}
          </div>

          {#if mode === "review"}
            <textarea
              bind:value={reviewText}
              bind:this={reviewTextareaEl}
              class="review-textarea"
              placeholder="Write a focused review for the current step..."
              spellcheck="false"
              rows="10"
              disabled={isEpisodeDone}
            ></textarea>
          {:else}
            <textarea
              bind:value={fixCode}
              class="review-textarea code-font"
              placeholder="Write the corrected code for this scenario..."
              spellcheck="false"
              rows="10"
              disabled={isEpisodeDone}
            ></textarea>
          {/if}

          <div class="review-actions">
            <button class="btn btn-primary" on:click={submitCurrentAction} disabled={isSubmitting || isEpisodeDone}>
              {isSubmitting ? "Scoring..." : "Submit Step"}
            </button>
            <button class="btn btn-outline" on:click={runBaseline} disabled={isRunningBaseline}>
              {isRunningBaseline ? "Running..." : "Run AI Baseline"}
            </button>
            <button class="btn btn-outline" on:click={restartCurrentTask} disabled={isBusy}>
              Restart Task
            </button>
            <button class="btn btn-ghost" on:click={clearCurrentInput}>Clear</button>
          </div>
        {/if}
      </section>

	      <section class="panel eval-panel" bind:this={evaluationPanelEl}>
        <div class="panel-header">
          <div>
            <div class="panel-label">Evaluation</div>
            <h2 class="panel-title">Transparent Scorecard</h2>
          </div>
        </div>

        {#if isBooting}
          <div class="processing-state">
            <div class="spinner"></div>
            <p>Preparing the environment...</p>
          </div>
        {:else if evaluation.reward !== null}
	          <div class="score-display {tone}" class:celebrating={celebrationState.active}>
            <div class="score-number">{formatReward(cumulativeBreakdown.total)}</div>
            <div class="score-verdict">Episode Total / 1.00</div>
            <div class="score-subline">Latest step: {formatReward(evaluation.reward)} · {evaluation.currentStep?.verdict?.replaceAll("_", " ") ?? "evaluated"}</div>
          </div>

          <div class="eval-section">
            <div class="eval-label">Coach Feedback</div>
            <p class="typewriter-text">{typedNarration}</p>
          </div>

          <div class="eval-section">
            <div class="eval-label">Reward Breakdown</div>
            <div class="breakdown-list">
              {#each breakdownRows as row}
                <div class="breakdown-row">
                  <div class="breakdown-head">
                    <span>{row.label}</span>
                    <strong>{formatReward(row.value)} / {row.max.toFixed(1)}</strong>
                  </div>
                  <div class="breakdown-bar">
                    <div class="breakdown-fill" style={`width: ${clampPercent(row.value, row.max)}`}></div>
                  </div>
                </div>
              {/each}
            </div>

            <div class="meta-chip-row">
              <span class="chip chip-green">Structure bonus: {formatReward(cumulativeBreakdown.structure_bonus)}</span>
              <span class="chip chip-red">Irrelevant penalty: {formatReward(cumulativeBreakdown.irrelevant_penalty)}</span>
              <span class="chip chip-red">Hallucinated fix penalty: {formatReward(cumulativeBreakdown.hallucinated_fix_penalty)}</span>
            </div>
          </div>

          <div class="eval-section">
            <div class="eval-label">Latest Signals</div>
            <div class="chip-group">
              {#each listOrFallback(latestMatched, "No strong matches yet") as keyword}
                <span class="chip chip-green">{keyword}</span>
              {/each}
            </div>
          </div>

          <div class="eval-section">
            <div class="eval-label">Missing Signals</div>
            <div class="chip-group">
              {#each listOrFallback(latestMissing, "Nothing critical missing") as keyword}
                <span class="chip chip-red">{keyword}</span>
              {/each}
            </div>
          </div>

          <div class="eval-section">
            <div class="eval-label">Step History</div>
            <div class="history-list">
              {#each evaluation.stepHistory as record}
                <div class="history-card">
                  <div class="history-top">
                    <div>
                      <strong>{phaseLabels[record.phase]}</strong>
                      <span>{record.action.type}</span>
                    </div>
                    <div class="history-score">{formatReward(record.reward.breakdown.total)}</div>
                  </div>
                  <p class="history-copy">{record.action.content}</p>
                  <div class="history-footer">
                    <span>{record.reward.verdict.replaceAll("_", " ")}</span>
                    <span>{record.reward.feedback || record.reward.rationale}</span>
                  </div>
                </div>
              {/each}
            </div>
          </div>

          <div class="eval-meta">
            <div><span>Mode</span><strong>{backendLabel}</strong></div>
            <div><span>Backend</span><strong>{evaluation.info?.grading_backend ?? "deterministic_v2"}</strong></div>
            <div><span>Episode</span><strong>{isEpisodeDone ? "Complete" : "In progress"}</strong></div>
          </div>

          {#if secondOpinionText}
            <div class="eval-section auditor-panel">
              <div class="eval-label auditor-label">Auditor Second Opinion</div>
              <p class="auditor-text">{secondOpinionText}</p>
            </div>
          {:else if evaluation.stepHistory.length > 0}
            <button class="btn btn-outline auditor-btn" on:click={getSecondOpinion} disabled={isGettingOpinion}>
              {isGettingOpinion ? "Consulting..." : "Request Second Opinion"}
            </button>
          {/if}
        {:else}
          <div class="empty-eval">
            <div class="empty-icon">⬡</div>
            <p>Work through the three-step review loop to see detailed rewards, penalties, and history.</p>
          </div>
        {/if}
      </section>
    </div>
  </main>
</div>

<style>
  .topbar {
    position: sticky;
    top: 0;
    z-index: 100;
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 56px;
    padding: 0 28px;
    background: rgba(9, 9, 11, 0.85);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border-bottom: 1px solid var(--border);
  }

  .topbar-left {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .logo-mark {
    width: 32px;
    height: 32px;
    border-radius: var(--radius-sm);
    background: linear-gradient(135deg, #3b82f6, #f59e0b);
    display: grid;
    place-items: center;
    font-weight: 700;
    font-size: 0.75rem;
    letter-spacing: 0.06em;
    color: #fff;
  }

  .logo-text {
    display: flex;
    flex-direction: column;
    line-height: 1.1;
  }

  .logo-text span:first-child {
    font-weight: 600;
    font-size: 0.9rem;
  }

  .logo-sub {
    font-size: 0.7rem;
    color: var(--text-tertiary);
    font-weight: 400;
  }

  .topbar-center {
    display: flex;
    align-items: center;
    gap: 20px;
    background: var(--bg-card);
    padding: 6px 20px;
    border-radius: 99px;
    border: 1px solid var(--border);
  }

  .stat {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .stat-val {
    font-weight: 700;
    font-size: 0.9rem;
    font-family: var(--font-mono);
  }

  .stat-dim {
    color: var(--text-tertiary);
    font-weight: 400;
  }

  .stat-lbl {
    font-size: 0.68rem;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .stat-divider {
    width: 1px;
    height: 18px;
    background: var(--border);
  }

  .topbar-right {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--text-tertiary);
    transition: background 0.3s;
  }

  .status-dot.active {
    background: var(--accent);
    box-shadow: 0 0 8px var(--accent-glow);
    animation: pulse 1.2s ease infinite;
  }

  .status-text {
    font-size: 0.75rem;
    color: var(--text-secondary);
  }

  .completion-banner {
    position: fixed;
    top: 72px;
    right: 24px;
    left: calc(300px + 20px);
    z-index: 120;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 18px;
    padding: 14px 18px;
    border-radius: 18px;
    border: 1px solid rgba(59, 130, 246, 0.28);
    background:
      linear-gradient(120deg, rgba(59, 130, 246, 0.16), rgba(8, 145, 178, 0.08) 45%, rgba(15, 23, 42, 0.92)),
      rgba(9, 9, 11, 0.92);
    box-shadow: 0 20px 60px rgba(2, 6, 23, 0.45);
    backdrop-filter: blur(18px);
    -webkit-backdrop-filter: blur(18px);
    overflow: hidden;
    animation: completion-slide 380ms cubic-bezier(0.2, 0.9, 0.2, 1);
  }

  .emoji-shower {
    position: fixed;
    top: 72px;
    left: calc(300px + 20px);
    right: 24px;
    height: 360px;
    z-index: 119;
    pointer-events: none;
    overflow: hidden;
  }

  .emoji-particle {
    position: absolute;
    opacity: 0;
    transform: translate3d(0, -18px, 0) scale(0.7) rotate(0deg);
    animation-name: emoji-fall;
    animation-timing-function: cubic-bezier(0.18, 0.72, 0.24, 1);
    animation-fill-mode: forwards;
    filter: drop-shadow(0 8px 18px rgba(2, 6, 23, 0.28));
  }

  .completion-banner::before {
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(115deg, transparent 18%, rgba(255,255,255,0.12) 34%, transparent 50%);
    transform: translateX(-130%);
    animation: completion-sheen 2.8s ease-out infinite;
    pointer-events: none;
  }

  .completion-banner.baseline {
    border-color: rgba(245, 158, 11, 0.34);
    background:
      linear-gradient(120deg, rgba(245, 158, 11, 0.16), rgba(34, 197, 94, 0.1) 50%, rgba(15, 23, 42, 0.92)),
      rgba(9, 9, 11, 0.92);
  }

  .completion-copy,
  .completion-icon,
  .completion-score {
    position: relative;
    z-index: 1;
  }

  .completion-icon {
    width: 52px;
    height: 52px;
    flex-shrink: 0;
    display: grid;
    place-items: center;
    border-radius: 16px;
    font-size: 1.7rem;
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.12);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.06);
    animation: completion-pop 520ms cubic-bezier(0.2, 0.9, 0.2, 1);
  }

  .completion-banner.baseline .completion-icon {
    background: rgba(245, 158, 11, 0.14);
    border-color: rgba(245, 158, 11, 0.24);
  }

  .completion-copy {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }

  .completion-kicker {
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: rgba(191, 219, 254, 0.92);
  }

  .completion-copy strong {
    font-size: 1rem;
    font-weight: 700;
    color: var(--text-primary);
  }

  .completion-detail {
    font-size: 0.8rem;
    color: var(--text-secondary);
    line-height: 1.45;
  }

  .completion-score {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 2px;
    white-space: nowrap;
  }

  .completion-score span {
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-tertiary);
  }

  .completion-score strong {
    font-family: var(--font-display);
    font-size: 2rem;
    line-height: 1;
    color: #facc15;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }

  @keyframes completion-slide {
    from {
      opacity: 0;
      transform: translateY(-12px) scale(0.98);
    }
    to {
      opacity: 1;
      transform: translateY(0) scale(1);
    }
  }

  @keyframes completion-pop {
    0% {
      opacity: 0;
      transform: scale(0.78) rotate(-10deg);
    }
    60% {
      opacity: 1;
      transform: scale(1.08) rotate(4deg);
    }
    100% {
      opacity: 1;
      transform: scale(1) rotate(0deg);
    }
  }

  @keyframes emoji-fall {
    0% {
      opacity: 0;
      transform: translate3d(0, -18px, 0) scale(0.7) rotate(0deg);
    }
    10% {
      opacity: 1;
    }
    100% {
      opacity: 0;
      transform: translate3d(var(--emoji-drift), 330px, 0) scale(1.02) rotate(var(--emoji-rotate));
    }
  }

  @keyframes completion-sheen {
    0% {
      transform: translateX(-130%);
    }
    55%, 100% {
      transform: translateX(130%);
    }
  }

  .page-wrapper {
    display: grid;
    grid-template-columns: 300px 1fr;
    min-height: calc(100vh - 56px);
  }

  .sidebar {
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    background: rgba(9, 9, 11, 0.5);
  }

  .sidebar-header {
    padding: 20px;
    border-bottom: 1px solid var(--border);
  }

  .section-title {
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-secondary);
    margin-bottom: 12px;
  }

  .filter-bar {
    display: flex;
    gap: 4px;
    background: var(--bg-card);
    padding: 3px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
  }

  .filter-pill {
    flex: 1;
    background: transparent;
    border: none;
    color: var(--text-secondary);
    padding: 5px 8px;
    border-radius: 6px;
    font-size: 0.72rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .filter-pill.active {
    background: var(--text-primary);
    color: var(--bg-root);
    font-weight: 600;
  }

  .task-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
  }

  .task-card {
    width: 100%;
    text-align: left;
    background: transparent;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    padding: 10px 12px;
    cursor: pointer;
    transition: all 0.12s;
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-bottom: 2px;
  }

  .task-card:hover {
    background: var(--bg-card-hover);
    border-color: var(--border);
  }

  .task-card.selected {
    background: var(--bg-card-hover);
    border-color: var(--border-hover);
  }

  .task-card.solved {
    border-left: 3px solid var(--green);
  }

  .task-card.has-progress:not(.solved) {
    border-left: 3px solid rgba(59, 130, 246, 0.8);
  }

  .task-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .diff-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .diff-dot.easy { background: var(--green); }
  .diff-dot.medium { background: var(--yellow); }
  .diff-dot.hard { background: var(--red); }

  .task-name {
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--text-primary);
    flex: 1;
  }

  .solved-check {
    color: var(--green);
    font-weight: 700;
    font-size: 0.85rem;
  }

  .task-meta {
    font-size: 0.7rem;
    color: var(--text-tertiary);
    padding-left: 16px;
  }

  .task-status-row {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    padding-left: 16px;
    margin-top: 4px;
  }

  .task-status-badge {
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 3px 7px;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: rgba(255,255,255,0.05);
    color: var(--text-secondary);
  }

  .task-status-badge.submitted {
    color: #93c5fd;
    background: rgba(59, 130, 246, 0.12);
    border-color: rgba(59, 130, 246, 0.3);
  }

  .task-status-badge.completed {
    color: var(--green);
    background: var(--green-bg);
    border-color: rgba(34,197,94,0.24);
  }

  .task-status-copy {
    font-size: 0.68rem;
    color: var(--text-secondary);
  }

  .main-content {
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    overflow-y: auto;
  }

  .panel {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    overflow: hidden;
  }

  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding: 18px 20px;
    border-bottom: 1px solid var(--border);
    gap: 14px;
  }

  .panel-label {
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--accent);
    margin-bottom: 4px;
  }

  .panel-title {
    font-family: var(--font-display);
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--text-primary);
    line-height: 1.3;
    margin: 0;
  }

  .badge-row {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .badge {
    font-size: 0.68rem;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 99px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .badge.easy { color: var(--green); background: var(--green-bg); }
  .badge.medium { color: var(--yellow); background: var(--yellow-bg); }
  .badge.hard { color: var(--red); background: var(--red-bg); }
  .badge.neutral { color: var(--text-secondary); background: rgba(255,255,255,0.05); }

  .phase-strip {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    padding: 14px 20px 0;
  }

  .step-pill {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: flex-start;
    gap: 10px;
    padding: 10px 12px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
    background: rgba(255,255,255,0.02);
    color: var(--text-secondary);
    font-size: 0.78rem;
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s, opacity 0.15s;
  }

  .step-pill:hover:not(.locked) {
    border-color: var(--border-hover);
    background: rgba(255,255,255,0.04);
  }

  .step-pill.active {
    border-color: rgba(59, 130, 246, 0.45);
    background: rgba(59, 130, 246, 0.1);
    color: var(--text-primary);
  }

  .step-pill.complete {
    border-color: rgba(34, 197, 94, 0.35);
    background: rgba(34, 197, 94, 0.08);
    color: var(--text-primary);
  }

  .step-pill.locked {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .step-index {
    width: 20px;
    height: 20px;
    display: grid;
    place-items: center;
    border-radius: 50%;
    background: rgba(255,255,255,0.08);
    font-size: 0.72rem;
    font-weight: 700;
  }

  .prompt-card {
    margin: 14px 20px 0;
    padding: 14px 16px;
    border: 1px solid rgba(59, 130, 246, 0.18);
    border-radius: var(--radius-md);
    background: linear-gradient(135deg, rgba(59, 130, 246, 0.08), rgba(245, 158, 11, 0.06));
  }

  .prompt-top {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 10px;
    font-size: 0.74rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .prompt-phase {
    color: var(--text-primary);
    font-weight: 600;
  }

  .prompt-step {
    color: var(--text-secondary);
  }

  .prompt-card p {
    margin: 0;
    color: var(--text-primary);
    line-height: 1.55;
  }

  .prompt-note {
    display: inline-block;
    margin-top: 10px;
    color: var(--text-secondary);
    font-size: 0.8rem;
  }

  .code-frame {
    background: #0c0c0e;
    border-radius: var(--radius-md);
    margin: 14px;
    overflow: hidden;
    border: 1px solid var(--border);
  }

  .code-toolbar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
    background: rgba(255,255,255,0.02);
  }

  .toolbar-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
  }

  .toolbar-dot.red { background: #ff5f57; }
  .toolbar-dot.yellow { background: #febc2e; }
  .toolbar-dot.green { background: #28c840; }

  .toolbar-filename {
    margin-left: 8px;
    font-size: 0.78rem;
    color: var(--text-tertiary);
    font-family: var(--font-mono);
  }

  .code-block {
    margin: 0;
    padding: 18px;
    overflow-x: auto;
    font-family: var(--font-mono);
    font-size: 0.88rem;
    line-height: 1.75;
    background: transparent !important;
  }

  .two-col {
    display: grid;
    grid-template-columns: minmax(360px, 0.92fr) minmax(420px, 1.08fr);
    gap: 16px;
    align-items: start;
  }

  .two-col.results-mode {
    grid-template-columns: minmax(0, 1fr);
  }

  .review-panel,
  .eval-panel {
    min-width: 0;
  }

  .review-panel {
    position: sticky;
    top: 16px;
  }

  .review-panel.results-compact {
    position: static;
  }

  .mode-toggle {
    display: flex;
    background: var(--bg-root);
    border-radius: var(--radius-sm);
    padding: 3px;
    border: 1px solid var(--border);
    width: fit-content;
  }

  .mode-btn {
    background: transparent;
    border: none;
    padding: 6px 12px;
    font-size: 0.75rem;
    font-weight: 500;
    color: var(--text-tertiary);
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .mode-btn.selected {
    background: var(--bg-card-hover);
    color: var(--text-primary);
  }

  .submission-note {
    padding: 12px 20px 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 0.82rem;
    color: var(--text-secondary);
  }

  .warning-note {
    color: #fbbf24;
  }

  .results-summary {
    padding: 18px 20px 14px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    background:
      radial-gradient(circle at top right, rgba(250, 204, 21, 0.08), transparent 34%),
      linear-gradient(180deg, rgba(255,255,255,0.02), transparent 80%);
  }

  .results-summary.celebrating {
    animation: results-glow 1.2s ease;
  }

  .results-summary-grid {
    display: grid;
    grid-template-columns: minmax(280px, 1.4fr) repeat(4, minmax(130px, 1fr));
    gap: 12px;
    align-items: stretch;
  }

  .results-summary-lead,
  .results-stat-card {
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: var(--radius-md);
    background: rgba(255,255,255,0.02);
  }

  .results-summary-lead {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 14px;
  }

  .results-summary-title {
    margin: 0;
    font-family: var(--font-display);
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-primary);
  }

  .results-summary-copy {
    margin: 0;
    color: var(--text-secondary);
    font-size: 0.8rem;
    line-height: 1.55;
    max-width: 640px;
  }

  .results-stat-card {
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    gap: 10px;
    padding: 14px;
    min-width: 0;
  }

  .results-stat-card.highlight {
    background: linear-gradient(180deg, rgba(250, 204, 21, 0.09), rgba(255,255,255,0.03));
    border-color: rgba(250, 204, 21, 0.18);
  }

  .results-stat-label {
    font-size: 0.66rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text-tertiary);
  }

  .results-stat-card strong {
    color: var(--text-primary);
    font-family: var(--font-display);
    font-size: 1.2rem;
    line-height: 1.15;
  }

  .results-stat-card.highlight strong {
    font-size: 2rem;
    color: #facc15;
  }

  .results-stat-card small {
    color: var(--text-secondary);
    font-size: 0.75rem;
    line-height: 1.45;
  }

  .summary-chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .summary-drawer {
    margin: 0 20px 18px;
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    background: rgba(255,255,255,0.015);
    overflow: hidden;
  }

  .summary-drawer summary {
    list-style: none;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    padding: 12px 14px;
    cursor: pointer;
    color: var(--text-secondary);
    font-size: 0.8rem;
    font-weight: 600;
    border-bottom: 1px solid transparent;
  }

  .summary-drawer summary::-webkit-details-marker {
    display: none;
  }

  .summary-drawer[open] summary {
    border-bottom-color: var(--border);
    color: var(--text-primary);
  }

  .summary-drawer-title,
  .summary-drawer-meta {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }

  .summary-drawer-title {
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
  }

  .summary-drawer-title small,
  .summary-drawer-hint {
    color: var(--text-tertiary);
    font-size: 0.72rem;
    font-weight: 500;
  }

  .summary-drawer-hint {
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .summary-list {
    padding: 14px;
    display: flex;
    flex-wrap: wrap;
    align-items: flex-start;
    gap: 12px;
  }

  .summary-card {
    flex: 1 1 240px;
    border: 1px solid var(--border);
    background: rgba(255,255,255,0.02);
    border-radius: var(--radius-md);
    padding: 12px;
    min-width: 0;
    align-self: flex-start;
  }

  .summary-card-top {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 8px;
  }

  .summary-card-top strong {
    display: block;
    color: var(--text-primary);
    font-size: 0.88rem;
  }

  .summary-card-top span {
    color: var(--text-tertiary);
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .summary-score {
    font-family: var(--font-mono);
    color: var(--text-primary);
    white-space: nowrap;
  }

  .summary-copy,
  .summary-feedback {
    margin: 0;
    font-size: 0.8rem;
    line-height: 1.55;
  }

  .summary-copy {
    color: var(--text-secondary);
  }

  .summary-feedback {
    margin-top: 10px;
    color: var(--text-tertiary);
  }

  .review-textarea {
    width: 100%;
    background: var(--bg-input);
    border: none;
    padding: 18px 20px;
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: 0.88rem;
    line-height: 1.65;
    resize: vertical;
    outline: none;
    min-height: 180px;
    transition: background 0.2s;
  }

  .review-textarea:focus {
    background: var(--bg-card-hover);
  }

  .review-textarea.code-font {
    color: #86efac;
  }

  .review-actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    padding: 12px 20px;
    border-top: 1px solid var(--border);
    background: rgba(255,255,255,0.015);
  }

  .summary-actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .btn {
    padding: 8px 18px;
    border-radius: var(--radius-sm);
    font-size: 0.82rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
    border: 1px solid transparent;
  }

  .btn:disabled { opacity: 0.4; cursor: not-allowed; }

  .btn-primary {
    background: var(--text-primary);
    color: var(--bg-root);
    font-weight: 600;
  }

  .btn-outline {
    background: transparent;
    border-color: var(--border-hover);
    color: var(--text-primary);
  }

  .btn-ghost {
    background: transparent;
    color: var(--text-tertiary);
  }

  .score-display {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 22px 20px 16px;
    gap: 6px;
    position: relative;
    overflow: hidden;
  }

  .score-display.celebrating::before {
    content: "";
    position: absolute;
    inset: -30% -20%;
    background: radial-gradient(circle, rgba(250, 204, 21, 0.16), transparent 55%);
    animation: score-bloom 1.4s ease-out;
    pointer-events: none;
  }

  .score-display.celebrating::after {
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(110deg, transparent 12%, rgba(255,255,255,0.12) 30%, transparent 48%);
    transform: translateX(-120%);
    animation: score-sheen 1.6s ease-out;
    pointer-events: none;
  }

  .score-number {
    font-family: var(--font-display);
    font-size: 3.5rem;
    font-weight: 700;
    line-height: 1;
  }

  .score-display.green .score-number { color: var(--green); }
  .score-display.yellow .score-number { color: var(--yellow); }
  .score-display.red .score-number { color: var(--red); }
  .score-display.neutral .score-number { color: var(--text-tertiary); }

  .score-display.green { background: rgba(34,197,94,0.04); }
  .score-display.yellow { background: rgba(234,179,8,0.04); }
  .score-display.red { background: rgba(239,68,68,0.04); }

  @keyframes results-glow {
    0% {
      box-shadow: inset 0 0 0 1px rgba(250, 204, 21, 0);
      transform: translateY(0);
    }
    40% {
      box-shadow: inset 0 0 0 1px rgba(250, 204, 21, 0.2), 0 12px 30px rgba(250, 204, 21, 0.08);
      transform: translateY(-1px);
    }
    100% {
      box-shadow: inset 0 0 0 1px rgba(250, 204, 21, 0);
      transform: translateY(0);
    }
  }

  @keyframes score-bloom {
    0% {
      opacity: 0;
      transform: scale(0.8);
    }
    20% {
      opacity: 1;
    }
    100% {
      opacity: 0;
      transform: scale(1.15);
    }
  }

  @keyframes score-sheen {
    0% {
      transform: translateX(-120%);
    }
    100% {
      transform: translateX(120%);
    }
  }

  .score-verdict {
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-secondary);
    font-weight: 600;
  }

  .score-subline {
    font-size: 0.82rem;
    color: var(--text-secondary);
  }

  .eval-section {
    padding: 14px 20px;
    border-top: 1px solid var(--border);
  }

  .eval-label {
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-tertiary);
    margin-bottom: 10px;
  }

  .typewriter-text {
    font-size: 0.88rem;
    line-height: 1.7;
    color: var(--text-secondary);
    margin: 0;
    white-space: pre-wrap;
    border-right: 2px solid var(--accent);
    padding-right: 2px;
    animation: blink-caret 0.8s step-end infinite;
  }

  @keyframes blink-caret {
    from, to { border-color: transparent; }
    50% { border-color: var(--accent); }
  }

  .breakdown-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .breakdown-row {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .breakdown-head {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    font-size: 0.82rem;
    color: var(--text-secondary);
  }

  .breakdown-bar {
    height: 10px;
    border-radius: 999px;
    background: rgba(255,255,255,0.06);
    overflow: hidden;
  }

  .breakdown-fill {
    height: 100%;
    border-radius: inherit;
    background: linear-gradient(90deg, #3b82f6, #22c55e);
  }

  .meta-chip-row,
  .chip-group {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .meta-chip-row {
    margin-top: 14px;
  }

  .chip {
    font-size: 0.75rem;
    padding: 4px 10px;
    border-radius: 6px;
    font-weight: 500;
  }

  .chip-green {
    color: var(--green);
    background: var(--green-bg);
    border: 1px solid rgba(34,197,94,0.2);
  }

  .chip-neutral {
    color: var(--text-secondary);
    background: rgba(255,255,255,0.04);
    border: 1px solid var(--border);
  }

  .chip-red {
    color: var(--red);
    background: var(--red-bg);
    border: 1px solid rgba(239,68,68,0.2);
  }

  .history-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .history-card {
    border: 1px solid var(--border);
    background: rgba(255,255,255,0.02);
    border-radius: var(--radius-md);
    padding: 12px;
  }

  .history-top {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 8px;
  }

  .history-top strong {
    display: block;
    color: var(--text-primary);
    font-size: 0.9rem;
  }

  .history-top span {
    color: var(--text-tertiary);
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .history-score {
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  .history-copy {
    margin: 0;
    color: var(--text-secondary);
    font-size: 0.84rem;
    line-height: 1.6;
    white-space: pre-wrap;
  }

  .history-footer {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    margin-top: 10px;
    font-size: 0.74rem;
    color: var(--text-tertiary);
  }

  .eval-meta {
    display: flex;
    gap: 20px;
    padding: 14px 20px;
    border-top: 1px solid var(--border);
    background: rgba(255,255,255,0.01);
  }

  .eval-meta div {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .eval-meta span {
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-tertiary);
  }

  .eval-meta strong {
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--text-secondary);
  }

  .empty-eval,
  .processing-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 60px 24px;
    gap: 16px;
    color: var(--text-secondary);
    text-align: center;
  }

  .empty-icon {
    font-size: 2rem;
    opacity: 0.3;
  }

  .spinner {
    width: 24px;
    height: 24px;
    border: 3px solid rgba(255,255,255,0.1);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .auditor-btn {
    width: calc(100% - 40px);
    margin: 14px 20px 20px;
    border-style: dashed;
  }

  .auditor-panel {
    margin: 0 20px 20px;
    padding: 16px;
    border-radius: var(--radius-md);
    background: rgba(245, 158, 11, 0.06);
    border: 1px solid rgba(245, 158, 11, 0.24);
  }

  .auditor-label {
    color: #fbbf24;
  }

  .auditor-text {
    font-size: 0.85rem;
    line-height: 1.6;
    color: var(--text-secondary);
    margin: 0;
    white-space: pre-wrap;
  }

  @media (max-width: 1100px) {
    .page-wrapper {
      grid-template-columns: 1fr;
    }

    .sidebar {
      border-right: none;
      border-bottom: 1px solid var(--border);
      max-height: 300px;
    }

    .two-col {
      grid-template-columns: 1fr;
    }

    .review-panel {
      position: static;
    }

    .topbar-center {
      display: none;
    }
  }

  @media (max-width: 720px) {
    .phase-strip {
      grid-template-columns: 1fr;
    }

    .panel-header,
    .review-actions,
    .eval-meta,
    .history-footer {
      flex-direction: column;
    }

    .prompt-top,
    .history-top {
      flex-direction: column;
    }

    .summary-chip-row {
      align-items: stretch;
    }

    .results-summary-grid {
      grid-template-columns: 1fr;
    }

    .results-summary-lead {
      flex-direction: column;
    }

    .summary-actions {
      justify-content: flex-start;
    }

    .summary-drawer summary,
    .summary-drawer-meta {
      flex-direction: column;
      align-items: flex-start;
    }
  }

  @media (max-width: 1100px) {
    .completion-banner {
      left: 20px;
      right: 20px;
    }

    .emoji-shower {
      left: 20px;
      right: 20px;
    }
  }
</style>
