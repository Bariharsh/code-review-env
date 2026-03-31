<script>
  import { createEventDispatcher } from "svelte";
  import { phaseDescriptions, phaseLabels, phaseOrder } from "./shared.js";

  export let activeTask = null;
  export let observation = null;
  export let highlightedCode = "";
  export let currentPhase = "identify_bug";
  export let currentStepNumber = 1;
  export let isEpisodeDone = false;
  export let isPhaseComplete = () => false;
  export let isPhaseUnlocked = () => false;

  const dispatch = createEventDispatcher();

  function selectPhase(phase) {
    dispatch("phaseclick", { phase });
  }
</script>

<section class="panel code-panel">
  <div class="panel-header">
    <div>
      <div class="panel-label">Observation</div>
      <h2 class="panel-title">{activeTask?.title ?? "Loading..."}</h2>
    </div>

    {#if observation}
      <div class="badge-row">
        <span class="badge {observation.difficulty}">{observation.difficulty}</span>
        <span class="badge neutral">{activeTask?.language ?? "code"}</span>
      </div>
    {/if}
  </div>

  <div class="phase-strip">
    {#each phaseOrder as phase, index}
      <button
        type="button"
        class="step-pill"
        class:active={currentPhase === phase && !isEpisodeDone}
        class:complete={isPhaseComplete(phase)}
        class:locked={!isPhaseUnlocked(phase)}
        on:click={() => selectPhase(phase)}
        title={isPhaseUnlocked(phase) ? phaseLabels[phase] : `Finish ${phaseLabels[currentPhase]} first`}
      >
        <span class="step-index">{index + 1}</span>
        <span>{phaseLabels[phase]}</span>
      </button>
    {/each}
  </div>

  <div class="prompt-card">
    <div class="prompt-top">
      <div class="prompt-phase">{phaseLabels[currentPhase]}</div>
      <div class="prompt-step">Step {Math.min(currentStepNumber, 3)} / 3</div>
    </div>
    <p>{observation?.prompt ?? "Loading prompt..."}</p>
    <span class="prompt-note">{phaseDescriptions[currentPhase]}</span>
  </div>

  <div class="code-frame">
    <div class="code-toolbar">
      <span class="toolbar-dot red"></span>
      <span class="toolbar-dot yellow"></span>
      <span class="toolbar-dot green"></span>
      <span class="toolbar-filename">{observation?.task_id ?? "snippet"}.txt</span>
    </div>
    <pre class="code-block hljs"><code>{@html highlightedCode || " "}</code></pre>
  </div>
</section>
