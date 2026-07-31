import { writable } from "svelte/store";
import { normalizeRenderMode, resolveRenderMode } from "$lib/mode.js";

export const preferencesChanged = writable(0);

/* The mode actually running, as opposed to the preference behind it: "auto"
   resolves to one of these two against the connection. The header carries a
   switch for it and the home screen loads the chunks for it, so it cannot live
   inside either one of them. */
export const activeRenderMode = writable("full");

export const store = {
  get locality() { return localStorage.getItem("locality"); },
  set locality(value) { localStorage.setItem("locality", value); },
  get language() { return localStorage.getItem("language") || "as"; },
  set language(value) { localStorage.setItem("language", value); },
  get selection() {
    try { return JSON.parse(localStorage.getItem("location-selection")) || null; }
    catch (_) { return null; }
  },
  set selection(value) { localStorage.setItem("location-selection", JSON.stringify(value)); },
  get recents() {
    try { return JSON.parse(localStorage.getItem("recent-localities")) || []; }
    catch (_) { return []; }
  },
  set recents(value) { localStorage.setItem("recent-localities", JSON.stringify(value)); },
  get renderMode() {
    return normalizeRenderMode(localStorage.getItem("render-mode"));
  },
  set renderMode(value) {
    localStorage.setItem("render-mode", normalizeRenderMode(value));
  },
  // Whether the browser location prompt has already been offered once. A reader
  // who dismissed or refused it must not meet it again on every visit.
  get locationAsked() {
    return localStorage.getItem("location-asked") === "true";
  },
  set locationAsked(value) {
    localStorage.setItem("location-asked", String(Boolean(value)));
  },
  get fullModePromptDismissed() {
    return localStorage.getItem("full-mode-prompt-dismissed") === "true";
  },
  set fullModePromptDismissed(value) {
    localStorage.setItem("full-mode-prompt-dismissed", String(Boolean(value)));
  },
  get theme() {
    const value = localStorage.getItem("theme");
    return value === "light" || value === "dark" ? value : null;
  },
  set theme(value) {
    if (value === "light" || value === "dark") localStorage.setItem("theme", value);
  },
};

function announceChange() {
  preferencesChanged.update(value => value + 1);
}

export function rememberLocality(localityId) {
  store.recents = [localityId, ...store.recents.filter(id => id !== localityId)].slice(0, 4);
}

export function selectLocality(localityId, selection) {
  store.locality = localityId;
  store.selection = selection;
  rememberLocality(localityId);
  announceChange();
}

export function selectLanguage(language) {
  store.language = language;
  announceChange();
}

export function selectRenderMode(mode) {
  store.renderMode = mode;
  activeRenderMode.set(resolveRenderMode(mode, navigator.connection));
  announceChange();
}

export function selectTheme(theme) {
  store.theme = theme;
  announceChange();
}

export function dismissFullModePrompt() {
  store.fullModePromptDismissed = true;
  announceChange();
}
