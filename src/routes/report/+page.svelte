<script>
  import DataUnavailable from "$lib/components/DataUnavailable.svelte";
  import LoadingState from "$lib/components/LoadingState.svelte";
  import { dataState } from "$lib/data/index.js";
  import { onMount } from "svelte";

  let ReportScreen = $state();
  let loadError = $state();

  onMount(async () => {
    try {
      ReportScreen = (await import("$lib/components/ReportScreen.svelte")).default;
    } catch (error) {
      loadError = error;
    }
  });
</script>

{#if $dataState.status === "error"}
  <DataUnavailable error={$dataState.error} />
{:else if !$dataState.bundle || (!ReportScreen && !loadError)}
  <LoadingState />
{:else if loadError}
  <section class="screen unavailable-screen">
    <header class="state-header">
      <h1 class="screen-title" tabindex="-1">Reporting is not saved yet</h1>
      <p class="screen-intro">Reconnect once to save the reporting screen on this phone, then open it again.</p>
    </header>
    <div class="empty-state">
      <h2>Your river bulletin still works</h2>
      <p>A missing reporting module does not affect official river readings already saved on this phone.</p>
      <a class="button secondary" href="/">Return to river information</a>
    </div>
  </section>
{:else}
  <ReportScreen />
{/if}
