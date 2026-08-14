/**
 * Whether anything printed on the chrome slab can be read in both schemes.
 *
 * `--chrome` is the sheet's margin -- the rail, the header, the mobile mast.
 * The token block in styles.css already says why it exists: "It is a structural
 * role, not a text colour. The previous system used one --ink token for both,
 * which works only while the page is light."
 *
 * That note was written when daylight arrived, and it was right, but the sweep
 * that followed it covered the header and the footer and stopped there.
 * Everything added afterwards went on reaching for a page token, and a page
 * token flips with the scheme while chrome deliberately does not:
 *
 *   .skip-link                --ink on --chrome, daylight    1.24:1
 *   .kill                     --ink on --chrome, daylight    1.24:1
 *   .header-tools .mode-toggle  --rail-text, daylight        1.83:1
 *
 * The skip link is the first control a keyboard reader meets on every page.
 * The kill screen is what replaces the river reading when it is paused. Both
 * were invisible on paper, and the skip link doubly so, since it is only drawn
 * once someone tabs into it.
 *
 * So this test does not check the three. It checks the rule: find every block
 * that paints itself `--chrome` and read what it puts on top.
 */

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const WCAG_BODY_TEXT = 4.5;

const sheet = await readFile(new URL("../static/styles.css", import.meta.url), "utf8");

function block(css, selector) {
  const opened = css.indexOf(`${selector} {`);
  assert.ok(opened >= 0, `no rule for ${selector}`);
  return css.slice(opened, css.indexOf("\n}", opened));
}

function tokens(selector) {
  const found = {};
  for (const [, name, value] of block(sheet, selector).matchAll(/(--[\w-]+):\s*([^;]+);/g)) {
    found[name] = value.trim();
  }
  return found;
}

const dark = tokens(":root");
const light = { ...dark, ...tokens(':root[data-theme="light"]') };

/** Follow `var(--a)` chains -- `--white: var(--surface)` and the like. */
function resolve(palette, token, depth = 0) {
  const value = palette[token];
  assert.ok(value, `undefined token ${token}`);
  assert.ok(depth < 8, `circular token ${token}`);
  const indirect = value.match(/^var\((--[\w-]+)\)$/);
  return indirect ? resolve(palette, indirect[1], depth + 1) : value;
}

function luminance(hex) {
  const raw = hex.replace("#", "");
  const full = raw.length === 3 ? [...raw].map(c => c + c).join("") : raw;
  assert.equal(full.length, 6, `not a plain colour: ${hex}`);
  const [r, g, b] = [0, 2, 4]
    .map(at => parseInt(full.slice(at, at + 2), 16) / 255)
    .map(v => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a, b) {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
}

const SCHEMES = [["night", dark], ["paper", light]];

test("chrome has a foreground of its own, in both schemes", () => {
  for (const [scheme, palette] of SCHEMES) {
    for (const token of ["--on-chrome", "--on-chrome-quiet"]) {
      const ratio = contrast(resolve(palette, token), resolve(palette, "--chrome"));
      assert.ok(
        ratio >= WCAG_BODY_TEXT,
        `${token} on ${scheme}: ${ratio.toFixed(2)}:1 on --chrome`,
      );
    }
  }
});

test("the page's own ink is exactly what chrome cannot use", () => {
  // The reason the pair exists. If --ink ever clears 4.5:1 on chrome in both
  // schemes then chrome has stopped being a separate surface, and the rules
  // below should be re-read rather than left running on an assumption.
  const worst = Math.min(
    ...SCHEMES.map(([, p]) => contrast(resolve(p, "--ink"), resolve(p, "--chrome"))),
  );
  assert.ok(worst < WCAG_BODY_TEXT, `--ink now clears chrome at ${worst.toFixed(2)}:1`);
});

/**
 * Every top-level rule that paints itself `--chrome`, with whatever `color`
 * token it sets. Selectors are read back so a failure names the thing on screen.
 */
function chromeBackedRules() {
  const rules = [];
  // Selector(s), then the declaration body up to the closing brace.
  for (const match of sheet.matchAll(/(^|\n)([^{}@\n][^{}]*?)\{([^{}]*?)\}/g)) {
    const [, , selector, body] = match;
    if (!/background:\s*var\(--chrome\)/.test(body)) continue;
    const colour = body.match(/(?:^|[;{\s])color:\s*var\((--[\w-]+)\)/);
    rules.push({ selector: selector.trim().replace(/\s+/g, " "), token: colour?.[1] ?? null });
  }
  return rules;
}

test("something in the sheet actually paints itself chrome", () => {
  // Guards the regex above. A parser that silently matches nothing would let
  // every assertion below pass while checking not one rule.
  const rules = chromeBackedRules();
  assert.ok(rules.length >= 4, `only found ${rules.length} chrome-backed rules`);
  assert.ok(rules.some(r => r.selector.includes(".skip-link")), "the skip link should be one");
});

test("nothing on the chrome slab reaches for a token that flips away from it", () => {
  const failures = [];
  for (const { selector, token } of chromeBackedRules()) {
    // A rule that sets no colour of its own inherits, and what it inherits is
    // the concern of whichever rule did set one.
    if (!token) continue;
    for (const [scheme, palette] of SCHEMES) {
      const ratio = contrast(resolve(palette, token), resolve(palette, "--chrome"));
      if (ratio < WCAG_BODY_TEXT) {
        failures.push(`${selector} — ${token} is ${ratio.toFixed(2)}:1 on ${scheme}`);
      }
    }
  }
  assert.deepEqual(failures, []);
});

test("the header's daylight block names tokens rather than repeating hexes", () => {
  // How the display-mode toggle came to be missed: the daylight block is a list
  // of controls, and a control had to be remembered into it. A token is
  // correct in both schemes without being listed anywhere.
  const daylightHeader = sheet.slice(
    sheet.indexOf(':root[data-theme="light"] .site-header'),
    sheet.indexOf(':root[data-theme="light"] .site-footer'),
  );
  assert.ok(daylightHeader.length > 0, "the daylight header block moved");
  assert.match(daylightHeader, /\.mode-toggle[\s\S]*?color: var\(--on-chrome-quiet\)/);
  assert.match(daylightHeader, /\.mode-toggle:hover[\s\S]*?color: var\(--on-chrome\)/);
});
