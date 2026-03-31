<script>
  import { onDestroy } from "svelte";

  export let value = "";
  export let label = "Copy";
  export let successLabel = "Copied";
  export let disabled = false;

  let copied = false;
  let resetTimer;

  async function copyValue() {
    if (!value.trim() || disabled || !navigator?.clipboard) return;

    try {
      await navigator.clipboard.writeText(value);
      copied = true;
      clearTimeout(resetTimer);
      resetTimer = window.setTimeout(() => {
        copied = false;
      }, 1600);
    } catch (error) {
      copied = false;
    }
  }

  onDestroy(() => {
    clearTimeout(resetTimer);
  });
</script>

<button type="button" class="btn btn-ghost btn-copy" on:click={copyValue} disabled={disabled || !value.trim()}>
  {copied ? successLabel : label}
</button>
