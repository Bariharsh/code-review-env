<script>
  import "./custom-reviewer/reviewer.css";
  import ReviewerHeroPanel from "./custom-reviewer/ReviewerHeroPanel.svelte";
  import ReviewerInputPanel from "./custom-reviewer/ReviewerInputPanel.svelte";
  import ReviewerResultsPanel from "./custom-reviewer/ReviewerResultsPanel.svelte";
  import ReviewerWorkspaceFrame from "./custom-reviewer/ReviewerWorkspaceFrame.svelte";
  import { demoSnippet, emptyCustomReviewResult } from "./custom-reviewer/shared.js";

  let language = "auto";
  let focus = "";
  let code = "";
  let isReviewing = false;
  let statusText = "Ready";
  let errorText = "";
  let result = null;
  let lastSubmittedCode = "";
  let lastSubmittedLanguage = "auto";

  $: hasCode = Boolean(code.trim());
  $: hasGoal = Boolean(focus.trim());
  $: hasResult = Boolean(result);
  $: pinWorkspaceRail = hasResult || isReviewing;

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
      ...options,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Request failed.");
    return data;
  }

  async function reviewSnippet() {
    if (!code.trim()) {
      errorText = "Paste some code first so the reviewer has something to analyze.";
      statusText = "Waiting for code";
      return;
    }

    isReviewing = true;
    errorText = "";
    statusText = "Reviewing snippet...";

    try {
      const data = await fetchJson("/api/custom-review", {
        method: "POST",
        body: JSON.stringify({
          language: language === "auto" ? "" : language,
          focus,
          code,
        }),
      });
      result = { ...emptyCustomReviewResult(), ...data };
      lastSubmittedCode = code;
      lastSubmittedLanguage = language;
      statusText = "Review complete";
    } catch (error) {
      result = null;
      errorText = error.message || "Review failed.";
      statusText = "Review failed";
    } finally {
      isReviewing = false;
    }
  }

  function clearForm() {
    language = "auto";
    focus = "";
    code = "";
    errorText = "";
    result = null;
    lastSubmittedCode = "";
    lastSubmittedLanguage = "auto";
    statusText = "Ready";
  }

  function loadDemo() {
    const demo = demoSnippet();
    language = demo.language;
    focus = demo.focus;
    code = demo.code;
    errorText = "";
    statusText = "Demo snippet loaded";
  }

  function applyPreset(event) {
    focus = event.detail.preset.value;
    errorText = "";
    statusText = `${event.detail.preset.label} goal loaded`;
  }
</script>

<div class="reviewer-shell">
  <div class="reviewer-shell-inner">
    <ReviewerHeroPanel {hasCode} {hasGoal} {isReviewing} {hasResult} />

    <ReviewerWorkspaceFrame pinRail={pinWorkspaceRail}>
      <ReviewerInputPanel
        slot="rail"
        bind:language
        bind:focus
        bind:code
        {isReviewing}
        {statusText}
        {errorText}
        on:review={reviewSnippet}
        on:clear={clearForm}
        on:demo={loadDemo}
        on:preset={applyPreset}
      />

      <ReviewerResultsPanel
        slot="main"
        {result}
        {isReviewing}
        originalCode={lastSubmittedCode}
        language={lastSubmittedLanguage}
      />
    </ReviewerWorkspaceFrame>
  </div>
</div>
