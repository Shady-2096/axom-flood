<script>
  import { onMount } from "svelte";
  import {
    formatLevel,
    formatObserved,
    getBundle,
    levelNumber,
    technicalReading,
    trendText,
  } from "$lib/data/index.js";
  import Icon from "./Icon.svelte";

  let { locality, gauge, open = $bindable(false) } = $props();
  const bundle = getBundle();

  let presentation = $derived(technicalReading(gauge));
  let forecast = $derived(gauge?.forecast);

  /* Rising and falling are not equally good news, so the trend gets a direction
     as well as a number. The 0.5 cm/hr deadband matches trendText(), which is
     what prints the words. */
  let trendDirection = $derived.by(() => {
    const rate = Number(gauge?.trend_cm_per_hr);
    if (!Number.isFinite(rate)) return null;
    if (Math.abs(rate) < .5) return "steady";
    return rate > 0 ? "rising" : "falling";
  });

  /* The distance to the next mark the river has not yet reached. This is the
     number a person actually wants — "how much room is left" — and until now it
     was something the reader had to work out by subtracting two figures on
     opposite sides of the deck. Stated against the nearest threshold above the
     reading, and once the danger mark is passed it measures upward from it
     instead, because at that point the remaining headroom is not the point. */
  let headroom = $derived.by(() => {
    const level = Number(gauge?.level_m);
    if (!Number.isFinite(level)) return null;
    const warning = Number(gauge?.warning_level_m);
    const danger = Number(gauge?.danger_level_m);
    const highest = Number(gauge?.highest_flood_level_m);
    if (Number.isFinite(warning) && level < warning) {
      return { metres: warning - level, label: "below the warning level", tone: "calm" };
    }
    if (Number.isFinite(danger) && level < danger) {
      return { metres: danger - level, label: "below the danger level", tone: "warning" };
    }
    if (Number.isFinite(highest) && level < highest) {
      return { metres: level - danger, label: "above the danger level", tone: "danger" };
    }
    if (Number.isFinite(highest)) {
      return { metres: level - highest, label: "above the highest recorded flood", tone: "danger" };
    }
    return null;
  });

  onMount(() => {
    const media = window.matchMedia("(min-width: 860px)");
    const update = () => {
      open = media.matches;
    };
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  });
</script>

<details class="technical-panel" bind:open>
  <summary>
    <span class="summary-text">
      <span class="summary-title">River gauge details</span>
      <!-- Collapsed, this row is the only thing on screen, so it carries the
           reading rather than a description of itself. A disclosure whose shut
           state says nothing is an empty box asking to be opened. -->
      <small>
        {#if !open && locality?.revenue_circle}
          {locality.revenue_circle}{gauge?.site_name ? ` · ${gauge.site_name} gauge` : ""}{Number.isFinite(presentation.reading)
            ? ` · ${levelNumber(gauge.level_m)} m` : ""}
        {:else}
          Water level, thresholds and source
        {/if}
      </small>
    </span>
    <span class="disclosure">
      {open ? "Show less" : "Show more"}
      <i aria-hidden="true"><Icon name="chevron" /></i>
    </span>
  </summary>

  <div class="technical-content">
    <header class="reading-header">
      <div>
        <p class="data-label">Selected area</p>
        <h2>{locality?.revenue_circle || "Area unavailable"} <span>/</span> {locality?.district || "District unavailable"}</h2>
      </div>
      <p>Levels are metres above mean sea level, not water depth at your house.</p>
    </header>

    <p class="gauge-attribution">
      <strong>River reading:</strong>
      {gauge?.site_name ? `${gauge.site_name} gauge` : "Gauge unavailable"}{gauge?.river ? ` on the ${gauge.river}` : ""}
      · {gauge?.agency || gauge?.source || "Central Water Commission"}
    </p>

    <div class="gauge-deck">
      <div class="lead">
        <p class="data-label">Current level</p>
        <p class="lead-value"><b>{levelNumber(gauge?.level_m)}</b>{#if Number.isFinite(presentation.reading)}<span>m</span>{/if}</p>
        {#if headroom}
          <p class={`headroom ${headroom.tone}`}>
            <b>{headroom.metres.toFixed(2)} m</b> {headroom.label}
          </p>
        {/if}
        <p class="lead-note">
          {#if Number.isFinite(presentation.reading)}
            Measured {formatObserved(gauge?.observed_at)}.
          {:else}
            No current level was published for this station.
          {/if}
        </p>
      </div>

      <dl class="support">
        {#each presentation.thresholds as item (item.label)}
          <div class:crossed={item.crossed} class={`support-row mark-${item.key}`}>
            <dt>{item.label}</dt>
            <dd>{item.value}{#if item.crossed}<span class="crossed-tag">Reached</span>{/if}</dd>
          </div>
        {/each}
        <div class={`support-row trend ${trendDirection || ""}`}>
          <dt>Recent trend</dt>
          <dd>
            {#if trendDirection}<i class="trend-arrow" aria-hidden="true"><Icon name={trendDirection} /></i>{/if}
            {trendText(gauge)}
          </dd>
        </div>
      </dl>
    </div>

    {#if presentation.hasCalibratedScale}
      {@const at = key => presentation.markers.find(marker => marker.key === key)}
      <div class="scale-section">
        <p class="scale-title">Position against official thresholds</p>
        <!-- Zones do the reading, not four chips on a hairline. The band is
             continuous so "how far below the warning mark am I" is a length the
             eye measures directly, and the current pointer sits above the band
             while the official marks label it from below, so the one number the
             reader owns never collides with the three they don't. -->
        <div
          class="level-track"
          role="img"
          style={`--at-warn:${at("warning").position.toFixed(1)}%; --at-danger:${at("danger").position.toFixed(1)}%; --at-cur:${at("current").position.toFixed(1)}%`}
          aria-label={`Current river level ${Number(gauge.level_m).toFixed(2)} metres. Warning ${Number(gauge.warning_level_m).toFixed(2)}, danger ${Number(gauge.danger_level_m).toFixed(2)}, and highest recorded flood ${Number(gauge.highest_flood_level_m).toFixed(2)} metres above mean sea level.`}
        >
          <div class="track-current" aria-hidden="true">
            <span class="track-current-value">{Number(gauge.level_m).toFixed(2)}<i>m</i></span>
            <span class="track-current-stem"></span>
          </div>
          <div class="track-band" aria-hidden="true"></div>
          <div class="track-marks" aria-hidden="true">
            {#each presentation.markers.filter(marker => marker.key !== "current") as marker (marker.key)}
              {#if Number.isFinite(Number(marker.value))}
                <div class={`track-mark ${marker.key}`} style={`--position:${marker.position.toFixed(1)}%`}>
                  <b>{Number(marker.value).toFixed(2)}</b>
                  <em>{marker.label}</em>
                </div>
              {/if}
            {/each}
          </div>
        </div>
      </div>
    {:else}
      <p class="empty">The comparison scale is unavailable because a current reading or official threshold is missing.</p>
    {/if}

    {#if forecast}
      <p class="forecast-note"><strong>CWC forecast:</strong> {formatLevel(forecast.forecast_level_m)}
        for {formatObserved(forecast.forecast_for)}{forecast.trend_word ? `, ${forecast.trend_word.toLowerCase()}` : ""}.</p>
    {/if}

    <footer class="data-foot">
      <p><strong>Measured {formatObserved(gauge?.observed_at)}</strong><br>
        {gauge?.agency || gauge?.source || "Central Water Commission"}<br>
        Station {gauge?.cwc_station_code || "not available"}.
        {locality.primary_gauge_mapping?.confidence || "unknown"} locality-match confidence</p>
      <a class="button secondary" href={gauge?.source_url || bundle.official_source_url}
        rel="noopener" target="_blank">Open official source <Icon name="external" /></a>
    </footer>
  </div>
</details>

<style>
  .technical-panel {
    margin-top: 56px;
    overflow: visible;
    border: 0;
    border-radius: 0;
    background: transparent;
  }

  /* A rule, not a card. The panel used to be a bordered box with its own fill,
     so shut it read as a large empty container with a "+" lost in the far
     corner — the widest, emptiest element on the page. A hairline separates it
     from the reading above at a fraction of the visual cost. */
  summary {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 24px;
    padding: 20px 0;
    border-top: 1px solid var(--line);
    color: var(--ink);
    cursor: pointer;
    font-family: var(--body);
    list-style: none;
  }

  summary::-webkit-details-marker { display: none; }

  summary:hover .disclosure {
    color: var(--ink);
    background: var(--surface-2);
  }

  .summary-text {
    display: grid;
    min-width: 0;
    gap: 4px;
  }

  .summary-title {
    font-size: 18px;
    font-weight: 760;
    letter-spacing: -.015em;
  }

  summary small {
    overflow: hidden;
    color: var(--muted);
    font-size: 14px;
    font-weight: 550;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* Named, not a glyph. "+" is a symbol the reader has to interpret; the two
     words say what happens, and the chevron only reinforces the direction. */
  .disclosure {
    display: inline-flex;
    min-height: 44px;
    align-items: center;
    flex: 0 0 auto;
    gap: 8px;
    padding: 12px 20px;
    border-radius: var(--r-pill);
    color: var(--ink);
    background: var(--surface);
    font-size: 14px;
    font-weight: 700;
    transition: background-color 140ms ease;
  }

  .disclosure i {
    display: block;
    width: 16px;
    height: 16px;
    transition: transform 180ms ease;
  }

  details[open] .disclosure i { transform: rotate(180deg); }

  .disclosure :global(svg) {
    width: 100%;
    height: 100%;
    fill: none;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 2;
  }

  @media (prefers-reduced-motion: reduce) {
    .disclosure i { transition: none; }
  }

  .technical-content { padding: 32px 0 0; }

  .reading-header {
    display: block;
  }

  .reading-header h2 {
    margin: 8px 0 0;
    font: 760 clamp(24px, 3vw, 36px)/1.08 var(--body);
    letter-spacing: -.025em;
    text-wrap: balance;
  }

  .reading-header h2 span {
    color: var(--river);
    font-weight: 500;
  }

  .reading-header > p {
    max-width: 65ch;
    margin: 8px 0 0;
    color: var(--muted);
    font-size: 14px;
    line-height: 1.5;
    text-align: left;
  }

  .gauge-attribution {
    margin: 20px 0 0;
    color: var(--muted);
    font-size: 14px;
    line-height: 1.5;
  }

  .gauge-attribution strong {
    color: var(--ink);
    font-weight: 720;
  }

  /* The deck is a raised plane now rather than a fixed dark slab, so it reads
     as an instrument in whichever scheme is running instead of only against
     paper. The hairline is what carries the edge at night, where a shadow on a
     near-black ground carries nothing. */
  .gauge-deck {
    display: grid;
    grid-template-columns: minmax(280px, .78fr) minmax(0, 1.22fr);
    margin-top: 12px;
    overflow: hidden;
    border: 1px solid var(--instrument-line);
    border-radius: var(--r-panel);
    color: var(--instrument-ink);
    background: var(--instrument);
    box-shadow: var(--shadow-1);
  }

  .lead {
    padding: 24px;
    border-right: 1px solid var(--instrument-line);
    background: var(--instrument-lead);
  }

  .lead .data-label { color: var(--instrument-accent); }

  /* The measurement is the one place the condensed face earns its keep: it is a
     calibrated number, not prose. */
  .lead-value {
    display: flex;
    align-items: baseline;
    gap: 6px;
    margin: 12px 0 0;
    color: var(--instrument-ink);
    font: 800 clamp(52px, 6.4vw, 76px)/.88 var(--display);
    font-variant-numeric: tabular-nums lining-nums;
    letter-spacing: -.035em;
  }

  .lead-value b { font-weight: 800; }

  .lead-value span {
    color: var(--instrument-muted);
    font-family: var(--body);
    font-size: .26em;
    font-weight: 700;
    letter-spacing: 0;
  }

  /* The one sentence that answers "how much room is left", sitting directly
     under the number it is derived from. */
  .headroom {
    margin: 12px 0 0;
    color: var(--instrument-lead-muted);
    font-size: 16px;
    font-weight: 600;
    line-height: 1.35;
    text-wrap: balance;
  }

  .headroom b {
    color: var(--instrument-ink);
    font-weight: 780;
    font-variant-numeric: tabular-nums lining-nums;
  }

  .headroom.warning b { color: var(--signal-ink); }
  .headroom.danger b { color: var(--instrument-danger); }

  .lead-note {
    max-width: 30ch;
    margin: 12px 0 0;
    color: var(--instrument-lead-muted);
    font-size: 14px;
    line-height: 1.5;
  }

  /* Ruled rather than floating. Four readings set loose in a 2×2 with 32px
     gutters had no structure holding them, so the eye had to decide for itself
     whether it was reading rows or columns. Hairlines make it a table, and a
     table is what four labelled numbers are. */
  .support {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    align-content: stretch;
    margin: 0;
    padding: 0;
  }

  .support-row {
    display: block;
    min-height: 0;
    padding: 20px 24px;
    border-bottom: 1px solid var(--instrument-line);
  }

  .support-row:nth-child(odd) { border-right: 1px solid var(--instrument-line); }
  .support-row:nth-last-child(-n+2) { border-bottom: 0; }

  .support-row dt {
    color: var(--instrument-muted);
    font-size: 14px;
    font-weight: 620;
    letter-spacing: .002em;
  }

  .support-row dd {
    margin: 6px 0 0;
    color: var(--instrument-ink);
    font-size: 24px;
    font-weight: 740;
    font-variant-numeric: tabular-nums lining-nums;
    letter-spacing: -.018em;
    text-align: left;
  }

  /* Each threshold value carries its own zone's colour, which is what ties the
     2×2 to the band underneath it. The deck used to print four white numbers
     and leave the reader to match them to a band by position alone; this is the
     legend, living on the values instead of in a separate row of swatches. The
     label beside each one still names it, so none of this is colour alone. */
  .support-row.mark-warning dd { color: var(--signal-ink); }
  .support-row.mark-danger dd { color: var(--danger-text); }
  .support-row.mark-highest dd { color: var(--sediment); }

  .support-row.trend.falling dd { color: var(--safe); }
  .support-row.trend.rising dd { color: var(--signal-ink); }

  .trend-arrow {
    display: inline-block;
    width: .85em;
    height: .85em;
    vertical-align: -.05em;
  }

  .trend-arrow :global(svg) {
    width: 100%;
    height: 100%;
    fill: none;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 2.2;
  }

  /* A breached threshold outranks its own zone colour. */
  .support-row.crossed dt,
  .support-row.crossed dd,
  .support-row.crossed.mark-warning dd,
  .support-row.crossed.mark-danger dd,
  .support-row.crossed.mark-highest dd { color: var(--instrument-danger); }

  .crossed-tag {
    display: block;
    margin-top: 4px;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: .06em;
    text-transform: uppercase;
  }

  .scale-section {
    padding: 32px 0 8px;
  }

  .scale-title {
    margin: 0;
    color: var(--muted);
    font-size: 14px;
    font-weight: 660;
  }

  .level-track {
    position: relative;
    margin-top: 56px;
  }

  /* Three zones read as one continuous quantity. Tints, not the safety colours
     at full strength: a solid red band would signal danger on a river sitting
     four metres below its danger mark. */
  .track-band {
    height: 14px;
    border-radius: var(--r-pill);
    /* Mixed into the surface rather than toward transparent. At 20–38% alpha
       over a near-black ground these zones were technically painted and
       practically invisible; mixing into an opaque base gives the same three
       steps a floor to sit on in either scheme.

       The stop positions are --at-* and not --warn/--danger on purpose: the
       latter would shadow the global safety-colour tokens for this whole
       subtree, and color-mix() handed a percentage where it wants a colour
       invalidates the entire declaration rather than just that stop. */
    background:
      linear-gradient(90deg,
        color-mix(in srgb, var(--river) 30%, var(--surface)) 0 var(--at-warn),
        color-mix(in srgb, var(--signal) 66%, var(--surface)) var(--at-warn) var(--at-danger),
        color-mix(in srgb, var(--danger) 78%, var(--surface)) var(--at-danger) 100%);
  }

  /* Where the river actually is, riding above the band on its own line. */
  .track-current {
    position: absolute;
    bottom: 100%;
    left: var(--at-cur);
    display: grid;
    justify-items: center;
    transform: translateX(-50%);
  }

  .track-current-value {
    display: inline-flex;
    align-items: baseline;
    gap: 4px;
    padding: 6px 12px;
    border-radius: var(--r-marker);
    color: var(--on-action);
    background: var(--action);
    font-size: 15px;
    font-weight: 780;
    font-variant-numeric: tabular-nums lining-nums;
    letter-spacing: -.01em;
    white-space: nowrap;
  }

  .track-current-value i {
    font-size: 11px;
    font-style: normal;
    font-weight: 700;
  }

  .track-current-stem {
    width: 3px;
    height: 16px;
    border-radius: 2px;
    background: var(--action);
  }

  .track-marks {
    position: relative;
    height: 46px;
  }

  /* The official marks label the band from below, each one anchored to its own
     position with a tick, so nothing has to be colour-matched to a legend. */
  .track-mark {
    position: absolute;
    top: 0;
    left: var(--position);
    display: grid;
    justify-items: center;
    gap: 4px;
    transform: translateX(-50%);
  }

  .track-mark::before {
    width: 1px;
    height: 8px;
    background: var(--line-strong);
    content: "";
  }

  .track-mark b {
    font-size: 14px;
    font-weight: 740;
    font-variant-numeric: tabular-nums lining-nums;
    letter-spacing: -.01em;
  }

  .track-mark em {
    color: var(--muted);
    font-size: 11px;
    font-style: normal;
    font-weight: 620;
    white-space: nowrap;
  }

  .track-mark.warning b { color: var(--signal-ink); }
  .track-mark.danger b { color: var(--danger-text); }
  .track-mark.highest b { color: var(--sediment); }

  .data-foot {
    padding-top: 0;
    border-top: 0;
  }

  @media (max-width: 859px) {
    .technical-panel {
      margin-top: 40px;
    }

    summary {
      min-height: 64px;
      padding: 0 0 16px;
    }

    .technical-content { padding: 20px 0 0; }
    .gauge-deck {
      display: block;
      margin-top: 20px;
    }

    .lead {
      border-right: 0;
      border-bottom: 0;
    }
  }

  @media (max-width: 520px) {
    .support {
      grid-template-columns: minmax(0, 1fr);
    }

    .support-row:nth-child(odd) { border-right: 0; }
    .support-row:nth-last-child(-n+2) { border-bottom: 1px solid var(--instrument-line); }
    .support-row:last-child { border-bottom: 0; }

    /* Three named marks cannot sit side by side in 320px without overlapping,
       so the words go and the numbers stay — the band already says which zone
       each boundary opens. */
    .track-mark em { display: none; }
    .track-mark b { font-size: 12px; }
    .track-marks { height: 28px; }
  }
</style>
