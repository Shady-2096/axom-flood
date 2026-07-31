"use strict";

function datePartsInTimeZone(moment, timeZone) {
  const parts = new Intl.DateTimeFormat("en", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(moment);
  return Object.fromEntries(parts.map(part => [part.type, part.value]));
}

function previousDateInTimeZone(moment, timeZone) {
  const { year, month, day } = datePartsInTimeZone(moment, timeZone);
  const previous = new Date(Date.UTC(
    Number(year),
    Number(month) - 1,
    Number(day) - 1,
  ));
  return [
    previous.getUTCFullYear(),
    String(previous.getUTCMonth() + 1).padStart(2, "0"),
    String(previous.getUTCDate()).padStart(2, "0"),
  ].join("-");
}

module.exports = { previousDateInTimeZone };
