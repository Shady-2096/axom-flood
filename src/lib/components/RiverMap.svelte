<script>
  // Assam's 177 mapped revenue-circle outlines, drawn from the shapes the product
  // publishes, with river state held on screen-sized gauge symbols.
  //
  // This is the surface people work on, not a backdrop: circles are hit targets,
  // hovering names a place, and choosing one changes the bulletin. A map you
  // cannot touch is decoration, and decoration behind a safety message is worse
  // than no map at all.
  //
  // It is deliberately absent in data-saver mode. The outline file is about
  // 295 KB, a real cost on 2G during a flood, and a reader who has told their
  // phone to save data has already answered the question.
  import { cacheFirst, siteUrl } from "$lib/data/cache.js";
  import { getBundle, statusInfo } from "$lib/data/index.js";
  import { selectLocality } from "$lib/data/preferences.js";
  import { loadVillageIndex } from "$lib/data/search.js";
  import { GAUGE_GLYPHS, GAUGE_RINGS } from "$lib/map/gaugeSymbol.js";

  let { localityId } = $props();

  const bundle = getBundle();
  const MIN_ZOOM = 1;
  const MAX_ZOOM = 12;
  const VILLAGE_ZOOM = 4;

  // The published outlines carry 15,582 points across 182 rings — survey
  // precision, drawn into a box about 700 pixels wide. At that scale roughly
  // nine points in ten land inside the same pixel as their neighbour, and the
  // cost is real: rasterising the whole sheet on every repaint overwhelmed the
  // compositor, which dropped the layer and painted stale tiles over a blank
  // canvas. The DOM was always correct; the paint was not.
  //
  // Perpendicular-distance simplification at half a pixel is invisible on
  // screen and cuts the point count by roughly three quarters. Rings keep at
  // least their first, last and extreme points, so no circle can collapse.
  const SIMPLIFY_TOLERANCE = 0.012;

  function simplify(ring, tolerance) {
    if (ring.length < 5) return ring;
    const kept = [ring[0]];
    let anchor = ring[0];
    for (let index = 1; index < ring.length - 1; index += 1) {
      const [x, y] = ring[index];
      const [ax, ay] = anchor;
      if (Math.abs(x - ax) > tolerance || Math.abs(y - ay) > tolerance) {
        kept.push(ring[index]);
        anchor = ring[index];
      }
    }
    kept.push(ring[ring.length - 1]);
    // A ring that simplified below a triangle is not a shape any more.
    return kept.length >= 4 ? kept : ring;
  }

  // Assam sits near 26 degrees north, where a degree of longitude covers about
  // 0.9 of a degree of latitude on the ground. Without the correction the state
  // comes out visibly stretched sideways. Matches MapPicker's projection.
  function project(circles) {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const circle of circles) {
      for (const ring of circle.rings) {
        for (const [x, y] of ring) {
          if (x < minX) minX = x;
          if (x > maxX) maxX = x;
          if (y < minY) minY = y;
          if (y > maxY) maxY = y;
        }
      }
    }
    const squeeze = Math.cos((minY + maxY) / 2 * Math.PI / 180);
    return {
      box: [minX * squeeze, -maxY, (maxX - minX) * squeeze, maxY - minY],
      path: circle => circle.rings
        .map(ring => "M" + simplify(ring, SIMPLIFY_TOLERANCE / squeeze)
          .map(([x, y]) => `${(x * squeeze).toFixed(3)},${(-y).toFixed(3)}`)
          .join("L") + "Z")
        .join(""),
      point: ([x, y]) => [x * squeeze, -y],
    };
  }

  const localityById = new Map(bundle.localities.map(item => [item.locality_id, item]));

  function localitiesOf(circle) {
    return (circle.locality_ids || []).map(id => localityById.get(id)).filter(Boolean);
  }

  let shapes = $state(null);
  let hovered = $state(null);
  let mapElement = $state();
  let svgElement = $state();
  let mapWidth = $state(900);
  let view = $state({ cx: 0, cy: 0, zoom: 1 });
  let viewReady = $state(false);
  let villageDocument = $state(null);
  let villageLoadStarted = $state(false);
  let dragged = false;
  let dragStart = null;
  let pinchStart = null;
  const pointers = new Map();
  // One outline can carry two localities: the Census splits a few circles across
  // district lines while OSM keeps a single shape. Asking is the only honest
  // response, because the answer decides which river gauge somebody is shown.
  let ambiguous = $state(null);

  $effect(() => {
    const url = bundle?.circle_shapes_url;
    if (!url || shapes) return;
    cacheFirst(siteUrl(url)).then(document_ => { shapes = document_; }).catch(() => {});
  });

  // Geometry depends on the outline file and nothing else. Selecting a circle
  // used to fall inside this derivation, so every click reprojected all 15,582
  // points and rebuilt 176 path strings before Svelte could diff them. That is
  // what was blowing up the compositor mid-repaint.
  let here = $derived.by(() => {
    if (!scene) return null;
    return scene.areas.find(area => area.ids.includes(localityId)) || null;
  });

  let scene = $derived.by(() => {
    if (!shapes?.circles) return null;
    const projection = project(shapes.circles);
    const districtGroups = new Map();
    for (const locality of bundle.localities) {
      if (!Array.isArray(locality.centroid)) continue;
      const point = projection.point(locality.centroid);
      const group = districtGroups.get(locality.district) || [];
      group.push(point);
      districtGroups.set(locality.district, group);
    }
    const placeLabels = [];
    const labelledLocalities = new Set();
    for (const place of bundle.osm_places || []) {
      const locality = (place.l || [])
        .map(id => localityById.get(id))
        .find(item => Array.isArray(item?.centroid));
      if (!locality || labelledLocalities.has(locality.locality_id)) continue;
      labelledLocalities.add(locality.locality_id);
      const [x, y] = projection.point(locality.centroid);
      placeLabels.push({ x, y, name: place.n });
    }
    return {
      box: projection.box,
      areas: shapes.circles.map(circle => ({
        d: projection.path(circle),
        ids: circle.locality_ids || [],
        name: circle.revenue_circle,
        district: circle.district,
        localities: localitiesOf(circle),
      })),
      gauges: bundle.gauges
        .filter(gauge => Array.isArray(gauge.coordinates))
        .map(gauge => {
          const [x, y] = projection.point(gauge.coordinates);
          const state = statusInfo(gauge).state;
          return {
            x,
            y,
            state,
            ring: GAUGE_RINGS[state] || null,
            glyph: GAUGE_GLYPHS[state] || "",
            site_name: gauge.site_name,
            river: gauge.river,
            level_m: gauge.level_m,
          };
        }),
      districtLabels: [...districtGroups].map(([name, points]) => ({
        name,
        x: points.reduce((sum, point) => sum + point[0], 0) / points.length,
        y: points.reduce((sum, point) => sum + point[1], 0) / points.length,
      })),
      placeLabels,
      circleLabels: bundle.localities
        .filter(locality => Array.isArray(locality.centroid))
        .map(locality => {
          const [x, y] = projection.point(locality.centroid);
          return { x, y, name: locality.revenue_circle };
        }),
      projectPoint: projection.point,
    };
  });

  let viewBox = $derived.by(() => {
    if (!scene) return "0 0 1 1";
    const [, , width, height] = scene.box;
    return [
      view.cx - width / view.zoom / 2,
      view.cy - height / view.zoom / 2,
      width / view.zoom,
      height / view.zoom,
    ].map(value => value.toFixed(5)).join(" ");
  });

  let viewport = $derived.by(() => {
    if (!scene) return null;
    const [, , width, height] = scene.box;
    const visibleWidth = width / view.zoom;
    const visibleHeight = height / view.zoom;
    return {
      left: view.cx - visibleWidth / 2,
      right: view.cx + visibleWidth / 2,
      top: view.cy - visibleHeight / 2,
      bottom: view.cy + visibleHeight / 2,
      width: visibleWidth,
      height: visibleHeight,
    };
  });

  // Text stays a readable screen size as the geography beneath it zooms.
  let labelUnit = $derived(viewport ? viewport.width / Math.max(mapWidth, 320) : 0.01);

  let villagePoints = $derived.by(() => {
    if (!villageDocument?.villages || !scene) return [];
    const seen = new Set();
    const points = [];
    for (const village of villageDocument.villages) {
      // A revenue-circle fallback puts hundreds of different village names on
      // one guessed point. That is useful for search, but dishonest on a map.
      if (!Array.isArray(village.centre)
        || village.centre_confidence === "revenue_circle_fallback") continue;
      const key = `${village.normalized_name}:${village.centre[0].toFixed(4)}:${village.centre[1].toFixed(4)}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const [x, y] = scene.projectPoint(village.centre);
      points.push({ x, y, name: village.village_name });
    }
    return points;
  });

  // At village scale, label one place per screen-grid cell. This keeps the
  // names legible and caps DOM work while panning through 26,550 records.
  let visibleVillages = $derived.by(() => {
    if (view.zoom < VILLAGE_ZOOM || !viewport) return [];
    const occupied = new Set();
    const labels = [];
    for (const village of villagePoints) {
      if (village.x < viewport.left || village.x > viewport.right
        || village.y < viewport.top || village.y > viewport.bottom) continue;
      const column = Math.floor((village.x - viewport.left) / viewport.width * 18);
      const row = Math.floor((village.y - viewport.top) / viewport.height * 12);
      const cell = `${column}:${row}`;
      if (occupied.has(cell)) continue;
      occupied.add(cell);
      labels.push(village);
    }
    return labels;
  });

  let visibleDistricts = $derived.by(() => {
    if (!viewport || !scene) return [];
    const occupied = new Set();
    const labels = [];
    // The all-state view cannot honestly print every compact central district
    // without turning names into a knot. The grid relaxes as the reader zooms,
    // so every district becomes available without overlapping at 1×.
    const columns = view.zoom < 1.6 ? 12 : 18;
    const rows = view.zoom < 1.6 ? 7 : 11;
    for (const label of scene.districtLabels) {
      if (label.x < viewport.left || label.x > viewport.right
        || label.y < viewport.top || label.y > viewport.bottom) continue;
      const column = Math.floor((label.x - viewport.left) / viewport.width * columns);
      const row = Math.floor((label.y - viewport.top) / viewport.height * rows);
      const cell = `${column}:${row}`;
      if (occupied.has(cell)) continue;
      occupied.add(cell);
      labels.push(label);
    }
    return labels;
  });

  $effect(() => {
    if (!scene || viewReady) return;
    const [x, y, width, height] = scene.box;
    view = { cx: x + width / 2, cy: y + height / 2, zoom: 1 };
    viewReady = true;
  });

  $effect(() => {
    if (!mapElement) return;
    const observer = new ResizeObserver(entries => {
      mapWidth = entries[0]?.contentRect.width || mapWidth;
    });
    observer.observe(mapElement);
    return () => observer.disconnect();
  });

  $effect(() => {
    // RiverMap itself only exists in detailed mode. That audience has opted
    // into the rich, connected view, so prepare the full place index up front
    // instead of making the first close zoom wait on another round trip.
    if (!scene || villageLoadStarted) return;
    villageLoadStarted = true;
    loadVillageIndex()
      .then(document_ => { villageDocument = document_; })
      .catch(() => {});
  });

  function clampView(candidate) {
    if (!scene) return candidate;
    const [x, y, width, height] = scene.box;
    const zoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, candidate.zoom));
    const halfWidth = width / zoom / 2;
    const halfHeight = height / zoom / 2;
    return {
      zoom,
      cx: Math.max(x + halfWidth, Math.min(x + width - halfWidth, candidate.cx)),
      cy: Math.max(y + halfHeight, Math.min(y + height - halfHeight, candidate.cy)),
    };
  }

  function clientPoint(clientX, clientY) {
    if (!svgElement?.getScreenCTM) return null;
    const matrix = svgElement.getScreenCTM();
    if (!matrix) return null;
    const point = new DOMPoint(clientX, clientY).matrixTransform(matrix.inverse());
    return { x: point.x, y: point.y };
  }

  function zoomTo(nextZoom, clientX, clientY) {
    if (!scene) return;
    const zoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, nextZoom));
    const anchor = Number.isFinite(clientX)
      ? clientPoint(clientX, clientY)
      : { x: view.cx, y: view.cy };
    if (!anchor) return;
    const ratio = view.zoom / zoom;
    view = clampView({
      zoom,
      cx: anchor.x + (view.cx - anchor.x) * ratio,
      cy: anchor.y + (view.cy - anchor.y) * ratio,
    });
  }

  function wheel(event) {
    event.preventDefault();
    zoomTo(view.zoom * Math.exp(-event.deltaY * 0.0015), event.clientX, event.clientY);
  }

  function pointerDown(event) {
    if (event.button !== 0) return;
    mapElement?.setPointerCapture(event.pointerId);
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.size === 1) {
      dragStart = { x: event.clientX, y: event.clientY, cx: view.cx, cy: view.cy };
      pinchStart = null;
    } else if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      pinchStart = {
        distance: Math.hypot(a.x - b.x, a.y - b.y),
        zoom: view.zoom,
        midpoint: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 },
      };
      dragStart = null;
    }
  }

  function pointerMove(event) {
    if (!pointers.has(event.pointerId)) return;
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.size === 2 && pinchStart) {
      const [a, b] = [...pointers.values()];
      const distance = Math.hypot(a.x - b.x, a.y - b.y);
      if (Math.abs(distance - pinchStart.distance) > 3) dragged = true;
      zoomTo(
        pinchStart.zoom * distance / Math.max(pinchStart.distance, 1),
        pinchStart.midpoint.x,
        pinchStart.midpoint.y,
      );
      return;
    }
    if (!dragStart || pointers.size !== 1 || !viewport) return;
    const dx = event.clientX - dragStart.x;
    const dy = event.clientY - dragStart.y;
    if (Math.hypot(dx, dy) > 4) dragged = true;
    const bounds = mapElement.getBoundingClientRect();
    view = clampView({
      zoom: view.zoom,
      cx: dragStart.cx - dx / Math.max(bounds.width, 1) * viewport.width,
      cy: dragStart.cy - dy / Math.max(bounds.height, 1) * viewport.height,
    });
  }

  function pointerUp(event) {
    pointers.delete(event.pointerId);
    if (pointers.size === 1) {
      const remaining = [...pointers.values()][0];
      dragStart = { x: remaining.x, y: remaining.y, cx: view.cx, cy: view.cy };
    } else {
      dragStart = null;
    }
    pinchStart = null;
    setTimeout(() => { dragged = false; }, 80);
  }

  function resetView() {
    if (!scene) return;
    const [x, y, width, height] = scene.box;
    view = { cx: x + width / 2, cy: y + height / 2, zoom: 1 };
  }

  function pick(area) {
    if (dragged) return;
    if (area.localities.length > 1) {
      ambiguous = area;
      return;
    }
    const locality = area.localities[0];
    if (!locality) return;
    ambiguous = null;
    selectLocality(locality.locality_id, {
      method: "map",
      label: locality.revenue_circle,
      selected_at: new Date().toISOString(),
    });
  }

  function resolve(locality) {
    ambiguous = null;
    selectLocality(locality.locality_id, {
      method: "map",
      label: locality.revenue_circle,
      selected_at: new Date().toISOString(),
    });
  }
</script>

<div
  class="atlas-map"
  class:dragging={pointers.size > 0}
  role="application"
  aria-label="Interactive river map of Assam"
  bind:this={mapElement}
  onwheel={wheel}
  onpointerdown={pointerDown}
  onpointermove={pointerMove}
  onpointerup={pointerUp}
  onpointercancel={pointerUp}
>
  {#if scene}
    <!-- Keep the complex, static basemap on its own SVG paint surface. Chrome
         on macOS can corrupt the shared raster when a path's geometry changes;
         the selected outline therefore lives in a separate one-path SVG. -->
    <svg
      class="basemap"
      bind:this={svgElement}
      viewBox={viewBox}
      preserveAspectRatio="xMidYMid meet"
      role="group"
      aria-label="Interactive map of revenue circles and river gauges across Assam. Drag to move and use the zoom controls or a pinch gesture to zoom."
    >
      {#each scene.areas as area, index (index)}
        <path
          class="area"
          class:hot={hovered === area}
          d={area.d}
          role="button"
          tabindex="0"
          aria-label={`${area.name}, ${area.district}`}
          onclick={() => pick(area)}
          onkeydown={event => {
            if (event.key === "Enter" || event.key === " ") { event.preventDefault(); pick(area); }
          }}
          onmouseenter={() => hovered = area}
          onmouseleave={() => { if (hovered === area) hovered = null; }}
          onfocus={() => hovered = area}
          onblur={() => { if (hovered === area) hovered = null; }}
        />
      {/each}
      <!-- Same symbol vocabulary as the detailed atlas: one size for every state,
           a fixed attention ring at raised levels, and a glyph so severity is not
           carried by colour alone. Light mode used to grow the halo from 10 to 30
           units as the river rose, which made the calmest map in the product the
           one implying the largest flood. -->
      {#each scene.gauges as gauge, index (index)}
        {#if gauge.ring}
          <circle
            class="gauge-ring"
            data-state={gauge.state}
            cx={gauge.x}
            cy={gauge.y}
            r={labelUnit * 13}
            style={`stroke-width:${labelUnit * gauge.ring}px`}
            aria-hidden="true"
          />
        {/if}
        <g
          class="gauge-symbol"
          data-state={gauge.state}
          transform={`translate(${gauge.x} ${gauge.y}) scale(${labelUnit * .9})`}
        >
          <circle class="gauge-disc" cx="0" cy="0" r="8.4" />
          <g class="gauge-glyph" transform="translate(-10 -10)">
            {@html gauge.glyph}
          </g>
          <title>{gauge.site_name || "CWC Station"}{gauge.river ? ` (${gauge.river} River)` : ""}: {gauge.level_m ? `${gauge.level_m} m` : gauge.state}</title>
        </g>
      {/each}

      {#if view.zoom < 3.2}
        {#each visibleDistricts as label (label.name)}
          <text
            class="map-label district-label"
            x={label.x}
            y={label.y}
            style={`font-size:${labelUnit * 12}px;stroke-width:${labelUnit * 3}px`}
          >{label.name}</text>
        {/each}
      {/if}
      {#if view.zoom >= 1.55 && view.zoom < 4.5}
        {#each scene.placeLabels as label (label.name)}
          {#if label.x >= viewport.left && label.x <= viewport.right && label.y >= viewport.top && label.y <= viewport.bottom}
            <text
              class="map-label place-label"
              x={label.x}
              y={label.y}
              style={`font-size:${labelUnit * 11}px;stroke-width:${labelUnit * 3}px`}
            >{label.name}</text>
          {/if}
        {/each}
      {/if}
      {#if view.zoom >= 3.2 && view.zoom < VILLAGE_ZOOM}
        {#each scene.circleLabels as label (label.name)}
          {#if label.x >= viewport.left && label.x <= viewport.right && label.y >= viewport.top && label.y <= viewport.bottom}
            <text
              class="map-label circle-label"
              x={label.x}
              y={label.y}
              style={`font-size:${labelUnit * 11}px;stroke-width:${labelUnit * 3}px`}
            >{label.name}</text>
          {/if}
        {/each}
      {/if}
      {#if view.zoom >= VILLAGE_ZOOM}
        {#each visibleVillages as label (`${label.name}:${label.x}:${label.y}`)}
          <text
            class="map-label village-label"
            x={label.x}
            y={label.y}
            style={`font-size:${labelUnit * 10}px;stroke-width:${labelUnit * 3}px`}
          >{label.name}</text>
        {/each}
      {/if}
    </svg>

    {#if here}
      <svg
        class="selection-map"
        viewBox={viewBox}
        preserveAspectRatio="xMidYMid meet"
        aria-hidden="true"
        focusable="false"
      >
        <path class="here" d={here.d} />
      </svg>
    {/if}

    <div class="map-controls" aria-label="Map zoom controls">
      <button type="button" aria-label="Zoom in" onclick={() => zoomTo(view.zoom * 1.7)}>+</button>
      <button type="button" aria-label="Zoom out" onclick={() => zoomTo(view.zoom / 1.7)}>−</button>
      <button class="map-home" type="button" onclick={resetView}>Assam</button>
    </div>

    <p class="map-scale" aria-live="polite">
      {#if view.zoom >= VILLAGE_ZOOM && !villageDocument}Loading village names…{:else}{view.zoom.toFixed(1)}×{/if}
    </p>

    {#if hovered}
      <p class="atlas-readout">
        <strong>{hovered.name}</strong><span>{hovered.district}</span>
      </p>
    {/if}

    {#if ambiguous}
      <div class="atlas-ask" role="group" aria-label="Choose a district">
        <p>{ambiguous.name} sits on a district boundary. Which one is yours?</p>
        {#each ambiguous.localities as locality (locality.locality_id)}
          <button type="button" onclick={() => resolve(locality)}>{locality.district}</button>
        {/each}
      </div>
    {/if}
  {/if}
</div>

<style>
  /* The map is its own paint world. Without containment the browser folded this
     layer in with the rest of the page and, on re-raster, smeared unrelated
     chrome across a blank buffer — a compositing failure, not a layout one: the
     DOM measured correct throughout (no element wider than 156px, nothing in a
     warning state, yet a full-viewport amber disc on screen).
     `contain: paint` and an explicit stacking context keep the failure from
     being possible, and cost nothing. */
  .atlas-map {
    position: absolute;
    contain: paint;
    inset: 0;
    isolation: isolate;
    overflow: hidden;
    cursor: grab;
    touch-action: none;
    user-select: none;
  }
  .atlas-map.dragging { cursor: grabbing; }
  .atlas-map svg {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
  }
  .selection-map { pointer-events: none; }

  .area {
    fill: var(--area-land);
    stroke: var(--river-deep);
    stroke-width: .005;
    stroke-linejoin: round;
    stroke-opacity: .5;
    /* Chrome focuses a tabbable SVG path on pointer clicks. Letting the
       document-level 3px focus outline reach that path scales the outline in
       this SVG's geographic viewBox, producing the viewport-sized blue and
       white discs. SVG stroke is the focus indicator for these paths, so the
       CSS outline must stay off for both pointer and keyboard focus. */
    outline: none;
    cursor: pointer;
  }
  /* No fill transition. Animating fill across 176 paths on every selection cost
     a full repaint of the map — expensive on the low-end Android this is built
     for, and it left visible compositing artefacts. Hover feedback is instant
     instead, which is also the honest behaviour for a hit target. */
  .area.hot { fill: var(--area-hot); }

  .here {
    fill: var(--area-here);
    stroke: var(--ink);
    stroke-width: .02;
    stroke-linejoin: round;
    pointer-events: none;
  }
  .area:focus-visible { stroke: var(--ink); stroke-width: .022; stroke-opacity: 1; }

  /* The attention ring: stroke only, one radius for every raised state, so
     nothing here can be measured off the map as a flood extent. */
  .gauge-ring {
    fill: none;
    stroke-opacity: .85;
    pointer-events: none;
  }
  .gauge-ring[data-state="warning"] { stroke: var(--gauge-warning); }
  .gauge-ring[data-state="danger"] { stroke: var(--gauge-danger); }
  .gauge-ring[data-state="extreme"] { stroke: var(--gauge-extreme); }

  /* One disc, one glyph, one size. No-data is hollow so stronger contrast cannot
     be mistaken for a live reading, and it carries no glyph at all — an empty
     symbol is the honest drawing of an absent measurement. */
  .gauge-symbol { pointer-events: none; }
  .gauge-disc {
    fill: var(--gauge-normal);
    stroke: var(--gauge-keyline);
    stroke-width: 1.7;
  }
  .gauge-symbol[data-state="warning"] .gauge-disc { fill: var(--gauge-warning); }
  .gauge-symbol[data-state="danger"] .gauge-disc { fill: var(--gauge-danger); }
  .gauge-symbol[data-state="extreme"] .gauge-disc { fill: var(--gauge-extreme); }
  .gauge-symbol[data-state="no-data"] .gauge-disc { fill: var(--gauge-none); }
  .gauge-glyph {
    fill: none;
    stroke: var(--gauge-keyline);
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.9;
    color: var(--gauge-keyline);
  }
  .gauge-symbol[data-state="danger"] .gauge-glyph,
  .gauge-symbol[data-state="extreme"] .gauge-glyph {
    stroke: #fff;
    color: #fff;
  }

  .map-label {
    fill: var(--ink);
    stroke: var(--ground);
    stroke-linejoin: round;
    paint-order: stroke;
    pointer-events: none;
    text-anchor: middle;
    dominant-baseline: central;
  }
  .district-label {
    fill: var(--ink-soft);
    font-weight: 800;
    letter-spacing: .04em;
    text-transform: uppercase;
  }
  .place-label { font-weight: 700; }
  .circle-label { fill: var(--ink-soft); font-weight: 700; }
  .village-label { fill: var(--graphite); font-weight: 600; }

  .map-controls {
    position: absolute;
    z-index: 2;
    top: 20px;
    right: 20px;
    display: grid;
    overflow: hidden;
    border: 1px solid var(--line);
    border-radius: 14px;
    background: var(--veil);
    box-shadow: var(--shadow-2);
  }
  .map-controls button {
    width: 42px;
    min-height: 39px;
    padding: 0;
    border: 0;
    border-bottom: 1px solid var(--line);
    border-radius: 0;
    color: var(--ink);
    background: transparent;
    font-size: 20px;
    line-height: 1;
  }
  .map-controls button:hover { background: var(--surface-2); }
  .map-controls .map-home {
    width: auto;
    min-width: 58px;
    padding: 0 8px;
    border-bottom: 0;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: .05em;
    text-transform: uppercase;
  }
  .map-scale {
    position: absolute;
    z-index: 2;
    right: 20px;
    bottom: 84px;
    margin: 0;
    padding: 4px 8px;
    border-radius: 999px;
    color: var(--muted);
    background: var(--veil);
    font-size: 11px;
    font-weight: 700;
    pointer-events: none;
  }

  /* The readout names what the cursor is over. It holds one fixed position
     rather than following the pointer, so it never covers the shape being
     judged — and it sits along the top, clear of the bulletin and the locate
     control, which own the bottom corners. */
  .atlas-readout {
    position: absolute;
    top: 20px;
    left: 50%;
    display: flex;
    gap: 8px;
    margin: 0;
    padding: 8px 16px;
    border: 1px solid var(--line);
    border-radius: var(--r-pill);
    background: var(--veil);
    box-shadow: var(--shadow-2);
    font-size: 12px;
    transform: translateX(-50%);
    white-space: nowrap;
  }
  .atlas-readout span { color: var(--muted); }

  .atlas-ask {
    position: absolute;
    top: 50%;
    left: 50%;
    width: min(320px, calc(100% - 32px));
    padding: 16px;
    border: 1px solid var(--line);
    border-radius: var(--r-panel);
    background: var(--surface);
    box-shadow: var(--shadow-3);
    transform: translate(-50%, -50%);
  }
  .atlas-ask p { margin: 0 0 12px; font-size: 14px; line-height: 1.45; }
  .atlas-ask button {
    width: 100%;
    min-height: 44px;
    margin-top: 8px;
    padding: 12px 16px;
    font-size: 14px;
  }

  /* The fallback map draws inside the same full-screen phone sheet, so its
     chrome clears the floating bulletin the same way the detailed map's does. */
  @media (max-width: 859px) {
    .map-controls { top: 76px; right: 12px; }

    .map-scale {
      right: auto;
      bottom: calc(var(--atlas-panel-h, 0px) + 20px);
      left: 12px;
    }
  }
</style>
