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
  const TASK_SNAPSHOT_STORAGE_KEY = "cr_task_snapshots_v1";
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
  const evalTabs = [
    { key: "overview", label: "Overview" },
    { key: "signals", label: "Signals" },
    { key: "history", label: "History" },
    { key: "opinion", label: "Second Opinion" },
  ];
  const highlightLanguageMap = {
    python: "python",
    sql: "sql",
    javascript: "javascript",
    react: "javascript",
    html: "xml",
    xml: "xml",
    go: "go",
  };
  const fileExtensionMap = {
    python: "py",
    sql: "sql",
    javascript: "js",
    react: "jsx",
    html: "html",
    xml: "xml",
    go: "go",
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
  let activeEvalTab = "overview";
  let savedTaskSnapshots = {};
  let restoredFromSnapshot = false;
  let reviewTextareaEl;

  let evaluation = emptyEvaluation();
  let typedNarration = "";
  const typingTimers = new Map();

  let sessionStats = { totalScore: 0, solvedTasks: new Set(), reviewsGiven: 0 };

  $: isBusy = isSubmitting || isRunningBaseline || isLoadingTask;
  $: filteredTasks = selectedDifficulty === "all" ? tasks : tasks.filter((task) => task.difficulty === selectedDifficulty);
  $: activeTask = tasks.find((task) => task.task_id === currentTaskId) ?? taskMeta;
  $: codeLanguage = highlightLanguageMap[activeTask?.language] ?? null;
  $: normalizedCode = normalizeCode(observation?.code ?? "");
  $: codeFilename = buildCodeFilename(observation?.task_id, activeTask?.language);
  $: codeLines = buildCodeLines(normalizedCode, codeLanguage);
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

  function loadTaskSnapshots() {
    try {
      const raw = localStorage.getItem(TASK_SNAPSHOT_STORAGE_KEY);
      savedTaskSnapshots = raw ? JSON.parse(raw) : {};
    } catch (error) {
      savedTaskSnapshots = {};
    }
  }

  function saveTaskSnapshots() {
    try {
      localStorage.setItem(TASK_SNAPSHOT_STORAGE_KEY, JSON.stringify(savedTaskSnapshots));
    } catch (error) {}
  }

  function snapshotScore(snapshot) {
    return snapshot?.evaluation?.cumulativeBreakdown?.total ?? snapshot?.environmentState?.cumulative_reward ?? 0;
  }

  function snapshotStepLabel(snapshot) {
    if (!snapshot) return "";
    if (snapshot.completed) {
      return `Completed · ${formatReward(snapshotScore(snapshot))}`;
    }

    const nextStep = Math.min((snapshot.environmentState?.step_count ?? 0) + 1, 3);
    return `Resume at step ${nextStep}/3`;
  }

  function persistCurrentTaskSnapshot() {
    if (!currentTaskId || !observation || evaluation.stepHistory.length === 0) {
      return;
    }

    savedTaskSnapshots = {
      ...savedTaskSnapshots,
      [currentTaskId]: {
        taskMeta,
        observation,
        environmentState,
        reviewText,
        fixCode,
        mode,
        secondOpinionText,
        backendLabel,
        evaluation,
        typedNarration,
        completed: isEpisodeDone,
        savedAt: Date.now(),
      },
    };
    saveTaskSnapshots();
  }

  function restoreTaskSnapshot(taskId) {
    const snapshot = savedTaskSnapshots[taskId];
    if (!snapshot) {
      return false;
    }

    currentTaskId = taskId;
    taskMeta = snapshot.taskMeta ?? tasks.find((task) => task.task_id === taskId) ?? null;
    observation = snapshot.observation ?? null;
    environmentState = snapshot.environmentState ?? null;
    reviewText = snapshot.reviewText ?? "";
    fixCode = snapshot.fixCode ?? "";
    mode = snapshot.mode ?? "review";
    secondOpinionText = snapshot.secondOpinionText ?? "";
    backendLabel = snapshot.backendLabel ?? "manual";
    evaluation = snapshot.evaluation ?? emptyEvaluation();
    typedNarration = snapshot.typedNarration ?? summarizeEpisode(snapshot.evaluation?.stepHistory ?? []);
    activeEvalTab = snapshot.completed ? "overview" : activeEvalTab;
    restoredFromSnapshot = true;
    statusText = snapshot.completed
      ? "Restored completed episode."
      : `Restored saved progress for ${taskMeta?.title ?? taskId}.`;
    return true;
  }

  function clearTaskSnapshot(taskId = currentTaskId) {
    if (!taskId || !savedTaskSnapshots[taskId]) {
      return;
    }

    const nextSnapshots = { ...savedTaskSnapshots };
    delete nextSnapshots[taskId];
    savedTaskSnapshots = nextSnapshots;
    saveTaskSnapshots();
  }

  function fireConfetti() {
    confetti({ particleCount: 120, spread: 80, origin: { y: 0.7 }, colors: ["#3b82f6", "#22c55e", "#f59e0b", "#fff"], zIndex: 99999 });
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
    activeEvalTab = "overview";
    restoredFromSnapshot = false;
    stopAllTyping();
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

  function combinedReviewText() {
    const reviewSteps = evaluation.stepHistory.filter((record) => record.action?.type === "review");
    if (!reviewSteps.length) {
      return reviewText.trim();
    }
    return reviewSteps
      .map((record) => `${phaseLabels[record.phase]}: ${record.action.content}`)
      .join("\n\n");
  }

  function escapeHtml(value) {
    return value
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }

  function normalizeCode(code) {
    return String(code ?? "").replace(/\r\n/g, "\n").replace(/\t/g, "  ").trimEnd();
  }

  function highlightLine(line, language) {
    const content = line.length > 0 ? line : " ";

    try {
      if (language) {
        return hljs.highlight(content, { language, ignoreIllegals: true }).value;
      }
      return hljs.highlightAuto(content).value;
    } catch (error) {
      return escapeHtml(content);
    }
  }

  function buildCodeLines(code, language) {
    const lines = (code || "").split("\n");
    const safeLines = lines.length > 0 ? lines : [""];
    return safeLines.map((line, index) => ({
      number: index + 1,
      html: highlightLine(line, language),
    }));
  }

  function buildCodeFilename(taskId, language) {
    const extension = fileExtensionMap[language] ?? "txt";
    return `${taskId ?? "snippet"}.${extension}`;
  }

  function historyPreview(record) {
    const text = record.action.content.trim();
    if (text.length <= 180) {
      return text;
    }
    return `${text.slice(0, 180).trim()}...`;
  }

  function historyFeedbackPreview(record) {
    const feedback = (record.reward.feedback || record.reward.rationale || "").trim();
    if (feedback.length <= 140) {
      return feedback;
    }
    return `${feedback.slice(0, 140).trim()}...`;
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
    evaluation = {
      reward: data.reward,
      done: data.done,
      currentStep: data.info?.step_evaluation ?? data.info?.score_details ?? null,
      stepHistory: data.info?.step_history ?? data.state?.history ?? [],
      cumulativeBreakdown: data.info?.cumulative_breakdown ?? emptyBreakdown(),
      info: data.info ?? null,
    };

    backendLabel = data.backend ?? source;
    restoredFromSnapshot = false;

    if (data.submitted_fixed_code) {
      fixCode = data.submitted_fixed_code;
    }
    if (data.done && data.submitted_review) {
      reviewText = data.submitted_review;
    }

    syncModeWithObservation();

    const narrative = data.done
      ? summarizeEpisode(evaluation.stepHistory)
      : evaluation.currentStep?.feedback || evaluation.currentStep?.rationale || observation?.prompt || "";
    typeNarration(narrative);

    if (!data.done && observation?.phase === "fix_code" && !fixCode.trim()) {
      fixCode = observation.code;
    }

    if (data.done) {
      activeEvalTab = "overview";
      statusText = `Episode complete: ${formatReward(data.state?.cumulative_reward)} / 1.00`;
    } else {
      statusText = `${phaseLabels[observation.phase]} ready`;
    }

    persistCurrentTaskSnapshot();
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

  async function loadTask(taskId, { preserveInputs = true, restoreSaved = true } = {}) {
    if (!taskId) return;

    if (restoreSaved && restoreTaskSnapshot(taskId)) {
      return;
    }

    isLoadingTask = true;
    try {
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
    } catch (error) {
      statusText = "Failed to load scenario.";
    } finally {
      isLoadingTask = false;
    }
  }

  async function retryTask(taskId = currentTaskId) {
    if (!taskId) return;
    clearTaskSnapshot(taskId);
    await loadTask(taskId, { preserveInputs: false, restoreSaved: false });
    statusText = "Started a fresh run for this task.";
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
      activeEvalTab = "opinion";
      statusText = "Second opinion received";
      persistCurrentTaskSnapshot();
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
      return;
    }
    fixCode = observation?.code ?? "";
  }

  onMount(() => {
    loadStats();
    loadTaskSnapshots();
    loadTasks();
  });

  onDestroy(() => {
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
        <button
          class="task-card"
          class:selected={task.task_id === currentTaskId}
          class:solved={sessionStats.solvedTasks.has(task.task_id)}
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
          {#if savedTaskSnapshots[task.task_id]}
            <div class="task-saved-row">
              <span class="task-saved-badge" class:completed={savedTaskSnapshots[task.task_id].completed}>
                {savedTaskSnapshots[task.task_id].completed ? "Completed" : "Saved"}
              </span>
              <span class="task-saved-copy">{snapshotStepLabel(savedTaskSnapshots[task.task_id])}</span>
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
          <span class="toolbar-filename">{codeFilename}</span>
        </div>
        <div class="code-block" role="region" aria-label="Code under review">
          <div class="code-lines">
            {#each codeLines as line (line.number)}
              <div class="code-line">
                <span class="code-line-number">{line.number}</span>
                <span class="code-line-content hljs">{@html line.html}</span>
              </div>
            {/each}
          </div>
        </div>
      </div>
    </section>

    <div class="two-col" class:results-mode={isResultsMode}>
      <section class="panel review-panel" class:results-compact={isResultsMode}>
        <div class="panel-header">
          <div>
            <div class="panel-label">Submission</div>
            <h2 class="panel-title">{isResultsMode ? "Episode Submission" : phaseLabels[currentPhase]}</h2>
          </div>
          {#if !isResultsMode}
            <div class="mode-toggle">
              <button class="mode-btn" class:selected={mode === "review"} on:click={() => mode = "review"}>Review</button>
              <button class="mode-btn" class:selected={mode === "fix"} on:click={() => mode = "fix"}>Fix</button>
            </div>
          {/if}
        </div>

        {#if isResultsMode}
          <div class="submission-summary">
            <div class="summary-chip-row">
              <span class="chip chip-green">Episode total: {formatReward(cumulativeBreakdown.total)}</span>
              <span class="chip chip-neutral">Backend: {backendLabel}</span>
              <span class="chip chip-neutral">Steps: {evaluation.stepHistory.length}/3</span>
              <span class="chip chip-neutral">{restoredFromSnapshot ? "Restored saved run" : "Saved automatically"}</span>
            </div>
            <p class="submission-summary-copy">
              The episode is complete. Use the tabs on the right to inspect the scorecard, signals, history, and auditor view without stretching the page.
            </p>
            <div class="summary-action-row">
              <button class="btn btn-outline" on:click={() => retryTask(currentTaskId)}>Retry Task</button>
            </div>
          </div>

          <details class="submission-drawer">
            <summary>Review transcript</summary>
            <pre class="submission-preview">{combinedReviewText() || reviewText || "No review transcript captured."}</pre>
          </details>

          {#if fixCode.trim()}
            <details class="submission-drawer">
              <summary>Submitted fix</summary>
              <pre class="submission-preview code-font">{fixCode}</pre>
            </details>
          {/if}
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
            <button class="btn btn-ghost" on:click={clearCurrentInput}>Clear</button>
          </div>
        {/if}
      </section>

      <section class="panel eval-panel">
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
          <div class="score-display {tone}">
            <div class="score-number">{formatReward(cumulativeBreakdown.total)}</div>
            <div class="score-verdict">Episode Total / 1.00</div>
            <div class="score-subline">Latest step: {formatReward(evaluation.reward)} · {evaluation.currentStep?.verdict?.replaceAll("_", " ") ?? "evaluated"}</div>
          </div>

          <div class="eval-tabs">
            {#each evalTabs as tab}
              <button
                type="button"
                class="eval-tab"
                class:active={activeEvalTab === tab.key}
                on:click={() => activeEvalTab = tab.key}
              >
                {tab.label}
              </button>
            {/each}
          </div>

          {#if activeEvalTab === "overview"}
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

            <div class="eval-meta">
              <div><span>Mode</span><strong>{backendLabel}</strong></div>
              <div><span>Backend</span><strong>{evaluation.info?.grading_backend ?? "deterministic_v2"}</strong></div>
              <div><span>Episode</span><strong>{isEpisodeDone ? "Complete" : "In progress"}</strong></div>
            </div>
          {:else if activeEvalTab === "signals"}
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
          {:else if activeEvalTab === "history"}
            <div class="eval-section history-section">
              <div class="eval-label">Step History</div>
              <div class="history-list">
                {#each evaluation.stepHistory as record, index}
                  <div class="history-card">
                    <div class="history-top">
                      <div>
                        <strong>{phaseLabels[record.phase]}</strong>
                        <span>{record.action.type}</span>
                      </div>
                      <div class="history-score">{formatReward(record.reward.breakdown.total)}</div>
                    </div>
                    <p class="history-copy">{historyPreview(record)}</p>
                    <div class="history-detail">
                      <span class="history-detail-label">Coach note</span>
                      <p>{historyFeedbackPreview(record)}</p>
                    </div>
                    <div class="history-footer">
                      <span>Step {index + 1}</span>
                      <span>{record.reward.verdict.replaceAll("_", " ")}</span>
                      <span>{record.action.type}</span>
                    </div>
                  </div>
                {/each}
              </div>
            </div>
          {:else if activeEvalTab === "opinion"}
            {#if secondOpinionText}
              <div class="eval-section auditor-panel">
                <div class="eval-label auditor-label">Auditor Second Opinion</div>
                <p class="auditor-text">{secondOpinionText}</p>
              </div>
            {:else}
              <div class="eval-section opinion-empty">
                <div class="eval-label">Auditor Second Opinion</div>
                <p>Keep the main scorecard compact, and pull in an auditor only when you want another lens on the submission.</p>
                {#if evaluation.stepHistory.length > 0}
                  <button class="btn btn-outline opinion-btn" on:click={getSecondOpinion} disabled={isGettingOpinion}>
                    {isGettingOpinion ? "Consulting..." : "Request Second Opinion"}
                  </button>
                {/if}
              </div>
            {/if}
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

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }

  .page-wrapper {
    display: grid;
    grid-template-columns: 300px 1fr;
    height: calc(100dvh - 56px);
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

  .task-saved-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding-left: 16px;
    margin-top: 6px;
  }

  .task-saved-badge {
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 3px 6px;
    border-radius: 999px;
    background: rgba(255,255,255,0.05);
    color: var(--text-secondary);
    border: 1px solid var(--border);
  }

  .task-saved-badge.completed {
    color: var(--green);
    background: var(--green-bg);
    border-color: rgba(34,197,94,0.22);
  }

  .task-saved-copy {
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
    overflow: auto;
    max-height: min(48vh, 420px);
    background:
      linear-gradient(180deg, rgba(59, 130, 246, 0.04), transparent 18%),
      transparent;
  }

  .code-lines {
    min-width: max-content;
    padding: 16px 0;
    font-family: var(--font-mono);
    font-size: 0.88rem;
    line-height: 1.65;
  }

  .code-line {
    display: grid;
    grid-template-columns: 52px minmax(0, 1fr);
    align-items: start;
  }

  .code-line:hover {
    background: rgba(255,255,255,0.02);
  }

  .code-line-number {
    padding: 0 12px 0 16px;
    color: var(--text-tertiary);
    text-align: right;
    user-select: none;
    border-right: 1px solid rgba(255,255,255,0.05);
  }

  .code-line-content {
    display: block;
    padding: 0 20px;
    color: var(--text-primary);
    white-space: pre;
  }

  .two-col {
    display: grid;
    grid-template-columns: minmax(360px, 0.92fr) minmax(420px, 1.08fr);
    gap: 16px;
    align-items: start;
  }

  .two-col.results-mode {
    grid-template-columns: 1fr;
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

  .submission-summary {
    padding: 16px 20px 6px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .submission-summary-copy {
    margin: 0;
    color: var(--text-secondary);
    font-size: 0.84rem;
    line-height: 1.6;
  }

  .summary-chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .summary-action-row {
    display: flex;
    gap: 10px;
    align-items: center;
  }

  .submission-drawer {
    margin: 0 20px 16px;
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    background: rgba(255,255,255,0.02);
    overflow: hidden;
  }

  .submission-drawer summary {
    list-style: none;
    cursor: pointer;
    padding: 12px 14px;
    font-size: 0.82rem;
    font-weight: 600;
    color: var(--text-primary);
    border-bottom: 1px solid transparent;
  }

  .submission-drawer[open] summary {
    border-bottom-color: var(--border);
  }

  .submission-drawer summary::-webkit-details-marker {
    display: none;
  }

  .submission-preview {
    margin: 0;
    padding: 14px;
    font-family: var(--font-mono);
    font-size: 0.82rem;
    line-height: 1.7;
    color: var(--text-secondary);
    white-space: pre-wrap;
    overflow-x: auto;
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
    padding: 12px 20px;
    border-top: 1px solid var(--border);
    background: rgba(255,255,255,0.015);
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

  .eval-tabs {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    padding: 0 20px 14px;
    border-top: 1px solid var(--border);
    background: rgba(255,255,255,0.015);
  }

  .eval-tab {
    border: 1px solid var(--border);
    background: transparent;
    color: var(--text-secondary);
    border-radius: 999px;
    padding: 8px 12px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.03em;
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s, color 0.15s;
  }

  .eval-tab.active {
    border-color: var(--border-hover);
    background: rgba(255,255,255,0.06);
    color: var(--text-primary);
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
    max-height: 440px;
    overflow-y: auto;
    padding-right: 4px;
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

  .history-detail {
    margin-top: 12px;
    padding: 10px 12px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: rgba(255,255,255,0.015);
  }

  .history-detail-label {
    display: block;
    margin-bottom: 6px;
    color: var(--accent);
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 700;
  }

  .history-detail p {
    margin: 0;
    color: var(--text-secondary);
    font-size: 0.8rem;
    line-height: 1.6;
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

  .opinion-empty {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .opinion-empty p {
    margin: 0;
    color: var(--text-secondary);
    line-height: 1.65;
  }

  .opinion-btn {
    width: fit-content;
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
      height: auto;
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

    .eval-tabs,
    .summary-chip-row {
      align-items: stretch;
    }

    .prompt-top,
    .history-top {
      flex-direction: column;
    }
  }
</style>
