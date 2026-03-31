<script>
  import { tick } from "svelte";
  import {
    applyBackspaceBehavior,
    applyCommentToggle,
    applyEnterBehavior,
    applyPairBehavior,
    applyTabBehavior,
    getCursorMeta,
  } from "./editorBehavior.js";
  import { highlightReviewerCode } from "./highlightCode.js";
  import { computeCodeStats, languageLabel } from "./shared.js";

  export let value = "";
  export let language = "auto";
  export let focus = "";
  export let placeholder = "";

  let textareaEl;
  let gutterEl;
  let codeLayerEl;
  let selectionStart = 0;
  let selectionEnd = 0;

  const fileNameByLanguage = {
    python: "review.py",
    javascript: "review.js",
    typescript: "review.ts",
    react: "ReviewComponent.jsx",
    html: "snippet.html",
    sql: "query.sql",
    go: "review.go",
    java: "ReviewSnippet.java",
    text: "snippet.txt",
    auto: "review-input.txt",
  };

  $: lineCount = Math.max(14, (value || "").split("\n").length);
  $: lineNumbers = Array.from({ length: lineCount }, (_, index) => index + 1);
  $: stats = computeCodeStats(value);
  $: modeLabel = focus.trim() ? "Focused review" : "General review";
  $: fileName = fileNameByLanguage[language] ?? fileNameByLanguage.auto;
  $: highlightedCode = highlightReviewerCode(value, language);
  $: cursorMeta = getCursorMeta(value, selectionStart, selectionEnd);

  function syncScroll() {
    if (!textareaEl || !gutterEl || !codeLayerEl) return;
    gutterEl.scrollTop = textareaEl.scrollTop;
    codeLayerEl.scrollTop = textareaEl.scrollTop;
    codeLayerEl.scrollLeft = textareaEl.scrollLeft;
  }

  function updateSelection() {
    if (!textareaEl) return;
    selectionStart = textareaEl.selectionStart ?? 0;
    selectionEnd = textareaEl.selectionEnd ?? selectionStart;
  }

  async function applyEditorOperation(operation, event) {
    if (!operation || !textareaEl) return;

    event.preventDefault();
    value = operation.value;
    await tick();
    textareaEl.focus();
    textareaEl.setSelectionRange(operation.start, operation.end);
    updateSelection();
    syncScroll();
  }

  async function handleKeydown(event) {
    if (!textareaEl) return;

    updateSelection();
    const start = textareaEl.selectionStart ?? 0;
    const end = textareaEl.selectionEnd ?? start;

    if (event.key === "Tab") {
      await applyEditorOperation(
        applyTabBehavior({ value, start, end, language, shiftKey: event.shiftKey }),
        event,
      );
      return;
    }

    if (event.key === "Enter") {
      await applyEditorOperation(applyEnterBehavior({ value, start, end, language }), event);
      return;
    }

    if ((event.metaKey || event.ctrlKey) && event.key === "/") {
      await applyEditorOperation(applyCommentToggle({ value, start, end, language }), event);
      return;
    }

    if (event.key === "Backspace") {
      await applyEditorOperation(applyBackspaceBehavior({ value, start, end }), event);
      return;
    }

    if (!event.metaKey && !event.ctrlKey && !event.altKey && event.key.length === 1) {
      await applyEditorOperation(applyPairBehavior({ value, start, end, key: event.key }), event);
    }
  }
</script>

<div class="reviewer-editor-shell">
  <div class="reviewer-editor-toolbar">
    <div class="reviewer-editor-toolbar-left">
      <div class="reviewer-editor-lights" aria-hidden="true">
        <span></span>
        <span></span>
        <span></span>
      </div>
      <div class="reviewer-editor-file">
        <strong>{fileName}</strong>
        <span>Unsaved review input</span>
      </div>
    </div>

    <div class="reviewer-editor-toolbar-right">
      <span class="reviewer-editor-pill">{languageLabel(language)}</span>
      <span class="reviewer-editor-pill">{modeLabel}</span>
    </div>
  </div>

  <div class="reviewer-editor-body">
    <div class="reviewer-editor-gutter" bind:this={gutterEl} aria-hidden="true">
      {#each lineNumbers as lineNumber}
        <span class:active={lineNumber === cursorMeta.line}>{lineNumber}</span>
      {/each}
    </div>

    <div class="reviewer-editor-surface">
      <div class="reviewer-editor-code-layer" bind:this={codeLayerEl} aria-hidden="true">
        <pre class="reviewer-editor-pre hljs"><code>{@html `${highlightedCode || " "}\n`}</code></pre>

        {#if !value}
          <div class="reviewer-editor-placeholder">{placeholder}</div>
        {/if}
      </div>

      <textarea
        bind:this={textareaEl}
        bind:value
        class="reviewer-editor-textarea"
        rows="18"
        spellcheck="false"
        autocapitalize="off"
        autocomplete="off"
        autocorrect="off"
        wrap="off"
        on:input={updateSelection}
        on:click={updateSelection}
        on:keyup={updateSelection}
        on:select={updateSelection}
        on:scroll={syncScroll}
        on:keydown={handleKeydown}
      ></textarea>
    </div>
  </div>

  <div class="reviewer-editor-footer">
    <div class="reviewer-editor-meta">
      <span>{stats.lineCount} line{stats.lineCount === 1 ? "" : "s"}</span>
      <span>{stats.nonEmptyLineCount} non-empty</span>
      <span>{stats.charCount} chars</span>
      <span>Ln {cursorMeta.line}, Col {cursorMeta.column}</span>
      {#if cursorMeta.selectedChars > 0}
        <span>{cursorMeta.selectedChars} selected</span>
      {/if}
    </div>

    <div class="reviewer-editor-hint">
      <span>Tab / Shift+Tab indents</span>
      <span>Enter keeps indentation</span>
      <span>Ctrl/Cmd + / comments lines</span>
    </div>
  </div>
</div>
