<script>
  export let pinRail = false;
</script>

<div class="reviewer-workspace-frame" class:reviewer-workspace-frame-pinned={pinRail}>
  <aside class="reviewer-workspace-rail">
    <slot name="rail" />
  </aside>

  <section class="reviewer-workspace-main">
    <slot name="main" />
  </section>
</div>
