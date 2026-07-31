<script>
  import { onMount } from "svelte";
  import {
    IMPACT_METRICS,
    compareSummaries,
    formatMetric,
    loadImpactSituation,
    metricValue,
  } from "$lib/data/impact.js";

  let status = $state("loading");
  let errorMessage = $state("");
  let situation = $state(null);
  let online = $state(true);

  const dateFormatter = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  const timeFormatter = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
  const integerFormatter = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
  const decimalFormatter = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

  let impact = $derived(situation?.impact);
  let pointer = $derived(situation?.pointer);
  let summary = $derived(impact?.state_summary);
  let seasonLosses = $derived(situation?.seasonLosses);
  let comparison = $derived(
    impact ? compareSummaries(summary, situation?.previous?.state_summary) : [],
  );
  let districts = $derived(
    [...(impact?.districts || [])]
      .sort((left, right) =>
        (right.affected_population || 0) - (left.affected_population || 0)
        || left.district.localeCompare(right.district)
      ),
  );
  let circles = $derived(
    [...(impact?.revenue_circles || [])]
      .sort((left, right) =>
        (right.affected_population || 0) - (left.affected_population || 0)
        || left.revenue_circle.localeCompare(right.revenue_circle)
      ),
  );
  let history = $derived(situation?.history?.reports || []);
  let lossEvidenceCount = $derived(seasonLosses?.coverage?.reports?.length || 0);
  let unpublishedLossDates = $derived(seasonLosses?.coverage?.unpublished_dates || []);

  function formatDate(value) {
    return dateFormatter.format(new Date(`${value}T12:00:00+05:30`));
  }

  function formatTime(value) {
    return timeFormatter.format(new Date(value));
  }

  function formatNumber(value, decimal = false) {
    if (!Number.isFinite(value)) return "Not reported";
    return (decimal ? decimalFormatter : integerFormatter).format(value);
  }

  function formatReportedPopulation(value) {
    if (!Number.isFinite(value)) return "Not reported";
    return value === 0 ? "0 reported" : integerFormatter.format(value);
  }

  function changeLabel(item) {
    if (!Number.isFinite(item.change)) return "Comparison unavailable";
    if (item.change === 0) return "No change";
    const direction = item.change > 0 ? "increase" : "decrease";
    return `${formatNumber(Math.abs(item.change), !Number.isInteger(item.change))} ${IMPACT_METRICS[item.metricKey].unit} ${direction}`;
  }

  function profileLabel(value) {
    return value === "validated_partial" ? "Validated partial" : "Validated";
  }

  function publicPath(value) {
    if (!value) return "";
    return value.startsWith("/") ? value : `/${value}`;
  }

  function historyStateLabel(report) {
    if (report.revision_id === pointer.revision_id) {
      return situation.state === "stale"
        ? "historical"
        : report.publication_state;
    }
    if (report.report_date < pointer.report_date) return "historical";
    if (report.report_date === pointer.report_date) return "superseded";
    return report.publication_state;
  }

  onMount(() => {
    online = navigator.onLine;
    const updateOnline = () => {
      online = navigator.onLine;
    };
    window.addEventListener("online", updateOnline);
    window.addEventListener("offline", updateOnline);
    loadImpactSituation()
      .then(result => {
        situation = result;
        status = "ready";
      })
      .catch(error => {
        status = error.code === "quarantined" ? "quarantined" : "error";
        errorMessage = error.message;
      });
    return () => {
      window.removeEventListener("online", updateOnline);
      window.removeEventListener("offline", updateOnline);
    };
  });
</script>

{#if status === "loading"}
  <section class="screen situation-screen" aria-busy="true">
    <header class="situation-heading">
      <div class="loading-line short"></div>
      <div class="loading-line title"></div>
      <div class="loading-line body"></div>
    </header>
    <div class="loading-metrics">
      {#each Array(6) as _}
        <div><span></span><strong></strong></div>
      {/each}
    </div>
    <p class="sr-only">Loading the ASDMA situation report.</p>
  </section>
{:else if status === "quarantined"}
  <section class="screen situation-screen state-message">
    <p class="state-label">Publication stopped</p>
    <h1>Latest report held for review</h1>
    <p>The newest ASDMA report did not pass deterministic validation. Its figures are not shown as current.</p>
    <a href="/" class="button secondary">Open river bulletin</a>
  </section>
{:else if status === "error"}
  <section class="screen situation-screen state-message">
    <p class="state-label">Report unavailable</p>
    <h1>Situation report could not load</h1>
    <p>{errorMessage || "Reconnect to save the latest validated ASDMA report on this device."}</p>
    <a href="/" class="button secondary">Open river bulletin</a>
  </section>
{:else}
  <article class="screen situation-screen">
    <header class="situation-heading">
      <div>
        <p class="state-label">Assam administrative impact</p>
        <h1>Statewide situation</h1>
        <p class="summary">
          ASDMA's report for {formatDate(impact.report_date)} lists
          <strong>{formatNumber(summary.affected_population)} affected people</strong>
          across <strong>{formatNumber(summary.affected_districts)} districts</strong>.
        </p>
      </div>
      <aside class:stale={situation.state === "stale"} class="report-state">
        <strong>{situation.state === "stale" ? "Historical report" : profileLabel(impact.publication.state)}</strong>
        <span>{situation.ageDays === 0 ? "Report dated today" : `${situation.ageDays} days since report date`}</span>
        <span>Fetched {formatTime(impact.fetched_at)}</span>
        <span>{online ? "Network available" : "Saved report shown offline"}</span>
      </aside>
    </header>

    {#if situation.state === "stale"}
      <p class="stale-notice">This report is outside the three-day current-impact window. It remains available as official history and appears only as a muted historical layer on the main map.</p>
    {/if}

    {#if situation.newerAttemptQuarantined}
      <p class="quarantine-notice">A newer ASDMA report revision was held by validation. This page continues to show the latest validated report and does not substitute the rejected figures.</p>
    {/if}

    <a class="revision-link" href={publicPath(impact.source.artifact_url)} rel="noopener" target="_blank">
      All figures: exact retained ASDMA report revision {impact.revision_id.slice(0, 12)}.
    </a>

    <dl class="headline-metrics">
      <div>
        <dt>Affected villages</dt>
        <dd>{formatNumber(summary.affected_villages)}</dd>
      </div>
      <div>
        <dt>Revenue circles</dt>
        <dd>{formatNumber(summary.affected_revenue_circles)}</dd>
      </div>
      <div>
        <dt>Crop area submerged</dt>
        <dd>{formatNumber(summary.crop_area_submerged_hectares, true)} <small>hectares</small></dd>
      </div>
      <div>
        <dt>Relief camps</dt>
        <dd>{formatNumber(summary.relief_camps_open)}</dd>
      </div>
      <div>
        <dt>Camp occupants</dt>
        <dd>{formatNumber(summary.relief_camp_occupants)}</dd>
      </div>
      <div>
        <dt>Distribution centres</dt>
        <dd>{formatNumber(summary.relief_distribution_centres_open)}</dd>
      </div>
    </dl>

    <section class="human-impact" aria-labelledby="human-impact-title">
      <div>
        <h2 id="human-impact-title">People, homes and livestock</h2>
        {#if seasonLosses}
          <p>These totals sum daily additions in {lossEvidenceCount} retained ASDMA reports from {formatDate(seasonLosses.season_start_date)} through {formatDate(seasonLosses.as_of_date)}. The missing figure records reports made, not the number of people still missing.</p>
          {#if unpublishedLossDates.length}
            <p>ASDMA did not publish a daily report for {unpublishedLossDates.map(formatDate).join(", ")}.</p>
          {/if}
          <p class="loss-sources">
            <a href="/data/asdma-season-losses.json" rel="noopener" target="_blank">Open the exact-report evidence manifest</a>
            <a href={seasonLosses.source.url} rel="noopener" target="_blank">Open ASDMA's daily report service</a>
          </p>
        {:else}
          <p>The generated statewide season-loss checkpoint is unavailable. Daily incident values are not substituted for cumulative totals.</p>
        {/if}
      </div>
      <dl>
        <div class="season-loss">
          <dt>Deaths newly confirmed in retained reports</dt>
          <dd>{seasonLosses ? formatNumber(seasonLosses.statewide.confirmed_deaths) : "Unavailable"}</dd>
          {#if seasonLosses}<small>Sum of daily additions through {formatDate(seasonLosses.as_of_date)}</small>{/if}
        </div>
        <div class="season-loss">
          <dt>People newly reported missing in retained reports</dt>
          <dd>{seasonLosses ? formatNumber(seasonLosses.statewide.people_reported_missing) : "Unavailable"}</dd>
          {#if seasonLosses}<small>Reports made, not currently missing</small>{/if}
        </div>
        <div><dt>Homes fully damaged</dt><dd>{formatNumber(summary.houses_damaged?.fully_total)}</dd></div>
        <div><dt>Homes partly damaged</dt><dd>{formatNumber(summary.houses_damaged?.partially_total)}</dd></div>
        <div><dt>Livestock affected</dt><dd>{formatNumber(summary.livestock_affected?.total)}</dd></div>
        <div><dt>Livestock washed away</dt><dd>{formatNumber(summary.livestock_washed_away?.total)}</dd></div>
      </dl>
    </section>

    <section class="activity" aria-labelledby="activity-title">
      <h2 id="activity-title">Relief, rescue and infrastructure</h2>
      <div class="activity-columns">
        <dl>
          <div><dt>Boats deployed</dt><dd>{formatNumber(impact.rescue.boats_deployed)}</dd></div>
          <div><dt>Medical teams</dt><dd>{formatNumber(impact.rescue.medical_teams_deployed)}</dd></div>
          <div><dt>People evacuated by boat</dt><dd>{formatNumber(impact.rescue.people_evacuated_by_boat)}</dd></div>
          <div><dt>Animals evacuated by boat</dt><dd>{formatNumber(impact.rescue.animals_evacuated_by_boat)}</dd></div>
        </dl>
        <dl>
          <div><dt>Damaged roads</dt><dd>{formatNumber(summary.damaged_roads)}</dd></div>
          <div><dt>Damaged bridges</dt><dd>{formatNumber(summary.damaged_bridges)}</dd></div>
          <div><dt>Breached embankments</dt><dd>{formatNumber(summary.breached_embankments)}</dd></div>
          <div><dt>Affected embankments</dt><dd>{formatNumber(summary.affected_embankments)}</dd></div>
        </dl>
      </div>
    </section>

    {#if situation.previous}
      <section class="comparison" aria-labelledby="comparison-title">
        <header>
          <h2 id="comparison-title">Change from {formatDate(situation.previous.report_date)}</h2>
          <p>Direct subtraction between two validated report revisions. A missing report is never treated as zero.</p>
        </header>
        <dl>
          {#each comparison as item}
            <div>
              <dt>{IMPACT_METRICS[item.metricKey].label}</dt>
              <dd class:increase={item.change > 0} class:decrease={item.change < 0}>{changeLabel(item)}</dd>
            </div>
          {/each}
        </dl>
      </section>
    {/if}

    <section class="main-map-link" aria-labelledby="main-map-title">
      <div>
        <h2 id="main-map-title">See the statewide pattern</h2>
        <p>Open the affected-people layer on the main Assam map. Switch layers there for villages, crop area, relief occupancy, relief centres and infrastructure reports.</p>
      </div>
      <a class="button" href="/?layer=affected_population">Open the main impact map</a>
    </section>

    <section class="table-section" aria-labelledby="district-table-title">
      <header>
        <h2 id="district-table-title">District figures</h2>
        <p>District totals from revision {impact.revision_id.slice(0, 12)}. “0 reported” is ASDMA's submitted value, not proof that nobody was affected.</p>
      </header>
      <div class="table-scroll" role="region" aria-label="Scrollable district impact table">
        <table>
          <caption>ASDMA district impact report dated {formatDate(impact.report_date)}</caption>
          <thead>
            <tr>
              <th scope="col">District</th>
              <th scope="col">Affected people</th>
              <th scope="col">Villages</th>
              <th scope="col">Crop hectares</th>
              <th scope="col">Camp occupants</th>
            </tr>
          </thead>
          <tbody>
            {#each districts as district}
              <tr>
                <th scope="row">{district.district}</th>
                <td>{formatReportedPopulation(district.affected_population)}</td>
                <td>{formatNumber(district.affected_villages)}</td>
                <td>{formatNumber(district.crop_area_submerged_hectares, true)}</td>
                <td>{formatNumber(district.relief_camp_occupants)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </section>

    <section class="table-section" aria-labelledby="circle-table-title">
      <header>
        <h2 id="circle-table-title">Revenue-circle figures</h2>
        <p>A circle count does not identify every affected village inside that circle. ASDMA can report zero affected people alongside non-zero village or crop figures; treat that combination as an incomplete or internally inconsistent submission.</p>
      </header>
      <div class="table-scroll" role="region" aria-label="Scrollable revenue-circle impact table">
        <table>
          <caption>ASDMA revenue-circle impact report dated {formatDate(impact.report_date)}</caption>
          <thead>
            <tr>
              <th scope="col">District</th>
              <th scope="col">Revenue circle</th>
              <th scope="col">Affected people</th>
              <th scope="col">Villages</th>
              <th scope="col">Crop hectares</th>
              <th scope="col">Relief centres</th>
            </tr>
          </thead>
          <tbody>
            {#each circles as circle}
              <tr>
                <td>{circle.district}</td>
                <th scope="row">{circle.revenue_circle}</th>
                <td>{formatReportedPopulation(circle.affected_population)}</td>
                <td>{formatNumber(circle.affected_villages)}</td>
                <td>{formatNumber(circle.crop_area_submerged_hectares, true)}</td>
                <td>{formatNumber(metricValue(circle, "relief_centres_open"))}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </section>

    <section class="history" aria-labelledby="history-title">
      <header>
        <h2 id="history-title">Report history and revisions</h2>
        <p>Same-date revisions remain separate. The source hash identifies the exact retained evidence.</p>
      </header>
      <div class="history-list">
        {#each history as report}
          <details open={report.revision_id === pointer.revision_id}>
            <summary>
              <span>{formatDate(report.report_date)}</span>
              <strong>{historyStateLabel(report).replaceAll("_", " ")}</strong>
            </summary>
            <div>
              <code>{report.revision_id}</code>
              <p>Fetched {formatTime(report.fetched_at)}. Extractor v{report.extractor_version}, {report.profile}.</p>
              <a href={publicPath(report.source_artifact_url)} rel="noopener" target="_blank">Open the exact retained report</a>
            </div>
          </details>
        {/each}
      </div>
    </section>

    <aside class="limitations" aria-labelledby="limits-title">
      <h2 id="limits-title">What this report can and cannot show</h2>
      <p>ASDMA compiles district submissions for a report date. It can establish administrative counts, reported damage, relief activity and affected revenue circles.</p>
      <p>The statewide season-loss checkpoint is generated from retained daily reports because each death and missing-person table contains only incidents added in that bulletin. Its missing figure records reports made during the covered period, not the number of people still unaccounted for now.</p>
      <p>It cannot establish live water depth at a house, a current flood boundary, every affected village, or whether a route is safe now. Check the river bulletin and local authority instructions before acting.</p>
      <a href="/">Open the current river bulletin</a>
    </aside>
  </article>
{/if}

<style>
  .situation-screen { max-width: 1180px; }
  h1, h2, p, dl, dd { margin: 0; }
  h1 { max-width: 12ch; font: 800 clamp(48px, 8vw, 72px)/.92 var(--display); letter-spacing: -.035em; }
  h2 { font: 800 28px/1 var(--display); letter-spacing: -.02em; }
  .state-label { margin-bottom: 12px; color: var(--river); font-size: 12px; font-weight: 800; letter-spacing: .05em; text-transform: uppercase; }

  .situation-heading {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(240px, .4fr);
    gap: 40px;
    align-items: end;
    padding: 32px 0 40px;
  }

  .summary { max-width: 62ch; margin-top: 24px; color: var(--ink-soft); font-size: 18px; line-height: 1.55; }
  .summary strong { color: var(--ink); }

  .report-state {
    display: grid;
    gap: 8px;
    padding: 20px 0 20px 20px;
    border-left: 4px solid var(--safe);
  }

  .report-state.stale { border-color: var(--sediment); }
  .report-state strong { font-size: 16px; }
  .report-state span { color: var(--muted); font-size: 12px; line-height: 1.4; }
  .stale-notice, .quarantine-notice { padding: 16px 20px; border-left: 4px solid var(--sediment); color: var(--ink-soft); background: var(--surface-inactive); font-size: 14px; line-height: 1.5; }
  .quarantine-notice { border-color: #744f59; }

  .revision-link {
    display: inline-block;
    margin-bottom: 24px;
    color: var(--river);
    font-size: 12px;
    font-weight: 700;
    line-height: 1.5;
    overflow-wrap: anywhere;
    text-underline-offset: 4px;
  }

  .headline-metrics {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    border-top: 1px solid var(--line);
  }

  .headline-metrics > div { padding: 24px 24px 24px 0; border-bottom: 1px solid var(--line); }
  dt { color: var(--muted); font-size: 12px; line-height: 1.4; }
  dd { margin-top: 8px; color: var(--ink); font-size: 28px; font-weight: 800; line-height: 1; }
  dd small { color: var(--muted); font-size: 12px; font-weight: 650; }

  .human-impact, .comparison, .activity, .table-section, .history, .limitations {
    margin-top: 56px;
    padding-top: 32px;
    border-top: 1px solid var(--line);
  }

  .human-impact {
    display: grid;
    grid-template-columns: minmax(220px, .6fr) minmax(0, 1fr);
    gap: 40px;
  }

  .human-impact > div > p,
  .comparison header p,
  .table-section header p,
  .history header p,
  .main-map-link p {
    max-width: 64ch;
    margin-top: 12px;
    color: var(--muted);
    font-size: 14px;
    line-height: 1.55;
  }

  .human-impact dl, .comparison dl {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 24px 32px;
  }

  .human-impact dd { font-size: 24px; }
  .human-impact .season-loss { padding-bottom: 16px; border-bottom: 2px solid var(--river); }
  .human-impact .season-loss dd { font-size: 28px; }
  .human-impact .season-loss small { display: block; margin-top: 8px; color: var(--muted); font-size: 11px; line-height: 1.4; }
  .loss-sources { display: flex; flex-wrap: wrap; gap: 8px 16px; }
  .loss-sources a { color: var(--river); font-size: 12px; font-weight: 700; text-underline-offset: 4px; }
  .activity-columns { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 40px; margin-top: 24px; }
  .activity dl > div { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; padding: 12px 0; border-bottom: 1px solid var(--line); }
  .activity dd { margin: 0; font-size: 18px; }

  .comparison dl { margin-top: 24px; }
  .comparison dl > div { padding: 16px 0; border-bottom: 1px solid var(--line); }
  .comparison dd { font-size: 16px; line-height: 1.35; }
  .comparison dd.increase, .comparison dd.decrease { color: var(--graphite); }

  .main-map-link {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: 24px;
    margin-top: 56px;
    padding: 24px;
    border: 1px solid var(--line);
    border-radius: var(--r-panel);
    background: var(--surface-inactive);
  }

  .main-map-link p {
    max-width: 64ch;
    margin-top: 12px;
    color: var(--muted);
    font-size: 14px;
    line-height: 1.55;
  }
  .main-map-link .button { flex: 0 0 auto; }

  .table-section header, .history header { margin-bottom: 24px; }
  .table-scroll { max-width: 100%; overflow-x: auto; border: 1px solid var(--line); border-radius: var(--r-control); }
  table { width: 100%; min-width: 720px; border-collapse: collapse; background: var(--surface-inactive); }
  caption { padding: 16px 20px; color: var(--muted); font-size: 12px; text-align: left; }
  th, td { padding: 12px 16px; border-top: 1px solid var(--line); font-size: 14px; text-align: right; }
  th { color: var(--ink); font-weight: 750; }
  th:first-child, td:first-child { text-align: left; }
  thead th { color: var(--muted); font-size: 11px; letter-spacing: .04em; text-transform: uppercase; }
  tbody tr:hover { background: var(--shade); }

  .history-list { border-top: 1px solid var(--line); }
  details { border-bottom: 1px solid var(--line); }
  summary { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 20px 0; cursor: pointer; }
  summary span { font-size: 16px; font-weight: 750; }
  summary strong { color: var(--river); font-size: 11px; text-transform: capitalize; }
  details > div { padding: 0 0 20px; }
  code { display: block; max-width: 100%; color: var(--graphite); font-size: 11px; overflow-wrap: anywhere; }
  details p { margin-top: 8px; color: var(--muted); font-size: 12px; }
  details a, .limitations a { display: inline-block; margin-top: 12px; color: var(--river); font-size: 14px; font-weight: 700; text-underline-offset: 4px; }

  .limitations { max-width: 820px; padding-bottom: 40px; }
  .limitations p { margin-top: 16px; color: var(--ink-soft); font-size: 15px; line-height: 1.65; }

  .state-message { max-width: 720px; padding-top: 72px; }
  .state-message h1 { font-size: clamp(40px, 7vw, 64px); }
  .state-message > p:not(.state-label) { max-width: 58ch; margin-top: 20px; color: var(--muted); font-size: 16px; line-height: 1.6; }
  .state-message .button { display: inline-flex; margin-top: 24px; }

  .loading-line, .loading-metrics span, .loading-metrics strong { display: block; border-radius: var(--r-control); background: var(--surface-inactive); }
  .loading-line.short { width: 180px; height: 12px; }
  .loading-line.title { width: min(560px, 90%); height: 72px; margin-top: 16px; }
  .loading-line.body { width: min(620px, 100%); height: 48px; margin-top: 24px; }
  .loading-metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border-top: 1px solid var(--line); }
  .loading-metrics div { padding: 24px 24px 24px 0; border-bottom: 1px solid var(--line); }
  .loading-metrics span { width: 120px; height: 12px; }
  .loading-metrics strong { width: 88px; height: 28px; margin-top: 12px; }

  @media (max-width: 700px) {
    .situation-heading { display: block; padding-top: 24px; }
    .report-state { margin-top: 24px; padding: 16px 0 16px 16px; }
    .headline-metrics, .loading-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .headline-metrics > div, .loading-metrics div { padding-right: 12px; }
    .human-impact { display: block; }
    .human-impact dl { margin-top: 24px; }
    .human-impact dl, .comparison dl, .activity-columns { grid-template-columns: 1fr; gap: 16px; }
    .activity-columns { gap: 0; }
    .main-map-link { display: block; padding: 20px; }
    .main-map-link .button { width: 100%; margin-top: 20px; }
    h1 { font-size: clamp(44px, 14vw, 64px); }
    h2 { font-size: 24px; }
    .summary { font-size: 16px; }
    dd { font-size: 24px; }
  }
</style>
