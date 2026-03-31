<script>
  import { createEventDispatcher } from "svelte";
  import { reviewerGoalPresets } from "./shared.js";

  export let selectedValue = "";

  const dispatch = createEventDispatcher();
</script>

<div class="reviewer-preset-grid">
  {#each reviewerGoalPresets as preset}
    <button
      type="button"
      class="reviewer-preset-card"
      class:active={selectedValue.trim() === preset.value}
      on:click={() => dispatch("select", { preset })}
    >
      <strong>{preset.label}</strong>
      <span>{preset.description}</span>
    </button>
  {/each}
</div>
