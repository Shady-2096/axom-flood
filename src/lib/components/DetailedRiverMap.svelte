<script>
  import { onMount } from "svelte";
  import RiverMap from "$lib/components/RiverMap.svelte";
  import { cacheFirst, siteUrl } from "$lib/data/cache.js";
  import { getBundle, statusInfo } from "$lib/data/index.js";
  import {
    IMPACT_METRICS,
    aggregateImpact,
    formatMetric,
    impactLegendRows,
    loadImpactOverlay,
    metricAvailable,
    metricColour,
    metricFillOpacity,
    metricValue,
    normalisePlace,
    placeKey,
  } from "$lib/data/impact.js";
  import {
    GAUGE_FILLS,
    GAUGE_GLYPHS,
    GAUGE_LEGEND,
    GAUGE_RING_RADIUS,
    GAUGE_RINGS,
    GAUGE_SIZE,
    gaugeStatusLabel,
  } from "$lib/map/gaugeSymbol.js";
  import { registerPmtiles } from "$lib/map/pmtiles.js";
  import { dissolveRings, windRing } from "$lib/map/outline.js";
  import { selectLocality } from "$lib/data/preferences.js";
  import { loadVillageIndex } from "$lib/data/search.js";

  /* `focusRequest` is a counter, not a place. The effect below only flies the
     map when the selected circle *changes*, which is right for a selection that
     arrives from somewhere else on the page — the map should not lurch on every
     unrelated re-render. But "use my location" is a direct request to be taken
     somewhere, and a reader who is already on their own circle got nothing at
     all for it: same id, no flight, and the map left wherever they had panned
     to. Bumping this counter says "go there again" without pretending the
     selection changed. */
  let { localityId, focusRequest = 0, onlayerchange = null } = $props();

  const bundle = getBundle();
  const localityById = new Map(bundle.localities.map(item => [item.locality_id, item]));
  const MAP_LAYERS = [
    { key: "river_conditions", label: "River levels", group: "now" },
    ...Object.entries(IMPACT_METRICS).map(([key, metric]) => ({
      key,
      label: {
        affected_population: "Affected people",
        affected_villages: "Affected villages",
        crop_area_submerged_hectares: "Crop area",
        relief_camp_occupants: "Camp residents",
        relief_centres_open: "Relief centres",
        infrastructure_incidents: "Infrastructure",
      }[key] || metric.label,
      group: "reported",
    })),
  ];
  const IMPACT_LAYER_KEYS = new Set(Object.keys(IMPACT_METRICS));
  const EMPTY_COLLECTION = { type: "FeatureCollection", features: [] };
  const PRECISE_BOUNDARY_ZOOM = 10;
  // Kept in step with the fade on .gauge-tooltip in static/styles.css.
  const GAUGE_CARD_FADE = 220;
  // How long the detailed map may spend loading before the plain map takes over.
  //
  // Generous on purpose. Detailed mode has no data budget and a slow connection
  // that is still making progress should be allowed to finish -- falling back
  // early would downgrade a reader who was about to get the full atlas. What
  // this catches is the load that is not slow but stopped, which the page
  // otherwise renders as a spinner with no end.
  const MAP_LOAD_TIMEOUT_MS = 15_000;
  const impactDateFormatter = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "numeric",
    month: "short",
    year: "numeric",
  });

  let mapElement = $state();
  let ready = $state(false);
  let visualReady = $state(false);
  let hovered = $state(null);
  let ambiguous = $state(null);
  let tilesFailed = $state(false);
  let mapFailed = $state(false);
  let zoom = $state(7);
  let basemap = $state("streets");
  let selectedLayer = $state("river_conditions");
  let layerMenuOpen = $state(false);
  let mapLayerElement = $state();
  let impactLoadState = $state("idle");
  let impactError = $state("");
  let impactOverlay = $state(null);
  let requestedDistrict = $state("");
  let map;
  let maplibre;
  let shapesDocument;
  let assamBounds;
  let focusedLocalityId;
  let focusedRequest = 0;
  let revealTimer;
  let loadWatchdog;
  let villageDocument = $state();
  let impactAggregation = { districts: new Map(), circles: new Map() };
  let gaugePopup;
  let gaugeCardTimer;
  const areaByFeatureId = new Map();
  const featureIdByLocality = new Map();
  const gaugeMarkers = [];

  let selectedMetric = $derived(IMPACT_METRICS[selectedLayer]);
  let selectedLayerOption = $derived(
    MAP_LAYERS.find(option => option.key === selectedLayer) || MAP_LAYERS[0],
  );
  let selectedLegendRows = $derived(
    selectedMetric
      ? impactLegendRows(selectedLayer, impactOverlay?.state || "current")
      : [],
  );

  function isImpactLayer(value = selectedLayer) {
    return IMPACT_LAYER_KEYS.has(value);
  }

  function revealMap() {
    clearTimeout(revealTimer);
    visualReady = true;
  }

  function localitiesOf(circle) {
    return (circle.locality_ids || []).map(id => localityById.get(id)).filter(Boolean);
  }

  function choose(locality, move = true) {
    ambiguous = null;
    if (move) focusLocality(locality.locality_id);
    focusedLocalityId = locality.locality_id;
    selectLocality(locality.locality_id, {
      method: "map",
      label: locality.revenue_circle,
      selected_at: new Date().toISOString(),
    });
  }

  function pick(area) {
    focusArea(area);
    if (isImpactLayer()) {
      hovered = area;
      ambiguous = null;
      return;
    }
    if (area.localities.length > 1) {
      ambiguous = area;
      return;
    }
    if (area.localities[0]) choose(area.localities[0], false);
  }

  function impactRecord(area) {
    return impactAggregation.circles.get(placeKey(area.district, area.name)) || null;
  }

  function asClosedRing(ring) {
    if (!ring.length) return ring;
    const first = ring[0];
    const last = ring[ring.length - 1];
    return first[0] === last[0] && first[1] === last[1] ? ring : [...ring, first];
  }

  function geometryFor(circle) {
    const rings = circle.rings.map(asClosedRing);
    if (rings.length === 1) return { type: "Polygon", coordinates: [rings[0]] };
    return {
      type: "MultiPolygon",
      coordinates: rings.map(ring => [ring]),
    };
  }

  function circleFeatures() {
    if (!shapesDocument) return EMPTY_COLLECTION;
    const impactMode = isImpactLayer();
    const reportState = impactOverlay?.state || "current";
    return {
      type: "FeatureCollection",
      features: shapesDocument.circles.map((circle, index) => {
        const featureId = `circle-${index}`;
        const area = areaByFeatureId.get(featureId);
        const selected = !impactMode && area.ids.includes(localityId);
        const value = impactMode
          ? metricValue(impactRecord(area), selectedLayer)
          : null;
        return {
          type: "Feature",
          geometry: geometryFor(circle),
          properties: {
            featureId,
            name: area.name,
            district: area.district,
            selected: selected ? 1 : 0,
            fill: impactMode
              ? metricColour(value, selectedLayer, reportState)
              : "#123e45",
            fillOpacity: impactMode
              ? metricFillOpacity(value, selectedLayer, reportState)
              : (selected ? .24 : .035),
          },
        };
      }),
    };
  }

  function updateCircleSource() {
    const source = map?.getSource("revenue-circles");
    if (source) source.setData(circleFeatures());
  }

  function gaugeLinkData(id = localityId) {
    if (isImpactLayer() || !id) return EMPTY_COLLECTION;
    const locality = localityById.get(id);
    const gauge = bundle.gauges.find(
      item => item.cwc_station_code === locality?.primary_gauge,
    );
    if (!locality?.centroid || !Array.isArray(gauge?.coordinates)) {
      return EMPTY_COLLECTION;
    }
    const mapping = locality.primary_gauge_mapping || {};
    const flagged = Boolean(mapping.far || mapping.much_nearer_gauge_exists);
    const from = locality.centroid;
    const to = gauge.coordinates;
    const midpoint = [(from[0] + to[0]) / 2, (from[1] + to[1]) / 2];
    const distance = Number.isFinite(mapping.distance_km)
      ? `${Math.round(mapping.distance_km)} km to ${gauge.site_name || "the gauge"}`
      : "";
    return {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: { type: "LineString", coordinates: [from, to] },
          properties: { kind: "line", flagged: flagged ? 1 : 0 },
        },
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: from },
          properties: { kind: "anchor", flagged: flagged ? 1 : 0 },
        },
        ...(distance ? [{
          type: "Feature",
          geometry: { type: "Point", coordinates: midpoint },
          properties: { kind: "label", flagged: flagged ? 1 : 0, label: distance },
        }] : []),
      ],
    };
  }

  function updateGaugeLink() {
    const source = map?.getSource("gauge-link");
    if (source) source.setData(gaugeLinkData());
  }

  function setGaugeVisibility(show) {
    for (const entry of gaugeMarkers) {
      entry.element.hidden = !show;
    }
    if (!show) hideGaugeCard();
  }

  function refreshMapLayers() {
    if (!map) return;
    updateCircleSource();
    updateGaugeLink();
    setGaugeVisibility(!isImpactLayer());
  }

  function formatImpactDate(value) {
    return impactDateFormatter.format(new Date(`${value}T12:00:00+05:30`));
  }

  async function ensureImpact() {
    if (impactOverlay || impactLoadState === "loading") return;
    impactLoadState = "loading";
    impactError = "";
    try {
      impactOverlay = await loadImpactOverlay();
      impactAggregation = aggregateImpact(impactOverlay.impact);
      impactLoadState = "ready";
      if (!metricAvailable(impactOverlay.impact, selectedLayer)) {
        selectedLayer = "affected_population";
        updateLayerUrl(selectedLayer);
      }
      refreshMapLayers();
      focusRequestedDistrict();
    } catch (error) {
      impactLoadState = "error";
      impactError = error?.code === "quarantined"
        ? "The latest ASDMA report was held and no validated overlay is available."
        : "The ASDMA overlay could not load. River levels remain available.";
      refreshMapLayers();
    }
  }

  async function selectLayer(next) {
    if (!MAP_LAYERS.some(option => option.key === next)) return;
    selectedLayer = next;
    onlayerchange?.(next);
    hovered = null;
    hideGaugeCard();
    ambiguous = null;
    updateLayerUrl(next);
    if (isImpactLayer()) await ensureImpact();
    refreshMapLayers();
  }

  function updateLayerUrl(next) {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    if (next === "river_conditions") url.searchParams.delete("layer");
    else url.searchParams.set("layer", next);
    window.history.replaceState({}, "", url);
  }

  function chooseLayer(next) {
    if (!globalThis.matchMedia?.("(max-width: 859px)")?.matches) {
      layerMenuOpen = false;
    }
    void selectLayer(next);
  }

  function geometryCoverage(district = "") {
    if (!impactOverlay) return null;
    const districtKey = normalisePlace(district);
    const reported = new Set(
      impactOverlay.impact.revenue_circles
        .filter(record => !district || normalisePlace(record.district) === districtKey)
        .map(record => placeKey(record.district, record.revenue_circle)),
    );
    const shown = new Set(
      [...areaByFeatureId.values()]
        .filter(area => !district || normalisePlace(area.district) === districtKey)
        .map(area => placeKey(area.district, area.name))
        .filter(key => reported.has(key)),
    );
    return { reported: reported.size, shown: shown.size };
  }

  function coverageLabel(district = "") {
    const coverage = geometryCoverage(district);
    if (!coverage) return "";
    const subject = district ? ` in ${district}` : " statewide";
    return `Display geometry covers ${coverage.shown} of ${coverage.reported} reported circles${subject}.`;
  }

  function boundsForArea(area) {
    const coordinates = [];
    const featureId = [...areaByFeatureId.entries()]
      .find(([, value]) => value === area)?.[0];
    const index = Number(featureId?.replace("circle-", ""));
    const circle = shapesDocument?.circles?.[index];
    for (const ring of circle?.rings || []) coordinates.push(...ring);
    if (!coordinates.length) return null;
    return coordinates.reduce(
      (bounds, point) => [
        [Math.min(bounds[0][0], point[0]), Math.min(bounds[0][1], point[1])],
        [Math.max(bounds[1][0], point[0]), Math.max(bounds[1][1], point[1])],
      ],
      [[Infinity, Infinity], [-Infinity, -Infinity]],
    );
  }

  function panelInset() {
    if (!mapElement || !map || map.getContainer().clientWidth >= 860) return 0;
    const declared = Number.parseFloat(
      getComputedStyle(mapElement).getPropertyValue("--atlas-panel-h"),
    );
    if (!Number.isFinite(declared)) return 0;
    return Math.min(declared, Math.round(map.getContainer().clientHeight * .5));
  }

  function focusArea(area) {
    if (!map) return;
    const bounds = boundsForArea(area);
    if (!bounds) return;
    const desktop = map.getContainer().clientWidth >= 860;
    const reducedMotion = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    map.fitBounds(bounds, {
      padding: desktop
        ? { top: 76, right: 88, bottom: 88, left: Math.min(500, map.getContainer().clientWidth * .36) }
        : { top: 76, right: 32, bottom: panelInset() + 24, left: 32 },
      maxZoom: 9.5,
      duration: reducedMotion ? 0 : 1050,
      essential: false,
    });
  }

  function focusLocality(id) {
    const featureId = featureIdByLocality.get(id);
    const area = areaByFeatureId.get(featureId);
    if (area) focusArea(area);
  }

  function applyDefaultView(animate = true) {
    if (!map || !assamBounds) return;
    const desktop = map.getContainer().clientWidth >= 860;
    const reducedMotion = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    map.fitBounds(assamBounds, {
      padding: desktop
        ? { top: 28, right: 28, bottom: 28, left: 28 }
        : { top: 76, right: 28, bottom: panelInset() + 28, left: 28 },
      duration: animate && !reducedMotion ? 700 : 0,
      essential: false,
    });
  }

  function resetView() {
    applyDefaultView();
  }

  function focusRequestedDistrict() {
    if (!requestedDistrict || !map) return;
    const areas = [...areaByFeatureId.values()].filter(
      area => normalisePlace(area.district) === normalisePlace(requestedDistrict),
    );
    const all = areas.flatMap(area => {
      const bounds = boundsForArea(area);
      return bounds ? [bounds[0], bounds[1]] : [];
    });
    if (!all.length) return;
    const bounds = all.reduce(
      (current, point) => [
        [Math.min(current[0][0], point[0]), Math.min(current[0][1], point[1])],
        [Math.max(current[1][0], point[0]), Math.max(current[1][1], point[1])],
      ],
      [[Infinity, Infinity], [-Infinity, -Infinity]],
    );
    map.fitBounds(bounds, { padding: 32, maxZoom: 9, duration: 700 });
    requestedDistrict = "";
  }

  function switchBasemap(next) {
    if (!map || next === basemap) return;
    basemap = next;
    tilesFailed = false;
    map.setLayoutProperty("streets", "visibility", next === "streets" ? "visible" : "none");
    map.setLayoutProperty("satellite", "visibility", next === "satellite" ? "visible" : "none");
  }

  /* Built as nodes rather than as an HTML string: every field here is source
     text from CWC, and a station name is not ours to trust into innerHTML. */
  function gaugeCard(gauge) {
    const state = statusInfo(gauge).state;
    const current = state !== "no-data";
    const card = document.createElement("div");
    card.className = "gauge-tooltip-card";

    const title = document.createElement("div");
    title.className = "gauge-tooltip-title";
    title.textContent = gauge.site_name || "CWC station";

    const river = document.createElement("div");
    river.className = "gauge-tooltip-river";
    river.textContent = `${gauge.river ? `${gauge.river} River` : "River gauge"} · ${gauge.district || "Assam"}`;

    const status = document.createElement("div");
    status.className = `gauge-tooltip-status state-${state}`;
    const dot = document.createElement("span");
    dot.className = "dot";
    const level = document.createElement("strong");
    level.textContent = gauge.level_m != null ? `${gauge.level_m} m` : "Gauge station";
    const separator = document.createElement("span");
    separator.className = "sep";
    separator.textContent = "•";
    const label = document.createElement("span");
    label.textContent = gaugeStatusLabel(state, current);
    status.append(dot, level, separator, label);

    card.append(title, river, status);
    return card;
  }

  function showGaugeCard(gauge) {
    if (!gaugePopup || !map) return;
    clearTimeout(gaugeCardTimer);
    hovered = null;
    gaugePopup.setDOMContent(gaugeCard(gauge)).setLngLat(gauge.coordinates).addTo(map);
    gaugePopup.getElement()?.classList.remove("leaving");
  }

  /* MapLibre takes a popup out of the DOM the moment it is removed, so the card
     cannot fade on its own way out. It is marked as leaving, the CSS fades it,
     and the removal waits for that to finish. */
  function hideGaugeCard() {
    const element = gaugePopup?.getElement();
    clearTimeout(gaugeCardTimer);
    if (!element) return;
    element.classList.add("leaving");
    gaugeCardTimer = setTimeout(() => gaugePopup?.remove(), GAUGE_CARD_FADE);
  }

  function addGaugeMarkers() {
    // One popup reused by every gauge, so a second station cannot leave the
    // first one's card behind. No anchor is set: MapLibre flips the card below
    // or beside a gauge that sits near the top edge of the map.
    gaugePopup = new maplibre.Popup({
      className: "gauge-tooltip",
      closeButton: false,
      closeOnClick: false,
      closeOnMove: false,
      focusAfterOpen: false,
      offset: GAUGE_RING_RADIUS + 4,
      maxWidth: "280px",
    });
    for (const gauge of bundle.gauges.filter(item => Array.isArray(item.coordinates))) {
      const state = statusInfo(gauge).state;
      const current = state !== "no-data";
      const element = document.createElement("button");
      element.type = "button";
      element.className = `maplibre-gauge state-${state}`;
      element.setAttribute(
        "aria-label",
        `${gauge.site_name || "CWC station"}, ${gaugeStatusLabel(state, current)}`,
      );
      element.style.setProperty("--gauge-fill", GAUGE_FILLS[state] || "var(--gauge-none)");
      element.style.setProperty("--gauge-ring-width", `${GAUGE_RINGS[state] || 0}px`);
      element.style.setProperty("--gauge-size", `${GAUGE_SIZE}px`);
      element.style.setProperty("--gauge-ring-size", `${GAUGE_RING_RADIUS * 2}px`);
      element.innerHTML = `<span class="maplibre-gauge-ring" aria-hidden="true"></span>
        <svg viewBox="0 0 20 20" aria-hidden="true">
          <circle class="gauge-disc" cx="10" cy="10" r="8.4"></circle>
          <g class="gauge-glyph">${current
            ? GAUGE_GLYPHS[state] || GAUGE_GLYPHS.normal
            : ""}</g>
        </svg>`;
      // Markers sit inside the canvas container, so a mousemove over this gauge
      // bubbles on to the map, which reads a revenue circle under the pointer
      // and closes the card again. Hovering a gauge looked like it did nothing
      // and only a click, which stops its own propagation, appeared to work.
      element.addEventListener("mousemove", event => event.stopPropagation());
      element.addEventListener("pointerenter", () => showGaugeCard(gauge));
      element.addEventListener("pointerleave", event => {
        // A tap fires pointerenter and pointerleave back to back on touch, so
        // the card would open and close in the same gesture. Only a real
        // pointer takes the card away again; a tap leaves it up until the
        // reader touches the map somewhere else.
        if (event.pointerType !== "touch") hideGaugeCard();
      });
      element.addEventListener("click", event => {
        // Markers sit inside the canvas container, so without this the map's own
        // click handler runs next and closes the card the tap just opened.
        event.stopPropagation();
        showGaugeCard(gauge);
        const matching = bundle.localities.find(
          locality => locality.primary_gauge === gauge.cwc_station_code,
        );
        if (matching) choose(matching, false);
      });
      const marker = new maplibre.Marker({ element, anchor: "center" })
        .setLngLat(gauge.coordinates)
        .addTo(map);
      gaugeMarkers.push({ marker, element });
    }
  }

  function villageFeatures(document_) {
    return {
      type: "FeatureCollection",
      features: (document_?.villages || [])
        .filter(village => Array.isArray(village.centre)
          && village.centre_confidence !== "revenue_circle_fallback")
        .map(village => ({
          type: "Feature",
          geometry: { type: "Point", coordinates: village.centre },
          properties: { name: village.village_name },
        })),
    };
  }

  async function loadVillages() {
    try {
      villageDocument = await loadVillageIndex();
      const source = map?.getSource("villages");
      if (source) source.setData(villageFeatures(villageDocument));
    } catch (_) {
      villageDocument = null;
    }
  }

  function buildAreas() {
    areaByFeatureId.clear();
    featureIdByLocality.clear();
    shapesDocument.circles.forEach((circle, index) => {
      const featureId = `circle-${index}`;
      const area = {
        ids: circle.locality_ids || [],
        name: circle.revenue_circle,
        district: circle.district,
        localities: localitiesOf(circle),
      };
      areaByFeatureId.set(featureId, area);
      for (const id of area.ids) featureIdByLocality.set(id, featureId);
    });
  }

  function calculateAssamBounds() {
    const coordinates = shapesDocument.circles.flatMap(circle => circle.rings.flat());
    return coordinates.reduce(
      (bounds, point) => [
        [Math.min(bounds[0][0], point[0]), Math.min(bounds[0][1], point[1])],
        [Math.max(bounds[1][0], point[0]), Math.max(bounds[1][1], point[1])],
      ],
      [[Infinity, Infinity], [-Infinity, -Infinity]],
    );
  }

  function outsideMask() {
    // One dissolved outline, not 182 touching circle rings: earcut cannot
    // triangulate holes that share edges. See src/lib/map/outline.js.
    const holes = dissolveRings(shapesDocument.circles.flatMap(circle => circle.rings))
      .map(ring => windRing(ring, false));
    return {
      type: "Feature",
      geometry: {
        type: "Polygon",
        coordinates: [
          windRing([[-180, -85], [180, -85], [180, 85], [-180, 85]], true),
          ...holes,
        ],
      },
      properties: {},
    };
  }

  function addOperationalLayers() {
    map.addSource("outside-mask", { type: "geojson", data: outsideMask() });
    map.addLayer({
      id: "outside-assam",
      type: "fill",
      source: "outside-mask",
      // Dimmed the same dark in both themes. The basemap under it is bright
      // either way, so a light wash gave the state no edge to stand against.
      paint: { "fill-color": "#061217", "fill-opacity": .72 },
    });
    map.addSource("revenue-circles", { type: "geojson", data: circleFeatures() });
    map.addLayer({
      id: "circle-fill",
      type: "fill",
      source: "revenue-circles",
      paint: {
        "fill-color": ["get", "fill"],
        "fill-opacity": ["get", "fillOpacity"],
      },
    });
    map.addLayer({
      id: "circle-line",
      type: "line",
      source: "revenue-circles",
      // Round joins. Circle boundaries follow river channels and arrive as
      // stair-stepped detail, and the default mitre put a spike on every one of
      // those corners.
      layout: { "line-join": "round", "line-cap": "round" },
      paint: {
        // Dark in both themes. Only the area outside Assam is dimmed, so the
        // basemap under these boundaries is bright either way. The boundary
        // carries itself on weight and colour: a pale casing under it read as a
        // glow against the dark theme.
        "line-color": [
          "case",
          ["==", ["get", "selected"], 1],
          "#06333d",
          "#0a5262",
        ],
        // A "zoom" expression is only legal at the top level of a step or
        // interpolate, so the zoom curve wraps the selected/unselected case
        // rather than the other way round.
        "line-opacity": [
          "interpolate", ["linear"], ["zoom"],
          7, ["case", ["==", ["get", "selected"], 1], .95, .8],
          10, ["case", ["==", ["get", "selected"], 1], .95, .85],
        ],
        // Thin. The boundary reads on contrast against a bright basemap, and
        // weight past a hairline only makes the source's own jaggedness bigger.
        "line-width": [
          "interpolate", ["linear"], ["zoom"],
          7, ["case", ["==", ["get", "selected"], 1], 1.6, .8],
          10, ["case", ["==", ["get", "selected"], 1], 2.2, 1.1],
        ],
        "line-dasharray": [
          "case",
          ["==", ["get", "selected"], 1],
          ["literal", [4, 3]],
          ["literal", [1, 0]],
        ],
      },
    });
    map.addSource("gauge-link", { type: "geojson", data: gaugeLinkData() });
    map.addLayer({
      id: "gauge-link-casing",
      type: "line",
      source: "gauge-link",
      filter: ["==", ["get", "kind"], "line"],
      paint: {
        "line-color": "#04171e",
        "line-width": ["case", ["==", ["get", "flagged"], 1], 6, 5],
        "line-opacity": .5,
      },
    });
    map.addLayer({
      id: "gauge-link-line",
      type: "line",
      source: "gauge-link",
      filter: ["==", ["get", "kind"], "line"],
      paint: {
        "line-color": ["case", ["==", ["get", "flagged"], 1], "#d66b24", "#0d7287"],
        "line-width": ["case", ["==", ["get", "flagged"], 1], 3, 2.4],
        "line-dasharray": [
          "case",
          ["==", ["get", "flagged"], 1],
          ["literal", [3, 2.3]],
          ["literal", [3, 3]],
        ],
      },
    });
    map.addLayer({
      id: "gauge-link-anchor",
      type: "circle",
      source: "gauge-link",
      filter: ["==", ["get", "kind"], "anchor"],
      paint: {
        "circle-radius": 4.5,
        "circle-color": ["case", ["==", ["get", "flagged"], 1], "#d66b24", "#0d7287"],
        "circle-stroke-color": "#04171e",
        "circle-stroke-width": 2,
      },
    });
    map.addLayer({
      id: "gauge-link-label",
      type: "symbol",
      source: "gauge-link",
      filter: ["==", ["get", "kind"], "label"],
      layout: {
        "text-field": ["get", "label"],
        "text-font": ["Noto Sans Regular"],
        "text-size": 11,
        "text-allow-overlap": true,
      },
      paint: {
        "text-color": ["case", ["==", ["get", "flagged"], 1], "#6c2b00", "#073f4b"],
        "text-halo-color": "#f7faf8",
        "text-halo-width": 3,
      },
    });
    map.addSource("villages", { type: "geojson", data: EMPTY_COLLECTION });
    map.addLayer({
      id: "village-labels",
      type: "symbol",
      source: "villages",
      minzoom: 13,
      layout: {
        "text-field": ["get", "name"],
        "text-font": ["Noto Sans Regular"],
        "text-size": 11,
        "text-variable-anchor": ["center"],
        "text-radial-offset": .2,
        "text-padding": 18,
      },
      paint: {
        "text-color": "#14343b",
        "text-halo-color": "#ffffff",
        "text-halo-width": 1.5,
      },
    });
  }

  function bindMapEvents() {
    // The id has to come off the properties: a GeoJSON source only keeps
    // feature ids that are non-negative integers, so the "circle-N" ids are
    // dropped on the way into the tile and every lookup here missed.
    map.on("mousemove", "circle-fill", event => {
      const featureId = event.features?.[0]?.properties?.featureId || "";
      hideGaugeCard();
      hovered = areaByFeatureId.get(featureId) || null;
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", "circle-fill", () => {
      hovered = null;
      map.getCanvas().style.cursor = "";
    });
    map.on("click", "circle-fill", event => {
      const featureId = event.features?.[0]?.properties?.featureId || "";
      const area = areaByFeatureId.get(featureId);
      if (area) pick(area);
    });
    // Both reach the canvas, not the markers, so a gauge card only closes when
    // the reader touches the map somewhere away from the gauge holding it.
    map.on("click", hideGaugeCard);
    map.on("dragstart", hideGaugeCard);
    map.on("moveend", () => {
      zoom = map.getZoom();
    });
    map.on("zoom", () => {
      zoom = map.getZoom();
    });
    map.on("error", event => {
      const sourceId = event?.sourceId || event?.error?.sourceId;
      if (sourceId === "streets" || sourceId === "satellite") tilesFailed = true;
    });
  }

  async function initialize() {
    const [maplibreModule, , shapes] = await Promise.all([
      import("maplibre-gl"),
      import("maplibre-gl/dist/maplibre-gl.css"),
      cacheFirst(siteUrl(bundle.circle_shapes_url)),
    ]);
    if (!mapElement) return;
    maplibre = maplibreModule.default || maplibreModule;
    await registerPmtiles(maplibre);
    shapesDocument = shapes;
    buildAreas();
    assamBounds = calculateAssamBounds();

    map = new maplibre.Map({
      container: mapElement,
      style: {
        version: 8,
        glyphs: "https://cdn.protomaps.com/basemaps-assets/fonts/{fontstack}/{range}.pbf",
        sources: {
          streets: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            maxzoom: 19,
            attribution: "© OpenStreetMap contributors",
          },
          satellite: {
            type: "raster",
            tiles: [
              "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            ],
            tileSize: 256,
            maxzoom: 18,
            attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
          },
        },
        // The map itself is drawn the same way under both themes. Only the
        // interface around it follows the theme, in CSS. A basemap that
        // darkened with the theme fought the dimmed surround for contrast, and
        // it left the boundaries reading differently in each theme.
        layers: [
          {
            id: "base-background",
            type: "background",
            paint: { "background-color": "#061c24" },
          },
          {
            id: "streets",
            type: "raster",
            source: "streets",
            paint: {
              "raster-fade-duration": 120,
              "raster-saturation": -.08,
            },
          },
          {
            id: "satellite",
            type: "raster",
            source: "satellite",
            layout: { visibility: "none" },
            paint: { "raster-fade-duration": 120 },
          },
        ],
      },
      bounds: assamBounds,
      fitBoundsOptions: { padding: 28 },
      minZoom: 6,
      maxZoom: 18,
      attributionControl: false,
      renderWorldCopies: false,
      cooperativeGestures: false,
    });
    map.addControl(new maplibre.AttributionControl({ compact: true }), "bottom-right");
    // Trackpad pinch runs through the zoom rate, the mouse wheel through the
    // wheel rate. Both were slow enough that reaching a circle from the state
    // view took a long series of gestures.
    map.scrollZoom.setWheelZoomRate(1 / 280);
    map.scrollZoom.setZoomRate(1 / 60);
    map.setMaxBounds([
      [assamBounds[0][0] - 4, assamBounds[0][1] - 4],
      [assamBounds[1][0] + 4, assamBounds[1][1] + 4],
    ]);
    // Before `load`, not inside it. Everything that notices a broken map used to
    // be registered in the load callback, so none of it was listening for the
    // one failure that matters: the style never finishing. MapLibre only fires
    // `load` once the whole style resolves, glyphs included, and the glyph CDN
    // is a third-party host. Block it -- a captive portal, an ISP filter, a
    // corporate proxy, or just a link too slow to finish -- and `load` never
    // arrives, so `ready` stays false, so the reader watches "Drawing the Assam
    // atlas…" for as long as they are willing to wait. Nothing else on the
    // screen is wrong. The river reading beside it is fine.
    //
    // `initialize()` could not catch it either: it resolves the moment the Map
    // is constructed, and the style loads afterwards.
    //
    // So give up out loud instead. `mapFailed` swaps in the plain RiverMap,
    // which fetches nothing and needs no remote host, and a reader who cannot
    // reach a tile server gets a map that works rather than a spinner.
    loadWatchdog = setTimeout(() => {
      if (!ready) mapFailed = true;
    }, MAP_LOAD_TIMEOUT_MS);

    map.once("load", () => {
      clearTimeout(loadWatchdog);
      addOperationalLayers();
      addGaugeMarkers();
      bindMapEvents();
      focusedLocalityId = localityId;
      ready = true;
      refreshMapLayers();
      applyDefaultView(false);
      if (isImpactLayer()) void ensureImpact();
      focusRequestedDistrict();
      void loadVillages();
      map.once("idle", revealMap);
      revealTimer = setTimeout(revealMap, 2500);
    });
  }

  $effect(() => {
    const selectedId = localityId;
    const mapReady = ready;
    const requested = focusRequest;
    if (map && mapReady) refreshMapLayers();
    if (!map || !mapReady || !selectedId) return;
    if (selectedId !== focusedLocalityId || requested !== focusedRequest) {
      focusedLocalityId = selectedId;
      focusedRequest = requested;
      focusLocality(selectedId);
    }
  });

  onMount(() => {
    let cancelled = false;
    const closeLayerMenu = event => {
      if (layerMenuOpen && !mapLayerElement?.contains(event.target)) layerMenuOpen = false;
    };
    const closeWithKeyboard = event => {
      if (event.key === "Escape") layerMenuOpen = false;
    };
    document.addEventListener("pointerdown", closeLayerMenu);
    document.addEventListener("keydown", closeWithKeyboard);
    const url = new URL(window.location.href);
    const requestedLayer = url.searchParams.get("layer");
    if (MAP_LAYERS.some(option => option.key === requestedLayer)) {
      selectedLayer = requestedLayer;
    }
    onlayerchange?.(selectedLayer);
    requestedDistrict = url.searchParams.get("district") || "";
    initialize().catch(() => {
      if (!cancelled) mapFailed = true;
    });
    return () => {
      cancelled = true;
      clearTimeout(revealTimer);
      clearTimeout(loadWatchdog);
      document.removeEventListener("pointerdown", closeLayerMenu);
      document.removeEventListener("keydown", closeWithKeyboard);
      clearTimeout(gaugeCardTimer);
      gaugePopup?.remove();
      gaugePopup = null;
      for (const entry of gaugeMarkers) entry.marker.remove();
      gaugeMarkers.length = 0;
      map?.remove();
      map = null;
    };
  });
</script>

{#if mapFailed}
  <RiverMap {localityId} />
{:else}
  <div
    class:visual-ready={visualReady}
    class="detailed-map"
    bind:this={mapElement}
    aria-label={isImpactLayer()
      ? `Map of Assam showing ${selectedMetric?.label || "administrative impact"} by reported revenue circle`
      : "WebGL map of Assam with neutral revenue-circle boundaries and current river gauge symbols"}
  ></div>
{/if}

{#if !ready && !mapFailed}
  <p class="map-loading">Drawing the Assam atlas…</p>
{/if}

{#if tilesFailed}
  <p class="tiles-note">The basemap is temporarily unavailable. Revenue-circle boundaries remain usable.</p>
{/if}

{#snippet mapKey(full = true)}
  {#if !isImpactLayer()}
    <div class="legend-rows gauge-legend">
      {#each GAUGE_LEGEND as row (row.state)}
        <div class="legend-row">
          <span class={`gauge-key state-${row.state}`} aria-hidden="true">
            <svg viewBox="0 0 20 20">
              <circle class="gauge-disc" cx="10" cy="10" r="8.4"/>
              <g class="gauge-glyph">{@html row.glyph}</g>
            </svg>
          </span>
          <span>{row.label}</span>
        </div>
      {/each}
    </div>
    {#if full}
      <p class="layer-caveat">
        A gauge reads one point on one river. Display-only circle boundaries stay
        neutral because a reading does not describe the whole circle.
      </p>
    {/if}
  {:else}
    {#if impactLoadState === "loading"}
      <p class="impact-message">Loading the latest validated overlay.</p>
    {:else if impactLoadState === "error"}
      <p class="impact-message error">{impactError}</p>
    {:else if impactOverlay}
      {#if impactOverlay.state === "stale"}
        <p class="impact-message stale">Historical overlay. The report is outside the three-day current window.</p>
      {/if}
      <div class="legend-rows">
        {#each selectedLegendRows as row}
          <div class="legend-row">
            <i style={`background:${row.colour}`}></i>
            <span>{row.label}</span>
          </div>
        {/each}
      </div>
      {#if full}
        <p class="layer-caveat">0 reported is ASDMA's submitted value, not confirmation that nobody was affected.</p>
      {/if}
    {/if}
    {#if full && impactOverlay}
      {#if impactOverlay?.newerAttemptQuarantined}
        <p class="impact-message held">A newer revision was held by validation. Showing the latest validated report.</p>
      {/if}
      <p class="coverage-note">{coverageLabel()}</p>
      <div class="impact-links">
        <a href="/situation/">Situation details</a>
        <a href={siteUrl(impactOverlay.impact.source.artifact_url)} target="_blank" rel="noopener">Exact report</a>
      </div>
    {/if}
  {/if}
{/snippet}

{#if !mapFailed}
  <div class:expanded={layerMenuOpen} class="map-layer-control" bind:this={mapLayerElement}>
    <button
      class:open={layerMenuOpen}
      class="layer-trigger"
      type="button"
      aria-expanded={layerMenuOpen}
      aria-controls="map-layer-options"
      aria-label={layerMenuOpen
        ? "Close map display"
        : `Change what the map shows. Showing: ${selectedLayerOption.label}`}
      onclick={() => { layerMenuOpen = !layerMenuOpen; }}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="m12 4 8 4-8 4-8-4 8-4Zm-8 8 8 4 8-4M4 16l8 4 8-4"/>
      </svg>
      <span><small>Map shows</small><b>{selectedLayerOption.label}</b></span>
      <i aria-hidden="true"></i>
    </button>

    {#if layerMenuOpen}
      <button
        class="drawer-scrim"
        type="button"
        tabindex="-1"
        aria-label="Close map display panel"
        onclick={() => layerMenuOpen = false}
      ></button>
      <div id="map-layer-options" class="layer-menu" aria-label="Map display">
        <header>
          <span>Map display</span>
          <button type="button" aria-label="Close map display panel" onclick={() => layerMenuOpen = false}>×</button>
        </header>
        <div class="layer-options" role="listbox" aria-label="Map view">
          {#each MAP_LAYERS as option, index}
            {#if index === 1}<p>ASDMA situation report</p>{/if}
            <button
              type="button"
              role="option"
              aria-selected={option.key === selectedLayer}
              disabled={option.key === "infrastructure_incidents"
                && impactOverlay
                && !metricAvailable(impactOverlay.impact, option.key)}
              onclick={() => chooseLayer(option.key)}
            >
              <span>{option.label}</span><b aria-hidden="true">✓</b>
            </button>
          {/each}
        </div>
        <section class="drawer-key" aria-label="Map key">
          {@render mapKey()}
        </section>
        <section class="drawer-tools" aria-label="Map tools">
          <p>Map base</p>
          <button type="button" aria-pressed={basemap === "streets"} onclick={() => switchBasemap("streets")}>Street</button>
          <button type="button" aria-pressed={basemap === "satellite"} onclick={() => switchBasemap("satellite")}>Satellite</button>
          <button type="button" onclick={resetView}>Fit Assam</button>
        </section>
      </div>
    {/if}
  </div>

  <div class="map-control-dock" role="group" aria-label="Map controls">
    <button type="button" aria-label="Zoom in" onclick={() => map?.zoomIn()}>+</button>
    <button type="button" aria-label="Zoom out" onclick={() => map?.zoomOut()}>−</button>
    <button type="button" aria-label="Fit all of Assam" title="Fit all of Assam" onclick={resetView}>
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 9V5.5A1.5 1.5 0 0 1 5.5 4H9M15 4h3.5A1.5 1.5 0 0 1 20 5.5V9M20 15v3.5a1.5 1.5 0 0 1-1.5 1.5H15M9 20H5.5A1.5 1.5 0 0 1 4 18.5V15"/>
      </svg>
    </button>
    <button
      class:active={basemap === "satellite"}
      type="button"
      aria-label="Satellite imagery"
      aria-pressed={basemap === "satellite"}
      title={basemap === "satellite" ? "Show the street map" : "Show satellite imagery"}
      onclick={() => switchBasemap(basemap === "satellite" ? "streets" : "satellite")}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="9"/>
        <path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9S14.5 18.4 12 21c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3Z"/>
      </svg>
    </button>
  </div>

  {#if selectedLayer === "river_conditions" && zoom >= 13 && !villageDocument}
    <p class="map-scale" aria-live="polite">Loading village names…</p>
  {/if}
  {#if selectedLayer === "river_conditions" && zoom >= PRECISE_BOUNDARY_ZOOM}
    <p class="boundary-note">Approximate display boundary</p>
  {/if}

  <aside
    class:stale={impactOverlay?.state === "stale"}
    class:river-key={!isImpactLayer()}
    class="map-legend"
    aria-live="polite"
  >
    <header>
      {#if isImpactLayer()}
        <p>ASDMA situation report</p>
        <h2>{selectedMetric?.label}</h2>
        {#if impactOverlay}<span>{formatImpactDate(impactOverlay.impact.report_date)}</span>{/if}
      {:else}
        <p>Central Water Commission</p>
        <h2>River levels</h2>
        <span>Current point readings</span>
      {/if}
    </header>
    {@render mapKey()}
  </aside>
{/if}

{#if hovered}
  <div class:impact={isImpactLayer()} class:hidden-by-drawer={layerMenuOpen} class="atlas-readout">
    <p><strong>{hovered.name}</strong><span>{hovered.district}</span></p>
    {#if isImpactLayer()}
      <p><b>{formatMetric(metricValue(impactRecord(hovered), selectedLayer), selectedLayer)}</b><small>{selectedMetric?.label}</small></p>
    {/if}
  </div>
{/if}

{#if ambiguous && selectedLayer === "river_conditions"}
  <div class="atlas-ask" role="group" aria-label="Choose a district">
    <p>{ambiguous.name} sits on a district boundary. Which one is yours?</p>
    {#each ambiguous.localities as locality (locality.locality_id)}
      <button type="button" onclick={() => choose(locality)}>{locality.district}</button>
    {/each}
  </div>
{/if}

<style>
  .detailed-map {
    position: absolute;
    inset: 0;
    z-index: 0;
    background: var(--ground);
    opacity: 0;
    transition: opacity 180ms ease-out;
  }
  .detailed-map.visual-ready { opacity: 1; }
  .map-loading,
  .tiles-note,
  .map-scale,
  .boundary-note {
    position: absolute;
    z-index: 5;
    margin: 0;
    padding: 8px 12px;
    border-radius: var(--r-pill);
    color: var(--map-control-ink);
    background: var(--map-control);
    box-shadow: var(--shadow-2);
    font-size: 12px;
  }
  .map-loading { top: 50%; left: 50%; transform: translate(-50%, -50%); }
  .tiles-note { right: 24px; bottom: 24px; }
  .map-scale,
  .boundary-note { right: 76px; bottom: 24px; }

  :global(.detailed-map .maplibregl-ctrl-attrib) {
    margin-right: 72px;
    border-radius: 6px 0 0;
    color: #23343a;
    background: rgba(255,255,255,.88);
    font: 11px/1.35 var(--body);
  }
  :global(html:not([data-theme="light"]) .detailed-map .maplibregl-ctrl-attrib) {
    color: #b6ccd1;
    background: rgba(4,20,26,.82);
  }
  :global(.detailed-map .maplibregl-canvas:focus-visible) {
    outline: 3px solid var(--focus);
    outline-offset: -3px;
  }
  :global(.maplibre-gauge) {
    position: relative;
    display: grid;
    width: var(--gauge-ring-size);
    /* The global button rule sets min-height: 46px for touch targets, which
       beats height and stretched this 28px marker into an egg once the ring
       was rounded to 50%. Leaflet drew the ring as an SVG circle and never
       inherited any of that. */
    min-width: 0;
    min-height: 0;
    height: var(--gauge-ring-size);
    place-items: center;
    padding: 0;
    border: 0;
    border-radius: 50%;
    color: var(--gauge-keyline);
    background: transparent;
    box-shadow: none;
    cursor: pointer;
  }
  /* Also from the global button rule, which fills on hover. On a marker that
     painted a white blob behind the gauge. */
  :global(.maplibre-gauge:hover),
  :global(.maplibre-gauge:focus-visible) { background: transparent; }
  :global(.maplibre-gauge[hidden]) { display: none; }
  :global(.maplibre-gauge svg) {
    position: relative;
    z-index: 1;
    width: var(--gauge-size);
    height: var(--gauge-size);
    overflow: visible;
    filter: drop-shadow(0 1px 2px rgba(4,23,30,.45));
  }
  :global(.maplibre-gauge .gauge-disc) {
    fill: var(--gauge-fill);
    stroke: var(--gauge-keyline);
    stroke-width: 1.7;
  }
  :global(.maplibre-gauge .gauge-glyph) {
    fill: none;
    stroke: var(--gauge-keyline);
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.9;
  }
  :global(.maplibre-gauge.state-danger .gauge-glyph),
  :global(.maplibre-gauge.state-extreme .gauge-glyph) { stroke: #fff; }
  :global(.maplibre-gauge-ring) {
    position: absolute;
    inset: 0;
    border: var(--gauge-ring-width) solid var(--gauge-fill);
    border-radius: 50%;
    pointer-events: none;
  }
  :global(.maplibre-gauge.state-danger .maplibre-gauge-ring),
  :global(.maplibre-gauge.state-extreme .maplibre-gauge-ring) {
    animation: gauge-ring-pulse 2.4s ease-in-out infinite;
  }
  @keyframes gauge-ring-pulse {
    0%, 100% { opacity: .85; transform: scale(1); }
    50% { opacity: .4; transform: scale(1.12); }
  }

  .map-layer-control {
    position: absolute;
    z-index: 8;
    top: 92px;
    left: 24px;
    width: min(248px, calc(100% - 96px));
    color: var(--map-control-ink);
  }
  .layer-trigger {
    display: grid;
    grid-template-columns: 18px minmax(0,1fr) 12px;
    align-items: center;
    gap: 12px;
    width: 100%;
    min-height: 56px;
    padding: 8px 16px;
    border: 0;
    border-radius: var(--r-control);
    color: inherit;
    background: var(--map-control);
    box-shadow: var(--shadow-2);
    text-align: left;
  }
  .layer-trigger.open { border-radius: var(--r-control) var(--r-control) 0 0; }
  .layer-trigger > svg,
  .map-control-dock svg {
    width: 18px;
    height: 18px;
    fill: none;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.7;
  }
  .layer-trigger small {
    display: block;
    color: var(--map-control-muted);
    font-size: 11px;
    font-weight: 800;
  }
  .layer-trigger b {
    display: block;
    overflow: hidden;
    font-size: 15px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .layer-trigger > i {
    width: 7px;
    height: 7px;
    border-right: 2px solid currentColor;
    border-bottom: 2px solid currentColor;
    transform: rotate(45deg);
  }
  .layer-trigger.open > i { transform: rotate(225deg); }
  .drawer-scrim { display: none; }
  .layer-menu {
    position: absolute;
    top: 100%;
    width: 100%;
    max-height: min(600px, calc(100vh - 220px));
    overflow-y: auto;
    padding: 6px;
    border-radius: 0 0 var(--r-control) var(--r-control);
    background: var(--map-control);
    box-shadow: var(--shadow-3);
  }
  .layer-menu > header {
    display: none;
    align-items: center;
    justify-content: space-between;
  }
  .layer-menu > header button {
    width: 44px;
    min-height: 44px;
    padding: 0;
    border: 0;
    color: inherit;
    background: transparent;
    box-shadow: none;
    font-size: 24px;
  }
  .layer-options > p {
    margin: 12px 12px 4px;
    color: var(--map-control-muted);
    font-size: 11px;
    font-weight: 800;
  }
  .layer-options > button {
    display: grid;
    grid-template-columns: 1fr 16px;
    align-items: center;
    gap: 8px;
    width: 100%;
    min-height: 40px;
    padding: 6px 12px;
    border: 0;
    border-radius: 12px;
    color: inherit;
    background: transparent;
    box-shadow: none;
    text-align: left;
  }
  .layer-options > button:hover { background: var(--map-control-hover); }
  .layer-options > button[aria-selected="true"] { color: var(--river); font-weight: 750; }
  .layer-options > button b { opacity: 0; }
  .layer-options > button[aria-selected="true"] b { opacity: 1; }
  .drawer-key,
  .drawer-tools { display: none; }

  .map-control-dock {
    position: absolute;
    z-index: 6;
    top: 24px;
    right: 24px;
    display: grid;
    overflow: hidden;
    border-radius: var(--r-control);
    color: var(--map-control-ink);
    background: var(--map-control);
    box-shadow: var(--shadow-2);
  }
  .map-control-dock button {
    display: grid;
    width: 44px;
    min-height: 44px;
    place-items: center;
    padding: 0;
    border: 0;
    border-radius: 0;
    color: inherit;
    background: transparent;
    box-shadow: none;
    font-size: 20px;
  }
  .map-control-dock button + button { border-top: 1px solid var(--map-control-line); }
  .map-control-dock button:hover,
  .map-control-dock button.active { background: var(--map-control-hover); }

  .map-legend {
    position: absolute;
    z-index: 5;
    top: 224px;
    right: 24px;
    width: 232px;
    max-height: calc(100% - 248px);
    overflow-y: auto;
    padding: 16px;
    border-radius: var(--r-control);
    color: var(--map-control-ink);
    background: var(--map-control);
    box-shadow: var(--shadow-2);
  }
  .map-legend header p,
  .map-legend header h2,
  .map-legend header span { margin: 0; }
  .map-legend header p,
  .map-legend header span {
    color: var(--map-control-muted);
    font-size: 11px;
  }
  .map-legend header h2 { margin: 4px 0; font-size: 16px; }
  .legend-rows { display: grid; gap: 8px; margin-top: 12px; }
  .legend-row { display: flex; align-items: center; gap: 8px; font-size: 12px; }
  .legend-row > i {
    width: 14px;
    height: 14px;
    border-radius: 4px;
  }
  .gauge-key { display: grid; width: 24px; height: 24px; place-items: center; }
  .gauge-key svg { width: 22px; height: 22px; }
  .gauge-key .gauge-disc { fill: var(--gauge-none); stroke: var(--gauge-keyline); stroke-width: 1.7; }
  .gauge-key.state-normal .gauge-disc { fill: var(--gauge-normal); }
  .gauge-key.state-warning .gauge-disc { fill: var(--gauge-warning); }
  .gauge-key.state-danger .gauge-disc { fill: var(--gauge-danger); }
  .gauge-key.state-extreme .gauge-disc { fill: var(--gauge-extreme); }
  .gauge-key .gauge-glyph {
    fill: none;
    stroke: var(--gauge-keyline);
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.9;
  }
  .gauge-key.state-danger .gauge-glyph,
  .gauge-key.state-extreme .gauge-glyph { stroke: #fff; }
  .layer-caveat,
  .impact-message,
  .coverage-note {
    margin: 12px 0 0;
    color: var(--map-control-muted);
    font-size: 11px;
    line-height: 1.45;
  }
  .impact-links { display: flex; gap: 12px; margin-top: 12px; font-size: 11px; }
  .impact-links a { color: var(--river); font-weight: 750; }

  .atlas-ask {
    position: absolute;
    z-index: 7;
    left: 50%;
    bottom: 24px;
    display: flex;
    gap: 16px;
    align-items: center;
    max-width: calc(100% - 160px);
    padding: 12px 16px;
    border-radius: var(--r-control);
    color: var(--map-control-ink);
    background: var(--map-control);
    box-shadow: var(--shadow-2);
    transform: translateX(-50%);
  }
  /* A hover readout is a label on the map, not a control on top of it, so it
     is set as bare text at the head of the map and carries its own contrast in
     a halo. Fixed ink in both themes, like everything else drawn on the map. */
  .atlas-readout {
    position: absolute;
    z-index: 7;
    top: 20px;
    left: 50%;
    display: flex;
    gap: 16px;
    align-items: baseline;
    max-width: calc(100% - 420px);
    color: #06333d;
    text-align: center;
    text-shadow:
      0 0 3px rgba(255,255,255,.95),
      0 0 10px rgba(255,255,255,.85),
      0 1px 2px rgba(255,255,255,.95);
    transform: translateX(-50%);
    pointer-events: none;
  }
  .atlas-readout p {
    display: flex;
    gap: 8px;
    align-items: baseline;
    margin: 0;
  }
  .atlas-readout strong,
  .atlas-readout b { font-size: 16px; font-weight: 780; letter-spacing: -.01em; }
  .atlas-readout span,
  .atlas-readout small { color: #2b5b67; font-size: 12px; font-weight: 650; }

  /* A gauge readout is not a place label: it carries a station, a river, a
     level and a status. Those four values sit in a card anchored to the gauge
     itself, in static/styles.css, because MapLibre owns that element. */
  .atlas-ask { display: grid; }
  .atlas-ask p { margin: 0; font-size: 14px; }
  .atlas-ask button { min-height: 40px; }

  @media (max-width: 859px) {
    /* The search pill owns the top of the phone screen (top: 12px, 48px tall,
       gutter to gutter). Both map controls start below it, not beside it. */
    .map-layer-control {
      top: 72px;
      left: 16px;
      width: 52px;
    }
    .layer-trigger {
      display: grid;
      width: 52px;
      min-height: 52px;
      grid-template-columns: 1fr;
      place-items: center;
      padding: 0;
    }
    .layer-trigger > span,
    .layer-trigger > i { display: none; }
    .layer-trigger.open { border-radius: var(--r-control); }
    .drawer-scrim {
      position: fixed;
      z-index: 8;
      inset: 0;
      display: block;
      width: 100vw;
      height: 100dvh;
      padding: 0;
      border: 0;
      border-radius: 0;
      background: rgba(2,16,21,.62);
      box-shadow: none;
    }
    .layer-menu {
      position: fixed;
      z-index: 9;
      top: auto;
      right: 10px;
      bottom: 10px;
      left: 10px;
      width: auto;
      max-height: min(78dvh, 680px);
      padding: 12px;
      border-radius: var(--r-panel);
    }
    .layer-menu > header { display: flex; }
    .drawer-key { display: block; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--map-control-line); }
    .drawer-tools {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 6px;
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--map-control-line);
    }
    .drawer-tools p { grid-column: 1/-1; margin: 0; font-size: 11px; }
    .drawer-tools button { min-height: 44px; padding: 6px; }
    .map-control-dock { top: 72px; right: 16px; }
    .map-control-dock button:nth-child(-n+3) { display: none; }
    .map-control-dock button + button { border-top: 0; }
    .map-legend { display: none; }
    .map-scale,
    .boundary-note,
    .tiles-note {
      right: 16px;
      bottom: calc(var(--atlas-panel-h, 240px) + 84px);
    }
    /* Centred in the map a phone can actually see, which is the band above the
       bulletin sheet rather than the whole element. The map is full-bleed and
       the sheet floats over its lower half, so a plain `top: 50%` put "Drawing
       the Assam atlas…" on top of the card -- covering the words "Local flood
       bulletin" on the one screen that has to be readable first. Every other
       note here is already lifted clear of the sheet; this one was missed. */
    .map-loading { top: calc((100dvh - var(--atlas-panel-h, 240px)) / 2); }
    .atlas-readout {
      /* Clear of the search field, which spans the head of the map here. */
      top: 84px;
      max-width: calc(100% - 32px);
    }
    .atlas-ask {
      bottom: calc(var(--atlas-panel-h, 240px) + 84px);
      width: calc(100% - 32px);
      max-width: none;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .detailed-map { transition: none; }
    :global(.maplibre-gauge-ring) { animation: none !important; }
  }
</style>
