<script>
  import DiffCodeBlock from "./DiffCodeBlock.svelte";
  import { buildLineDiffRows, splitCodeLines, summarizeDiff } from "./diffUtils.js";

  export let variant = "results";
  export let beforeCode = "";
  export let submittedFix = "";
  export let referenceFix = "";
  export let language = "text";

  let selectedView = "submitted";

  $: views = [
    submittedFix.trim()
      ? {
        id: "submitted",
        label: variant === "live" ? "Live Preview" : "Your Fix",
        copy: variant === "live"
          ? "Compare your current editor changes against the original snippet before submitting."
          : "See exactly what was changed in the submitted fix.",
        code: submittedFix,
      }
      : null,
    referenceFix.trim()
      ? {
        id: "reference",
        label: "Reference Fix",
        copy: "Compare against the grader's reference implementation for a stronger demo story.",
        code: referenceFix,
      }
      : null,
  ].filter(Boolean);

  $: if (!views.some((view) => view.id === selectedView)) {
    selectedView = views[0]?.id ?? "submitted";
  }

  $: activeView = views.find((view) => view.id === selectedView) ?? null;
  $: diffRows = activeView ? buildLineDiffRows(beforeCode, activeView.code) : [];
  $: diffSummary = summarizeDiff(diffRows);
  $: originalLineCount = splitCodeLines(beforeCode).length;
  $: nextLineCount = splitCodeLines(activeView?.code ?? "").length;
  $: hasChanges = diffSummary.changed > 0;
  $: title = variant === "live" ? "Patch Preview" : "Before / After Fix";
  $: subtitle = variant === "live"
    ? "A live code diff helps the fix step feel tangible and demo-ready."
    : "Judges can immediately see the transformation instead of reading only prose.";
</script>

{#if views.length > 0}
  <section class="fix-diff-panel" class:live-preview={variant === "live"}>
    <div class="fix-diff-header">
      <div>
        <div class="panel-label">{variant === "live" ? "Live Diff" : "Fix Diff"}</div>
        <h3 class="fix-diff-title">{title}</h3>
        <p class="fix-diff-copy">{subtitle}</p>
      </div>

      {#if views.length > 1}
        <div class="diff-view-toggle">
          {#each views as view}
            <button
              type="button"
              class="diff-view-btn"
              class:selected={selectedView === view.id}
              on:click={() => selectedView = view.id}
            >
              {view.label}
            </button>
          {/each}
        </div>
      {/if}
    </div>

    <div class="diff-summary-grid">
      <article class="diff-summary-card">
        <span>Changed Lines</span>
        <strong>{diffSummary.changed}</strong>
        <small>{hasChanges ? "Added and removed lines compared to the original." : "No line-level changes detected yet."}</small>
      </article>

      <article class="diff-summary-card positive">
        <span>Lines Added</span>
        <strong>{diffSummary.added}</strong>
        <small>New lines introduced in {activeView?.label?.toLowerCase() ?? "this view"}.</small>
      </article>

      <article class="diff-summary-card negative">
        <span>Lines Removed</span>
        <strong>{diffSummary.removed}</strong>
        <small>Original lines removed or replaced by the fix.</small>
      </article>

      <article class="diff-summary-card">
        <span>Line Count</span>
        <strong>{originalLineCount} → {nextLineCount}</strong>
        <small>{activeView?.copy ?? "Compare versions side by side through the unified diff."}</small>
      </article>
    </div>

    <div class="diff-legend-row">
      <span class="chip chip-neutral">Language {language}</span>
      <span class="chip chip-green">+ Added</span>
      <span class="chip chip-red">- Removed</span>
      <span class="chip chip-neutral">Original lines preserved</span>
    </div>

    <DiffCodeBlock
      rows={diffRows}
      emptyMessage={variant === "live" ? "Start editing the fix to see a live patch preview." : "No fix changes were captured for this run."}
    />
  </section>
{/if}
