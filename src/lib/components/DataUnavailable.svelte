<script>
  let { error: _error } = $props();
</script>

<section class="screen unavailable-screen">
  <header class="state-header">
    <h1 class="screen-title" tabindex="-1">River information could not open</h1>
    <p class="screen-intro">The saved update is missing or damaged. Reconnect once, then try again.</p>
  </header>
  <div class="empty-state">
    <h2>Your emergency number is still available</h2>
    <p>River readings and camp listings may be unavailable, but the emergency screen is part of the app shell.</p>
    <a class="button" href="/emergency/">Open emergency number</a>
  </div>
</section>
