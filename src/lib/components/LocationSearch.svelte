<script>
  import { goto } from "$app/navigation";
  import { getBundle } from "$lib/data/index.js";
  import { selectLocality } from "$lib/data/preferences.js";
  import {
    combinedMatches,
    loadVillageIndex,
    nearbyMatches,
    searchKeys,
  } from "$lib/data/search.js";

  let {
    prefix,
    label,
    placeholder,
    goHome = false,
    // On the map the field is a single pill floating over the sheet. The label
    // and the keyboard hint still ship — they move to the accessible layer
    // rather than being deleted, because they are what makes the combobox usable.
    compact = false,
    onselected = () => {},
  } = $props();

  const bundle = getBundle();
  let value = $state("");
  let matches = $state([]);
  let open = $state(false);
  let status = $state("");
  let heading = $state("");
  let activeIndex = $state(-1);
  let requestNumber = 0;

  function show(nextMatches, nextHeading = "") {
    matches = nextMatches;
    heading = nextHeading;
    activeIndex = -1;
    open = true;
  }

  async function choose(item) {
    // A handful of places sit in a circle the Census split across two
    // districts. Offer both rather than picking one, since the choice
    // decides which river gauge this person is shown.
    if (item.locality_ids?.length > 1) {
      show(item.locality_ids
        .map(id => bundle.localities.find(locality => locality.locality_id === id))
        .filter(Boolean)
        .map(locality => ({
          label: locality.revenue_circle,
          detail: `${locality.district}, revenue circle`,
          locality_id: locality.locality_id,
          source: "manual_circle",
        })), `${item.label} sits on a district boundary`);
      status = `Choose the district ${item.label} is in.`;
      return;
    }
    if (item.source === "manual_district") {
      // A district covers several circles and several gauges, so it can never
      // stand in for one of them. Open its circles and let the person pick.
      show(item.circles.map(circle => ({
        label: circle.revenue_circle,
        detail: `${circle.district}, revenue circle`,
        locality_id: circle.locality_id,
        source: "manual_circle",
      })), `Revenue circles in ${item.district}`);
      status = `Choose a revenue circle in ${item.district}.`;
      return;
    }
    selectLocality(item.locality_id, {
      method: item.source,
      label: item.label,
      selected_at: new Date().toISOString(),
    });
    open = false;
    activeIndex = -1;
    onselected();
    if (goHome) await goto("/");
  }

  async function search() {
    const localRequest = ++requestNumber;
    const query = searchKeys(value);
    // Assamese script leaves the Latin keys empty, so the length gate reads the
    // raw text and both scripts get the same two-character threshold.
    const typed = Math.max(query.normalized.length, query.raw.length);
    if (typed < 2) {
      open = false;
      activeIndex = -1;
      status = "";
      return;
    }
    const nearby = nearbyMatches(query);
    show(nearby);
    if (typed < 3) return;
    status = "Checking saved village names…";
    try {
      await loadVillageIndex();
      if (localRequest !== requestNumber) return;
      const combined = combinedMatches(query, nearby);
      show(combined);
      status = `${combined.length} matching place${combined.length === 1 ? "" : "s"} found.`;
    } catch (_) {
      status = "The larger village list is not cached yet. District and revenue-circle matches are still available.";
    }
  }

  function onkeydown(event) {
    if (event.key === "Escape") {
      if (!open) return;
      event.preventDefault();
      open = false;
      activeIndex = -1;
      status = "Search results closed.";
      return;
    }
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp" && event.key !== "Enter") return;
    if (event.key === "Enter") {
      if (!open || activeIndex < 0 || !matches[activeIndex]) return;
      event.preventDefault();
      choose(matches[activeIndex]);
      return;
    }
    if (!open || !matches.length) return;
    event.preventDefault();
    const direction = event.key === "ArrowDown" ? 1 : -1;
    activeIndex = (activeIndex + direction + matches.length) % matches.length;
  }
</script>

<div class:compact class="search-wrap">
  <label class:sr-only={compact} for={`${prefix}-search`}>{label}</label>
  <p id={`${prefix}-search-hint`} class:sr-only={compact} class="field-hint">Enter at least 2 letters. Use the arrow keys to review matches.</p>
  {#if compact}
    <svg class="search-icon" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="11" cy="11" r="6.5"></circle>
      <path d="m16 16 4 4"></path>
    </svg>
  {/if}
  <input
    id={`${prefix}-search`}
    type="search"
    role="combobox"
    aria-autocomplete="list"
    aria-controls={`${prefix}-results`}
    aria-expanded={open}
    aria-activedescendant={open && activeIndex >= 0 ? `${prefix}-result-${activeIndex}` : undefined}
    aria-describedby={`${prefix}-search-hint ${prefix}-search-status`}
    autocomplete="off"
    {placeholder}
    bind:value
    oninput={search}
    {onkeydown}
  >
  <div
    id={`${prefix}-results`}
    class="search-results"
    role="listbox"
    aria-label="Matching places"
    hidden={!open}
  >
    {#if heading}<p class="result-heading" role="presentation">{heading}</p>{/if}
    {#if matches.length}
      {#each matches as item, index}
        <button
          id={`${prefix}-result-${index}`}
          class:active={activeIndex === index}
          type="button"
          role="option"
          aria-selected={activeIndex === index}
          onclick={() => choose(item)}
          onmousemove={() => activeIndex = index}
        >
          {item.label}<small>{item.detail}</small>
        </button>
      {/each}
    {:else}
      <p class="empty">No matching district, revenue circle or village found.</p>
    {/if}
  </div>
</div>
<p
  id={`${prefix}-search-status`}
  class:sr-only={compact && !status}
  class="field-status"
  aria-live="polite"
>{status}</p>
