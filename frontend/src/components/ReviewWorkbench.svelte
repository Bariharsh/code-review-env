<script>
  import { onMount } from "svelte";
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

  let tasks = [];
  let currentTaskId = "";
  let observation = null;
  let reviewText = "";
  let isBooting = true;
  let isLoadingTask = false;
  let isSubmitting = false;
  let isRunningBaseline = false;
  let statusText = "Ready";
  let backendLabel = "manual";
  let selectedDifficulty = "all";

  let sessionStats = { totalScore: 0, solvedTasks: new Set(), reviewsGiven: 0 };

  $: filteredTasks = selectedDifficulty === "all" ? tasks : tasks.filter(t => t.difficulty === selectedDifficulty);

  let evaluation = {
    reward: null, done: null,
    explanation: "Submit a review to see the evaluation.",
    details: null, state: null, submittedReview: "",
  };

  let typedExplanation = "";
  let typingTimeout;

  function typeOut(text, speed = 18) {
    clearTimeout(typingTimeout);
    typedExplanation = "";
    let i = 0;
    function step() {
      if (i < text.length) {
        typedExplanation += text.charAt(i);
        i++;
        typingTimeout = setTimeout(step, speed);
      }
    }
    step();
  }

  function fireConfetti() {
    confetti({ particleCount: 120, spread: 80, origin: { y: 0.7 }, colors: ['#3b82f6','#22c55e','#a855f7','#fff'], zIndex: 99999 });
    setTimeout(() => confetti({ particleCount: 60, spread: 100, origin: { y: 0.5, x: 0.3 }, colors: ['#3b82f6','#22c55e'] }), 200);
    setTimeout(() => confetti({ particleCount: 60, spread: 100, origin: { y: 0.5, x: 0.7 }, colors: ['#a855f7','#fff'] }), 400);
  }

  async function fetchJson(url, options = {}) {
    const r = await fetch(url, { headers: { "Content-Type": "application/json", ...(options.headers ?? {}) }, ...options });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "Request failed.");
    return data;
  }

  function resetEvaluation() {
    backendLabel = "manual";
    evaluation = { reward: null, done: null, explanation: "", details: null, state: null, submittedReview: "" };
    typedExplanation = "";
    clearTimeout(typingTimeout);
  }

  async function loadTasks() {
    isBooting = true;
    try {
      const data = await fetchJson("/api/tasks");
      tasks = data.tasks;
      if (tasks.length > 0) {
        currentTaskId = tasks[0].task_id;
        await loadTask(currentTaskId, { preserveReview: false });
      }
    } catch (e) { statusText = "Failed to load tasks."; }
    finally { isBooting = false; }
  }

  async function loadTask(taskId, { preserveReview = true } = {}) {
    if (!taskId) return;
    isLoadingTask = true;
    try {
      const data = await fetchJson(`/api/tasks/${encodeURIComponent(taskId)}`);
      observation = data.observation;
      currentTaskId = data.observation.task_id;
      if (!preserveReview) reviewText = "";
      resetEvaluation();
      statusText = "Ready";
    } catch (e) { statusText = "Failed to load scenario."; }
    finally { isLoadingTask = false; }
  }

  async function submitReview() {
    if (!currentTaskId || !reviewText.trim()) { statusText = "Write a review first."; return; }
    isSubmitting = true;
    statusText = "Evaluating...";
    try {
      const data = await fetchJson("/api/review", { method: "POST", body: JSON.stringify({ task_id: currentTaskId, review: reviewText.trim() }) });
      backendLabel = "manual";
      evaluation = { reward: data.reward, done: data.done, explanation: data.info.expected_explanation, details: data.info.score_details, state: data.state, submittedReview: data.submitted_review };
      sessionStats.reviewsGiven += 1;
      sessionStats.totalScore += data.reward;
      if (data.reward === 1) { sessionStats.solvedTasks.add(currentTaskId); sessionStats = sessionStats; fireConfetti(); }
      typeOut(data.info.expected_explanation);
      statusText = `Scored: ${data.info.score_details.verdict.replaceAll("_"," ")}`;
    } catch (e) { statusText = "Evaluation failed."; }
    finally { isSubmitting = false; }
  }

  async function runBaseline() {
    if (!currentTaskId) return;
    isRunningBaseline = true;
    statusText = "Running AI reviewer...";
    try {
      const data = await fetchJson("/api/baseline-review", { method: "POST", body: JSON.stringify({ task_id: currentTaskId }) });
      backendLabel = data.backend;
      reviewText = data.submitted_review;
      evaluation = { reward: data.reward, done: data.done, explanation: data.info.expected_explanation, details: data.info.score_details, state: data.state, submittedReview: data.submitted_review };
      sessionStats.reviewsGiven += 1;
      sessionStats.totalScore += data.reward;
      if (data.reward === 1) { sessionStats.solvedTasks.add(currentTaskId); sessionStats = sessionStats; fireConfetti(); }
      typeOut(data.info.expected_explanation);
      statusText = `AI review: ${data.reward.toFixed(1)} reward`;
    } catch (e) { statusText = "AI review failed."; }
    finally { isRunningBaseline = false; }
  }

  function clearReview() { reviewText = ""; resetEvaluation(); }

  function formatReward(v) { return v == null ? "—" : Number(v).toFixed(1); }
  function listOrFallback(v, fb) { return v && v.length > 0 ? v : [fb]; }

  $: activeTask = tasks.find(t => t.task_id === currentTaskId) ?? null;
  $: highlightedCode = observation ? hljs.highlightAuto(observation.code).value : "";
  $: tone = evaluation.reward === 1 ? "green" : evaluation.reward === 0.5 ? "yellow" : evaluation.reward === 0 ? "red" : "neutral";

  onMount(() => loadTasks());
</script>

<!-- ===== HEADER ===== -->
<header class="topbar">
  <div class="topbar-left">
    <div class="logo-mark">CR</div>
    <div class="logo-text">
      <span>Code Review</span>
      <span class="logo-sub">Workspace</span>
    </div>
  </div>
  <div class="topbar-center">
    <div class="stat"><span class="stat-val">{sessionStats.totalScore.toFixed(1)}</span><span class="stat-lbl">Score</span></div>
    <div class="stat-divider"></div>
    <div class="stat"><span class="stat-val">{sessionStats.solvedTasks.size}<span class="stat-dim">/{tasks.length}</span></span><span class="stat-lbl">Solved</span></div>
    <div class="stat-divider"></div>
    <div class="stat"><span class="stat-val">{sessionStats.reviewsGiven ? ((sessionStats.solvedTasks.size / sessionStats.reviewsGiven) * 100).toFixed(0) : 0}%</span><span class="stat-lbl">Accuracy</span></div>
  </div>
  <div class="topbar-right">
    <span class="status-dot" class:active={isSubmitting || isRunningBaseline}></span>
    <span class="status-text">{statusText}</span>
  </div>
</header>

<!-- ===== MAIN CONTENT ===== -->
<div class="page-wrapper">

  <!-- SCENARIO SIDEBAR -->
  <aside class="sidebar">
    <div class="sidebar-header">
      <h2 class="section-title">Scenarios</h2>
      <div class="filter-bar">
        {#each ["all","easy","medium","hard"] as level}
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
          on:click={() => loadTask(task.task_id, { preserveReview: false })}
          disabled={isLoadingTask}
        >
          <div class="task-row">
            <span class="diff-dot {task.difficulty}"></span>
            <span class="task-name">{task.title}</span>
            {#if sessionStats.solvedTasks.has(task.task_id)}
              <span class="solved-check">✓</span>
            {/if}
          </div>
          <span class="task-meta">{task.difficulty} · {task.task_id}</span>
        </button>
      {/each}
    </div>
  </aside>

  <!-- MAIN PANELS -->
  <main class="main-content">

    <!-- CODE OBSERVATION -->
    <section class="panel code-panel">
      <div class="panel-header">
        <div>
          <div class="panel-label">Observation</div>
          <h2 class="panel-title">{activeTask?.title ?? "Loading..."}</h2>
        </div>
        {#if observation}
          <span class="badge {observation.difficulty}">{observation.difficulty}</span>
        {/if}
      </div>
      <div class="code-frame">
        <div class="code-toolbar">
          <span class="toolbar-dot red"></span>
          <span class="toolbar-dot yellow"></span>
          <span class="toolbar-dot green"></span>
          <span class="toolbar-filename">{observation?.task_id ?? "snippet"}.py</span>
        </div>
        <pre class="code-block hljs"><code>{@html highlightedCode || " "}</code></pre>
      </div>
    </section>

    <!-- REVIEW + EVALUATION -->
    <div class="two-col">

      <!-- REVIEW INPUT -->
      <section class="panel review-panel">
        <div class="panel-header">
          <div>
            <div class="panel-label">Your Review</div>
            <h2 class="panel-title">Write your analysis</h2>
          </div>
        </div>
        <textarea
          bind:value={reviewText}
          class="review-textarea"
          placeholder="Explain the bug, why it matters, and what the fix should be..."
          spellcheck="false"
          rows="8"
        ></textarea>
        <div class="review-actions">
          <button class="btn btn-primary" on:click={submitReview} disabled={isSubmitting}>
            {isSubmitting ? "Evaluating..." : "Submit Review"}
          </button>
          <button class="btn btn-outline" on:click={runBaseline} disabled={isRunningBaseline}>
            {isRunningBaseline ? "Running..." : "Run AI Baseline"}
          </button>
          <button class="btn btn-ghost" on:click={clearReview}>Clear</button>
        </div>
      </section>

      <!-- EVALUATION PANEL -->
      <section class="panel eval-panel">
        <div class="panel-header">
          <div>
            <div class="panel-label">Evaluation</div>
            <h2 class="panel-title">AI Scorecard</h2>
          </div>
        </div>

        {#if evaluation.reward !== null}
          <div class="score-display {tone}">
            <div class="score-number">{formatReward(evaluation.reward)}</div>
            <div class="score-verdict">{evaluation.details?.verdict?.replaceAll("_"," ") ?? "Evaluated"}</div>
          </div>

          <div class="eval-section">
            <div class="eval-label">Expected Rationale</div>
            <p class="typewriter-text">{typedExplanation}</p>
          </div>

          <div class="eval-section">
            <div class="eval-label">Matched Signals</div>
            <div class="chip-group">
              {#each listOrFallback(evaluation.details?.matched_keywords, "No matches yet") as kw}
                <span class="chip chip-green">{kw}</span>
              {/each}
            </div>
          </div>

          <div class="eval-section">
            <div class="eval-label">Missing Signals</div>
            <div class="chip-group">
              {#each listOrFallback(evaluation.details?.missing_keywords, "All matched ✓") as kw}
                <span class="chip chip-red">{kw}</span>
              {/each}
            </div>
          </div>

          <div class="eval-meta">
            <div><span>Backend</span><strong>{backendLabel}</strong></div>
            <div><span>Overlap</span><strong>{(evaluation.details?.semantic_overlap ?? 0).toFixed(3)}</strong></div>
          </div>
        {:else}
          <div class="empty-eval">
            <div class="empty-icon">⬡</div>
            <p>Submit a review or run the baseline to see the AI evaluation.</p>
          </div>
        {/if}
      </section>
    </div>

  </main>
</div>

<style>
  /* =================== TOPBAR =================== */
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
    background: linear-gradient(135deg, #3b82f6, #8b5cf6);
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

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }

  .status-text {
    font-size: 0.75rem;
    color: var(--text-secondary);
  }

  /* =================== PAGE LAYOUT =================== */
  .page-wrapper {
    display: grid;
    grid-template-columns: 300px 1fr;
    min-height: calc(100vh - 56px);
  }

  /* =================== SIDEBAR =================== */
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

  .filter-pill:hover { color: var(--text-primary); }

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

  .task-card:disabled { opacity: 0.5; cursor: wait; }

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

  /* =================== MAIN =================== */
  .main-content {
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 20px;
    overflow-y: auto;
  }

  /* =================== PANELS =================== */
  .panel {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    overflow: hidden;
    transition: border-color 0.2s;
  }

  .panel:hover {
    border-color: var(--border-hover);
  }

  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding: 20px 24px;
    border-bottom: 1px solid var(--border);
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

  /* =================== CODE PANEL =================== */
  .code-frame {
    background: #0c0c0e;
    border-radius: var(--radius-md);
    margin: 16px;
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
    padding: 20px;
    overflow-x: auto;
    font-family: var(--font-mono);
    font-size: 0.88rem;
    line-height: 1.75;
    background: transparent !important;
  }

  .code-block code {
    display: block;
    white-space: pre;
    word-break: normal;
    word-wrap: normal;
  }

  /* =================== TWO COL =================== */
  .two-col {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
  }

  /* =================== REVIEW PANEL =================== */
  .review-textarea {
    width: 100%;
    background: var(--bg-input);
    border: none;
    padding: 20px 24px;
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: 0.88rem;
    line-height: 1.65;
    resize: vertical;
    outline: none;
    min-height: 160px;
    transition: background 0.2s;
  }

  .review-textarea:focus {
    background: var(--bg-card-hover);
  }

  .review-textarea::placeholder {
    color: var(--text-tertiary);
  }

  .review-actions {
    display: flex;
    gap: 8px;
    padding: 14px 24px;
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

  .btn-primary:hover:not(:disabled) {
    box-shadow: 0 0 20px rgba(255,255,255,0.15);
    transform: translateY(-1px);
  }

  .btn-outline {
    background: transparent;
    border-color: var(--border-hover);
    color: var(--text-primary);
  }

  .btn-outline:hover:not(:disabled) {
    background: var(--bg-card-hover);
    border-color: var(--border-focus);
  }

  .btn-ghost {
    background: transparent;
    color: var(--text-tertiary);
  }

  .btn-ghost:hover:not(:disabled) {
    color: var(--text-secondary);
  }

  /* =================== EVALUATION PANEL =================== */
  .score-display {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 28px 24px 20px;
    gap: 4px;
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

  .eval-section {
    padding: 16px 24px;
    border-top: 1px solid var(--border);
  }

  .eval-label {
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-tertiary);
    margin-bottom: 8px;
  }

  .typewriter-text {
    font-size: 0.88rem;
    line-height: 1.6;
    color: var(--text-secondary);
    margin: 0;
    border-right: 2px solid var(--accent);
    padding-right: 2px;
    animation: blink-caret 0.8s step-end infinite;
  }

  @keyframes blink-caret {
    from, to { border-color: transparent; }
    50% { border-color: var(--accent); }
  }

  .chip-group {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .chip {
    font-size: 0.75rem;
    padding: 3px 10px;
    border-radius: 6px;
    font-weight: 500;
  }

  .chip-green {
    color: var(--green);
    background: var(--green-bg);
    border: 1px solid rgba(34,197,94,0.2);
  }

  .chip-red {
    color: var(--red);
    background: var(--red-bg);
    border: 1px solid rgba(239,68,68,0.2);
  }

  .eval-meta {
    display: flex;
    gap: 20px;
    padding: 16px 24px;
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

  .empty-eval {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 48px 24px;
    color: var(--text-tertiary);
    text-align: center;
    gap: 12px;
  }

  .empty-icon {
    font-size: 2rem;
    opacity: 0.3;
  }

  .empty-eval p {
    font-size: 0.85rem;
    max-width: 24ch;
    margin: 0;
    line-height: 1.5;
  }

  /* =================== RESPONSIVE =================== */
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

    .topbar-center { display: none; }
  }
</style>
