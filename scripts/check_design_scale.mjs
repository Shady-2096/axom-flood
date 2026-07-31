// Fail when a stylesheet drifts off the type ramp or spacing rhythm in
// DESIGN.md. The previous build carried 38 distinct spacing values with only
// 17% of occurrences on the declared scale, which is the most literal
// fingerprint of a hand-nudged interface. A token would not have prevented it;
// nothing stops anyone writing a literal. This does.

import { readFileSync } from "node:fs";
import { globSync } from "node:fs";

const TYPE_RAMP = new Set([11, 12, 14, 15, 16, 18, 20, 24, 28]);
const SPACE_RAMP = new Set([0, 4, 6, 8, 12, 16, 20, 24, 32, 40, 56, 72]);
const SPACE_PROPERTY = /\b(margin|padding|gap|row-gap|column-gap)(-top|-right|-bottom|-left|-block|-inline)?\s*:\s*([^;{}]+)/g;
const FONT_SIZE = /\bfont-size\s*:\s*(\d+(?:\.\d+)?)px/g;
const FONT_SHORTHAND = /\bfont\s*:\s*[^;{}]*?(\d+(?:\.\d+)?)px\s*\//g;

const files = globSync("{static/*.css,src/**/*.svelte}");
const problems = [];

for (const file of files) {
  const source = readFileSync(file, "utf8");
  const lineOf = index => source.slice(0, index).split("\n").length;

  for (const match of source.matchAll(FONT_SIZE)) {
    const size = Number(match[1]);
    if (!TYPE_RAMP.has(size)) problems.push(`${file}:${lineOf(match.index)} font-size ${size}px is off the type ramp`);
  }
  for (const match of source.matchAll(FONT_SHORTHAND)) {
    const size = Number(match[1]);
    if (!TYPE_RAMP.has(size)) problems.push(`${file}:${lineOf(match.index)} font shorthand ${size}px is off the type ramp`);
  }
  for (const match of source.matchAll(SPACE_PROPERTY)) {
    // Fluid values are deliberate responsive endpoints, not rhythm steps.
    if (match[3].includes("clamp(")) continue;
    for (const value of match[3].matchAll(/(-?\d+(?:\.\d+)?)px/g)) {
      const step = Math.abs(Number(value[1]));
      if (!SPACE_RAMP.has(step)) {
        problems.push(`${file}:${lineOf(match.index)} ${match[1]} step ${step}px is off the spacing rhythm`);
      }
    }
  }
}

if (problems.length) {
  console.error(`${problems.length} value(s) off the DESIGN.md scale:`);
  for (const problem of problems) console.error(`  ${problem}`);
  process.exit(1);
}
console.log(`Design scale: ${files.length} files on ramp`);
