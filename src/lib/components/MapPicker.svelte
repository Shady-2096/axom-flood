<script>
  import { cacheFirst, siteUrl } from "$lib/data/cache.js";
  import { getBundle } from "$lib/data/index.js";
  import { onMount } from "svelte";

  let { currentLocalityId, onselect = () => {} } = $props();
  let container;
  let shapes;

  const bundle = getBundle();
  const NS = "http://www.w3.org/2000/svg";

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, character => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[character]);
  }

  function element(name, attributes) {
    const node = document.createElementNS(NS, name);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
    return node;
  }

  async function loadShapes() {
    if (shapes) return shapes;
    const url = bundle?.circle_shapes_url;
    if (!url) throw new Error("No map outlines are published in this build.");
    shapes = await cacheFirst(siteUrl(url));
    return shapes;
  }

  // Assam sits near 26 degrees north, where a degree of longitude is about 0.9 of
  // a degree of latitude on the ground. Without that correction the state comes
  // out visibly stretched sideways.
  function projector(circles) {
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
      point: ([x, y]) => [(x * squeeze).toFixed(4), (-y).toFixed(4)],
    };
  }

  function pathFor(circle, project) {
    return circle.rings
      .map(ring => "M" + ring.map(point => project.point(point).join(",")).join("L") + "Z")
      .join("");
  }

  function districtsOf(circles) {
    const districts = new Map();
    for (const circle of circles) {
      if (!districts.has(circle.district)) districts.set(circle.district, []);
      districts.get(circle.district).push(circle);
    }
    return [...districts].sort((a, b) => a[0].localeCompare(b[0]));
  }

  async function renderMapPicker() {
    container.innerHTML = '<p class="map-status">Loading the map…</p>';
    let document_;
    try {
      document_ = await loadShapes();
    } catch (_) {
      container.innerHTML = `<p class="map-status error">The map could not load.
        You can still search for your place by name.</p>`;
      return;
    }

    const all = document_.circles;
    let focus = null; // null shows the whole state, otherwise a district name

    const draw = () => {
      const visible = focus ? all.filter(circle => circle.district === focus) : all;
      const project = projector(visible);
      const svg = element("svg", {
        viewBox: project.box.map(value => value.toFixed(4)).join(" "),
        class: "map-canvas",
        role: "img",
        "aria-label": focus ? `Map of revenue circles in ${focus}` : "Map of Assam districts",
      });

      const groups = focus ? visible.map(circle => [circle.revenue_circle, [circle]])
        : districtsOf(visible);
      const choiceHandlers = new Map();

      for (const [name, members] of groups) {
        const group = element("g", {
          class: "map-area",
          "aria-hidden": "true",
        });
        if (members.some(circle => circle.locality_ids?.includes(currentLocalityId))) {
          group.classList.add("is-current");
        }
        for (const circle of members) {
          group.appendChild(element("path", { d: pathFor(circle, project) }));
        }
        const choose = () => {
          if (!focus) {
            focus = members[0].district;
            draw();
            return;
          }
          // One outline can carry two localities: the Census splits a few circles
          // across district lines while OSM keeps a single shape. Asking is the
          // only honest response -- guessing would pick somebody's river gauge.
          const circle = members[0];
          if (circle.locality_ids.length > 1) {
            askWhich(circle);
            return;
          }
          onselect({
            locality_id: circle.locality_ids[0],
            label: circle.revenue_circle,
            district: circle.district,
          });
        };
        svg.appendChild(group);
        group.dataset.choiceName = name;
        choiceHandlers.set(name, choose);
      }

      container.innerHTML = "";
      const bar = document.createElement("div");
      bar.className = "map-bar";
      bar.innerHTML = focus
        ? `<button type="button" class="map-back">← All districts</button><strong>${
          escapeHtml(focus)}</strong>`
        : "<p>Tap your district, then your revenue circle.</p>";
      container.appendChild(bar);
      container.appendChild(svg);
      const choices = document.createElement("div");
      choices.className = "map-choices";
      choices.setAttribute("role", "group");
      choices.setAttribute("aria-label", focus
        ? `Choose a revenue circle in ${focus}`
        : "Choose a district");
      for (const [name] of groups) {
        const button = document.createElement("button");
        const group = [...svg.querySelectorAll(".map-area")]
          .find(item => item.dataset.choiceName === name);
        button.type = "button";
        button.className = "map-choice";
        button.textContent = name;
        if (group?.classList.contains("is-current")) button.classList.add("is-current");
        button.onclick = choiceHandlers.get(name);
        choices.appendChild(button);
      }
      container.appendChild(choices);
      const credit = document.createElement("p");
      credit.className = "map-credit";
      credit.textContent = document_.attribution || "© OpenStreetMap contributors";
      container.appendChild(credit);
      const back = container.querySelector(".map-back");
      if (back) back.onclick = () => { focus = null; draw(); };
    };

    const askWhich = circle => {
      const bar = container.querySelector(".map-bar");
      bar.innerHTML = `<p>${escapeHtml(circle.revenue_circle)} is split across
        two districts. Which one is yours?</p>`;
      for (const localityId of circle.locality_ids) {
        const locality = bundle.localities.find(item => item.locality_id === localityId);
        if (!locality) continue;
        const button = document.createElement("button");
        button.type = "button";
        button.className = "map-choice";
        button.textContent = `${locality.revenue_circle}, ${locality.district}`;
        button.onclick = () => onselect({
          locality_id: localityId,
          label: locality.revenue_circle,
          district: locality.district,
        });
        bar.appendChild(button);
      }
    };

    draw();
  }

  onMount(renderMapPicker);
</script>

<div bind:this={container} style="display: contents"></div>
