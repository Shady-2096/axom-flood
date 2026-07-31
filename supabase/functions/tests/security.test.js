import assert from "node:assert/strict";
import test from "node:test";
import { webcrypto } from "node:crypto";

if (!globalThis.crypto) globalThis.crypto = webcrypto;

import {
  boundedBody,
  hmacHex,
  identityPeriod,
  sha256Hex,
  verifyHmacSha256,
} from "../_shared/security.js";

const SECRET = "test-only-secret-at-least-thirty-two-characters";

test("keyed subject hash is stable and does not contain the identifier", async () => {
  const first = await hmacHex(SECRET, "telegram:test-subject");
  const second = await hmacHex(SECRET, "telegram:test-subject");
  assert.equal(first, second);
  assert.match(first, /^[0-9a-f]{64}$/);
  assert.doesNotMatch(first, /test-subject/);
});

test("request hash is deterministic", async () => {
  assert.equal(await sha256Hex("{}"), await sha256Hex("{}"));
});

test("Meta-style HMAC verification accepts exact body and rejects tampering", async () => {
  const body = '{"object":"whatsapp_business_account"}';
  const signature = `sha256=${await hmacHex(SECRET, body)}`;
  assert.equal(await verifyHmacSha256(SECRET, body, signature), true);
  assert.equal(await verifyHmacSha256(SECRET, `${body} `, signature), false);
});

test("body limit rejects oversized input before parsing", () => {
  assert.equal(boundedBody("ok"), "ok");
  assert.throws(() => boundedBody("x".repeat(16 * 1024 + 1)), /exceeds/);
});

test("identity period rotates monthly", () => {
  assert.equal(identityPeriod(new Date("2026-07-31T23:59:00Z")), "2026-07-01");
  assert.equal(identityPeriod(new Date("2026-08-01T00:00:00Z")), "2026-08-01");
});
