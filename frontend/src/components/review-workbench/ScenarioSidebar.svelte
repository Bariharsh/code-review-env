<script>
  import { createEventDispatcher } from "svelte";

  export let filteredTasks = [];
  export let selectedDifficulty = "all";
  export let currentTaskId = "";
  export let sessionStats = { solvedTasks: new Set() };
  export let taskStatusById = {};
  export let isLoadingTask = false;

  const levels = ["all", "easy", "medium", "hard"];
  const dispatch = createEventDispatcher();

  function changeDifficulty(level) {
    dispatch("difficultychange", { level });
  }

  function selectTask(taskId) {
    dispatch("selecttask", { taskId });
  }
</script>

<aside class="sidebar">
  <div class="sidebar-header">
    <h2 class="section-title">Scenarios</h2>
    <div class="filter-bar">
      {#each levels as level}
        <button
          type="button"
          class="filter-pill"
          class:active={selectedDifficulty === level}
          on:click={() => changeDifficulty(level)}
        >
          {level === "all" ? "All" : level.charAt(0).toUpperCase() + level.slice(1)}
        </button>
      {/each}
    </div>
  </div>

  <div class="task-list">
    {#if filteredTasks.length === 0}
      <div class="task-empty">
        <strong>No scenarios here yet</strong>
        <span>Try another difficulty filter to bring tasks back into view.</span>
      </div>
    {:else}
      {#each filteredTasks as task}
        {@const sidebarStatus = taskStatusById[task.task_id]}
        <button
          type="button"
          class="task-card"
          class:selected={task.task_id === currentTaskId}
          class:solved={sessionStats.solvedTasks.has(task.task_id)}
          class:has-progress={Boolean(sidebarStatus)}
          on:click={() => selectTask(task.task_id)}
          disabled={isLoadingTask}
        >
          <div class="task-row">
            <span class="diff-dot {task.difficulty}"></span>
            <span class="task-name">{task.title}</span>
            {#if sessionStats.solvedTasks.has(task.task_id)}
              <span class="solved-check">✓</span>
            {/if}
          </div>
          <span class="task-meta">{task.difficulty} · {task.category} · {task.language}</span>
          {#if sidebarStatus}
            <div class="task-status-row">
              <span class="task-status-badge {sidebarStatus.tone}">{sidebarStatus.badge}</span>
              <span class="task-status-copy">{sidebarStatus.detail}</span>
            </div>
          {/if}
        </button>
      {/each}
    {/if}
  </div>
</aside>
