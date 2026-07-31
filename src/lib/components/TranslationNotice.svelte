<script>
  import { getBundle } from "$lib/data/index.js";
  import { store } from "$lib/data/preferences.js";

  const bundle = getBundle();
</script>

{#if store.language === "as" && !bundle.i18n.as.reviewed}
  <p class="review-note">{bundle.i18n.en.strings.assamese_pending}</p>
{/if}
