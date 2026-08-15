import { cacheFirst } from "$lib/data/cache.js";
import { crowdUrl, getBundle } from "$lib/data/index.js";
import { store } from "$lib/data/preferences.js";
import { syncReportConversation } from "./conversation.js";
import { isAbandonedSync, isHeldOnDevice, retryPauseMs } from "./records.js";

export { isHeldOnDevice };

let dbPromise = null;

/* The record ids this page is sending right now. `syncing` in the database means
   "in flight" only while the page that wrote it is alive, so this is what tells a
   live send apart from one abandoned by a closed tab. See `isAbandonedSync`. */
const inFlight = new Set();

/* When the endpoint will next accept anything from this device. Rate limiting is
   per device rather than per report, so one refusal pauses the whole outbox.
   Elapsed time within this page, never a stored deadline — see `retryPauseMs`. */
let pausedUntil = 0;

function paused() {
  return pausedUntil > Date.now();
}

function outbox() {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open("axom-crowd", 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains("outbox")) {
        db.createObjectStore("outbox", { keyPath: "record_id" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return dbPromise;
}

export async function dbAdd(record) {
  const db = await outbox();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("outbox", "readwrite");
    tx.objectStore("outbox").put(record);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function dbAll() {
  const db = await outbox();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("outbox", "readonly");
    const req = tx.objectStore("outbox").getAll();
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => reject(req.error);
  });
}

async function dbUpdate(record) {
  const db = await outbox();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("outbox", "readwrite");
    tx.objectStore("outbox").put(record);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function dbRemove(recordId) {
  const db = await outbox();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("outbox", "readwrite");
    tx.objectStore("outbox").delete(recordId);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export function deviceToken() {
  let token = localStorage.getItem("axom-device-token");
  if (!token) {
    token = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now())) + Math.random().toString(36).slice(2);
    localStorage.setItem("axom-device-token", token);
  }
  return token;
}

export function roundCoordinate(lat, lon) {
  // Mirrors src/axom_flood/crowd/privacy.py: 3 decimals of a degree, which is
  // ~100 m at Assam latitudes and never finer than the 50 m policy floor.
  return [Math.round(lon * 1000) / 1000, Math.round(lat * 1000) / 1000];
}

const PII_PHONE = /\+?\d{7,15}|\b[6-9]\d{9}\b/;
const PII_EMAIL = /[^\s@]+@[^\s@]+\.[^\s@]+/;

export function looksLikePii(text) {
  return PII_EMAIL.test(text) || PII_PHONE.test(text);
}

export function getReportPosition() {
  return new Promise((resolve) => {
    if (!("geolocation" in navigator)) return resolve(null);
    navigator.geolocation.getCurrentPosition(
      position => resolve(position),
      () => resolve(null),
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 },
    );
  });
}

async function syncOne(record) {
  const bundle = getBundle();
  const url = bundle?.runtime?.crowd_submission_url;
  if (!url) return { status: "queued", reason: "sync_unconfigured" };
  const updated = { ...record, status: "syncing", attempts: (record.attempts || 0) + 1 };
  inFlight.add(updated.record_id);
  await dbUpdate(updated);
  try {
    // The record is stored flat because that is what the report screen and
    // IndexedDB want. The intake endpoint speaks the shared conversation flow
    // instead, so the replay happens here rather than in either of them.
    const outcome = await syncReportConversation(updated, url);
    if (outcome.status === "synced") {
      await dbRemove(updated.record_id);
      return outcome;
    }
    await dbUpdate({
      ...updated,
      status: "queued",
      last_error: outcome.code ? `HTTP ${outcome.code}` : outcome.reason,
    });
    return outcome;
  } catch (error) {
    await dbUpdate({ ...updated, status: "queued", last_error: String(error?.message || error) });
    return { status: "queued", reason: "network" };
  } finally {
    inFlight.delete(updated.record_id);
  }
}

// Whether a queued report has anywhere to go. Reports are queued locally first
// either way, but the screen must not promise a sync that cannot happen: the
// difference between "it will send when you are back online" and "it is on this
// phone and nowhere else" is the whole difference to the person who wrote it.
export function canSync() {
  return Boolean(getBundle()?.runtime?.crowd_submission_url);
}

export async function flushOutbox() {
  const records = await dbAll();
  let queued = 0;
  let synced = 0;
  let held = 0;
  let reclaimed = 0;
  if (paused()) {
    // Nothing leaves during the pause, but the reports are still counted: they
    // are waiting, which is what the screen has to be able to say.
    return {
      queued: records.filter(item => !isHeldOnDevice(item)).length,
      synced: 0,
      held: records.filter(isHeldOnDevice).length,
      reclaimed: 0,
      rateLimited: true,
    };
  }
  for (const record of records) {
    // A leftover `syncing` flag from a page that went away goes back in the
    // queue and is sent in this pass. Only a send this page is running is
    // skipped, and a skipped one is still counted, so the number on screen
    // matches the number of reports actually waiting.
    let candidate = record;
    if (isAbandonedSync(record, inFlight)) {
      candidate = { ...record, status: "queued" };
      await dbUpdate(candidate);
      reclaimed += 1;
    } else if (record.status === "syncing") {
      queued += 1;
      continue;
    }
    if (isHeldOnDevice(candidate)) {
      held += 1;
      continue;
    }
    const outcome = await syncOne(candidate);
    if (outcome.status === "synced") synced += 1;
    else queued += 1;
    const pause = retryPauseMs(outcome);
    if (pause) {
      // The refusal is about this device, not this record, so there is nothing
      // to gain from trying the rest of the queue against the same wall.
      pausedUntil = Date.now() + pause;
      queued += records.length - records.indexOf(record) - 1;
      return { queued, synced, held, reclaimed, rateLimited: true };
    }
  }
  return { queued, synced, held, reclaimed, rateLimited: false };
}

export function uuid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return "rid-" + Date.now() + "-" + Math.random().toString(36).slice(2);
}

export async function queueCrowdReport({ depth, lat, lon }) {
  const rounded = roundCoordinate(lat, lon);
  const record = {
    record_id: uuid(),
    record_type: "crowd",
    latitude: rounded[1],
    longitude: rounded[0],
    location_precision_m: 50,
    depth_class: depth,
    locality_id: store.locality,
    submitted_at: new Date().toISOString(),
    device_token: deviceToken(),
    source: "app",
    status: "queued",
    attempts: 0,
  };
  // Queue locally first so submission completes in well under 3 s even when
  // the network is unusable; the network sync runs in the background below.
  await dbAdd(record);
  flushOutbox();
}

export async function loadAggregate() {
  const url = crowdUrl();
  if (!url) return null;
  try {
    return await cacheFirst(url);
  } catch (_) {
    return null;
  }
}
