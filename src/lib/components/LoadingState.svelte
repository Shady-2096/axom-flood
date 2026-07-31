<script>
  let { home = false } = $props();
</script>

<section class:home-loading={home} class="loading-state">
  <div class="loading-copy">
    <span class="signal-loader" aria-hidden="true"><i></i><i></i><i></i></span>
    <div><strong>Tuning to saved information</strong><p>Opening the latest river bulletin on this phone…</p></div>
  </div>
</section>

<style>
  .loading-copy {
    display: flex;
    align-items: center;
    gap: 20px;
  }

  /* app.html knows the saved locality and display preference synchronously,
     before the cached data bundle is restored. On a returning atlas visit the
     loading state therefore holds the final map plane instead of painting a
     centred document message that disappears a frame later. */
  :global(html[data-returning-view="atlas"]) .home-loading {
    display: block;
    height: min(760px, calc(100svh - 64px));
    min-height: 620px;
    margin: -8px calc(-1 * var(--page-pad-x)) 0;
    background: var(--ground-deep);
  }

  :global(html[data-returning-view="atlas"]) .home-loading .loading-copy {
    display: none;
  }

  @media (max-width: 859px) {
    :global(html[data-returning-view="atlas"]) .home-loading {
      height: 44svh;
      min-height: 0;
      margin: -8px calc(-1 * var(--page-pad-x)) 0;
    }
  }
</style>
