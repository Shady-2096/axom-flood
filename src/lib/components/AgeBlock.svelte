<script>
  import { ageLabel, isCurrent } from "$lib/data/index.js";

  /* `ungauged` is not the same as a missing timestamp. "Reading time
     unavailable" tells a reader to wait for one; there is nothing to wait for
     when no gauge covers the circle. */
  let { gauge, ungauged = false } = $props();
  let stale = $derived(!isCurrent(gauge));
</script>

{#if ungauged}
  <p class="age stale">No gauge</p>
{:else if !gauge?.observed_at}
  <p class="age stale">Reading time unavailable</p>
{:else}
  <p class:stale class="age">{ageLabel(gauge)}</p>
{/if}
