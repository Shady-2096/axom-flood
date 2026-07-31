<!--
  THESIS: The homepage is a river observation desk, not a dashboard of cards or a theatrical emergency broadcast.
  OWN-WORLD: Mineral daylight and deep night surfaces, river-blue controls, calibrated rules, and normal-width Archivo.
  STORY: Choose a place, understand the local situation in plain language, then report conditions or follow the safest next action.
  FIRST VIEWPORT: A full-width Assam map holds search, one briefing panel, one control dock, and one reporting action.
  FORM: Monsoon gauge-station instrument, sixth grounded direction, staged as one active working surface; seed e2906d8c.
-->
<script>
  import DataUnavailable from "$lib/components/DataUnavailable.svelte";
  import FloodBulletin from "$lib/components/FloodBulletin.svelte";
  import Icon from "$lib/components/Icon.svelte";
  import LoadingState from "$lib/components/LoadingState.svelte";
  import LocateButton from "$lib/components/LocateButton.svelte";
  import LocationSearch from "$lib/components/LocationSearch.svelte";
  import LocationTuner from "$lib/components/LocationTuner.svelte";
  import ProvenanceNotes from "$lib/components/ProvenanceNotes.svelte";
  import {
    currentSentence,
    dataState,
    displayContext,
    getPosition,
    nearestLocality,
    selectionNote,
    statusInfo,
  } from "$lib/data/index.js";
  import {
    activeRenderMode,
    dismissFullModePrompt,
    preferencesChanged,
    selectLocality,
    selectRenderMode,
    store,
  } from "$lib/data/preferences.js";
  import { serializeJsonLd, websiteSchema } from "$lib/landing-seo.js";
  import { resolveRenderMode, shouldOfferFullMode } from "$lib/mode.js";
  import { onMount } from "svelte";

  // The site identity schema belongs on the site's front door, which is this
  // map. It used to sit on a search-only landing page at `/` that redirected
  // here on mount, so every real visitor saw that page flash first.
  const websiteJsonLd = serializeJsonLd(websiteSchema);

  let shareLabel = $state("Share update");
  let shareIcon = $state("share");
  let tunerOpen = $state(false);
  let TechnicalPanel = $state();
  let RiverMap = $state();
  let renderMode = $state("light");
  let offerFullMode = $state(false);
  let atlasSection = $state();
  let atlasPanel = $state();
  let panelCollapsed = $state(false);
  let technicalSection = $state();
  let technicalOpen = $state(false);
  /* Bumped when the reader asks to be taken to their own circle. The map flies
     on a change of selected circle, so locating the circle already selected
     produced no movement at all — the commonest case, since the app remembers
     the last choice. */
  let focusRequest = $state(0);

  let bundle = $derived($dataState.bundle);
  /* A reader who has chosen nothing still lands on a working map with a real
     bulletin on it — the worst reading in the state — rather than on a form.
     The screen that used to stand here asked for a village name before it would
     show anything at all, which is a toll gate in front of a safety page. */
  let context = $derived.by(() => {
    $preferencesChanged;
    return bundle ? displayContext() : null;
  });
  let status = $derived(context ? statusInfo(context.gauge) : null);
  let urgent = $derived(Boolean(status) && status.level >= 2);
  /* The chosen layout is decided while the loading shell is still visible,
     before the selected locality paints. This used to also require RiverMap to
     have arrived, which meant every load rendered the document layout first and
     then swapped the whole page for the map layout once the chunk landed. The
     mode is a preference plus a connection check, both readable synchronously,
     so only the map itself arrives late, into space the section already holds. */
  let atlas = $derived(renderMode === "full");

  async function loadFullMode() {
    // The ground plane and the measurement panel are the two things data-saver
    // mode does without. Loaded together, after the bulletin has already painted.
    const [panel, ground] = await Promise.all([
      import("$lib/components/TechnicalPanel.svelte"),
      import("$lib/components/DetailedRiverMap.svelte"),
    ]);
    TechnicalPanel = panel.default;
    RiverMap = ground.default;
  }

  function applyMode(mode) {
    renderMode = mode;
    activeRenderMode.set(mode);
  }

  function resolveMode() {
    const connection = navigator.connection;
    const preference = store.renderMode;
    const requestedLayer = new URL(window.location.href).searchParams.get("layer");
    if (requestedLayer) {
      // A situation-page map link is an explicit request for the atlas. Honour
      // it for this visit without overwriting the reader's stored display
      // preference.
      applyMode("full");
      loadFullMode().catch(() => {
        applyMode("light");
        offerFullMode = false;
      });
      return;
    }
    if (resolveRenderMode(preference, connection) === "full") {
      applyMode("full");
      loadFullMode().catch(() => {
        applyMode("light");
        offerFullMode = false;
      });
      return;
    }
    applyMode("light");
    offerFullMode = shouldOfferFullMode(
      preference,
      connection,
      store.fullModePromptDismissed,
    );
  }

  async function switchToFullMode() {
    selectRenderMode("full");
    offerFullMode = false;
    renderMode = "full";
    try {
      await loadFullMode();
    } catch {
      // Keep the document view usable when either lazy full-mode chunk cannot
      // be fetched (for example, after an offline cache was partially updated).
      // The stored choice remains intact so a later reload can retry it.
      renderMode = "light";
      offerFullMode = false;
    }
  }

  function dismissOffer() {
    dismissFullModePrompt();
    offerFullMode = false;
  }

  function showTechnicalDetails() {
    technicalOpen = true;
    requestAnimationFrame(() => {
      const reducedMotion = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
      technicalSection?.scrollIntoView({
        behavior: reducedMotion ? "auto" : "smooth",
        block: "start",
      });
    });
  }

  function handleMapLayerChange(layer) {
    if (layer === "river_conditions") return;
    if (globalThis.matchMedia?.("(max-width: 859px), (max-height: 820px)")?.matches) {
      panelCollapsed = true;
    }
  }

  /* The reader has no place saved, so the map is showing the state's worst
     reading. Ask the browser once — the prompt is the shortest path from a
     stranger's district to their own, and a granted one skips the search field
     entirely. Refused, dismissed, or unavailable, the default place stays on
     screen with the search pill and the locate control both still there, and
     the prompt is not raised again on the next visit. */
  async function offerLocationOnce() {
    if (store.locality || store.locationAsked) return;
    store.locationAsked = true;
    try {
      const permission = await navigator.permissions?.query({ name: "geolocation" });
      if (permission?.state === "denied") return;
      const position = await getPosition();
      const nearest = nearestLocality(position.coords.latitude, position.coords.longitude);
      if (!nearest) return;
      selectLocality(nearest.locality.locality_id, {
        method: "approximate_location",
        distance_km: Number(nearest.distance.toFixed(1)),
        selected_at: new Date().toISOString(),
      });
    } catch (_) {
      // A refusal is an answer. The default place is already on screen.
    }
  }

  onMount(() => {
    // Resolve the client-only preference while the data loading shell is still
    // on screen. Waiting for `context` meant a cached bundle briefly rendered
    // the document layout before the next effect swapped in the atlas.
    resolveMode();
  });

  // Only once the bundle is in hand: the nearest circle is computed from it, so
  // asking earlier would spend the one prompt on a lookup that cannot answer.
  $effect(() => {
    if (bundle) offerLocationOnce();
  });

  /* The header switch writes the mode too, so this screen follows it rather
     than owning it. Coming back to the map re-imports the two lazy chunks; the
     module cache makes that free after the first time. */
  $effect(() => {
    const next = $activeRenderMode;
    if (next === renderMode) return;
    renderMode = next;
    if (next !== "full" || RiverMap) return;
    loadFullMode().catch(() => {
      renderMode = "light";
    });
  });

  /* On a phone the map is the whole screen and the bulletin floats on top of
     it, so everything else anchored to the bottom of the map — the locate
     control, the tile attribution, the map's own notes — has to clear the
     panel. Its height is not a constant anyone can write down: it moves with
     the place name, the length of the status sentence, and the reader's text
     size. Measure it and publish it as one custom property the map chrome
     reads. */
  $effect(() => {
    const section = atlasSection;
    const panel = atlasPanel;
    if (!section || !panel) return;
    const publish = () => {
      section.style.setProperty("--atlas-panel-h", `${Math.round(panel.offsetHeight)}px`);
    };
    publish();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(publish);
    observer.observe(panel);
    return () => observer.disconnect();
  });

  // "(Pt)" is a Census part-circle suffix, not part of what anyone calls the
  // place. Setting it inline and smaller keeps the disclosure while letting
  // most names hold a single line.
  let place = $derived.by(() => {
    const name = context?.locality.revenue_circle || "";
    const match = name.match(/^(.*?)\s*(\(Pt\))$/i);
    return match ? { name: match[1], suffix: match[2] } : { name, suffix: "" };
  });

  async function share() {
    const shareText = currentSentence(context.gauge);
    try {
      if (navigator.share) {
        await navigator.share({
          title: `Flood update for ${context.locality.revenue_circle}`,
          text: shareText,
        });
      } else {
        await navigator.clipboard.writeText(shareText);
        shareIcon = "copy";
        shareLabel = "Update copied";
      }
    } catch (error) {
      if (error?.name !== "AbortError") {
        shareIcon = "";
        shareLabel = "Could not share. Try the source link";
      }
    }
  }
</script>

<svelte:head>
  {@html `<script type="application/ld+json">${websiteJsonLd}</script>`}
</svelte:head>

{#if $dataState.status === "error"}
  <DataUnavailable error={$dataState.error} />
{:else if !bundle}
  <LoadingState home />
{:else if bundle.runtime.kill_switch.enabled}
  <section class="home kill">
    <p class="screen-kicker">Remote safety pause</p>
    <h1 class="screen-title" tabindex="-1">River information paused</h1>
    <p>{bundle.runtime.kill_switch.message_en}</p>
  </section>
{:else if !context}
  <section class="home">
    <p class="screen-kicker">No river areas in this update</p>
    <h1 class="screen-title" tabindex="-1">Nothing to show yet</h1>
    <p>This update carries no revenue circles. Reconnect once to fetch a complete one.</p>
  </section>
{:else}
  <!-- Nobody has chosen a place, so this is the state's worst reading standing
       in for one. It says so, in the panel, above the reading it is describing —
       a default that looked chosen would be the one way this screen could
       mislead. Both routes out sit inside the notice. -->
  {#snippet notYours()}
    <p class="stand-in">
      <span>Not your area?</span>
      <LocateButton statusId="stand-in-location-status" />
    </p>
  {/snippet}

  {#snippet bulletin(withPlace = null)}
    <FloodBulletin
      gauge={context.gauge}
      {shareLabel}
      {shareIcon}
      place={withPlace}
      kicker={context.fallback ? "Assam's highest reading" : "Local flood bulletin"}
      lead={context.fallback ? notYours : null}
      folded={withPlace ? panelCollapsed : false}
      onfold={withPlace ? () => { panelCollapsed = !panelCollapsed; } : null}
      onshare={share}
      onmoreinfo={showTechnicalDetails}
    />
  {/snippet}

  {#if atlas}
    <!-- Map-first. The sheet is the map, and everything else floats on it as
         small controls: a search pill, a locate button, and the bulletin. The
         previous layout gave a permanent third of the screen to a location form
         that most readers touch once. On a phone this composition is the same
         one, at phone scale: the map runs the full screen between the header
         and the tab bar, and the bulletin floats on it. It used to break into a
         stack of full-width bands, which spent the first screen on a search
         field, a 44svh strip of map, and the top third of a bulletin. -->
    <section class="atlas" aria-label="River conditions across Assam" bind:this={atlasSection}>
      <div class="atlas-search">
        <LocationSearch
          prefix="atlas"
          compact
          label="Village, revenue circle, or district"
          placeholder="Search a place in Assam"
        />
      </div>

      <!-- The section holds the map's space whether or not the chunk has landed,
           so nothing below it moves when it does. -->
      {#if RiverMap}
        <RiverMap
          localityId={context.locality.locality_id}
          {focusRequest}
          onlayerchange={handleMapLayerChange}
        />
      {:else}
        <div class="atlas-map-pending" aria-hidden="true"></div>
      {/if}

      <!-- On a phone the card can be folded down to its identity and its state,
           which is the part a reader keeps on screen while looking at terrain.
           The handle is the whole top edge of the card, not a small target in a
           corner: it is the control most likely to be reached for with a thumb
           while the other hand is holding something. -->
      <div class="atlas-panel" bind:this={atlasPanel}>
        {@render bulletin({
          name: `${place.name}${place.suffix ? ` ${place.suffix}` : ""}`,
          meta: `${context.locality.district}, ${context.gauge?.river || "Gauge review pending"}`,
        })}
      </div>

      <div class="atlas-dock">
        <a class="atlas-report-cta" href="/report/">
          <Icon name="report" />
          Report local conditions
        </a>
        <LocateButton
          statusId="atlas-location-status"
          compact
          onselected={() => { focusRequest += 1; }}
        />
      </div>

    </section>
  {/if}

  <section class:has-atlas={atlas} class="home home-details">
    {#if !atlas}
      <div class="receiver" class:urgent class:tuner-open={tunerOpen}>
        <header class="place-block">
          <h1
            class:long-place={place.name.length > 14}
            class="place"
            tabindex="-1"
          >{place.name}{#if place.suffix}<span class="place-suffix">{place.suffix}</span>{/if}</h1>
          <p class="place-meta">
            <span>{context.locality.district}</span><span class="divider">/</span>
            <span>{context.gauge?.river || "Gauge review pending"}</span>
          </p>
          <p class="place-source">
            <span>{context.fallback
              ? "No place chosen yet, so this is the highest reading in Assam."
              : selectionNote(context.locality)}</span>
            <button
              class="change-place"
              type="button"
              aria-controls="location-tuner"
              aria-expanded={tunerOpen}
              onclick={() => { tunerOpen = !tunerOpen; }}
            >{tunerOpen ? "Keep this place" : "Change place"}</button>
          </p>
        </header>

        {@render bulletin()}

        {#if offerFullMode}
          <aside class="mode-offer" aria-label="Full display mode available">
            <span>Your connection can load the detailed river view.</span>
            <button type="button" onclick={switchToFullMode}>Show full view</button>
            <button class="mode-dismiss" type="button" aria-label="Dismiss full view suggestion" onclick={dismissOffer}>×</button>
          </aside>
        {/if}

        <div id="location-tuner" class:open={tunerOpen} class="tuner-slot">
          <LocationTuner locality={context.locality} onselected={() => { tunerOpen = false; }} />
        </div>
      </div>

      <div class="community-action">
        <p>{bundle.i18n.en.strings.reciprocity_prompt}</p>
        <a class="button" href="/report/">Report local conditions</a>
      </div>
    {/if}

    {#if renderMode === "full" && TechnicalPanel}
      <div
        id="technical-details"
        class="technical-anchor"
        bind:this={technicalSection}
      >
        <TechnicalPanel
          locality={context.locality}
          gauge={context.gauge}
          bind:open={technicalOpen}
        />
      </div>
    {/if}

    <div class="reading-context">
      <ProvenanceNotes locality={context.locality} gauge={context.gauge} />
    </div>
  </section>
{/if}

<style>
  /* Mirrors the map's own box so the reserved space matches what fills it. The
     section carries the height at every width now, including the phone, so this
     is one rule rather than two. */
  .atlas-map-pending {
    position: absolute;
    z-index: 0;
    inset: 0;
    background: var(--ground-deep);
  }

  @media (max-width: 859px) {
    .atlas-map-pending { background: var(--ground); }
  }

  .mode-offer {
    display: flex;
    align-items: center;
    gap: 8px;
    width: fit-content;
    max-width: 100%;
    margin: 16px 0 0;
    padding: 8px 8px 8px 12px;
    border: 1px solid var(--line);
    border-radius: var(--r-control);
    color: var(--muted);
    background: var(--surface);
    font-size: 12px;
    line-height: 1.35;
  }
  .mode-offer button {
    min-height: 34px;
    padding: 8px 12px;
    border-radius: var(--r-control);
    font-size: 12px;
    white-space: nowrap;
  }
  .mode-offer .mode-dismiss {
    width: 28px;
    padding: 0;
    border-color: transparent;
    color: var(--muted);
    background: transparent;
    font-size: 18px;
  }
  @media (max-width: 520px) {
    .mode-offer {
      align-items: flex-start;
      flex-wrap: wrap;
      border-radius: var(--r-control);
    }
    .mode-dismiss { margin-left: auto; }
  }
</style>
