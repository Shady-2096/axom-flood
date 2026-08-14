/**
 * Whether the flood bulletin's words survive losing their card.
 *
 * The bulletin's foreground travels with the safety state, not with the page:
 * dark ink on the amber field, white on the two reds. That only works while the
 * field is under it. `.bulletin.standalone` -- the data-saver layout, where the
 * place name is already set above the panel -- used to drop the field to
 * transparent for every state while leaving that ink in place.
 *
 * Measured in the running app at 375x812:
 *
 *   dark  / warning   1.02:1
 *   light / danger    1.23:1
 *   light / extreme   1.23:1
 *
 * Not "low contrast". Invisible -- in the mode built for a reader on a bad
 * connection during a flood, on the screen that is nothing but this panel.
 * Every calm state measured 12:1 or better, which is why it went unnoticed:
 * the states that broke are the three nobody sees on an ordinary day.
 *
 * So this is not a source-text check. It reads the real token values out of
 * styles.css and the real per-state foreground out of the component, and does
 * the arithmetic. A future edit that retints a ground or a safety ink has to
 * come past it.
 */

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const WCAG_BODY_TEXT = 4.5;

const sheet = await readFile(new URL("../static/styles.css", import.meta.url), "utf8");
const bulletin = await readFile(
  new URL("../src/lib/components/FloodBulletin.svelte", import.meta.url),
  "utf8",
);

/** The declarations inside one top-level rule, by its selector. */
function block(css, selector) {
  const opened = css.indexOf(`${selector} {`);
  assert.ok(opened >= 0, `no rule for ${selector}`);
  const closed = css.indexOf("\n}", opened);
  return css.slice(opened, closed);
}

function tokens(selector) {
  const found = {};
  for (const [, name, value] of block(sheet, selector).matchAll(/(--[\w-]+):\s*([^;]+);/g)) {
    found[name] = value.trim();
  }
  return found;
}

const dark = tokens(":root");
// Daylight only redefines what it changes, so it inherits the rest from night.
const light = { ...dark, ...tokens(':root[data-theme="light"]') };

function channels(hex) {
  const raw = hex.replace("#", "");
  const full = raw.length === 3 ? [...raw].map(c => c + c).join("") : raw;
  assert.equal(full.length, 6, `not a colour: ${hex}`);
  return [0, 2, 4].map(at => parseInt(full.slice(at, at + 2), 16) / 255);
}

function luminance(hex) {
  const [r, g, b] = channels(hex).map(v => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a, b) {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
}

/** The `--on-field` a given `data-state` resolves to, read from the component. */
function foregroundToken(state) {
  // `normal` has no state block of its own -- it is the base .bulletin rule.
  const rule = state === "normal" ? ".bulletin" : `.bulletin[data-state="${state}"]`;
  const declared = block(bulletin, rule).match(/--on-field:\s*var\((--[\w-]+)\)/);
  assert.ok(declared, `no --on-field under ${rule}`);
  return declared[1];
}

const STATES = ["normal", "no-data", "warning", "danger", "extreme"];

/** The states `standalone` strips the card from, read from the component. */
const bodiless = new Set(
  [...bulletin.matchAll(/\.bulletin\.standalone\[data-state="([\w-]+)"\]/g)].map(m => m[1]),
);

test("a bodiless bulletin is only ever a calm one", () => {
  // Not a style preference. Losing the field means the page ground shows
  // through, and the raised states are exactly the ones whose ink was chosen
  // for a field rather than for the page.
  assert.deepEqual([...bodiless].sort(), ["no-data", "normal"]);
});

test("every state the card is stripped from stays readable on both grounds", () => {
  for (const state of bodiless) {
    const ink = foregroundToken(state);
    for (const [scheme, palette] of [["night", dark], ["paper", light]]) {
      const ratio = contrast(palette[ink], palette["--ground"]);
      assert.ok(
        ratio >= WCAG_BODY_TEXT,
        `${state} on ${scheme}: ${ink} is ${ratio.toFixed(2)}:1 on --ground, needs ${WCAG_BODY_TEXT}`,
      );
    }
  }
});

test("the raised states would be unreadable without their field", () => {
  // The other half of the first test. It is not that warning, danger and
  // extreme merely look better on a card -- it is that on the page they are
  // gone. If a future palette ever makes one of them safe on the ground, this
  // fails and someone re-reads the rule instead of inheriting it.
  for (const state of STATES.filter(s => !bodiless.has(s))) {
    const ink = foregroundToken(state);
    const worst = Math.min(
      contrast(dark[ink], dark["--ground"]),
      contrast(light[ink], light["--ground"]),
    );
    assert.ok(worst < WCAG_BODY_TEXT, `${state} no longer needs its field (${worst.toFixed(2)}:1)`);
  }
});

test("every state's ink is readable on the field it was chosen for", () => {
  // The card-on state, which is the common one and was never broken. Here so a
  // fix to the page case cannot be made by retinting a safety ink and quietly
  // wrecking the card.
  for (const state of STATES) {
    const rule = state === "normal" ? ".bulletin" : `.bulletin[data-state="${state}"]`;
    const ink = foregroundToken(state);
    const field = block(bulletin, rule).match(/--field:\s*var\((--[\w-]+)\)/)[1];
    for (const [scheme, palette] of [["night", dark], ["paper", light]]) {
      const ratio = contrast(palette[ink], palette[field]);
      assert.ok(
        ratio >= WCAG_BODY_TEXT,
        `${state} on ${scheme}: ${ink} is ${ratio.toFixed(2)}:1 on ${field}`,
      );
    }
  }
});

test("a card that keeps its field keeps the inset that goes with it", () => {
  // The padding rule is scoped the same way the bodiless rule is. Left
  // unscoped, `padding: 24px 0` put the amber hard against the type.
  const padding = bulletin.match(
    /\.standalone\[data-state="normal"\] \.face,\s*\.standalone\[data-state="no-data"\] \.face \{\s*padding: 24px 0;/,
  );
  assert.ok(padding, "the bodiless padding must be scoped to the bodiless states");
});
