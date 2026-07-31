import assert from "node:assert/strict";
import test from "node:test";

import {
  geolocationErrorMessage,
  getPosition,
} from "../src/lib/data/geolocation.js";

function replaceNavigator(value) {
  const original = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value,
  });
  return () => {
    if (original) Object.defineProperty(globalThis, "navigator", original);
    else delete globalThis.navigator;
  };
}

test("a quick location timeout retries once with a precise request", async t => {
  const calls = [];
  const expected = { coords: { latitude: 26.1, longitude: 91.7 } };
  const restore = replaceNavigator({
    geolocation: {
      getCurrentPosition(resolve, reject, options) {
        calls.push(options);
        if (calls.length === 1) reject({ code: 3 });
        else resolve(expected);
      },
    },
  });
  t.after(restore);

  assert.equal(await getPosition(), expected);
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[0], {
    enableHighAccuracy: false,
    timeout: 3000,
    maximumAge: 900000,
  });
  assert.deepEqual(calls[1], {
    enableHighAccuracy: true,
    timeout: 12000,
    maximumAge: 0,
  });
});

test("permission refusal does not retry or raise another prompt", async t => {
  let calls = 0;
  const restore = replaceNavigator({
    geolocation: {
      getCurrentPosition(_resolve, reject) {
        calls += 1;
        reject({ code: 1 });
      },
    },
  });
  t.after(restore);

  await assert.rejects(getPosition(), error => error.code === 1);
  assert.equal(calls, 1);
});

test("the final timeout message explains the device setting and manual fallback", () => {
  assert.match(geolocationErrorMessage({ code: 3 }), /Location is on/);
  assert.match(geolocationErrorMessage({ code: 3 }), /enter your place/);
});
