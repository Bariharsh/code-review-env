<script>
  export let celebrationState = {
    active: false,
    source: "manual",
    emoji: "",
    title: "",
    detail: "",
    score: "0.00",
    run: 0,
  };

  export let emojiShower = [];
</script>

{#if celebrationState.active}
  {#key celebrationState.run}
    <div class="completion-banner {celebrationState.source}" aria-live="polite">
      <div class="completion-icon" aria-hidden="true">{celebrationState.emoji}</div>
      <div class="completion-copy">
        <span class="completion-kicker">{celebrationState.source === "baseline" ? "Baseline Run" : "Submission Complete"}</span>
        <strong>{celebrationState.title}</strong>
        <span class="completion-detail">{celebrationState.detail}</span>
      </div>
      <div class="completion-score">
        <span>Score</span>
        <strong>{celebrationState.score}</strong>
      </div>
    </div>
  {/key}
{/if}

{#if emojiShower.length > 0}
  <div class="emoji-shower" aria-hidden="true">
    {#each emojiShower as particle (particle.id)}
      <span
        class="emoji-particle"
        style={`left:${particle.left}%; top:${particle.top}px; font-size:${particle.size}px; --emoji-drift:${particle.drift}px; --emoji-rotate:${particle.rotation}deg; animation-delay:${particle.delay}ms; animation-duration:${particle.duration}ms;`}
      >
        {particle.emoji}
      </span>
    {/each}
  </div>
{/if}
