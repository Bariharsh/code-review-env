<script>
  import { createEventDispatcher } from "svelte";
  import ReviewerCodeEditor from "./ReviewerCodeEditor.svelte";
  import ReviewerQuickGoals from "./ReviewerQuickGoals.svelte";
  import { reviewerLanguageOptions } from "./shared.js";

  export let language = "auto";
  export let focus = "";
  export let code = "";
  export let isReviewing = false;
  export let statusText = "Ready";
  export let errorText = "";

  const dispatch = createEventDispatcher();
</script>

<section class="reviewer-panel reviewer-form-panel">
  <div class="reviewer-panel-header">
    <div>
      <div class="reviewer-kicker">Review Setup</div>
      <h2 class="reviewer-panel-title">Paste code and run the review</h2>
      <p class="reviewer-panel-copy">Set the context once, then work directly in the editor-style input.</p>
    </div>
    <div class="reviewer-status">
      <span class="reviewer-status-dot" class:active={isReviewing}></span>
      <span>{statusText}</span>
    </div>
  </div>

  <div class="reviewer-input-stack">
    <div class="reviewer-input-body">
      <div class="reviewer-control-row">
        <div class="reviewer-form-grid reviewer-form-grid-single">
          <label class="reviewer-field">
            <span>Language</span>
            <select bind:value={language} >
              {#each reviewerLanguageOptions as option}
                <option value={option.value}>{option.label}</option>
              {/each}
            </select>
          </label>
        </div>

        <label class="reviewer-field reviewer-focus-field">
          <span>Review Focus</span>
          <textarea
            bind:value={focus}
            rows="2"
            placeholder="Optional: focus on security, bugs, performance, maintainability, or suggested changes."
          ></textarea>
        </label>
      </div>

      <div class="reviewer-field reviewer-field-compact">
        <span>Quick Focus</span>
        <ReviewerQuickGoals selectedValue={focus} on:select={(event) => dispatch("preset", event.detail)} />
      </div>

      <section class="reviewer-editor-stage">
        <div class="reviewer-editor-stage-head">
          <div>
            <div class="reviewer-kicker">Editor</div>
            <h3>Paste the file, function, or component to review</h3>
          </div>
          <p>Use the editor below like a lightweight IDE input instead of a plain textarea.</p>
        </div>

        <div class="reviewer-editor-wrap">
          <ReviewerCodeEditor
            bind:value={code}
            {language}
            {focus}
            placeholder="Paste code from your editor, file, or PR here..."
          />
        </div>
      </section>
    </div>

    <div class="reviewer-input-footer">
      {#if errorText}
        <div class="reviewer-error">{errorText}</div>
      {/if}

      <div class="reviewer-actions reviewer-actions-wide">
        <button type="button" class="btn btn-primary" on:click={() => dispatch("review")} disabled={isReviewing}>
          {isReviewing ? "Reviewing..." : "Review Code"}
        </button>
        <button type="button" class="btn btn-outline" on:click={() => dispatch("demo")} disabled={isReviewing}>
          Load Demo Code
        </button>
        <button type="button" class="btn btn-ghost" on:click={() => dispatch("clear")} disabled={isReviewing}>
          Clear
        </button>
      </div>

      <p class="reviewer-form-note">Best results come from pasting the exact part of the codebase you want feedback on, not the entire project.</p>
    </div>
  </div>
</section>
