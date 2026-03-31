<script>
  import CopyTextButton from "./CopyTextButton.svelte";
  import DiffCodeBlock from "../review-workbench/DiffCodeBlock.svelte";
  import { buildLineDiffRows, splitCodeLines, summarizeDiff } from "../review-workbench/diffUtils.js";
  import { languageLabel } from "./shared.js";

  export let originalCode = "";
  export let improvedCode = "";
  export let language = "text";

  $: diffRows = buildLineDiffRows(originalCode, improvedCode);
  $: diffSummary = summarizeDiff(diffRows);
  $: originalLines = splitCodeLines(originalCode).length;
  $: improvedLines = splitCodeLines(improvedCode).length;
</script>

{#if improvedCode.trim()}
  <section class="reviewer-panel reviewer-diff-panel">
    <div class="reviewer-section-header">
      <div>
        <div class="reviewer-kicker">Suggested Upgrade</div>
        <h3 class="reviewer-section-title">Before / After Improvement</h3>
      </div>
      <div class="reviewer-diff-actions">
        <span class="chip chip-neutral">Language {languageLabel(language)}</span>
        <CopyTextButton value={improvedCode} label="Copy Improved Code" successLabel="Copied" />
      </div>
    </div>

    <div class="reviewer-stat-grid compact">
      <article class="reviewer-stat-card">
        <span>Changed</span>
        <strong>{diffSummary.changed}</strong>
      </article>
      <article class="reviewer-stat-card positive">
        <span>Added</span>
        <strong>{diffSummary.added}</strong>
      </article>
      <article class="reviewer-stat-card negative">
        <span>Removed</span>
        <strong>{diffSummary.removed}</strong>
      </article>
      <article class="reviewer-stat-card">
        <span>Line Count</span>
        <strong>{originalLines} → {improvedLines}</strong>
      </article>
    </div>

    <DiffCodeBlock rows={diffRows} emptyMessage="The reviewer did not produce a concrete code rewrite for this snippet." />
  </section>
{/if}
