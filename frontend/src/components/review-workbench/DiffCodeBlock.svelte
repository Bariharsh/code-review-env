<script>
  export let rows = [];
  export let emptyMessage = "No changes to show yet.";
</script>

<div class="diff-code-block">
  {#if rows.length === 0}
    <div class="diff-empty">{emptyMessage}</div>
  {:else}
    <div class="diff-grid-head">
      <span>Old</span>
      <span>New</span>
      <span></span>
      <span>Code</span>
    </div>

    <div class="diff-grid-body">
      {#each rows as row}
        <div class="diff-row {row.type}">
          <span class="diff-line-no">{row.beforeLineNumber ?? "—"}</span>
          <span class="diff-line-no">{row.afterLineNumber ?? "—"}</span>
          <span class="diff-line-mark">{row.type === "add" ? "+" : row.type === "remove" ? "-" : "·"}</span>
          <code class="diff-line-code">{row.content || " "}</code>
        </div>
      {/each}
    </div>
  {/if}
</div>
