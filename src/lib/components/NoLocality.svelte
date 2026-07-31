<script>
  let { title, what } = $props();
</script>

<section class="screen">
  <header class="screen-header">
    <div><h1 class="screen-title" tabindex="-1">{title}</h1></div>
    <p class="screen-intro">{what}</p>
  </header>
  <p class="no-locality">
    <a class="button" href="/">Choose your place</a>
  </p>
</section>

<style>
  .no-locality {
    margin: 0;
    padding-top: 20px;
    border-top: 1px solid var(--line);
  }
</style>
