<script>
  export let sessionStats = { totalScore: 0, solvedTasks: new Set(), reviewsGiven: 0 };
  export let tasksLength = 0;
  export let statusText = "Ready";
  export let isBusy = false;
</script>

<header class="topbar">
  <div class="topbar-left">
    <span class="topbar-kicker">Review Game</span>
    <div class="topbar-copy">
      <strong>Session Snapshot</strong>
      <span>{tasksLength} challenge{tasksLength === 1 ? "" : "s"} available</span>
    </div>
  </div>

  <div class="topbar-center">
    <div class="stat">
      <span class="stat-val">{sessionStats.totalScore.toFixed(2)}</span>
      <span class="stat-lbl">Score</span>
    </div>
    <div class="stat-divider"></div>
    <div class="stat">
      <span class="stat-val">{sessionStats.solvedTasks.size}<span class="stat-dim">/{tasksLength}</span></span>
      <span class="stat-lbl">Solved</span>
    </div>
    <div class="stat-divider"></div>
    <div class="stat">
      <span class="stat-val">
        {sessionStats.reviewsGiven ? ((sessionStats.solvedTasks.size / sessionStats.reviewsGiven) * 100).toFixed(0) : 0}%
      </span>
      <span class="stat-lbl">Accuracy</span>
    </div>
  </div>

  <div class="topbar-right">
    <div class="status-pill" class:active={isBusy} title={statusText}>
      <span class="status-dot" class:active={isBusy}></span>
      <span class="status-text">{statusText}</span>
    </div>
  </div>
</header>
