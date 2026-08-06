<script>
  import AgeBlock from "./AgeBlock.svelte";
  import Icon from "./Icon.svelte";
  import { displaySentence, isUngauged, statusInfo } from "$lib/data/index.js";

  /* `kicker` names what this panel is; it changes when the panel is standing in
     for a place nobody chose. `lead` is the one-line notice under it — today,
     the way back to your own area from that stand-in. */
  let {
    gauge,
    /* Passed so the bulletin can tell "the gauge went quiet" from "no gauge
       covers this circle". Optional: surfaces that only have a gauge in hand
       keep the older wording, which is correct for them. */
    locality = null,
    /* One circle's satellite rainfall, already chosen and worded by
       `data/rainfall.js`. Null on every surface that has no rainfall artifact,
       which is every surface until the pipeline has run once. */
    rainfall = null,
    shareLabel,
    shareIcon,
    place = null,
    kicker = "Local flood bulletin",
    lead = null,
    /* The fold. It lives in here rather than in the panel around it because the
       card's foreground travels with its safety state — dark ink on the amber
       and red fields, light on smoke — and a hinge drawn outside the card has
       no way to know which. */
    folded = false,
    onfold = null,
    onshare,
    onmoreinfo = null,
  } = $props();

  let status = $derived(statusInfo(gauge, locality));
  let ungauged = $derived(isUngauged(locality));
  let urgent = $derived(status.level >= 2);

  /* The mark beside the status is the state's own glyph, never colour alone —
     it has to survive greyscale and it has to survive a reader who cannot tell
     amber from red. */
  const stateIcon = {
    "no-data": "no-reading",
    normal: "level",
    warning: "alert",
    danger: "alert",
    extreme: "alert",
  };

  /* Naming the instrument is what separates a bulletin from a notification. A
     reader deciding whether to move should be able to see which gauge this came
     off without opening the technical panel. */
  let attribution = $derived.by(() => {
    if (!gauge?.site_name) return null;
    const agency = gauge.agency || gauge.source || "Central Water Commission";
    return gauge.river
      ? `${gauge.site_name} gauge on the ${gauge.river} · ${agency}`
      : `${gauge.site_name} gauge · ${agency}`;
  });

  const camps = { href: "/camps/", label: "Relief camps" };
  const emergency = { href: "/emergency/", label: "Emergency numbers" };

  const moreInfo = { action: "more-info", label: "More info" };
  let plan = $derived.by(() => {
    if (status.level >= 3) return { lead: emergency, second: camps, minor: [moreInfo], share: "minor" };
    if (status.level === 2) return { lead: camps, second: "share", minor: [moreInfo] };
    // "More info" leads the no-data card because the reading is the thing
    // missing and the panel explains why. When no gauge exists there is no
    // reading to explain, so the useful thing to offer is somewhere to go.
    if (ungauged) return { lead: camps, second: emergency, minor: [moreInfo] };
    if (status.level === 0) return { lead: moreInfo, second: camps, minor: [] };
    return { lead: "share", second: moreInfo, minor: [] };
  });
</script>

{#snippet control(item, tone)}
  {#if item === "share"}
    <button class={`act ${tone}`} type="button" onclick={onshare}>
      {#if shareIcon}<Icon name={shareIcon} />{/if}{shareLabel}
    </button>
  {:else if item.action === "more-info"}
    <button class={`act ${tone}`} type="button" aria-controls="technical-details" onclick={onmoreinfo}>
      {item.label}
    </button>
  {:else}
    <a
      class={`act ${tone}`}
      href={item.href}
      rel={item.external ? "noopener" : undefined}
      target={item.external ? "_blank" : undefined}
    >{item.label}{#if item.external}<Icon name="external" />{/if}</a>
  {/if}
{/snippet}

<article
  class="bulletin"
  class:urgent
  class:standalone={!place}
  class:folded
  data-state={status.state}
  aria-labelledby="bulletin-status"
>
  <div class="face">
    {#if onfold}
      <button
        class="fold"
        type="button"
        aria-expanded={!folded}
        aria-controls="bulletin-detail"
        aria-label={folded ? "Expand the flood bulletin" : "Collapse the flood bulletin"}
        title={folded ? "Expand the flood bulletin" : "Collapse the flood bulletin"}
        onclick={onfold}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 14 5-5 5 5"/></svg>
      </button>
    {/if}

    <div class="head">
      <span class="type">
        <i class="status-mark" aria-hidden="true"></i>
        {kicker}
      </span>
      <AgeBlock {gauge} {ungauged} />
    </div>

    {#if lead}
      <div class="lead-note">{@render lead()}</div>
    {/if}

    {#if place}
      <h1 class="place-line" tabindex="-1">{place.name}<span>{place.meta}</span></h1>
    {/if}

    <div class="message">
      <h2 class="status" id="bulletin-status">
        <i class="status-icon" aria-hidden="true"><Icon name={stateIcon[status.state] || "level"} /></i>
        <span>{status.label}</span>
      </h2>
      <p class="sentence" id="bulletin-detail">{displaySentence(gauge, locality)}</p>
      {#if rainfall}
        <!-- Rain is not a river reading, and this line is built so it can never
             be mistaken for one. It sits below the sentence, at the quiet
             weight, behind a label that names the instrument as a satellite,
             and it carries no status colour of its own. A circle with no usable
             estimate still prints a line here saying so: the gap where rainfall
             belongs would otherwise be read as no rain. -->
        <p class="rainfall" data-rain-status={rainfall.status}>
          <span class="rain-label">Satellite rainfall</span>
          {rainfall.headline}
          <span class="rain-note">{rainfall.estimateNote} {rainfall.hedge}</span>
        </p>
      {/if}
    </div>

    <div class="actions">
      {@render control(plan.lead, "lead")}
      {@render control(plan.second, "second")}
    </div>

    {#if plan.minor.length || plan.share === "minor"}
      <p class="minor">
        {#if plan.share === "minor"}
          <button class="quiet" type="button" onclick={onshare}>{shareLabel}</button>
        {/if}
        {#each plan.minor as item (item.label)}
          {#if item.action === "more-info"}
            <button class="quiet" type="button" aria-controls="technical-details" onclick={onmoreinfo}>{item.label}</button>
          {:else}
            <a class="quiet" href={item.href} rel="noopener" target="_blank">{item.label}</a>
          {/if}
        {/each}
      </p>
    {/if}

    {#if attribution}
      <p class="attribution">{attribution}</p>
    {/if}
  </div>
</article>

<style>
  .bulletin {
    --field: var(--surface);
    --on-field: var(--ink);
    --on-field-quiet: var(--muted);
    --status-mark: var(--river);
    /* Where the field goes on hover: away from the text, never toward it. */
    --field-shade: var(--shade);

    position: relative;
    overflow: hidden;
    border: 0;
    border-radius: var(--r-panel);
    color: var(--on-field);
    background: var(--field);
    box-shadow: var(--shadow-2);
  }

  .bulletin[data-state="warning"] {
    --field: var(--signal);
    --field-shade: #f7b075;
    --on-field: var(--on-warning);
    --on-field-quiet: rgba(31, 21, 12, .76);
    --status-mark: var(--on-warning);
  }

  .bulletin[data-state="danger"] {
    --field: var(--danger);
    --field-shade: var(--flood-deep);
    --on-field: var(--on-danger);
    --on-field-quiet: rgba(255, 255, 255, .78);
    --status-mark: var(--on-danger);
  }

  .bulletin[data-state="extreme"] {
    --field: var(--flood-deep);
    --field-shade: #2c0903;
    --on-field: var(--on-danger);
    --on-field-quiet: rgba(255, 255, 255, .78);
    --status-mark: var(--signal);
  }

  .bulletin[data-state="no-data"] {
    --field: var(--surface-inactive);
    --on-field: var(--ink);
    --on-field-quiet: var(--muted);

    border: 0;
    box-shadow: var(--shadow-2);
  }

  .bulletin.standalone,
  .bulletin.standalone[data-state="no-data"] {
    border: 0;
    border-radius: 0;
    background: transparent;
    box-shadow: none;
  }

  /* Inside the atlas the bulletin floats on the map, so the calm and no-data
     states become optical glass: translucency and blur, and nothing else. The
     1px translucent border and the `inset 0 1px 0` bevel that used to come with
     them were two more devices saying "card", and they are not coming back.

     The field is smoke, not the scheme's surface. Translucency only reads when
     what is behind it differs — a sage panel over sage landcover disappeared
     into the terrain in daylight, which is the one thing this panel must never
     do. Smoke is cool and near-neutral, the one family the OSM sheet never uses,
     so it separates by hue as well as by luminance and it does not flip between
     schemes: on paper the map is at its brightest, so the panel stays dark and
     gains contrast rather than losing it.

     These live here, and not in styles.css, because the base fields below are
     scoped to this component and load after it — anything declared out there at
     the same specificity loses, silently. */
  :global(.atlas-panel) .bulletin[data-state="normal"],
  :global(.atlas-panel) .bulletin[data-state="no-data"] {
    --field: color-mix(in srgb, var(--smoke) calc(var(--smoke-alpha) * 100%), transparent);
    --on-field: var(--on-smoke);
    --on-field-quiet: var(--on-smoke-quiet);
    --field-shade: var(--smoke-shade);
    --status-mark: var(--on-smoke-mark);

    border: 0;
    background: var(--field);
    -webkit-backdrop-filter: blur(20px) saturate(130%);
    backdrop-filter: blur(20px) saturate(130%);
    box-shadow: var(--shadow-3);
  }

  /* Warning, danger and extreme stay opaque. A state you can see the map through
     is a state you can miss, and those three are the ones that must not be. */

  /* Two ways the blur can be unavailable: the reader asked for less
     transparency, or the engine has no backdrop-filter — which on the low-end
     Android this is built for is a real case, not a theoretical one. Both land
     on an opaque smoke field rather than a washed-out one. */
  @media (prefers-reduced-transparency: reduce) {
    :global(.atlas-panel) .bulletin[data-state="normal"],
    :global(.atlas-panel) .bulletin[data-state="no-data"] {
      --field: var(--smoke);

      -webkit-backdrop-filter: none;
      backdrop-filter: none;
    }
  }

  @supports not ((-webkit-backdrop-filter: blur(1px)) or (backdrop-filter: blur(1px))) {
    :global(.atlas-panel) .bulletin[data-state="normal"],
    :global(.atlas-panel) .bulletin[data-state="no-data"] {
      --field: var(--smoke);
    }
  }

  .face {
    padding: clamp(20px, 2.4vw, 28px);
  }

  /* On the desktop atlas the bulletin floats on the map and can grow tall with
     a warning or danger reading. The fold handle reclaims terrain the same way
     it does on mobile — same chevron, same targets, same hiding rules. */
  :global(.atlas-panel) .fold { display: grid; }

  :global(.atlas-panel) .folded .sentence,
  :global(.atlas-panel) .folded .rainfall,
  :global(.atlas-panel) .folded .actions,
  :global(.atlas-panel) .folded .minor,
  :global(.atlas-panel) .folded .attribution,
  :global(.atlas-panel) .folded .lead-note {
    display: none;
  }

  /* The hinge: the card's whole top edge is the target, with a small chevron
     centred in it. It appears wherever a caller asks for one — on both the
     phone and the desktop atlas, where a tall bulletin can cover the map. */
  .fold {
    display: none;
    width: 100%;
    min-height: 44px;
    margin-bottom: 4px;
    padding: 4px 0;
    border: 0;
    border-radius: 0;
    color: var(--on-field);
    background: transparent;
    box-shadow: none;
    place-items: center;
    cursor: pointer;
  }

  .fold svg {
    width: 22px;
    height: 22px;
    fill: none;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 2.6;
    opacity: .85;
    transition: transform 180ms ease, opacity 160ms ease;
  }

  .fold:hover svg,
  .fold:focus-visible svg {
    opacity: 1;
    transform: scale(1.15);
  }

  .folded .fold svg { transform: rotate(180deg); }
  .folded .fold:hover svg { transform: rotate(180deg) scale(1.15); }

  .standalone .face {
    padding: 24px 0;
  }

  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    color: var(--on-field-quiet);
  }

  .type {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: var(--on-field);
    font-size: 14px;
    font-weight: 720;
  }

  .status-mark {
    width: 9px;
    height: 9px;
    flex: 0 0 auto;
    border-radius: 50%;
    background: var(--status-mark);
  }

  .bulletin[data-state="no-data"] .status-mark {
    background: transparent;
    box-shadow: inset 0 0 0 2px var(--muted);
  }

  .head :global(.age) {
    color: var(--on-field-quiet);
    font-size: 12px;
    font-weight: 650;
    letter-spacing: 0;
    text-transform: none;
    white-space: nowrap;
  }

  .head :global(.age-dot) {
    background: var(--safe);
    box-shadow: none;
  }

  .head :global(.age.stale .age-dot) {
    background: none;
    box-shadow: inset 0 0 0 2px var(--signal-ink);
  }

  /* The stand-in notice. It reads as an annotation on the place name below it,
     not as another control block: one line, quiet type, and the locate button
     carried inline at the size of the sentence it interrupts. */
  .lead-note {
    margin-top: 12px;
  }

  .lead-note :global(.stand-in) {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px 12px;
    margin: 0;
    color: var(--on-field-quiet);
    font-size: 12px;
    font-weight: 600;
    line-height: 1.4;
  }

  .lead-note :global(button) {
    min-height: 32px;
    padding: 6px 12px;
    border: 0;
    border-radius: var(--r-pill);
    color: var(--field);
    background: var(--on-field);
    font-size: 12px;
    font-weight: 700;
  }

  .lead-note :global(button svg) {
    width: 14px;
    height: 14px;
  }

  /* The locate control ships its own live region. Empty, it still reserved a
     20px row inside the notice, which read as a broken gap above the place
     name; it earns height only once it has something to announce. */
  .lead-note :global(.field-status) {
    flex: 1 1 100%;
    min-height: 0;
    margin: 0;
    color: var(--on-field-quiet);
    font-size: 12px;
  }

  .lead-note + .place-line { margin-top: 12px; }

  .place-line {
    margin: 24px 0 0;
    font: 760 clamp(28px, 3vw, 40px)/1.06 var(--body);
    letter-spacing: -.025em;
    text-wrap: balance;
  }

  .place-line span {
    display: block;
    margin-top: 8px;
    color: var(--on-field-quiet);
    font: 600 14px/1.4 var(--body);
    letter-spacing: 0;
  }

  .message {
    margin-top: 24px;
  }

  .place-line + .message { margin-top: 20px; }

  .status {
    display: flex;
    max-width: 26ch;
    align-items: baseline;
    gap: 12px;
    margin: 0;
    font: 760 clamp(18px, 2vw, 24px)/1.12 var(--body);
    letter-spacing: -.018em;
    text-wrap: balance;
  }

  /* Sized in em so the mark tracks the heading it belongs to instead of drifting
     as the status scales up at warning and above. */
  .status-icon {
    display: block;
    width: 1.05em;
    height: 1.05em;
    flex: 0 0 auto;
    transform: translateY(.1em);
  }

  .status-icon :global(svg) {
    width: 100%;
    height: 100%;
    fill: none;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.7;
  }

  .bulletin[data-state="no-data"] .status-icon { color: var(--on-field-quiet); }
  /* Tracks the state mark rather than naming a colour, so it stays correct on
     the smoke field, where raw --river only reaches 2.71:1. */
  .bulletin[data-state="normal"] .status-icon { color: var(--status-mark); }

  .attribution {
    margin: 20px 0 0;
    padding-top: 16px;
    border-top: 1px solid color-mix(in srgb, var(--on-field) 16%, transparent);
    color: var(--on-field-quiet);
    font-size: 12px;
    font-weight: 560;
    line-height: 1.45;
  }

  .sentence {
    max-width: 58ch;
    margin: 12px 0 0;
    color: var(--on-field-quiet);
    font-size: 15px;
    font-weight: 500;
    font-variant-numeric: tabular-nums lining-nums;
    line-height: 1.55;
  }

  /* Deliberately not on the ramp for weight: this line is quieter than the
     status sentence above it at every size, because it is context and the
     sentence is the reading. */
  .rainfall {
    max-width: 58ch;
    margin: 12px 0 0;
    color: var(--on-field-quiet);
    font-size: 14px;
    font-weight: 500;
    font-variant-numeric: tabular-nums lining-nums;
    line-height: 1.5;
  }

  .rain-label {
    display: block;
    color: var(--on-field-quiet);
    font-size: 11px;
    font-weight: 620;
    letter-spacing: .06em;
    text-transform: uppercase;
  }

  /* The estimate note and the hedge travel with every number, so they are set
     smaller rather than dropped. Dropping them is how a satellite estimate
     turns into a statement about somebody's house. */
  .rain-note {
    display: block;
    margin-top: 4px;
    font-size: 12px;
    font-weight: 500;
    opacity: .86;
  }

  .rainfall[data-rain-status="unavailable"] .rain-note { display: none; }

  .bulletin.urgent .status {
    font-size: clamp(24px, 3vw, 36px);
  }

  .bulletin.urgent .sentence {
    color: var(--on-field);
    font-weight: 560;
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-top: 24px;
  }

  .act {
    display: inline-flex;
    min-height: 46px;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 12px 20px;
    border: 0;
    border-radius: var(--r-control);
    color: var(--field);
    background: var(--on-field);
    cursor: pointer;
    font-size: 15px;
    font-weight: 700;
    line-height: 1.2;
    text-decoration: none;
    transition: background-color 140ms ease, color 140ms ease, transform 140ms ease;
  }

  /* Mixed toward the field rather than toward transparent. The old value was
     12% of the foreground over nothing, so on a pale card it landed as a barely
     tinted rectangle that read as an outline instead of a fill, and on the
     amber and red safety fields it let the field bleed through the control. */
  .act.second {
    color: var(--on-field);
    background: color-mix(in srgb, var(--on-field) 16%, var(--field));
  }

  .act:hover { transform: translateY(-1px); }
  .act.lead:hover { opacity: .9; }
  /* Hover deepens the fill away from the label rather than toward it. Mixing
     more --on-field in was the intuitive move and the wrong one: it walks the
     fill toward the text colour, so on the amber field the secondary's label
     fell to 3.92:1 exactly when a pointer was on it. */
  .act.second:hover { background: color-mix(in srgb, var(--field-shade) 34%, var(--field)); }

  .act:focus-visible,
  .quiet:focus-visible {
    outline: 3px solid var(--on-field);
    outline-offset: 3px;
  }

  .act :global(svg) {
    width: 17px;
    height: 17px;
    fill: none;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.8;
  }

  .minor {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0 20px;
    margin: 8px 0 0;
  }

  .quiet {
    display: inline-flex;
    min-height: 40px;
    align-items: center;
    padding: 0;
    border: 0;
    border-radius: 0;
    color: var(--on-field);
    background: none;
    box-shadow: none;
    cursor: pointer;
    font-size: 14px;
    font-weight: 700;
    text-decoration: underline;
    text-underline-offset: 4px;
  }

  .quiet:hover {
    color: var(--on-field);
    background: none;
    text-decoration-thickness: 2px;
  }

  @media (max-width: 700px) {
    .bulletin {
      border-radius: 0;
      box-shadow: none;
    }

    .face { padding: 20px; }
    .head { align-items: flex-start; }
    .actions { display: grid; }
    .act { width: 100%; }

    /* Inside the atlas none of that holds: the bulletin is not the document,
       it is an object floating on a full-screen map, so it keeps its edges and
       its shadow. Everything else here is compression. A card that floats has
       to earn its footprint against the terrain it covers, and at document
       rhythm this one stood ~430px tall on a 680px sheet — the map became a
       margin. Same words, same order, same actions, one step tighter
       throughout, and the two controls back on a single row. */
    :global(.atlas-panel) .bulletin {
      border-radius: var(--r-panel);
      box-shadow: var(--shadow-3);
    }

    :global(.atlas-panel) .face { padding: 8px 16px 16px; }

    :global(.atlas-panel) .fold { display: grid; }

    :global(.atlas-panel) .head { align-items: center; }

    /* Folded, the card keeps what a glance is for: which place, how old the
       reading is, and what state the river is in. The sentence, the actions and
       the stand-in notice are what the reader folded away to see terrain. */
    :global(.atlas-panel) .folded .sentence,
    :global(.atlas-panel) .folded .rainfall,
    :global(.atlas-panel) .folded .actions,
    :global(.atlas-panel) .folded .minor,
    :global(.atlas-panel) .folded .lead-note {
      display: none;
    }

    :global(.atlas-panel) .type { font-size: 12px; }

    :global(.atlas-panel) .place-line {
      margin-top: 8px;
      font-size: 24px;
    }

    :global(.atlas-panel) .place-line span {
      margin-top: 4px;
      font-size: 12px;
    }

    :global(.atlas-panel) .place-line + .message { margin-top: 12px; }

    :global(.atlas-panel) .status { font-size: 20px; }

    /* On the phone atlas the panel floats over the map, so the rainfall note
       gives up its explanatory second line. The label and the estimate word
       inside the headline still say what it is. */
    :global(.atlas-panel) .rain-note { display: none; }

    :global(.atlas-panel) .sentence {
      margin-top: 6px;
      font-size: 14px;
      line-height: 1.42;
    }

    /* Two columns rather than two rows: a floating card pays for every vertical
       pixel in map it covers, and a stacked pair costs 96px where a paired one
       costs 52. */
    :global(.atlas-panel) .actions {
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-top: 12px;
    }

    :global(.atlas-panel) .act {
      min-height: 44px;
      padding: 12px 8px;
      font-size: 14px;
      text-align: center;
    }

    /* Icons are decoration on labels that already state their action. */
    :global(.atlas-panel) .act :global(svg) { display: none; }

    :global(.atlas-panel) .minor { margin-top: 4px; }

    /* Naming the gauge is what makes this a reading rather than a notification,
       and it is not being dropped — on a phone it moves one scroll down, to the
       gauge panel that always sits under this map. Keeping it here as well cost
       ~50px of terrain for a line the same screen already carries. */
    :global(.atlas-panel) .attribution { display: none; }
  }

  @media (prefers-reduced-motion: reduce) {
    .act { transition: none; }
    .act:hover { transform: none; }
  }
</style>
