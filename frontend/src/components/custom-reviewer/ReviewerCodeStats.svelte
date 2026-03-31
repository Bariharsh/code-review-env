<script>
  import { computeCodeStats, languageLabel } from "./shared.js";

  export let code = "";
  export let language = "auto";
  export let focus = "";

  $: stats = computeCodeStats(code);
  $: reviewMode = focus.trim() ? "Targeted review" : "General review";
  $: helperCopy = stats.lineCount
    ? `${stats.lineCount} lines detected. ${focus.trim() ? "The reviewer will stay anchored to your chosen goal." : "Add a review goal if you want more focused feedback."}`
    : "Paste code to unlock ranked findings, next steps, and the suggested rewrite view.";
</script>

<div class="reviewer-code-metrics">
  <article class="reviewer-mini-stat">
    <span>Lines</span>
    <strong>{stats.lineCount}</strong>
  </article>
  <article class="reviewer-mini-stat">
    <span>Non-empty</span>
    <strong>{stats.nonEmptyLineCount}</strong>
  </article>
  <article class="reviewer-mini-stat">
    <span>Language</span>
    <strong>{languageLabel(language)}</strong>
  </article>
  <article class="reviewer-mini-stat">
    <span>Mode</span>
    <strong>{reviewMode}</strong>
  </article>
</div>

<p class="reviewer-helper-copy">{helperCopy}</p>
