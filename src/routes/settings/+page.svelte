<script>
  import { goto } from "$app/navigation";
  import DataUnavailable from "$lib/components/DataUnavailable.svelte";
  import LoadingState from "$lib/components/LoadingState.svelte";
  import LocateButton from "$lib/components/LocateButton.svelte";
  import LocationSearch from "$lib/components/LocationSearch.svelte";
  import TranslationNotice from "$lib/components/TranslationNotice.svelte";
  import { currentContext, dataState, getBundle } from "$lib/data/index.js";
  import {
    preferencesChanged,
    selectLanguage,
    selectLocality,
    selectRenderMode,
    store,
  } from "$lib/data/preferences.js";

  let context = $derived.by(() => {
    $preferencesChanged;
    return $dataState.bundle ? currentContext() : null;
  });
  let mapVisible = $state(false);
  let MapPicker = $state();
  let mapError = $state("");
  let notificationStatus = $state("");
  let notificationBusy = $state(false);

  async function toggleMap() {
    if (mapVisible) {
      mapVisible = false;
      return;
    }
    mapVisible = true;
    mapError = "";
    try {
      MapPicker = (await import("$lib/components/MapPicker.svelte")).default;
    } catch (_) {
      mapError = "The map is not saved on this phone yet. Reconnect once to keep it, or search for your place by name.";
    }
  }

  async function chooseMap(selection) {
    selectLocality(selection.locality_id, {
      method: "manual_map",
      label: selection.label,
      selected_at: new Date().toISOString(),
    });
    await goto("/home/");
  }

  async function enableNotifications() {
    const bundle = getBundle();
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) return "Web push is unavailable in this browser.";
    const permission = await Notification.requestPermission();
    if (permission !== "granted") return "Notifications were not enabled. You can change this in browser settings.";
    const registration = await navigator.serviceWorker.ready;
    if (!bundle.runtime.push_public_key || !bundle.runtime.push_subscription_url) {
      return "Browser permission is ready, but the Axom Flood push service is not configured yet.";
    }
    const key = Uint8Array.from(atob(bundle.runtime.push_public_key.replace(/-/g, "+").replace(/_/g, "/")), character => character.charCodeAt(0));
    const subscription = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
    await fetch(bundle.runtime.push_subscription_url, {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(subscription),
    });
    return "Flood update notifications are enabled.";
  }

  async function requestNotifications() {
    notificationBusy = true;
    notificationStatus = "Waiting for browser permission…";
    try {
      notificationStatus = await enableNotifications();
    } catch (_) {
      notificationStatus = "Notifications could not be enabled. Check your connection and browser settings.";
    }
    notificationBusy = false;
  }
</script>

{#if $dataState.status === "error"}
  <DataUnavailable error={$dataState.error} />
{:else if !$dataState.bundle}
  <LoadingState />
{:else}
  <section class="screen settings-screen">
    <header class="settings-header">
      <h1 class="screen-title" tabindex="-1">Settings</h1>
      <p>Choose what this phone remembers and what this browser may do. No account is required.</p>
      <dl class="settings-summary">
        <div><dt>River area</dt><dd>{context ? `${context.locality.revenue_circle}, ${context.locality.district}` : "Not chosen"}</dd></div>
        <div><dt>Safety language</dt><dd>Reviewed English</dd></div>
        <div><dt>Location tracking</dt><dd>Off</dd></div>
      </dl>
    </header>
    <div class="settings-content">
      <section class="settings-block">
        <h2>Location</h2>
        <p>
          {#if context}
            Current area: <strong>{context.locality.revenue_circle}, {context.locality.district}</strong>.
          {:else}
            No place is chosen yet, so no river bulletin is shown.
          {/if}
          Browser location is used once to choose an approximate locality and is not saved by Axom Flood.
        </p>
        <LocateButton statusId="settings-location-status" goHome={true} />
        <LocationSearch
          prefix="settings"
          label="Find a village, revenue circle, or district"
          placeholder="Type at least 2 letters"
          goHome={true}
        />
        <div class="or-divider">or point to it</div>
        <button class="secondary" type="button" onclick={toggleMap}>{mapVisible ? "Hide the map" : "Choose on a map"}</button>
        <div class="map-holder" hidden={!mapVisible}>
          {#if mapError}
            <p class="map-status error">{mapError}</p>
          {:else if MapPicker}
            <MapPicker currentLocalityId={store.locality} onselect={chooseMap} />
          {:else}
            <p class="map-status">Loading the map…</p>
          {/if}
        </div>
      </section>
      <section class="settings-block">
        <h2>Language</h2><p>Only reviewed translations can appear in a safety message.</p>
        <label for="language">Preferred language</label>
        <select id="language" value={store.language} onchange={event => selectLanguage(event.currentTarget.value)}>
          <option value="en">English — reviewed</option>
          <option value="as" disabled>অসমীয়া — unavailable until reviewed</option>
        </select>
        <TranslationNotice />
      </section>
      <section class="settings-block">
        <h2>Display mode</h2>
        <p>Light mode shows the complete flood bulletin with fewer downloads. Full mode adds the detailed river visualization after the bulletin appears.</p>
        <label for="render-mode">Preferred display</label>
        <select id="render-mode" value={store.renderMode} onchange={event => selectRenderMode(event.currentTarget.value)}>
          <option value="auto">Automatic — save data on slow connections</option>
          <option value="light">Data saver</option>
          <option value="full">Detailed map</option>
        </select>
      </section>
      <section class="settings-block">
        <h2>Flood notifications</h2><p>Allow this browser to receive a local update before power or network conditions worsen.</p>
        <button class="secondary" type="button" disabled={notificationBusy} onclick={requestNotifications}>Enable web push</button>
        <p class="field-status" aria-live="polite">{notificationStatus}</p>
      </section>
      <section class="settings-block">
        <h2>Privacy</h2><p>No account and no continuous location tracking. Your chosen locality and queued community reports stay in this browser until they can be used or cleared by browser settings.</p>
      </section>
    </div>
  </section>
{/if}
