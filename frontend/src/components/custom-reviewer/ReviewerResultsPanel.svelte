<script>
  import ReviewerCodeDiff from "./ReviewerCodeDiff.svelte";
  import ReviewerFindingCard from "./ReviewerFindingCard.svelte";
  import ReviewerResultOverview from "./ReviewerResultOverview.svelte";
  import { backendLabel, severityLabel, verdictLabel } from "./shared.js";

  export let result = null;
  export let isReviewing = false;
  export let originalCode = "";
  export let language = "auto";
</script>

<section class="reviewer-panel reviewer-results-panel">
  <div class="reviewer-panel-header">
    <div>
      <div class="reviewer-kicker">Review Output</div>
      <h2 class="reviewer-panel-title">Review comments and suggested changes</h2>
      <p class="reviewer-panel-copy">Start with the summary and best next move, then drill into the detailed findings and rewrite suggestions.</p>
    </div>
  </div>

  {#if isReviewing}
    <div class="reviewer-loading-shell">
      <div class="spinner"></div>
      <div class="reviewer-loading-copy">
        <h3>Building your review</h3>
        <p>The reviewer is reading the snippet, checking for issues, and preparing a practical improvement plan.</p>
      </div>

      <div class="reviewer-loading-grid">
        <article class="reviewer-loading-card active">
          <strong>Reading context</strong>
          <span>Parsing the language, structure, and review goal.</span>
        </article>
        <article class="reviewer-loading-card active">
          <strong>Ranking issues</strong>
          <span>Sorting the most important findings by impact and urgency.</span>
        </article>
        <article class="reviewer-loading-card active">
          <strong>Preparing next steps</strong>
          <span>Writing recommended changes and an improved version when possible.</span>
        </article>
      </div>
    </div>
  {:else if result}
    <div class="reviewer-summary-hero {result.risk_level}">
      <div class="reviewer-summary-top">
        <span class="chip chip-neutral">{backendLabel(result.backend)}</span>
        <span class="chip chip-neutral">{verdictLabel(result.overall_verdict)}</span>
        <span class="chip chip-neutral">{severityLabel(result.risk_level)} risk</span>
      </div>
      <p>{result.summary}</p>
    </div>

    <div class="reviewer-stat-grid">
      <article class="reviewer-stat-card">
        <span>Findings</span>
        <strong>{result.findings.length}</strong>
        <small>Concrete issues identified in the snippet.</small>
      </article>
      <article class="reviewer-stat-card">
        <span>Strengths</span>
        <strong>{result.strengths.length}</strong>
        <small>Positive signals worth preserving.</small>
      </article>
      <article class="reviewer-stat-card">
        <span>Next Steps</span>
        <strong>{result.suggested_changes.length}</strong>
        <small>Recommended follow-up improvements.</small>
      </article>
    </div>

    <ReviewerResultOverview {result} />

    <div class="reviewer-results-stack">
      <section class="reviewer-results-section">
        <div class="reviewer-section-header">
          <div>
            <div class="reviewer-kicker">What Is Good</div>
            <h3 class="reviewer-section-title">Strengths</h3>
          </div>
        </div>

        {#if result.strengths.length > 0}
          <div class="reviewer-chip-list">
            {#each result.strengths as strength}
              <span class="chip chip-green">{strength}</span>
            {/each}
          </div>
        {:else}
          <p class="reviewer-muted">The reviewer focused mostly on changes rather than positive highlights.</p>
        {/if}
      </section>

      <section class="reviewer-results-section">
        <div class="reviewer-section-header">
          <div>
            <div class="reviewer-kicker">What Needs Attention</div>
            <h3 class="reviewer-section-title">Findings</h3>
          </div>
        </div>

        {#if result.findings.length > 0}
          <div class="reviewer-finding-grid">
            {#each result.findings as finding}
              <ReviewerFindingCard {finding} />
            {/each}
          </div>
        {:else}
          <p class="reviewer-muted">No major issue was detected in this pass.</p>
        {/if}
      </section>

      <section class="reviewer-results-section">
        <div class="reviewer-section-header">
          <div>
            <div class="reviewer-kicker">What To Do Next</div>
            <h3 class="reviewer-section-title">Suggested Changes</h3>
          </div>
        </div>

        {#if result.suggested_changes.length > 0}
          <div class="reviewer-next-list">
            {#each result.suggested_changes as change}
              <article class="reviewer-next-card">
                <span>{change}</span>
              </article>
            {/each}
          </div>
        {:else}
          <p class="reviewer-muted">No specific follow-up items were returned for this snippet.</p>
        {/if}
      </section>

      <ReviewerCodeDiff
        originalCode={originalCode}
        improvedCode={result.improved_code}
        {language}
      />
    </div>
  {:else}
    <div class="reviewer-empty reviewer-empty-rich">
      <div class="empty-icon">⌘</div>
      <h3>Your review will appear here</h3>
      <p>Submit a snippet to get a summary, a ranked issue list, clear next steps, and a suggested rewrite when the problem is concrete enough to fix.</p>

      <div class="reviewer-empty-grid">
        <article class="reviewer-preview-card">
          <span>1</span>
          <strong>Big-picture summary</strong>
          <p>A quick read on what is working, what is risky, and the overall verdict.</p>
        </article>
        <article class="reviewer-preview-card">
          <span>2</span>
          <strong>Prioritized findings</strong>
          <p>Issues are presented with severity, why they matter, and the best recommendation.</p>
        </article>
        <article class="reviewer-preview-card">
          <span>3</span>
          <strong>Fix plan</strong>
          <p>Users can move from suggested changes to a before / after code comparison without guessing.</p>
        </article>
      </div>
    </div>
  {/if}
</section>
