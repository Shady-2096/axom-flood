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
