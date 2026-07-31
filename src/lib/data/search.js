import { cacheFirst, siteUrl } from "./cache.js";

let bundle;
let villages;
let villagePointer;
let villageIndexPromise;
let localityKeys;
let villageKeys;
let placeKeys;

export function configureSearch(nextBundle, pointer) {
  bundle = nextBundle;
  villagePointer = pointer;
  villages = undefined;
  villageIndexPromise = undefined;
  localityKeys = undefined;
  villageKeys = undefined;
  placeKeys = undefined;
}

export function getVillages() {
  return villages;
}

export function loadVillageIndex(pointer = villagePointer) {
  villageIndexPromise ||= cacheFirst(siteUrl(pointer.village_index_url)).then(loaded => {
    villages = loaded;
    return loaded;
  });
  return villageIndexPromise;
}

export function normalizedSearch(value) {
  return value.toLowerCase().normalize("NFKD").replace(/[^a-z0-9]/g, "");
}

// Assamese place names reach us through several English spellings: Sivasagar and
// Sibsagar, Jorhat and Zorhat, Guwahati and Gauhati. A person typing the spelling
// they know must still find their own place, so every name is also indexed under
// a folded form (predictable transliteration swaps) and a consonant skeleton
// (vowels dropped entirely), and the two are searched in that order of confidence.
export function foldedSearch(value) {
  return normalizedSearch(value)
    .replace(/sh/g, "s")
    .replace(/([bcdfgjklmnpqrstx])h/g, "$1")
    .replace(/[vw]/g, "b")
    .replace(/z/g, "j")
    .replace(/y/g, "i")
    .replace(/ck|q/g, "k")
    .replace(/ee|ie/g, "i")
    .replace(/oo|ou/g, "u")
    .replace(/(.)\1+/g, "$1");
}

export function skeletonSearch(value) {
  return foldedSearch(value).replace(/[aeiou]/g, "");
}

export function searchKeys(value) {
  return {
    raw: String(value ?? "").trim().toLowerCase(),
    normalized: normalizedSearch(value),
    folded: foldedSearch(value),
    skeleton: skeletonSearch(value),
  };
}

// Lower rank sorts first: an exact opening beats a match buried mid-name, and a
// real spelling beats a folded guess. Returns null when nothing matches at all.
export function matchRank(keys, query) {
  // Assamese script leaves nothing behind in the Latin keys, and an empty key
  // is a substring of every name, which would match the whole of Assam.
  if (!query.normalized) return null;
  if (keys.normalized.startsWith(query.normalized)) return 0;
  if (keys.normalized.includes(query.normalized)) return 1;
  if (keys.folded.startsWith(query.folded)) return 2;
  if (keys.folded.includes(query.folded)) return 3;
  // The skeleton is vowel-free and therefore matches loosely, so it is only
  // trusted from the start of a name. Anchoring it keeps "gauhati" from dragging
  // in every unrelated name that happens to contain g-h-t.
  if (query.skeleton.length >= 3 && keys.skeleton.startsWith(query.skeleton)) return 4;
  return null;
}

// Towns and localities the Census has no administrative unit for, from
// OpenStreetMap. Gaurisagar is the reason this layer exists: everyone there
// calls it that, and no census file has ever contained the name. These ride in
// the main bundle, so they are searchable before the large village index has
// been downloaded.
export function placeMatches(query) {
  // Records are shipped abbreviated to keep the first-visit download small:
  // n is the name, k its matching key, l the locality ids, a an Assamese name.
  placeKeys ||= (bundle.osm_places || []).map(item => ({ item, keys: searchKeys(item.n) }));
  return placeKeys
    .map(entry => {
      // Someone typing অসমীয়া gets nothing from the Latin keys, so where an
      // Assamese name exists, match the script directly.
      const inAssamese = entry.item.a && entry.item.a.includes(query.raw);
      const rank = inAssamese ? 0 : matchRank(entry.keys, query);
      return rank === null ? null : { entry, rank };
    })
    .filter(Boolean)
    .sort((a, b) => a.rank - b.rank || a.entry.item.n.length - b.entry.item.n.length)
    .slice(0, 8)
    .map(({ entry }) => {
      const home = bundle.localities.find(item => item.locality_id === entry.item.l[0]);
      return {
        label: entry.item.n,
        detail: home ? `${home.revenue_circle}, ${home.district}` : "Assam",
        locality_id: entry.item.l[0],
        locality_ids: entry.item.l,
        source: "manual_place",
      };
    });
}

function localityIndex() {
  localityKeys ||= bundle.localities.map(item => ({
    item,
    keys: [
      searchKeys(item.revenue_circle),
      ...(item.source_aliases || []).map(searchKeys),
    ],
    districtKeys: searchKeys(item.district),
  }));
  return localityKeys;
}

// Districts are what most people name first, and post-2011 districts such as
// Charaideo share no word with the circles inside them. A district result is a
// folder: choosing it opens the circles that belong to it.
export function districtMatches(query) {
  const districts = new Map();
  for (const entry of localityIndex()) {
    if (!districts.has(entry.item.district)) {
      districts.set(entry.item.district, { keys: entry.districtKeys, circles: [] });
    }
    districts.get(entry.item.district).circles.push(entry.item);
  }
  return [...districts]
    .map(([district, group]) => {
      const rank = matchRank(group.keys, query);
      return rank === null ? null : { district, group, rank };
    })
    .filter(Boolean)
    .sort((a, b) => a.rank - b.rank || a.district.localeCompare(b.district))
    .slice(0, 4)
    .map(({ district, group }) => ({
      label: district,
      detail: `District · ${group.circles.length} revenue circle${group.circles.length === 1 ? "" : "s"}`,
      district,
      circles: group.circles,
      source: "manual_district",
    }));
}

export function circleMatches(query) {
  return localityIndex()
    .map(entry => {
      const ranks = entry.keys.map(keys => matchRank(keys, query)).filter(rank => rank !== null);
      const rank = ranks.length ? Math.min(...ranks) : null;
      return rank === null ? null : { entry, rank };
    })
    .filter(Boolean)
    .sort((a, b) => a.rank - b.rank || a.entry.item.revenue_circle.localeCompare(b.entry.item.revenue_circle))
    .slice(0, 8)
    .map(({ entry }) => ({
      label: entry.item.revenue_circle,
      detail: `${entry.item.district} · revenue circle`,
      locality_id: entry.item.locality_id,
      source: "manual_circle",
    }));
}

// The village index carries the Census 2011 district a village sat in, so villages
// in circles that were later carved into new districts still read "Sivasagar" when
// the alert bundle now calls them "Charaideo". The bundle is the current authority.
function currentDistrict(localityId, fallback) {
  return bundle.localities.find(item => item.locality_id === localityId)?.district || fallback;
}

export function villageMatches(query) {
  if (!villages) return [];
  villageKeys ||= villages.villages.map(item => ({ item, keys: searchKeys(item.village_name) }));
  return villageKeys
    .map(entry => {
      const rank = matchRank(entry.keys, query);
      return rank === null ? null : { entry, rank };
    })
    .filter(Boolean)
    .sort((a, b) => a.rank - b.rank || a.entry.item.village_name.length - b.entry.item.village_name.length)
    .slice(0, 12)
    .map(({ entry }) => ({
      label: entry.item.village_name,
      detail: `${entry.item.revenue_circle}, ${currentDistrict(entry.item.locality_id, entry.item.district)}`,
      locality_id: entry.item.locality_id,
      source: "manual_village",
    }));
}

export function nearbyMatches(query) {
  const queries = query.normalized === "gauhati" ? [query, searchKeys("guwahati")] : [query];
  return queries.flatMap(candidate => [
    ...districtMatches(candidate),
    ...circleMatches(candidate),
    ...placeMatches(candidate),
  ]).filter((item, index, all) => all.findIndex(other =>
    other.label === item.label && other.locality_id === item.locality_id
      && other.source === item.source
  ) === index);
}

export function combinedMatches(query, nearby = nearbyMatches(query)) {
  return [...nearby, ...villageMatches(query)]
    .filter((item, index, all) => all.findIndex(other =>
      other.label === item.label && other.locality_id === item.locality_id
        && other.source === item.source
    ) === index).slice(0, 16);
}
