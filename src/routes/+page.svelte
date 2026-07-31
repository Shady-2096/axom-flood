<!--
  THESIS: Search visitors need a stable Assam flood information desk before they
  enter the live, locality-aware river instrument.
  MODE: Preserve the River Observatory visual system. Add crawlable public-
  service content without changing the working app routes.

  Real visitors are redirected to /home/ immediately. The prerendered HTML
  keeps the structured data, FAQ schema, and crawlable text for search
  engines that do not execute JavaScript.
-->
<script>
  import { goto } from "$app/navigation";
  import {
    faqItems,
    faqSchema,
    serializeJsonLd,
    websiteSchema,
  } from "$lib/landing-seo.js";
  import { onMount } from "svelte";

  const websiteJsonLd = serializeJsonLd(websiteSchema);
  const faqJsonLd = serializeJsonLd(faqSchema);

  onMount(() => {
    goto("/home/", { replaceState: true });
  });
</script>

<svelte:head>
  <meta http-equiv="refresh" content="0;url=/home/">
  {@html `<script type="application/ld+json">${websiteJsonLd}</script>`}
  {@html `<script type="application/ld+json">${faqJsonLd}</script>`}
</svelte:head>

<article class="search-landing">
  <section class="landing-hero">
    <div class="hero-copy">
      <p class="landing-kicker">Assam flood information</p>
      <h1>Clear information on Assam floods.</h1>
      <p class="landing-lede">
        Check official river measurements, local alerts, relief camps and emergency contacts in plain language.
      </p>
      <div class="hero-actions">
        <a class="landing-primary" href="/home/">Check Assam rivers</a>
        <a class="landing-secondary" href="#how-it-works">How the information works</a>
      </div>
    </div>
    <figure class="river-portrait">
      <img
        src="/assam-river-landscape.avif"
        width="960"
        height="560"
        alt="Illustrative aerial view of braided river channels in Assam"
        fetchpriority="high"
      >
      <figcaption>Illustrative river landscape. Open the live bulletin for current conditions.</figcaption>
    </figure>
  </section>

  <nav class="need-paths" aria-label="Assam flood information">
    <a href="/home/">
      <span>River status</span>
      <strong>Latest Assam flood alerts and river levels</strong>
      <small>Search by village, revenue circle or district</small>
    </a>
    <a href="/camps/">
      <span>Relief</span>
      <strong>Published Assam flood camp listings</strong>
      <small>Confirm locally before travelling</small>
    </a>
    <a href="/emergency/">
      <span>Emergency</span>
      <strong>Reviewed flood contacts and helplines</strong>
      <small>Coverage limits are shown clearly</small>
    </a>
  </nav>

  <section class="meaning-section" id="how-it-works">
    <header>
      <h2>How to read an Assam flood update</h2>
      <p>
        A river number means little without its threshold, direction, age and source. Axom Flood keeps those parts together.
      </p>
    </header>
    <dl class="meaning-list">
      <div>
        <dt>Observed river level</dt>
        <dd>The latest available CWC measurement, labelled in metres above mean sea level.</dd>
      </div>
      <div>
        <dt>Warning and danger levels</dt>
        <dd>Published station thresholds used to explain whether a river needs attention.</dd>
      </div>
      <div>
        <dt>Trend and forecast</dt>
        <dd>Whether the reading is rising, steady or falling, plus an official forecast when available.</dd>
      </div>
      <div>
        <dt>Age and source</dt>
        <dd>The observation time and original source stay visible. Stale numbers are not shown as current.</dd>
      </div>
    </dl>
  </section>

  <section class="source-section">
    <div class="source-copy">
      <h2>Built around official Assam flood sources</h2>
      <p>
        River measurements come from the Central Water Commission. Relief information comes from published district and ASDMA documents when available.
      </p>
      <p>
        Axom Flood is an independent interpretation layer. It links back to sources and never claims to replace an official warning.
      </p>
    </div>
    <aside>
      <strong>What the search understands</strong>
      <p>
        Village names and spelling variants resolve to a revenue circle. River gauges are assigned by reviewed river topology, never by nearest distance.
      </p>
      <a href="/home/">Search for a place in Assam</a>
    </aside>
  </section>

  <section class="faq-section">
    <header>
      <h2>Assam flood information questions</h2>
      <p>Short answers about freshness, sources, relief information and offline use.</p>
    </header>
    <div class="faq-list">
      {#each faqItems as item}
        <details>
          <summary>{item.question}</summary>
          <p>{item.answer}</p>
        </details>
      {/each}
    </div>
  </section>

  <footer class="landing-footer">
    <p>
      <strong>Axom Flood</strong>
      <span>Independent plain-language river information for Assam.</span>
    </p>
    <nav aria-label="Information links">
      <a href="/home/">River</a>
      <a href="/camps/">Relief camps</a>
      <a href="/emergency/">Emergency</a>
      <a href="https://ffs.india-water.gov.in/" rel="noopener" target="_blank">CWC source</a>
    </nav>
  </footer>
</article>

<style>
  .search-landing {
    width: min(1180px, 100%);
    margin: 0 auto;
    padding: 32px 0 72px;
  }

  .landing-hero {
    display: grid;
    grid-template-columns: minmax(0, 1.05fr) minmax(360px, .95fr);
    align-items: center;
    gap: clamp(36px, 6vw, 84px);
    min-height: min(720px, calc(100dvh - 112px));
  }

  .hero-copy {
    max-width: 650px;
  }

  .landing-kicker {
    margin: 0 0 24px;
    color: var(--river);
    font-size: 14px;
    font-weight: 800;
    letter-spacing: .12em;
    text-transform: uppercase;
  }

  h1,
  h2 {
    font-family: var(--body);
    color: var(--ink);
  }

  h1 {
    max-width: 680px;
    margin: 0;
    font-size: clamp(40px, 5vw, 64px);
    line-height: .98;
    letter-spacing: -.045em;
  }

  .landing-lede {
    max-width: 590px;
    margin: 32px 0 0;
    color: var(--graphite);
    font-size: clamp(18px, 2vw, 23px);
    line-height: 1.45;
  }

  .hero-actions {
    display: flex;
    align-items: center;
    gap: 20px;
    margin-top: 32px;
  }

  .landing-primary,
  .landing-secondary {
    min-height: 48px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    white-space: nowrap;
    font-weight: 800;
    text-decoration: none;
  }

  .landing-primary {
    padding: 0 24px;
    border-radius: var(--r-control);
    color: var(--on-action);
    background: var(--action);
  }

  .landing-primary:hover {
    color: var(--on-action);
    background: var(--action-hover);
  }

  .landing-secondary {
    color: var(--ink);
    border-bottom: 1px solid var(--line-strong);
  }

  .landing-primary:active,
  .landing-secondary:active {
    transform: translateY(1px);
  }

  .river-portrait {
    margin: 0;
  }

  .river-portrait img {
    display: block;
    width: 100%;
    min-height: 420px;
    object-fit: cover;
    border: 1px solid var(--line);
    border-radius: var(--r-sheet);
    box-shadow: var(--shadow-3);
  }

  .river-portrait figcaption {
    max-width: 52ch;
    margin: 12px 4px 0;
    color: var(--muted);
    font-size: 12px;
    line-height: 1.5;
  }

  .need-paths {
    display: grid;
    grid-template-columns: 1fr 1.2fr 1fr;
    margin: 32px 0 0;
    border-top: 1px solid var(--line);
    border-bottom: 1px solid var(--line);
  }

  .need-paths a {
    display: flex;
    min-height: 170px;
    flex-direction: column;
    justify-content: center;
    padding: 28px clamp(20px, 3vw, 38px);
    color: var(--ink);
    text-decoration: none;
  }

  .need-paths a + a {
    border-left: 1px solid var(--line);
  }

  .need-paths a:hover {
    background: var(--surface-inactive);
  }

  .need-paths span,
  .need-paths small {
    color: var(--muted);
  }

  .need-paths span {
    margin-bottom: 16px;
    font-size: 12px;
    font-weight: 800;
    letter-spacing: .08em;
    text-transform: uppercase;
  }

  .need-paths strong {
    max-width: 30ch;
    font-size: 18px;
    line-height: 1.35;
  }

  .need-paths small {
    margin-top: 12px;
    font-size: 14px;
    line-height: 1.45;
  }

  .meaning-section,
  .source-section,
  .faq-section {
    padding: clamp(72px, 9vw, 116px) 0;
  }

  .meaning-section > header,
  .faq-section > header {
    max-width: 720px;
  }

  h2 {
    margin: 0;
    font-size: clamp(36px, 4.5vw, 58px);
    line-height: 1.02;
    letter-spacing: -.035em;
  }

  .meaning-section > header p,
  .faq-section > header p {
    max-width: 64ch;
    margin: 20px 0 0;
    color: var(--muted);
    font-size: 18px;
    line-height: 1.6;
  }

  .meaning-list {
    display: grid;
    grid-template-columns: 1.1fr .9fr;
    gap: 0 clamp(42px, 7vw, 96px);
    margin: 56px 0 0;
  }

  .meaning-list div {
    padding: 24px 0;
    border-top: 1px solid var(--line);
  }

  .meaning-list dt {
    color: var(--ink);
    font-size: 18px;
    font-weight: 800;
  }

  .meaning-list dd {
    max-width: 48ch;
    margin: 12px 0 0;
    color: var(--graphite);
    line-height: 1.6;
  }

  .source-section {
    display: grid;
    grid-template-columns: minmax(0, 1.15fr) minmax(300px, .85fr);
    gap: clamp(40px, 9vw, 120px);
    align-items: start;
    border-top: 1px solid var(--line);
  }

  .source-copy p {
    max-width: 62ch;
    margin: 24px 0 0;
    color: var(--graphite);
    font-size: 18px;
    line-height: 1.65;
  }

  .source-section aside {
    padding: 32px;
    border: 1px solid var(--line);
    border-radius: var(--r-panel);
    color: var(--graphite);
    background: var(--surface-inactive);
  }

  .source-section aside strong {
    display: block;
    color: var(--ink);
    font-size: 18px;
  }

  .source-section aside p {
    margin: 16px 0 24px;
    line-height: 1.6;
  }

  .source-section aside a {
    color: var(--river);
    font-weight: 800;
  }

  .faq-section {
    border-top: 1px solid var(--line);
  }

  .faq-list {
    max-width: 900px;
    margin-top: 56px;
  }

  .faq-list details {
    border-bottom: 1px solid var(--line);
  }

  .faq-list summary {
    padding: 24px 40px 24px 0;
    color: var(--ink);
    cursor: pointer;
    font-size: 18px;
    font-weight: 800;
    line-height: 1.4;
  }

  .faq-list p {
    max-width: 72ch;
    margin: -4px 0 24px;
    color: var(--graphite);
    line-height: 1.65;
  }

  .landing-footer {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 40px;
    padding: 32px 0 8px;
    border-top: 1px solid var(--line-strong);
  }

  .landing-footer p {
    margin: 0;
  }

  .landing-footer strong,
  .landing-footer span {
    display: block;
  }

  .landing-footer strong {
    color: var(--ink);
    font-size: 18px;
  }

  .landing-footer span {
    margin-top: 6px;
    color: var(--muted);
  }

  .landing-footer nav {
    display: flex;
    flex-wrap: wrap;
    gap: 12px 24px;
  }

  .landing-footer a {
    color: var(--graphite);
  }

  @media (max-width: 860px) {
    .search-landing {
      padding-top: 12px;
    }

    .landing-hero,
    .source-section {
      grid-template-columns: 1fr;
    }

    .landing-hero {
      gap: 40px;
      min-height: 0;
      padding: 40px 0 32px;
    }

    h1 {
      max-width: 620px;
    }

    .river-portrait img {
      min-height: 0;
      aspect-ratio: 16 / 10;
    }

    .need-paths {
      grid-template-columns: 1fr;
    }

    .need-paths a {
      min-height: 0;
      padding: 24px 0;
    }

    .need-paths a + a {
      border-top: 1px solid var(--line);
      border-left: 0;
    }

    .meaning-list {
      grid-template-columns: 1fr;
    }

    .source-section {
      gap: 40px;
    }
  }

  @media (max-width: 560px) {
    .hero-actions {
      align-items: stretch;
      flex-direction: column;
    }

    .landing-secondary {
      justify-content: flex-start;
      width: fit-content;
    }

    .landing-footer {
      align-items: flex-start;
      flex-direction: column;
    }

    .landing-footer nav {
      display: grid;
    }
  }
</style>
