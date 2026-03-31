<script>
  export let hasCode = false;
  export let hasGoal = false;
  export let isReviewing = false;
  export let hasResult = false;

  const steps = [
    {
      id: "snippet",
      step: "01",
      title: "Paste Code",
      copy: "Drop in the function, file section, or component you want the assistant to review.",
    },
    {
      id: "goal",
      step: "02",
      title: "Choose Focus",
      copy: "Optionally guide the review toward security, bugs, performance, or maintainability.",
    },
    {
      id: "review",
      step: "03",
      title: "Run Review",
      copy: "The assistant analyzes the code and turns the output into clear comments and suggestions.",
    },
    {
      id: "action",
      step: "04",
      title: "Apply Suggestions",
      copy: "Use the findings, change recommendations, and rewrite diff to improve the code quickly.",
    },
  ];

  function statusFor(stepId) {
    if (stepId === "snippet") {
      return hasCode || isReviewing || hasResult ? "done" : "active";
    }

    if (stepId === "goal") {
      if (hasGoal || isReviewing || hasResult) return "done";
      return hasCode ? "active" : "todo";
    }

    if (stepId === "review") {
      if (hasResult) return "done";
      return isReviewing ? "active" : "todo";
    }

    return hasResult ? "active" : "todo";
  }

  function statusLabel(status) {
    if (status === "done") return "Done";
    if (status === "active") return "Current";
    return "Up next";
  }
</script>

<section class="reviewer-flow-strip" aria-label="Review workflow">
  {#each steps as step}
    <article class="reviewer-flow-card {statusFor(step.id)}">
      <div class="reviewer-flow-top">
        <span class="reviewer-flow-step">{step.step}</span>
        <span class="reviewer-flow-status">{statusLabel(statusFor(step.id))}</span>
      </div>
      <h2>{step.title}</h2>
      <p>{step.copy}</p>
    </article>
  {/each}
</section>
