<script>
  export let hasCode = false;
  export let hasGoal = false;
  export let isReviewing = false;
  export let hasResult = false;

  $: statusTitle = hasResult
    ? "Review ready"
    : isReviewing
      ? "AI review in progress"
      : hasCode
        ? "Ready to run"
        : "Waiting for snippet";

  $: statusCopy = hasResult
    ? "The result panel now shows the summary, ranked issues, next steps, and upgrade diff."
    : isReviewing
      ? "The reviewer is reading the snippet, checking for issues, and building an action plan."
      : hasGoal
        ? "The snippet has enough context for a more targeted review."
        : "Paste code and optionally set a review focus to get useful feedback fast.";
</script>

<section class="reviewer-hero">
  <div class="reviewer-hero-compact">
    <div class="reviewer-hero-copy">
      <div class="reviewer-kicker">AI Code Review</div>
      <h1>Review code with a cleaner, editor-first workflow.</h1>
      <p>Paste the exact code you want feedback on and get practical review comments, suggested changes, and an improved rewrite when it helps.</p>
    </div>

    <article class="reviewer-hero-status-card">
      <div class="reviewer-kicker">Current Status</div>
      <h2>{statusTitle}</h2>
      <p>{statusCopy}</p>

      <div class="reviewer-hero-pills reviewer-hero-pills-compact">
        <span class="chip chip-neutral">Paste code</span>
        <span class="chip chip-neutral">Review comments</span>
        <span class="chip chip-neutral">Suggested changes</span>
      </div>
    </article>
  </div>
</section>
