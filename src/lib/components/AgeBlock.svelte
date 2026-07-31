<script>
  import { ageLabel, isCurrent } from "$lib/data/index.js";

  let { gauge } = $props();
  let stale = $derived(!isCurrent(gauge));
</script>

{#if !gauge?.observed_at}
  <p class="age stale">Reading time unavailable</p>
{:else}
  <p class:stale class="age">{ageLabel(gauge)}</p>
{/if}
