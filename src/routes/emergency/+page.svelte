<script>
  import DataUnavailable from "$lib/components/DataUnavailable.svelte";
  import LoadingState from "$lib/components/LoadingState.svelte";
  import TranslationNotice from "$lib/components/TranslationNotice.svelte";
  import { sourceAgeLabel } from "$lib/data/age.js";
  import { currentContext, dataState } from "$lib/data/index.js";
  import { preferencesChanged } from "$lib/data/preferences.js";

  /* Half a year, not the three days a camp list gets. 1070 has been ASDMA's
     number for years and does not go stale on a weekly cycle, so warning about
     it early would be crying wolf on the one screen where that costs the most.
     What this length does say is that nobody has looked in a very long time. */
  const HELPLINES_STALE_AFTER_DAYS = 180;

  let context = $derived.by(() => {
    $preferencesChanged;
    return $dataState.bundle ? currentContext() : null;
  });
  /* "Checked", not "saved": these are hand-maintained and reviewed, not fetched.
     The screen used to show the river gauge's reading age here. */
  let checked = $derived($dataState.bundle
    ? sourceAgeLabel($dataState.bundle.helplines_updated_at, {
        verb: "Checked",
        staleAfterDays: HELPLINES_STALE_AFTER_DAYS,
      })
    : null);
</script>

{#if $dataState.status === "error"}
  <DataUnavailable error={$dataState.error} />
{:else if !$dataState.bundle}
  <LoadingState />
{:else}
  <!-- These numbers are never gated behind choosing a place. Somebody who
       opened the app for the first time in an emergency still gets them. -->
  <section class="screen emergency-screen">
    <header class="emergency-header">
      <div>
        <h1 class="screen-title" tabindex="-1">Emergency</h1>
        <p class="emergency-lede">One verified state helpline is saved with Axom Flood. Calls require a mobile signal.</p>
      </div>
      <aside class="coverage-boundary" aria-labelledby="coverage-heading">
        <h2 id="coverage-heading">This is not a complete emergency directory</h2>
        <p>Police, ambulance, and district control-room contacts are not yet verified for this app. Use locally issued numbers when you have them.</p>
      </aside>
    </header>
    {#if context}
      <div class="emergency-context">
        <p>Your selected area is <strong>{context.locality.revenue_circle}, {context.locality.district}</strong>. The saved helpline below is state-wide, not district-specific.</p>
      </div>
    {/if}
    <!-- Outside the context block, because these numbers are never gated behind
         choosing a place and neither is the date on them. -->
    {#if checked}
      <p class:stale={checked.stale} class="age">{checked.text}</p>
    {/if}
    <div class="emergency-list">
      {#each $dataState.bundle.helplines as item}
        <a class="emergency-call" href={`tel:${item.number}`}>
          <span class="call-agency">{item.label_en}</span>
          <strong>{item.number}</strong>
          <span class="call-command">Call now <span aria-hidden="true">→</span></span>
        </a>
      {/each}
    </div>
    <p class="source-note">Emergency contacts can change. This screen only includes numbers supplied in the reviewed Axom Flood data bundle.</p>
    <TranslationNotice />
  </section>
{/if}
