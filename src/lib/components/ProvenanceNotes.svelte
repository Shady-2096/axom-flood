<script>
  let { locality, gauge } = $props();

  // The gauge match is a permanent condition of the build, not an event: three
  // quarters of localities carry a non-high match, so alert styling made it
  // wallpaper. It is stated once, plainly, as provenance of the reading.
  //
  // The Assamese review notice used to sit here too and has been removed. It was
  // true on every visit for every reader, and the product never shows unreviewed
  // Assamese as approved — reviewed English is simply what renders. A notice
  // that can never turn off explains nothing and costs attention that the gauge
  // match, which does vary by place, actually needs.
  let notes = $derived.by(() => {
    const list = [];
    const mapping = locality?.primary_gauge_mapping;
    const review = mapping?.review;
    if (review?.decision === "no_suitable_gauge_exists") {
      /* The one place on the site that explains a blank. Without it the circle
         reads as broken, and somebody keeps refreshing for a number that is
         never coming. It also names who decided, because a permanent absence
         is a claim and claims carry an author. */
      list.push({
        label: "No gauge",
        text: `${review.reasoning} Checked by ${review.reviewer} — `
          + `${review.reviewer_qualification} — on ${review.reviewed_at}. `
          + "Rainfall and official bulletins are the sources to watch for this area.",
      });
    } else if (review) {
      // Never write river knowledge up as a hydrologist sign-off. The reviewer's
      // stated qualification is shown as they gave it.
      list.push({
        label: "Gauge match",
        text: `${gauge?.site_name || "This gauge"} was chosen for this circle by `
          + `${review.reviewer} — ${review.reviewer_qualification} — on `
          + `${review.reviewed_at}. ${review.reasoning}`,
      });
    } else if (gauge && mapping && mapping.confidence !== "high") {
      /* The distance is the part that used to be missing, and it is the part a
         reader can act on. "A hydrologist has not checked this" is a process
         fact. "This gauge is 101 km away and a nearer one exists" is the same
         warning in terms somebody in Silonijan can weigh against what they can
         see out of the window. */
      const away = Number.isFinite(mapping.distance_km)
        ? ` about ${Math.round(mapping.distance_km)} km away`
        : "";
      const nearer = mapping.much_nearer_gauge_exists && mapping.nearest_gauge_name
        ? ` The nearest gauge, ${mapping.nearest_gauge_name}, is about `
          + `${Math.round(mapping.nearest_gauge_km)} km away, and it may sit on a `
          + "different river."
        : "";
      list.push({
        label: "Gauge match",
        text: `This reading comes from the ${gauge.site_name || "nearest"} gauge on the `
          + `${gauge.river || "river"},${away || " assigned to this circle"}. A hydrologist `
          + `has not confirmed that it is the right gauge for here.${nearer} Treat it as `
          + "background if your area floods from another river.",
      });
    }
    list.push({
      label: "Decision note",
      text: "Axom Flood translates official measurements into plain language. "
        + "It does not replace CWC, ASDMA, or local authority warnings.",
    });
    return list;
  });
</script>

<section class="provenance" aria-label="Reading context">
  <dl>
    {#each notes as note (note.label)}
      <div class="row">
        <dt>{note.label}</dt>
        <dd>{note.text}</dd>
      </div>
    {/each}
  </dl>
</section>

<style>
  .provenance {
    margin: 0;
  }
  dl { margin: 0; }
  .row {
    display: grid;
    grid-template-columns: minmax(0, 120px) minmax(0, 1fr);
    gap: 8px 24px;
    padding: 12px 0 0;
  }
  .row:first-child { padding-top: 0; }
  dt {
    color: var(--graphite);
    font-size: 12px;
    font-weight: 720;
  }
  dd {
    max-width: 62ch;
    margin: 0;
    color: var(--muted);
    font-size: 14px;
    line-height: 1.55;
  }

  @media (max-width: 859px) {
    .row { grid-template-columns: minmax(0, 1fr); gap: 4px; }
  }
</style>

