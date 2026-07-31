<script>
  import { dev } from "$app/environment";
  import { afterNavigate, goto } from "$app/navigation";
  import { page } from "$app/state";
  import {
    ageLabel,
    currentContext,
    currentSentence,
    dataState,
    initializeData,
    statusInfo,
  } from "$lib/data/index.js";
  import {
    activeRenderMode,
    preferencesChanged,
    selectRenderMode,
    selectTheme,
  } from "$lib/data/preferences.js";
  import {
    metadataForPath,
    routeKey,
    SITE_NAME,
    SITE_URL,
    SOCIAL_IMAGE,
  } from "$lib/seo.js";
  import { onMount, tick } from "svelte";

  let { children } = $props();
  let online = $state(true);
  let theme = $state("dark");
  let mainElement = $state();
  let focusObserver;
  let seo = $derived(metadataForPath(page.url.pathname));
  let canonicalUrl = $derived(`${SITE_URL}${seo.path}`);
  let liveStatus = $derived.by(() => {
    $preferencesChanged;
    if (currentRoute() !== "home" || !$dataState.bundle) return "";
    const context = currentContext();
    if (!context) return "";
    const freshness = context.gauge?.observed_at ? ` Reading is ${ageLabel(context.gauge)}.` : "";
    return `${statusInfo(context.gauge).label}. ${currentSentence(context.gauge)}${freshness}`;
  });

  const routes = [
    {
      href: "/",
      route: "home",
      label: "River",
      path: "M3 8c2-1.5 4-1.5 6 0s4 1.5 6 0 4-1.5 6 0M3 13c2-1.5 4-1.5 6 0s4 1.5 6 0 4-1.5 6 0M3 18c2-1.5 4-1.5 6 0s4 1.5 6 0 4-1.5 6 0",
    },
    {
      href: "/camps/",
      route: "camps",
      label: "Camps",
      path: "M4 20 12 4l8 16M7 15h10M12 4v16",
    },
    {
      href: "/situation/",
      route: "situation",
      label: "Situation",
      path: "M4 19V9m5 10V5m5 14v-7m5 7V3M3 19h18",
    },
    {
      href: "/report/",
      route: "report",
      label: "Report",
      path: "M4 13v-2l13-5v12L4 13Zm0 0v6h4l2-5M17 9h3M18 5l2-2M18 19l2 2",
    },
    {
      href: "/emergency/",
      route: "emergency",
      label: "Emergency",
      path: "M7 3h3l1 5-2 1c1.2 2.7 3.3 4.8 6 6l1-2 5 1v3c0 2.2-1.8 4-4 4C9.3 21 3 14.7 3 7c0-2.2 1.8-4 4-4Z",
    },
    {
      href: "/settings/",
      route: "settings",
      label: "Settings",
      path: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm0-5 1 3 3 1 3-1 2 4-2 2 1 3-2 4-3-1-3 3-3-3-3 1-2-4 1-3-2-2 2-4 3 1 3-1 1-3Z",
    },
  ];

  const currentRoute = () => routeKey(page.url.pathname);

  function applyTheme(nextTheme) {
    theme = nextTheme;
    document.documentElement.dataset.theme = nextTheme;
    document.querySelector('meta[name="theme-color"]')
      ?.setAttribute("content", nextTheme === "light" ? "#063947" : "#04171e");
  }

  function toggleTheme() {
    const nextTheme = theme === "dark" ? "light" : "dark";
    selectTheme(nextTheme);
    applyTheme(nextTheme);
  }

  /* Data saver used to be reachable only through a select on the settings
     screen, three taps from the map it changes. Both directions are worth one
     tap: a reader on a failing line needs out of the tiles quickly, and a
     reader the connection check demoted needs the map back. Choosing here
     stores the choice explicitly, so it also ends the automatic guessing. */
  let detailed = $derived($activeRenderMode === "full");
  let modeLabel = $derived(detailed ? "Data saver" : "Detailed map");

  afterNavigate(async () => {
    window.scrollTo(0, 0);
    await tick();
    focusObserver?.disconnect();
    const focusHeading = () => {
      const heading = mainElement?.querySelector("h1");
      if (!heading) return false;
      heading.setAttribute("tabindex", "-1");
      heading.focus();
      return true;
    };
    if (focusHeading()) return;
    focusObserver = new MutationObserver(() => {
      if (focusHeading()) focusObserver.disconnect();
    });
    focusObserver.observe(mainElement, { childList: true, subtree: true });
  });

  onMount(() => {
    applyTheme(document.documentElement.dataset.theme === "light" ? "light" : "dark");

    // A production worker can still control this origin when the developer
    // later starts Vite on the same port. Remove it before it can serve cached
    // component modules and make a live edit look broken or unchanged.
    if (dev && "serviceWorker" in navigator) {
      navigator.serviceWorker.getRegistrations().then(async registrations => {
        const local = registrations.filter(registration =>
          new URL(registration.scope).origin === location.origin
        );
        if (!local.length) return;
        await Promise.all(local.map(registration => registration.unregister()));
        if (navigator.serviceWorker.controller) location.reload();
      }).catch(() => {});
    }

    /* The map moved from `/home/` to `/`, so "home" resolves to the root here
       and `/home/` itself is a server-side redirect. */
    const oldRoutes = new Set(["home", "camps", "situation", "report", "emergency", "settings"]);
    const hashRoute = location.hash.slice(1);
    if (oldRoutes.has(hashRoute) && currentRoute() !== hashRoute) {
      goto(hashRoute === "home" ? "/" : `/${hashRoute}/`, { replaceState: true });
    }
    initializeData().catch(() => {});
    let lastRefreshAt = Date.now();
    const refreshData = () => {
      if (!navigator.onLine || Date.now() - lastRefreshAt < 15_000) return;
      lastRefreshAt = Date.now();
      initializeData({ force: true }).catch(() => {});
    };
    const refreshVisibleData = () => {
      if (document.visibilityState === "visible") refreshData();
    };
    const update = () => {
      online = navigator.onLine;
      if (online) refreshData();
    };
    let controlled = Boolean(navigator.serviceWorker?.controller);
    const updateWorker = () => {
      if (controlled) {
        // A newly activated worker means a deployment with a new application
        // shell is ready. Reload once so old component code cannot keep reading
        // a newer data contract.
        location.reload();
        return;
      }
      controlled = true;
      refreshData();
    };
    update();
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    window.addEventListener("focus", refreshData);
    document.addEventListener("visibilitychange", refreshVisibleData);
    navigator.serviceWorker?.addEventListener("controllerchange", updateWorker);
    return () => {
      focusObserver?.disconnect();
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
      window.removeEventListener("focus", refreshData);
      document.removeEventListener("visibilitychange", refreshVisibleData);
      navigator.serviceWorker?.removeEventListener("controllerchange", updateWorker);
    };
  });
</script>

<svelte:head>
  <title>{seo.title}</title>
  <meta name="description" content={seo.description}>
  <meta name="robots" content={seo.robots}>
  <link rel="canonical" href={canonicalUrl}>
  <link rel="alternate" hreflang="en-IN" href={canonicalUrl}>
  <meta property="og:type" content="website">
  <meta property="og:locale" content="en_IN">
  <meta property="og:site_name" content={SITE_NAME}>
  <meta property="og:title" content={seo.title}>
  <meta property="og:description" content={seo.description}>
  <meta property="og:url" content={canonicalUrl}>
  <meta property="og:image" content={SOCIAL_IMAGE}>
  <meta property="og:image:secure_url" content={SOCIAL_IMAGE}>
  <meta property="og:image:type" content="image/jpeg">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="Axom Flood, river information for Assam">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content={seo.title}>
  <meta name="twitter:description" content={seo.description}>
  <meta name="twitter:image" content={SOCIAL_IMAGE}>
  <meta name="twitter:image:alt" content="Axom Flood, river information for Assam">
</svelte:head>

<a class="skip-link" href="#app">Skip to flood information</a>

<header class="site-header">
  <a class="brand" href="/" aria-label="Axom Flood home">
    <span class="brand-mark" aria-hidden="true">
      <svg viewBox="0 0 32 32"><path d="M5 10h22M5 16c3-2 5-2 8 0s5 2 8 0 5-2 6-1M5 22c3-2 5-2 8 0s5 2 8 0 5-2 6-1"/></svg>
    </span>
    <span><strong>AXOM FLOOD</strong><small>Assam river observatory</small></span>
  </a>

  <nav class="primary-nav" aria-label="Primary">
    {#each routes as route}
      <a href={route.href} data-route={route.route} class:active={currentRoute() === route.route}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d={route.path}/></svg>
        <span>{route.label}</span>
      </a>
    {/each}
  </nav>

  <div class="header-tools">
    <span class:offline={!online} class="network-state">
      <i></i><span>{online ? "Connected" : "Offline"}</span>
    </span>
    <button
      class="mode-toggle"
      type="button"
      aria-label={`Switch to ${modeLabel.toLowerCase()}`}
      title={detailed
        ? "Data saver: the bulletin without the map"
        : "Detailed map: the full river atlas"}
      onclick={() => selectRenderMode(detailed ? "light" : "full")}
    >
      {#if detailed}
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h11M4 18h7"/></svg>
      {:else}
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 9 4.5-9 4.5-9-4.5L12 3ZM3 12l9 4.5 9-4.5M3 16.5 12 21l9-4.5"/></svg>
      {/if}
      <span>{modeLabel}</span>
    </button>
    <button
      class="theme-toggle"
      type="button"
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
      title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
      onclick={toggleTheme}
    >
      {#if theme === "dark"}
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
      {:else}
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.2 15.3A8.5 8.5 0 0 1 8.7 3.8 8.5 8.5 0 1 0 20.2 15.3Z"/></svg>
      {/if}
      <span>{theme === "dark" ? "Light" : "Dark"}</span>
    </button>
    {#if !online}<span class="offline-copy">Saved bulletin</span>{/if}
  </div>
</header>

<main id="app" tabindex="-1" bind:this={mainElement}>
  {@render children()}
</main>

<footer class="site-footer">
  <div class="footer-inner">
    <div class="footer-brand">
      <span class="footer-mark" aria-hidden="true">
        <svg viewBox="0 0 32 32"><path d="M5 10h22M5 16c3-2 5-2 8 0s5 2 8 0 5-2 6-1M5 22c3-2 5-2 8 0s5 2 8 0 5-2 6-1"/></svg>
      </span>
      <span><strong>Axom Flood</strong><small>Assam river observatory</small></span>
    </div>
    <div class="footer-notes">
      <p>River levels from the Central Water Commission (CWC). Does not replace CWC, ASDMA, or local authority warnings.</p>
    </div>
    <nav class="footer-links" aria-label="Footer">
      <a href="https://cwc.gov.in" rel="noopener" target="_blank">CWC</a>
      <a href="https://sdmassam.nic.in" rel="noopener" target="_blank">ASDMA</a>
      <a href="/about/">About</a>
      <a href="/settings/">Settings</a>
    </nav>
  </div>
</footer>

<p class="sr-only" aria-live="polite" aria-atomic="true">{liveStatus}</p>
