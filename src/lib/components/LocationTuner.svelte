<script>
  import { goto } from "$app/navigation";
  import { getBundle } from "$lib/data/index.js";
  import { selectLocality, store } from "$lib/data/preferences.js";
  import LocateButton from "./LocateButton.svelte";
  import LocationSearch from "./LocationSearch.svelte";

  let { locality, prefix = "home", goHome = false, onselected = () => {} } = $props();

  const bundle = getBundle();
  let recents = $derived(store.recents
    .map(id => bundle.localities.find(item => item.locality_id === id))
    .filter(item => item && item.locality_id !== locality?.locality_id));

  async function chooseRecent(item) {
    selectLocality(item.locality_id, {
      method: "recent",
      label: item.revenue_circle,
      selected_at: new Date().toISOString(),
    });
    onselected();
    if (goHome) await goto("/home/");
  }
</script>

<aside class="location-tuner" aria-label="Choose location">
  <h2>Change place</h2>
  <p>Axom Flood shows one revenue circle at a time. Your choice stays on this phone.</p>
  <LocateButton statusId={`${prefix}-location-status`} {goHome} {onselected} />
  <p class="search-method">Or search by name</p>
  <LocationSearch
    {prefix}
    label="Village, revenue circle, or district"
    placeholder="For example, Gaurisagar"
    {goHome}
    {onselected}
  />
  {#if recents.length}
    <div class="recents"><p>Recent places</p>
      {#each recents as item}
        <button class="recent-place" type="button" onclick={() => chooseRecent(item)}>
          {item.revenue_circle}, {item.district}</button>
      {/each}
    </div>
  {/if}
</aside>
