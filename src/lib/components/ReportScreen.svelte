<script>
  import { getBundle, resolvedStrings } from "$lib/data/index.js";
  import {
    canSync,
    dbAdd,
    deviceToken,
    flushOutbox,
    getReportPosition,
    loadAggregate,
    looksLikePii,
    queueCrowdReport,
    roundCoordinate,
    uuid,
  } from "$lib/report/outbox.js";
  import { onMount } from "svelte";

  const bundle = getBundle();
  const options = [
    ["dry", "depth_dry", "○"],
    ["ankle", "depth_ankle", "◐"],
    ["knee", "depth_knee", "◑"],
    ["waist_plus", "depth_waist_plus", "●"],
  ];
  const currentYear = new Date().getFullYear();

  let chosen = $state(null);
  let lat = $state(null);
  let lon = $state(null);
  let locationText = $state("");
  let reportStatus = $state("");
  let justQueued = $state(false);
  let aggregate = $state(null);
  let aggregateLoaded = $state(false);
  let online = $state(true);
  let hwmYear = $state("");
  let hwmDepth = $state("");
  let hwmReference = $state("");
  let hwmStatus = $state("");

  function t(key, vars) {
    const strings = resolvedStrings();
    let text = strings[key] || key;
    if (vars) {
      for (const variable of Object.keys(vars)) {
        text = text.replace(`{${variable}}`, vars[variable]);
      }
    }
    return text;
  }

  function depthPhrase(depth) {
    return {
      dry: "dry ground",
      ankle: "ankle-deep water",
      knee: "knee-deep water",
      waist_plus: "waist-deep or higher water",
    }[depth] || depth;
  }

  let aggregateStatements = $derived((aggregate?.aggregate_statements || []).filter(statement => statement.quorum));

  async function submitReport() {
    if (!chosen) {
      reportStatus = "Choose the closest water depth before saving the report.";
      return;
    }
    if (lat == null || lon == null) {
      reportStatus = t("report_geolocation_unsupported");
      return;
    }
    reportStatus = t("report_submitting");
    const start = performance.now();
    try {
      await queueCrowdReport({ depth: chosen, lat, lon });
      justQueued = true;
      reportStatus = "";
    } catch (_) {
      reportStatus = "This phone could not save the report. Check available storage and try again.";
      return;
    }
    const elapsed = performance.now() - start;
    if (elapsed > 3000) {
      // The local-queue commit must complete in under 3 s; sync runs after.
      console.warn(`crowd submit took ${elapsed.toFixed(0)} ms to commit locally`);
    }
  }

  async function submitHwm() {
    const year = Number(hwmYear);
    const depthCm = Number(hwmDepth);
    const referenceEn = String(hwmReference || "").trim();
    if (!year || !depthCm || !referenceEn) {
      hwmStatus = "Year, depth, and a plain-language reference are all required.";
      return;
    }
    if (year < 1900 || year > currentYear || depthCm < 1 || depthCm > 2000) {
      hwmStatus = `Enter a year from 1900 to ${currentYear} and a depth from 1 to 2000 cm.`;
      return;
    }
    if (looksLikePii(referenceEn)) {
      hwmStatus = "Please remove phone numbers or email addresses from the note.";
      return;
    }
    const position = await getReportPosition();
    if (!position) {
      hwmStatus = t("report_geolocation_unsupported");
      return;
    }
    const rounded = roundCoordinate(position.coords.latitude, position.coords.longitude);
    try {
      await dbAdd({
        record_id: uuid(),
        record_type: "hwm",
        latitude: rounded[1],
        longitude: rounded[0],
        year,
        depth_cm: depthCm,
        reference_en: referenceEn,
        confidence: "recalled",
        submitted_at: new Date().toISOString(),
        device_token: deviceToken(),
        status: "queued",
        attempts: 0,
      });
      // Never "it will sync when the network returns". A high-water mark has no
      // route off the device at all, so saying it is waiting for a network would
      // be false on a phone with a perfect connection.
      hwmStatus = t("hwm_kept_on_this_phone");
    } catch (_) {
      hwmStatus = "This phone could not save the mark. Check available storage and try again.";
    }
  }

  onMount(() => {
    online = navigator.onLine;
    locationText = t("report_geolocation_prompt");
    getReportPosition().then(position => {
      if (!position) {
        locationText = t("report_geolocation_unsupported");
        return;
      }
      lat = position.coords.latitude;
      lon = position.coords.longitude;
      const rounded = roundCoordinate(lat, lon);
      locationText = t("report_rounded_to", { lat: rounded[1], lon: rounded[0] });
    });
    loadAggregate().then(value => {
      aggregate = value;
      aggregateLoaded = true;
    });
    const sync = () => {
      online = navigator.onLine;
      void flushOutbox().catch(() => {});
    };
    window.addEventListener("online", sync);
    window.addEventListener("offline", sync);
    void flushOutbox().catch(() => {});
    return () => {
      window.removeEventListener("online", sync);
      window.removeEventListener("offline", sync);
    };
  });
</script>

<svelte:head>
  <link rel="stylesheet" href="/report.css">
</svelte:head>

<section class="screen report-screen">
  <header class="report-header">
    <h1 class="screen-title" tabindex="-1">{t("report_question")}</h1>
    <div>
      <p class="screen-intro">Choose the closest depth. Your precise position is rounded on this phone before a report is queued.</p>
      <p class="report-privacy">Community reports never change the official CWC river status shown by Axom Flood.</p>
    </div>
  </header>
  <div class="depth-grid" role="radiogroup" aria-label={t("report_question")}>
    {#each options as option}
      <button
        class:selected={chosen === option[0]}
        class="depth-btn"
        type="button"
        role="radio"
        aria-checked={chosen === option[0]}
        onclick={() => chosen = option[0]}
      >
        <span class="depth-glyph" aria-hidden="true">{option[2]}</span>
        <span class="depth-label">{t(option[1])}</span>
      </button>
    {/each}
  </div>
  <p class="report-loc">{locationText || t("report_geolocation_prompt")}</p>
  <button id="report-submit" type="button" disabled={!chosen || lat == null || lon == null} onclick={submitReport}>{t("report_submit")}</button>
  <p class="report-note small" aria-live="polite">{reportStatus}</p>
  <!-- No submission endpoint is configured yet, so today this always reads
       "nothing is sent anywhere". Promising a sync that cannot happen is worse
       than saying the report is only on this phone. -->
  {#if justQueued}<p class="report-note">{t(canSync() ? "report_queued" : "report_kept_on_this_phone")}</p>{/if}
  <h2 class="report-h2">What nearby reports can say</h2>
  {#if !aggregateLoaded || !aggregate}
    <p class="report-note">{t("aggregate_none")}</p>
  {:else if !aggregateStatements.length}
    <p class="report-note">{t("aggregate_one")}</p>
    <p class="report-note small">{t("report_quorum_note")}</p>
  {:else}
    <ul class="report-agg">
      {#each aggregateStatements as statement}
        <li>{t("aggregate_many", {
          count: statement.count,
          depth: depthPhrase(statement.depth_class),
          place: statement.place,
        })}</li>
      {/each}
    </ul>
    <p class="report-note small">{t("report_quorum_note")}</p>
  {/if}
  <details class="hwm">
    <summary>{t("hwm_eyebrow")}</summary>
    <p class="report-note">{t("hwm_intro")}</p>
    <label for="hwm-year">{t("hwm_year")}</label>
    <input id="hwm-year" type="number" inputmode="numeric" min="1900" max={currentYear}
      placeholder={t("hwm_year_hint")} bind:value={hwmYear}>
    <label for="hwm-depth">{t("hwm_depth_cm")}</label>
    <input id="hwm-depth" type="number" inputmode="numeric" min="0" max="2000" bind:value={hwmDepth}>
    <label for="hwm-ref">{t("hwm_reference")}</label>
    <input id="hwm-ref" type="text" maxlength="200" placeholder={t("hwm_reference_hint")} bind:value={hwmReference}>
    <button type="button" class="secondary" onclick={submitHwm}>{t("hwm_submit")}</button>
    <p class="report-note small">{hwmStatus}</p>
  </details>
  <!-- Being online only matters if there is somewhere to send to. Until an
       endpoint is configured, "queued reports will sync now" is false for a
       phone with a perfect connection, which is the reader most likely to
       believe it. -->
  <p class="source-note">
    {#if !canSync()}
      Reports stay on this phone. Sending is not switched on yet.
    {:else if online}
      Online · queued reports will sync now.
    {:else}
      OFFLINE · reports are queued on this phone.
    {/if}
  </p>
</section>
