<script>
  import DataUnavailable from "$lib/components/DataUnavailable.svelte";
  import LoadingState from "$lib/components/LoadingState.svelte";
  import NoLocality from "$lib/components/NoLocality.svelte";
  import { campPhoneNumbers, campsForLocality, campsSavedLabel } from "$lib/data/camps.js";
  import { currentContext, dataState } from "$lib/data/index.js";
  import { preferencesChanged } from "$lib/data/preferences.js";

  let context = $derived.by(() => {
    $preferencesChanged;
    return $dataState.bundle ? currentContext() : null;
  });
  let matches = $derived(context
    ? campsForLocality($dataState.bundle.camps, context.locality)
    : []);
  let saved = $derived($dataState.bundle
    ? campsSavedLabel($dataState.bundle.camps_saved_at)
    : null);

  function confidenceLabel(camp) {
    const value = camp.geocode_confidence || camp.udise_match_confidence;
    return {
      source_coordinates: "Source coordinates",
      high: "High map confidence",
      medium: "Medium map confidence",
      unverified: "Unverified map location",
    }[value] || "Map confidence not stated";
  }
</script>

{#if $dataState.status === "error"}
  <DataUnavailable error={$dataState.error} />
{:else if !$dataState.bundle}
  <LoadingState />
{:else if !context}
  <NoLocality
    title="Relief camps"
    what="Camp listings are held per revenue circle, so Axom Flood needs to know which place is yours before it can show any."
  />
{:else}
  <section class="screen camps-screen">
    <header class="camps-header">
      <div>
        <h1 class="screen-title" tabindex="-1">Relief camps</h1>
        <p class="camps-place">{context.locality.revenue_circle}, {context.locality.district}</p>
      </div>
      <div class="camps-guidance">
        <p>Listings saved from published district camp documents. Confirm a camp by phone before travelling.</p>
        <p class="saved-count">{matches.length} unique listing{matches.length === 1 ? "" : "s"} saved for this circle</p>
        {#if saved}
          <p class:stale={saved.stale} class="age">{saved.text}</p>
        {:else}
          <p class="age stale">Save date unavailable</p>
        {/if}
      </div>
    </header>
    <div class="list">
      {#if matches.length}
        {#each matches as camp (`${camp.source_document_id}-${camp.source_page}-${camp.name_normalized}`)}
          {@const phones = campPhoneNumbers(camp.contact_phone)}
          <article class="list-card">
            <div><h2>{camp.name_raw}</h2>
              <p><span class="camp-status">{camp.status || "Status not stated"}</span> · {camp.revenue_circle || context.locality.revenue_circle}</p>
              {#if camp.udise_match_confidence === "unverified"}
                <p>Location is unverified. Call the listed contact or district authority before travelling.</p>
              {/if}
            </div>
            <div class="list-meta">
              {#if phones.length}
                <div class="camp-phones" aria-label={`Phone contacts for ${camp.name_raw}`}>
                  {#each phones as phone (phone.dial)}
                    <a href={`tel:${phone.dial}`}>Call {phone.display}</a>
                  {/each}
                </div>
              {/if}
              <span class="tag">{confidenceLabel(camp)}</span>
            </div>
          </article>
        {/each}
      {:else}
        <div class="empty-state">
          <h2>No camp listing is saved for this circle</h2>
          <p>This does not mean no camp is open. Camp lists change quickly and this phone may not have the latest district document.</p>
          <a class="button secondary" href="/emergency/">Call the saved emergency number</a>
        </div>
      {/if}
    </div>
    <p class="source-note">
      Camp lists can change quickly. Call the district authority or ASDMA before travelling when possible.
      {#if matches[0]?.source_url}
        <a href={matches[0].source_url} rel="noopener" target="_blank">Open the district source document.</a>
      {/if}
    </p>
  </section>
{/if}
