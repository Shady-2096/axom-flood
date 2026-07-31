<script>
  import { goto } from "$app/navigation";
  import {
    geolocationErrorMessage,
    getPosition,
    nearestLocality,
  } from "$lib/data/index.js";
  import { selectLocality } from "$lib/data/preferences.js";
  import Icon from "./Icon.svelte";

  // `compact` is the map's circular control: the same action with its label
  // carried by the accessible name instead of a slab of text beside the icon.
  let { statusId, goHome = false, compact = false, onselected = () => {} } = $props();
  let finding = $state(false);
  let status = $state("");
  let error = $state(false);

  async function locate() {
    finding = true;
    error = false;
    status = "Your precise position stays in this browser. We use it only to choose the nearest locality.";
    try {
      const position = await getPosition();
      const nearest = nearestLocality(position.coords.latitude, position.coords.longitude);
      if (!nearest) {
        status = "No supported Assam locality could be matched. Enter your place below.";
        error = true;
        finding = false;
        return;
      }
      selectLocality(nearest.locality.locality_id, {
        method: "approximate_location",
        distance_km: Number(nearest.distance.toFixed(1)),
        selected_at: new Date().toISOString(),
      });
      // The privacy note answers "what is happening to my position right now",
      // so it belongs to the search and not to its result. Leaving it up made it
      // read as a standing claim about the located circle, and left the button
      // disabled, so the control could not be used a second time.
      status = "";
      finding = false;
      onselected();
      if (goHome) await goto("/home/");
    } catch (geolocationError) {
      status = geolocationErrorMessage(geolocationError);
      error = true;
      finding = false;
    }
  }
</script>

<button
  class:icon-button={compact}
  type="button"
  disabled={finding}
  aria-label={compact ? (finding ? "Finding your area" : "Use my location") : undefined}
  onclick={locate}
>
  {#if finding}
    <span class="signal-loader" aria-hidden="true"><i></i><i></i><i></i></span>{#if !compact} Finding your area{/if}
  {:else}
    <Icon name="locate" />{#if !compact} Use my location{/if}
  {/if}
</button>
<p id={statusId} class:error class:sr-only={compact && !status} class="field-status" aria-live="polite">{status}</p>
