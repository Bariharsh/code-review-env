<script>
  import { createEventDispatcher } from "svelte";
  import FixDiffPanel from "./FixDiffPanel.svelte";
  import { formatReward, historyFeedbackPreview, historyPreview, phaseLabels, phaseOrder } from "./shared.js";

  export let isResultsMode = false;
  export let celebrationActive = false;
  export let activeTask = null;
  export let isRunningBaseline = false;
  export let isBusy = false;
  export let evaluation = { stepHistory: [] };
  export let cumulativeBreakdown = { total: 0 };
  export let matchedEpisodeSignals = [];
  export let missingEpisodeSignals = [];
  export let bestStepRecord = null;
  export let mode = "review";
  export let currentPhase = "identify_bug";
  export let expectedActionType = "review";
  export let reviewText = "";
  export let fixCode = "";
  export let isEpisodeDone = false;
  export let isSubmitting = false;
  export let reviewTextareaEl;
  export let originalCode = "";
  export let language = "text";

  const dispatch = createEventDispatcher();

  function selectMode(nextMode) {
    mode = nextMode;
  }

  $: submittedFixRecord = [...(evaluation.stepHistory ?? [])].reverse().find((record) => record.action?.type === "fix");
  $: submittedFix = submittedFixRecord?.action?.content ?? "";
  $: referenceFix = evaluation.info?.reference_fix ?? "";
  $: showLiveDiff = mode === "fix" && !isResultsMode;
</script>

<section class="panel review-panel" class:results-compact={isResultsMode}>
  <div class="panel-header">
    <div>
      <div class="panel-label">Submission</div>
      <h2 class="panel-title">{isResultsMode ? "Episode Summary" : phaseLabels[currentPhase]}</h2>
    </div>

    {#if !isResultsMode}
      <div class="mode-toggle">
        <button type="button" class="mode-btn" class:selected={mode === "review"} on:click={() => selectMode("review")}>Review</button>
        <button type="button" class="mode-btn" class:selected={mode === "fix"} on:click={() => selectMode("fix")}>Fix</button>
      </div>
    {/if}
  </div>

  {#if isResultsMode}
    <div class="results-summary" class:celebrating={celebrationActive}>
      <div class="results-summary-grid">
        <div class="results-summary-lead">
          <div class="panel-label">Episode Complete</div>
          <h3 class="results-summary-title">{activeTask?.title ?? "Scenario complete"}</h3>
          <p class="results-summary-copy">The score is locked in. Open the captured submissions only when you want details, so the scorecard stays front and center.</p>
          <div class="summary-actions">
            <button type="button" class="btn btn-outline" on:click={() => dispatch("baseline")} disabled={isRunningBaseline}>
              {isRunningBaseline ? "Running..." : "Run AI Baseline"}
            </button>
            <button type="button" class="btn btn-outline" on:click={() => dispatch("restart")} disabled={isBusy}>
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

    <FixDiffPanel
      variant="results"
      beforeCode={originalCode}
      {submittedFix}
      {referenceFix}
      {language}
    />
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

    {#if showLiveDiff}
      <FixDiffPanel
        variant="live"
        beforeCode={originalCode}
        submittedFix={fixCode}
        {language}
      />
    {/if}

    <div class="review-actions">
      <button type="button" class="btn btn-primary" on:click={() => dispatch("submit")} disabled={isSubmitting || isEpisodeDone}>
        {isSubmitting ? "Scoring..." : "Submit Step"}
      </button>
      <button type="button" class="btn btn-outline" on:click={() => dispatch("baseline")} disabled={isRunningBaseline}>
        {isRunningBaseline ? "Running..." : "Run AI Baseline"}
      </button>
      <button type="button" class="btn btn-outline" on:click={() => dispatch("restart")} disabled={isBusy}>
        Restart Task
      </button>
      <button type="button" class="btn btn-ghost" on:click={() => dispatch("clear")}>Clear</button>
    </div>
  {/if}
</section>
