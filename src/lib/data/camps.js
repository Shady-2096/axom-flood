function normalized(value) {
  return String(value ?? "")
    .normalize("NFKC")
    .toLocaleLowerCase("en-IN")
    .replace(/\s*\(pt\)\s*$/i, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

export function normalizeCircleName(value) {
  return normalized(value);
}

function campIdentity(camp) {
  const coordinates = Array.isArray(camp.coordinates)
    ? camp.coordinates.map(value => Number(value).toFixed(5)).join(",")
    : "";
  return [
    normalized(camp.district),
    normalized(camp.revenue_circle),
    normalized(camp.name_normalized || camp.name_raw),
    normalized(camp.village),
    coordinates,
  ].join("|");
}

export function campsForLocality(camps, locality) {
  if (!locality) return [];
  const district = normalized(locality.district);
  const circle = normalizeCircleName(locality.revenue_circle);
  const unique = new Map();

  for (const camp of camps || []) {
    if (normalized(camp.district) !== district) continue;
    if (camp.revenue_circle && normalizeCircleName(camp.revenue_circle) !== circle) continue;
    const identity = campIdentity(camp);
    if (!unique.has(identity)) unique.set(identity, camp);
  }
  return [...unique.values()];
}

/* How long a saved camp list may go without being called old.
   Matched to the ASDMA report window, and for the same reason the page already
   states out loud: camp lists change quickly. */
export const CAMPS_STALE_AFTER_DAYS = 3;

/* How old the saved camp listings are.
   Deliberately its own answer rather than the gauge's. The camps screen had no
   date of its own and rendered the river gauge's reading age, so a list read
   from district documents saved eighteen days earlier was headed "3.2 hours
   old". True about the gauge, false about every camp under it, and this is the
   one screen somebody might act on by travelling.
   `saved`, never `published` or `updated`: this is when the notifications were
   fetched, not when a district issued them. Most are PDFs carrying no date we
   can parse, and inventing a publication time would be the same mistake again. */
export function campsSavedLabel(savedAt, now = new Date()) {
  const stamp = Date.parse(savedAt ?? "");
  if (Number.isNaN(stamp)) return null;
  const days = Math.floor((now.getTime() - stamp) / 86_400_000);
  const on = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "numeric",
    month: "short",
  }).format(stamp);
  if (days < 1) return { text: `Saved today`, stale: false };
  if (days === 1) return { text: `Saved yesterday, ${on}`, stale: false };
  return {
    text: `Saved ${on}, ${days} days ago`,
    stale: days > CAMPS_STALE_AFTER_DAYS,
  };
}

export function campPhoneNumbers(value) {
  const seen = new Set();
  const phones = [];
  for (const part of String(value ?? "").split(/\s*\/\s*|\s*,\s*(?=\+?\d)/)) {
    const display = part.trim().replace(/\s+/g, " ");
    const dial = display.replace(/[^\d+]/g, "");
    const digits = dial.replace(/\D/g, "");
    if (digits.length < 4 || seen.has(dial)) continue;
    seen.add(dial);
    phones.push({ display, dial });
  }
  return phones;
}
