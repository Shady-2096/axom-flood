const encoder = new TextEncoder();

function bytesToHex(bytes) {
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
}

function hexToBytes(hex) {
  if (!/^[0-9a-f]+$/i.test(hex) || hex.length % 2 !== 0) return null;
  return Uint8Array.from(hex.match(/.{2}/g).map((pair) => Number.parseInt(pair, 16)));
}

export async function sha256Hex(value) {
  const digest = await crypto.subtle.digest("SHA-256", encoder.encode(String(value)));
  return bytesToHex(new Uint8Array(digest));
}

export async function hmacHex(secret, value) {
  if (typeof secret !== "string" || secret.length < 32) {
    throw new Error("HMAC secret must be at least 32 characters");
  }
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, encoder.encode(String(value)));
  return bytesToHex(new Uint8Array(signature));
}

export async function verifyHmacSha256(secret, body, signatureHeader) {
  const match = /^sha256=([0-9a-f]{64})$/i.exec(signatureHeader || "");
  if (!match || typeof secret !== "string" || secret.length < 32) return false;
  const supplied = hexToBytes(match[1]);
  const expectedHex = await hmacHex(secret, body);
  const expected = hexToBytes(expectedHex);
  if (!supplied || supplied.length !== expected.length) return false;
  let difference = 0;
  for (let index = 0; index < supplied.length; index += 1) {
    difference |= supplied[index] ^ expected[index];
  }
  return difference === 0;
}

export function identityPeriod(at = new Date()) {
  return `${at.getUTCFullYear()}-${String(at.getUTCMonth() + 1).padStart(2, "0")}-01`;
}

export function boundedBody(text, maxBytes = 16 * 1024) {
  if (encoder.encode(text).byteLength > maxBytes) {
    throw new Error("request body exceeds 16 KiB");
  }
  return text;
}
