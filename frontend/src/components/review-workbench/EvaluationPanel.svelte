<script>
  import { createEventDispatcher } from "svelte";
  import { clampPercent, formatReward, formatVerdict, listOrFallback, phaseLabels, phaseOrder } from "./shared.js";

  export let evaluationPanelEl;
  export let isBooting = true;
  export let evaluation = { reward: null, stepHistory: [], info: null, currentStep: null };
  export let tone = "neutral";
  export let celebrationActive = false;
  export let cumulativeBreakdown = {};
  export let breakdownRows = [];
  export let typedNarration = "";
  export let latestMatched = [];
  export let latestMissing = [];
  export let backendLabel = "manual";
  export let isEpisodeDone = false;
  export let secondOpinionText = "";
  export let isGettingOpinion = false;
  export let currentPhase = "identify_bug";
  export let currentStepNumber = 1;
  export let statusText = "Ready";

  const dispatch = createEventDispatcher();
  const breakdownDescriptions = {
    bug_detected: "How clearly you found the real issue in the code.",
    explanation: "How well you explained the production or security impact.",
    fix: "How correct and complete the proposed fix is.",
  };

  function scoreToneClass(value) {
    if (value >= 0.75) return "green";
    if (value >= 0.4) return "yellow";
    return "red";
  }

  $: latestVerdict = formatVerdict(evaluation.currentStep?.verdict);
  $: completedSteps = evaluation.stepHistory.length;
  $: progressPercent = `${Math.max(0, Math.min(100, (completedSteps / phaseOrder.length) * 100))}%`;
  $: currentFocusLabel = isEpisodeDone ? "Episode complete" : phaseLabels[currentPhase];
  $: nextMove = isEpisodeDone
    ? "This run is complete. Compare with the auditor or restart to try a stronger submission."
    : latestMissing.length > 0
      ? `Strengthen this step by covering ${latestMissing[0]}.`
      : `Stay focused on ${phaseLabels[currentPhase]} and keep the answer specific to the bug.`;
</script>

<section class="panel eval-panel" bind:this={evaluationPanelEl}>
  <div class="panel-header scorecard-header">
    <div>
      <div class="panel-label">Evaluation</div>
      <h2 class="panel-title">Transparent Scorecard</h2>
      <p class="panel-subcopy">See what the grader understood, what changed the score, and what to improve next.</p>
    </div>
    <div class="scorecard-status">
      <span class="scorecard-status-badge" class:complete={isEpisodeDone} class:active={!isEpisodeDone}>
        {isEpisodeDone ? "Episode Complete" : "Live Grading"}
      </span>
      <span class="scorecard-status-copy">{statusText}</span>
    </div>
  </div>

  {#if isBooting}
    <div class="processing-state">
      <div class="spinner"></div>
      <p>Preparing the environment...</p>
    </div>
  {:else if evaluation.reward !== null}
    <div class="score-display {tone}" class:celebrating={celebrationActive}>
      <div class="score-display-top">
        <span class="score-pill">{currentFocusLabel}</span>
        <span class="score-pill neutral">Step {Math.min(currentStepNumber, phaseOrder.length)} / {phaseOrder.length}</span>
      </div>
      <div class="score-number">{formatReward(cumulativeBreakdown.total)}</div>
      <div class="score-verdict">Episode Total / 1.00</div>
      <div class="score-subline">
        Latest step: {formatReward(evaluation.reward)} · {latestVerdict}
      </div>
    </div>

    <div class="score-summary-grid">
      <article class="score-summary-card">
        <span class="score-summary-label">Workflow Progress</span>
        <strong>{completedSteps}/{phaseOrder.length}</strong>
        <div class="mini-progress">
          <span style={`width: ${progressPercent}`}></span>
        </div>
        <small>{isEpisodeDone ? "All steps were submitted and scored." : "The episode advances as each step is graded."}</small>
      </article>

      <article class="score-summary-card">
        <span class="score-summary-label">Current Focus</span>
        <strong>{currentFocusLabel}</strong>
        <small>{isEpisodeDone ? "The score is now locked for this run." : `Step ${Math.min(currentStepNumber, phaseOrder.length)} is active right now.`}</small>
      </article>

      <article class="score-summary-card">
        <span class="score-summary-label">Signals Matched</span>
        <strong>{latestMatched.length}</strong>
        <small>{latestMatched[0] ?? "Strong matches appear here after grading."}</small>
      </article>

      <article class="score-summary-card">
        <span class="score-summary-label">Open Gaps</span>
        <strong>{latestMissing.length}</strong>
        <small>{latestMissing[0] ?? "No critical gaps are highlighted right now."}</small>
      </article>
    </div>

    <div class="eval-section">
      <div class="insight-layout">
        <article class="insight-card insight-primary">
          <div class="eval-label">What The Grader Is Saying</div>
          <p class="typewriter-text">{typedNarration}</p>
        </article>

        <div class="insight-stack">
          <article class="insight-card">
            <div class="eval-label">Current Status</div>
            <p class="insight-copy">{statusText}</p>
          </article>

          <article class="insight-card">
            <div class="eval-label">Best Next Move</div>
            <p class="insight-copy">{nextMove}</p>
          </article>
        </div>
      </div>
    </div>

    <div class="eval-section">
      <div class="section-heading">
        <div>
          <div class="eval-label">Why The Score Moved</div>
          <p class="section-copy">Each scoring pillar contributes to the final episode total.</p>
        </div>
      </div>

      <div class="breakdown-list breakdown-cards">
        {#each breakdownRows as row}
          <article class="breakdown-row breakdown-card">
            <div class="breakdown-head">
              <span>{row.label}</span>
              <strong>{formatReward(row.value)} / {row.max.toFixed(1)}</strong>
            </div>
            <p class="breakdown-copy">{breakdownDescriptions[row.key]}</p>
            <div class="breakdown-bar">
              <div class="breakdown-fill" style={`width: ${clampPercent(row.value, row.max)}`}></div>
            </div>
          </article>
        {/each}
      </div>

      <div class="adjustment-grid">
        <article class="adjustment-card positive">
          <span>Structure Bonus</span>
          <strong>{formatReward(cumulativeBreakdown.structure_bonus)}</strong>
          <small>Rewarded for a clean, well-organized answer.</small>
        </article>

        <article class="adjustment-card negative">
          <span>Irrelevant Penalty</span>
          <strong>{formatReward(cumulativeBreakdown.irrelevant_penalty)}</strong>
          <small>Applied when parts of the response drift off-target.</small>
        </article>

        <article class="adjustment-card negative">
          <span>Hallucinated Fix Penalty</span>
          <strong>{formatReward(cumulativeBreakdown.hallucinated_fix_penalty)}</strong>
          <small>Applied when the proposed fix invents unsupported changes.</small>
        </article>
      </div>
    </div>

    <div class="eval-section">
      <div class="section-heading">
        <div>
          <div class="eval-label">Signal Summary</div>
          <p class="section-copy">These are the concepts the grader detected and the ones it still expected.</p>
        </div>
      </div>

      <div class="signals-grid">
        <article class="signal-card positive">
          <div class="signal-card-top">
            <div>
              <strong>Matched Well</strong>
              <span>{latestMatched[0] ?? "Strong signals will appear here after grading."}</span>
            </div>
            <span class="signal-count positive">{latestMatched.length}</span>
          </div>
          <div class="chip-group">
            {#each listOrFallback(latestMatched, "No strong matches yet") as keyword}
              <span class="chip chip-green">{keyword}</span>
            {/each}
          </div>
        </article>

        <article class="signal-card negative">
          <div class="signal-card-top">
            <div>
              <strong>Still Missing</strong>
              <span>{latestMissing[0] ?? "Nothing critical is missing right now."}</span>
            </div>
            <span class="signal-count negative">{latestMissing.length}</span>
          </div>
          <div class="chip-group">
            {#each listOrFallback(latestMissing, "Nothing critical missing") as keyword}
              <span class="chip chip-red">{keyword}</span>
            {/each}
          </div>
        </article>
      </div>
    </div>

    <div class="eval-section">
      <div class="section-heading">
        <div>
          <div class="eval-label">Step Timeline</div>
          <p class="section-copy">A cleaner view of what you submitted and how each step was judged.</p>
        </div>
      </div>

      <div class="history-list history-timeline">
        {#each evaluation.stepHistory as record, index}
          <article class="history-card timeline-card {scoreToneClass(record.reward.breakdown.total)}">
            <div class="history-index">{index + 1}</div>
            <div class="history-body">
              <div class="history-top">
                <div>
                  <strong>{phaseLabels[record.phase] ?? record.phase?.replaceAll("_", " ")}</strong>
                  <span>{record.action.type === "fix" ? "Submitted fix" : "Submitted review"}</span>
                </div>
                <div class="history-score">{formatReward(record.reward.breakdown.total)}</div>
              </div>

              <p class="history-feedback-callout">{record.reward.feedback || record.reward.rationale}</p>

              <div class="history-chip-row">
                <span class="chip chip-neutral">{formatVerdict(record.reward?.verdict)}</span>
                <span class="chip chip-green">{(record.reward?.matched_keywords ?? []).length} matched</span>
                <span class="chip chip-red">{(record.reward?.missing_keywords ?? []).length} missing</span>
              </div>

              <details class="history-drawer">
                <summary>View submitted {record.action.type}</summary>
                <pre class="history-submission" class:code-font={record.action.type === "fix"}>{record.action.content}</pre>
              </details>
            </div>
          </article>
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
      <button type="button" class="btn btn-outline auditor-btn" on:click={() => dispatch("secondopinion")} disabled={isGettingOpinion}>
        {isGettingOpinion ? "Consulting..." : "Request Second Opinion"}
      </button>
    {/if}
  {:else}
    <div class="empty-eval empty-scorecard">
      <div class="empty-icon">⬡</div>
      <h3>Scorecard appears after your first submission</h3>
      <p>Once you submit a step, this panel will explain the score, show the matched signals, and guide you on what to improve next.</p>
      <div class="empty-path">
        {#each phaseOrder as phase, index}
          <article class="empty-path-card">
            <span>{index + 1}</span>
            <strong>{phaseLabels[phase]}</strong>
          </article>
        {/each}
      </div>
    </div>
  {/if}
</section>
