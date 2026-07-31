<script>
  import LocateButton from "./LocateButton.svelte";
  import LocationSearch from "./LocationSearch.svelte";
  import { ageLabel, getBundle, isCurrent, stateOverview, statusInfo } from "$lib/data/index.js";
  import { selectLocality } from "$lib/data/preferences.js";

  const bundle = getBundle();
  const overview = stateOverview();
  const gauges = new Map(bundle.gauges.map(gauge => [gauge.cwc_station_code, gauge]));
  const freshest = bundle.gauges.filter(isCurrent)
    .sort((a, b) => Date.parse(b.observed_at) - Date.parse(a.observed_at))[0];

  let mapVisible = $state(false);
  let MapPicker = $state();
  let mapError = $state("");

  async function toggleMap() {
    if (mapVisible) {
      mapVisible = false;
      return;
    }
    mapVisible = true;
    mapError = "";
    try {
      MapPicker = (await import("./MapPicker.svelte")).default;
    } catch (_) {
      mapError = "The map is not saved on this phone yet. Reconnect once to keep it, or search for your place by name.";
    }
  }

  function chooseMap(selection) {
    selectLocality(selection.locality_id, {
      method: "manual_map",
      label: selection.label,
      selected_at: new Date().toISOString(),
    });
  }

  function chooseRaised(locality) {
    selectLocality(locality.locality_id, {
      method: "manual_circle",
      label: locality.revenue_circle,
      selected_at: new Date().toISOString(),
    });
  }
</script>

<section class="first-run">
  <div class="ask">
    <header>
      <p class="data-label">Local river information</p>
      <h1 tabindex="-1">Choose your place</h1>
      <p class="lede">
        Select a village, revenue circle, or district to see the nearest supported river bulletin.
        Your choice stays on this phone. No account and no location history.
      </p>
    </header>

    <div class="tune">
      <LocateButton statusId="first-run-location-status" />

      <p class="method-label">Or search by name</p>
      <LocationSearch
        prefix="first-run"
        label="Village, revenue circle, or district"
        placeholder="For example, Gaurisagar"
      />

      <button class="secondary map-choice" type="button" aria-expanded={mapVisible} onclick={toggleMap}>
        {mapVisible ? "Close the map" : "Choose on a map"}
      </button>

      <div class="map-holder" hidden={!mapVisible}>
        {#if mapError}
          <p class="map-status error">{mapError}</p>
        {:else if MapPicker}
          <MapPicker currentLocalityId={null} onselect={chooseMap} />
        {:else}
          <p class="map-status">Loading the map…</p>
        {/if}
      </div>
    </div>
  </div>

  <aside class="meanwhile" aria-label="Raised river states elsewhere in Assam">
    <p class="data-label">Across Assam</p>
    {#if overview.raised.length}
      <p class="meanwhile-lede">
        {overview.raised.length} of {overview.readable} circles with a current reading are at or
        above their warning level.
      </p>
      <ul class="raised">
        {#each overview.raised.slice(0, 8) as locality (locality.locality_id)}
          {@const status = statusInfo(gauges.get(locality.primary_gauge))}
          <li>
            <button type="button" onclick={() => chooseRaised(locality)}>
              <span class="raised-place">{locality.revenue_circle}<small>{locality.district}</small></span>
              <span class={`raised-state level-${status.level}`}>
                <i aria-hidden="true"></i>{status.label}
              </span>
            </button>
          </li>
        {/each}
      </ul>
      {#if overview.raised.length > 8}
        <p class="meanwhile-foot">{overview.raised.length - 8} more are not listed here. Search for a place to see it.</p>
      {/if}
    {:else}
      <p class="meanwhile-lede">
        No circle with a current reading is at or above its warning level in the update saved on
        this phone.
      </p>
    {/if}
    <p class="meanwhile-foot">
      {#if freshest}
        Newest reading in this update is {ageLabel(freshest)}. Readings older than
        {bundle.stale_after_hours} hours are not counted.
      {:else}
        No current reading is saved on this phone yet. Reconnect once to fetch one.
      {/if}
    </p>
  </aside>
</section>

<style>
  .first-run {
    display: grid;
    grid-template-columns: minmax(0, 1.15fr) minmax(280px, .85fr);
    gap: clamp(40px, 6vw, 72px);
    align-items: start;
  }

  .ask header { max-width: 620px; }

  h1 {
    max-width: 12ch;
    margin: 12px 0 0;
    font: 780 clamp(36px, 5vw, 56px)/1.02 var(--body);
    letter-spacing: -.03em;
    text-wrap: balance;
  }

  .lede {
    max-width: 58ch;
    margin: 16px 0 0;
    color: var(--graphite);
    font-size: 16px;
    line-height: 1.6;
  }

  .tune {
    margin-top: 32px;
    padding: 24px;
    border: 1px solid var(--line);
    border-radius: var(--r-panel);
    background: var(--surface);
  }

  .tune > :global(button) { width: 100%; }

  .tune > :global(button:first-child) {
    color: var(--ink-deep);
    background: var(--river);
  }

  .method-label {
    margin: 24px 0 8px;
    color: var(--muted);
    font-size: 12px;
    font-weight: 700;
  }

  .map-choice { margin-top: 20px; }
  .map-holder { margin-top: 16px; }

  .meanwhile {
    padding: 24px;
    border-radius: var(--r-panel);
    background: var(--surface-2);
  }

  .meanwhile-lede {
    max-width: 38ch;
    margin: 12px 0 0;
    color: var(--graphite);
    font-size: 15px;
    line-height: 1.55;
  }

  .meanwhile-foot {
    margin: 16px 0 0;
    color: var(--muted);
    font-size: 12px;
    line-height: 1.5;
  }

  .raised {
    margin: 20px 0 0;
    padding: 0;
    list-style: none;
  }

  .raised li { border-top: 1px solid var(--line); }
  .raised li:last-child { border-bottom: 1px solid var(--line); }

  .raised button {
    display: grid;
    width: 100%;
    min-height: 56px;
    justify-content: start;
    justify-items: start;
    gap: 4px;
    padding: 12px 0;
    border: 0;
    border-radius: 0;
    color: var(--ink);
    background: none;
    box-shadow: none;
    text-align: left;
  }

  .raised button:hover {
    color: var(--river);
    background: none;
  }

  .raised-place {
    font-size: 18px;
    font-weight: 750;
    line-height: 1.15;
  }

  .raised-place small {
    display: block;
    margin-top: 4px;
    color: var(--muted);
    font-size: 12px;
    font-weight: 550;
  }

  .raised-state {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: var(--graphite);
    font-size: 11px;
    font-weight: 800;
    letter-spacing: .05em;
    text-transform: uppercase;
  }

  .raised-state i {
    display: block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: currentColor;
  }

  .raised-state.level-2 i { color: var(--signal-ink); }
  .raised-state.level-3 i,
  .raised-state.level-4 i { color: var(--danger-text); }

  @media (max-width: 859px) {
    .first-run { display: block; }
    .meanwhile { margin-top: 32px; }
    .tune { padding: 20px; }
  }
</style>
