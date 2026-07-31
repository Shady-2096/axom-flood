// Shared-edge dissolve for the revenue-circle rings.
//
// The atlas dims everything outside Assam by drawing one polygon: a world-sized
// outer ring with the state punched out of it. Leaflet drew that with an
// even-odd fill rule, so it did not care that the state was handed over as 182
// separate circle rings that all touch their neighbours. MapLibre triangulates
// fills with earcut instead, and earcut is only defined for holes that are
// disjoint. Feeding it every circle produced long wedges of fill sprayed across
// the middle of the state, and they changed shape on every zoom because each
// tile is triangulated on its own.
//
// So the circles are dissolved into the state outline before they are used as a
// hole. Every border between two neighbouring circles is walked twice, once in
// each direction, and those pairs cancel; what survives is the outside edge.
//
// Cancelling is not enough on its own. Where two neighbours were simplified
// apart from each other their shared border is two slightly different lines,
// neither of which cancels, and the walk threads both into the outline as a
// short zigzag that crosses itself. A ring that crosses itself is not simple
// either, so the outline is cut at the nodes it revisits and cleaned of its
// crossings before it is used.

const PRECISION = 6;

// Roughly two kilometres at this latitude. Only used to bucket segments for the
// crossing search, so it trades memory against comparisons and nothing else.
const GRID_CELL = 0.02;

// The source rings are not perfectly noded: neighbouring circles were
// simplified apart from each other, so their shared borders differ by a metre
// here and there and leave hairline slivers behind after the cancellation. The
// real outline holds 99.8% of the dissolved area, so anything under a
// thousandth of the largest ring is one of those slivers and is dropped.
const SLIVER_SHARE = 1 / 1000;

export function signedRingArea(ring) {
  let total = 0;
  for (let index = 0, previous = ring.length - 1; index < ring.length; previous = index++) {
    total += (ring[previous][0] - ring[index][0]) * (ring[index][1] + ring[previous][1]);
  }
  return total / 2;
}

export function closeRing(ring) {
  if (!ring.length) return ring;
  const first = ring[0];
  const last = ring[ring.length - 1];
  return first[0] === last[0] && first[1] === last[1] ? ring : [...ring, first];
}

/**
 * Return the ring wound in the requested direction.
 *
 * MapLibre reads outer rings and holes off the winding order alone: a ring
 * wound like the first one starts a new filled polygon, an oppositely wound one
 * is punched out of it.
 */
export function windRing(ring, positive) {
  const closed = closeRing(ring);
  if (closed.length < 4) return closed;
  return signedRingArea(closed) >= 0 === positive ? closed : [...closed].reverse();
}

/**
 * Cut a ring at every node it passes through twice.
 *
 * The dissolved outline comes back pinched: nine nodes where two parts of the
 * state meet at a single point, so the ring touches itself. That is not a
 * simple ring, and earcut is only defined for simple rings — fed one, it
 * bridged straight across the pinch and painted a wedge of the outside dim a
 * second time, which showed up as a dark diagonal band running off the map.
 * MapLibre re-triangulates the mask for every tile, so the band moved and
 * changed shape with the view instead of staying put where the geometry was.
 *
 * Each pinch is cut into its own loop and handed over as its own hole. The
 * loops still cover exactly the area the pinched ring covered.
 */
function splitSelfTouches(ring) {
  const open = openRing(ring);
  const loops = [];
  const walk = [];
  const positionByKey = new Map();
  for (const point of open) {
    const key = keyOf(point);
    const seen = positionByKey.get(key);
    if (seen !== undefined) {
      // Everything since the earlier visit is a closed loop of its own. The
      // node itself goes back on the walk, which carries on around the rest.
      const loop = walk.splice(seen);
      for (const dropped of loop) positionByKey.delete(keyOf(dropped));
      if (loop.length >= 3) loops.push(loop);
    }
    positionByKey.set(key, walk.length);
    walk.push(point);
  }
  if (walk.length >= 3) loops.push(walk);
  return loops;
}

function cross(origin, from, to) {
  return (from[0] - origin[0]) * (to[1] - origin[1]) - (from[1] - origin[1]) * (to[0] - origin[0]);
}

/**
 * Where two segments cross each other, or null.
 *
 * Only a proper crossing counts: segments that merely share an endpoint, or
 * that touch end-on, are how a ring is meant to be built and are left alone.
 */
function crossingPoint(a1, a2, b1, b2) {
  const d1 = cross(b1, b2, a1);
  const d2 = cross(b1, b2, a2);
  const d3 = cross(a1, a2, b1);
  const d4 = cross(a1, a2, b2);
  if (d1 === 0 || d2 === 0 || d3 === 0 || d4 === 0) return null;
  if ((d1 > 0) === (d2 > 0) || (d3 > 0) === (d4 > 0)) return null;
  const share = d1 / (d1 - d2);
  return [a1[0] + share * (a2[0] - a1[0]), a1[1] + share * (a2[1] - a1[1])];
}

/**
 * Bucket segment indices by the grid cells their bounding box covers.
 *
 * The crossings are local — a seam kink spans a handful of vertices — but a
 * full pairwise search over two thousand of them on every pass is wasteful, and
 * a fixed window would quietly miss anything that is not local.
 */
function gridSegments(points) {
  const cells = new Map();
  for (let index = 0; index < points.length; index++) {
    const from = points[index];
    const to = points[(index + 1) % points.length];
    const xMin = Math.floor(Math.min(from[0], to[0]) / GRID_CELL);
    const xMax = Math.floor(Math.max(from[0], to[0]) / GRID_CELL);
    const yMin = Math.floor(Math.min(from[1], to[1]) / GRID_CELL);
    const yMax = Math.floor(Math.max(from[1], to[1]) / GRID_CELL);
    for (let x = xMin; x <= xMax; x++) {
      for (let y = yMin; y <= yMax; y++) {
        const key = `${x},${y}`;
        const list = cells.get(key);
        if (list) list.push(index);
        else cells.set(key, [index]);
      }
    }
  }
  return cells;
}

/**
 * Cut the loops out of a ring that crosses itself.
 *
 * The stretch between one crossing and the other is a loop hanging off the
 * outline; it is dropped and the two sides are pinned together at the crossing
 * itself. Every one of these is a seam artefact a few hundred metres across,
 * far below the sliver floor further down, so nothing that matters is lost.
 */
function removeSelfCrossings(ring) {
  let points = openRing(ring).slice();
  // Each pass removes at least one vertex, so this cannot run away; the bound
  // is only here so a geometry nobody anticipated cannot hang the map.
  for (let pass = 0; pass < points.length; pass++) {
    const cells = gridSegments(points);
    let cut = null;
    for (const indices of cells.values()) {
      for (let first = 0; first < indices.length && !cut; first++) {
        for (let second = first + 1; second < indices.length && !cut; second++) {
          const left = Math.min(indices[first], indices[second]);
          const right = Math.max(indices[first], indices[second]);
          // Neighbouring segments share an endpoint by construction, and the
          // last segment neighbours the first.
          if (right - left < 2 || (left === 0 && right === points.length - 1)) continue;
          const hit = crossingPoint(
            points[left], points[(left + 1) % points.length],
            points[right], points[(right + 1) % points.length],
          );
          if (hit) cut = { left, right, hit };
        }
      }
      if (cut) break;
    }
    if (!cut) return points;
    points.splice(cut.left + 1, cut.right - cut.left, cut.hit);
  }
  return points;
}

function openRing(ring) {
  if (ring.length < 2) return ring;
  const first = ring[0];
  const last = ring[ring.length - 1];
  return first[0] === last[0] && first[1] === last[1] ? ring.slice(0, -1) : ring;
}

function keyOf(point) {
  return `${point[0].toFixed(PRECISION)},${point[1].toFixed(PRECISION)}`;
}

/**
 * Dissolve touching rings into the outline of the area they cover.
 *
 * Rings may arrive wound either way; they are normalised first so that a border
 * shared by two neighbours is walked in opposite directions and cancels.
 */
export function dissolveRings(rings) {
  const points = new Map();
  const edges = new Map();

  for (const ring of rings) {
    const open = openRing(ring);
    if (open.length < 3) continue;
    const wound = signedRingArea(closeRing(open)) >= 0 ? open : [...open].reverse();
    for (let index = 0; index < wound.length; index++) {
      const from = wound[index];
      const to = wound[(index + 1) % wound.length];
      const fromKey = keyOf(from);
      const toKey = keyOf(to);
      if (fromKey === toKey) continue;
      points.set(fromKey, from);
      points.set(toKey, to);
      const edge = `${fromKey}|${toKey}`;
      edges.set(edge, (edges.get(edge) || 0) + 1);
    }
  }

  const outgoing = new Map();
  for (const [edge, count] of edges) {
    const [fromKey, toKey] = edge.split("|");
    const surviving = count - (edges.get(`${toKey}|${fromKey}`) || 0);
    if (surviving <= 0) continue;
    const list = outgoing.get(fromKey) || [];
    for (let index = 0; index < surviving; index++) list.push(toKey);
    outgoing.set(fromKey, list);
  }

  const found = [];
  for (const startKey of outgoing.keys()) {
    while (outgoing.get(startKey)?.length) {
      const walk = [startKey];
      let currentKey = startKey;
      while (outgoing.get(currentKey)?.length) {
        currentKey = outgoing.get(currentKey).pop();
        walk.push(currentKey);
        if (currentKey === startKey) break;
      }
      // A walk that ran out of edges before returning to its start is a broken
      // chain across an unnoded seam, not a ring, and cannot be filled.
      if (walk.length > 3 && walk[walk.length - 1] === startKey) {
        for (const loop of splitSelfTouches(walk.map(key => points.get(key)))) {
          const cleaned = removeSelfCrossings(loop);
          if (cleaned.length >= 3) found.push(cleaned);
        }
      }
    }
  }

  if (!found.length) return [];
  const measured = found
    .map(ring => ({ ring, area: Math.abs(signedRingArea(ring)) }))
    .sort((left, right) => right.area - left.area);
  const floor = measured[0].area * SLIVER_SHARE;
  return measured.filter(entry => entry.area >= floor).map(entry => closeRing(entry.ring));
}
