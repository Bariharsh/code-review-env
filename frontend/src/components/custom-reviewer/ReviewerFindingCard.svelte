<script>
  import { severityLabel } from "./shared.js";

  export let finding = {
    title: "",
    severity: "medium",
    why_it_matters: "",
    evidence: "",
    recommendation: "",
  };
</script>

<article class="reviewer-finding-card {finding.severity}">
  <div class="reviewer-finding-top">
    <div>
      <h4>{finding.title}</h4>
      <span>{severityLabel(finding.severity)}</span>
    </div>
  </div>

  <div class="reviewer-finding-body">
    <div>
      <strong>Why it matters</strong>
      <p>{finding.why_it_matters}</p>
    </div>

    {#if finding.evidence}
      <div>
        <strong>Evidence</strong>
        <p>{finding.evidence}</p>
      </div>
    {/if}

    {#if finding.recommendation}
      <div>
        <strong>Suggested change</strong>
        <p>{finding.recommendation}</p>
      </div>
    {/if}
  </div>
</article>
