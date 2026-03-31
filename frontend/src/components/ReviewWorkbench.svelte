<script>
  import { onDestroy, onMount } from "svelte";
  import confetti from "canvas-confetti";
  import hljs from "highlight.js/lib/core";
  import python from "highlight.js/lib/languages/python";
  import sql from "highlight.js/lib/languages/sql";
  import javascript from "highlight.js/lib/languages/javascript";
  import xml from "highlight.js/lib/languages/xml";
  import go from "highlight.js/lib/languages/go";
  import "./review-workbench/reviewWorkbench.css";
  import CelebrationOverlay from "./review-workbench/CelebrationOverlay.svelte";
  import EvaluationPanel from "./review-workbench/EvaluationPanel.svelte";
  import ObservationPanel from "./review-workbench/ObservationPanel.svelte";
  import ScenarioSidebar from "./review-workbench/ScenarioSidebar.svelte";
  import SubmissionPanel from "./review-workbench/SubmissionPanel.svelte";
  import TopBar from "./review-workbench/TopBar.svelte";
  import {
    SOLVED_THRESHOLD,
    TASK_SESSION_STORAGE_KEY,
    emptyBreakdown,
    emptyEvaluation,
    formatReward,
    normalizeEvaluation,
    phaseLabels,
    phaseOrder,
    summarizeEpisode,
    taskScore,
    uniqueEpisodeSignals,
  } from "./review-workbench/shared.js";

  hljs.registerLanguage("python", python);
  hljs.registerLanguage("sql", sql);
  hljs.registerLanguage("javascript", javascript);
  hljs.registerLanguage("xml", xml);
  hljs.registerLanguage("go", go);

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

  function currentNarration(nextEvaluation = evaluation, nextObservation = observation) {
    if (nextEvaluation?.done) {
      return summarizeEpisode(nextEvaluation.stepHistory ?? []);
    }

    return nextEvaluation?.currentStep?.feedback || nextEvaluation?.currentStep?.rationale || nextObservation?.prompt || "";
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
    const nextSolvedTasks = new Set(sessionStats.solvedTasks);
    const episodeTotal = data.state?.cumulative_reward ?? data.info?.cumulative_breakdown?.total ?? 0;
    const wasSolved = nextSolvedTasks.has(currentTaskId);
    if (data.done && episodeTotal >= SOLVED_THRESHOLD) {
      nextSolvedTasks.add(currentTaskId);
      if (!wasSolved) {
        fireConfetti();
      }
    }

    sessionStats = {
      totalScore: sessionStats.totalScore + (data.reward ?? 0),
      solvedTasks: nextSolvedTasks,
      reviewsGiven: sessionStats.reviewsGiven + 1,
    };

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

  function combinedReviewText() {
    const reviewSteps = evaluation.stepHistory.filter((record) => record.action?.type === "review");
    if (!reviewSteps.length) {
      return reviewText.trim();
    }
    return reviewSteps
      .map((record) => `${phaseLabels[record.phase]}: ${record.action.content}`)
      .join("\n\n");
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

  function handleDifficultyChange(event) {
    selectedDifficulty = event.detail.level;
  }

  function handleTaskSelect(event) {
    loadTask(event.detail.taskId, { preserveInputs: false });
  }

  function handlePhaseSelection(event) {
    handlePhaseClick(event.detail.phase);
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

<TopBar
  {sessionStats}
  tasksLength={tasks.length}
  {statusText}
  {isBusy}
/>

<CelebrationOverlay
  {celebrationState}
  {emojiShower}
/>

<div class="workbench-shell">
  <div class="page-wrapper">
    <ScenarioSidebar
      {filteredTasks}
      {selectedDifficulty}
      {currentTaskId}
      {sessionStats}
      {taskStatusById}
      {isLoadingTask}
      on:difficultychange={handleDifficultyChange}
      on:selecttask={handleTaskSelect}
    />

    <main class="main-content">
      <ObservationPanel
        {activeTask}
        {observation}
        {highlightedCode}
        {currentPhase}
        {currentStepNumber}
        {isEpisodeDone}
        {isPhaseComplete}
        {isPhaseUnlocked}
        on:phaseclick={handlePhaseSelection}
      />

      <div class="two-col" class:results-mode={isResultsMode}>
        <SubmissionPanel
          {isResultsMode}
          celebrationActive={celebrationState.active}
          {activeTask}
          {isRunningBaseline}
          {isBusy}
          {evaluation}
          {cumulativeBreakdown}
          {matchedEpisodeSignals}
          {missingEpisodeSignals}
          {bestStepRecord}
          bind:mode
          {currentPhase}
          {expectedActionType}
          bind:reviewText
          bind:fixCode
          {isEpisodeDone}
          {isSubmitting}
          bind:reviewTextareaEl
          originalCode={observation?.code ?? ""}
          language={activeTask?.language ?? "text"}
          on:submit={submitCurrentAction}
          on:baseline={runBaseline}
          on:restart={restartCurrentTask}
          on:clear={clearCurrentInput}
        />

        <EvaluationPanel
          bind:evaluationPanelEl
          {isBooting}
          {evaluation}
          {tone}
          celebrationActive={celebrationState.active}
          {cumulativeBreakdown}
          {breakdownRows}
          {typedNarration}
          {latestMatched}
          {latestMissing}
          {backendLabel}
          {isEpisodeDone}
          {secondOpinionText}
          {isGettingOpinion}
          {currentPhase}
          {currentStepNumber}
          {statusText}
          on:secondopinion={getSecondOpinion}
        />
      </div>
    </main>
  </div>
</div>
