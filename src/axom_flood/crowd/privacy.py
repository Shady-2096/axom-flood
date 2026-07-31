"""Privacy primitives for crowd reports.

Two guarantees this module exists to make enforceable:

1. Coordinates round to a deliberately coarse grid before they are stored or
   transmitted &mdash; full-precision home locations of flood victims are a
   liability we never hold. Reports are published openly as a public good;
   a precise coordinate plus a timestamp would be a public map of which
   specific houses are flooded and empty.

2. ``device_hash`` is a salted, monthly-rotating, anonymous hash used only
   for duplicate detection. The raw device token is never persisted, the
   salt rotates monthly, and the published hash cannot be reversed to a
   device or linked across monthly rotations.

The grid stores coordinates to three decimal places of a degree, matching
``assam-flood-implementation-plan.md`` PART 3 §3.5 example
(``"location": [94.681, 26.912]``). At every latitude in India that is at
least as coarse as the 50 m policy floor declared by ``location_precision_m``
in every published report &mdash; at 26.6 N (mid-Assam) three decimals is
~111 m of latitude and ~99 m of longitude, both above 50 m.
``location_precision_m`` declares the deliberate lower bound; the achieved
resolution is coarser and never finer.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

#: The public policy floor. ``location_precision_m`` in every published
#: report is this value. The actual stored grid is coarser; it is never finer.
MIN_PRECISION_M = 50

#: Number of decimal places of a degree that are stored. Matches the plan.
COORD_DECIMALS = 3

_MONTH_SALT_BYTES = 32

# ---------------------------------------------------------------------------
# Coordinate rounding
# ---------------------------------------------------------------------------

_METRES_PER_DEGREE = 111_320.0


def resolution_metres(latitude: float, *, decimals: int = COORD_DECIMALS) -> tuple[float, float]:
    """Ground resolution in metres of one unit in the last stored decimal place."""
    step_deg = 10 ** -decimals
    return (
        step_deg * _METRES_PER_DEGREE,
        step_deg * _METRES_PER_DEGREE * max(math.cos(math.radians(latitude)), 1e-6),
    )


def round_coordinate(latitude: float, longitude: float) -> tuple[float, float]:
    """Round a full-precision GPS reading to the coarse published grid.

    The grid is fixed at three decimal degrees. Across the entire country
    that is at least ~88 m of ground resolution: never finer than the 50 m
    policy floor, and the same shape the plan's example record shows.

    Raises ``ValueError`` outside the populated latitude band so a malformed
    submission cannot quietly pass.
    """
    if not -90.0 < latitude < 90.0 or not -180.0 < longitude < 180.0:
        raise ValueError(f"coordinate out of range: ({latitude!r}, {longitude!r})")
    lat_resolution, lon_resolution = resolution_metres(latitude)
    if lat_resolution < MIN_PRECISION_M or lon_resolution < MIN_PRECISION_M:
        # Defence in depth: the grid is fixed, so this is unreachable on Earth.
        raise ValueError(
            f"stored grid would be finer than the {MIN_PRECISION_M} m policy floor "
            f"at latitude {latitude}"
        )
    return round(latitude, COORD_DECIMALS), round(longitude, COORD_DECIMALS)


# ---------------------------------------------------------------------------
# device_hash
# ---------------------------------------------------------------------------


def month_string(at: datetime | None = None) -> str:
    """The rotating period for the device-hash salt, e.g. ``"2026-07"``."""
    moment = at or datetime.now(IST)
    return f"{moment.year:04d}-{moment.month:02d}"


def device_hash(device_token: str, salt: bytes, month: str) -> str:
    """Salted, monthly-rotating, anonymous hash for duplicate detection only.

    Properties, all deliberate:

    * The raw ``device_token`` is consumed here and never persisted anywhere
      by callers in this package. Only the returned hash is published.
    * The salt is operator-controlled and rotates monthly. The month string
      is mixed into the hash too, so even if a salt were reused the hash
      for the same device still changes between months.
    * SHA-256 is not reversible, and the salted input has no structure a
      third party could brute-force without the salt, the token, and the
      month &mdash; none of which the public dataset exposes.

    A reviewer of the published hashes cannot link the same device across
    months because both the salt and the month change.
    """
    if not isinstance(device_token, str) or not device_token:
        raise ValueError("device_token must be a non-empty string")
    if not isinstance(salt, (bytes, bytearray)) or len(salt) < 16:
        raise ValueError("salt must be at least 16 bytes of operator-controlled entropy")
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise ValueError(f"month must be YYYY-MM, got {month!r}")
    digest = hashlib.sha256()
    digest.update(bytes(salt))
    digest.update(b"\x00")
    digest.update(device_token.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(month.encode("ascii"))
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# PII scanning
# ---------------------------------------------------------------------------

#: Field names that are categorically PII and must never appear in a record.
_PII_KEYS = {
    "name",
    "full_name",
    "first_name",
    "last_name",
    "phone",
    "phone_number",
    "mobile",
    "email",
    "email_address",
    "imei",
    "imsi",
    "device_token",
    "device_id",
    "device_imei",
    "user_id",
    "username",
    "account",
    "password",
    "token",
    "secret",
    "aadhaar",
    "aadhar",
    "pan",
    "voter_id",
    "address",
    "street_address",
    "house",
    "house_number",
    "ip",
    "ip_address",
}

_PHONE = re.compile(r"(?:\+?91[\s-]?)?(?<!\d)[6-9]\d{9}(?!\d)")
_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")


class PrivacyError(ValueError):
    """Raised when a stored or published record would carry PII."""


#: Keys exempt from phone/email pattern scanning, because their values are
#: machine-generated identifiers rather than reporter input. A SHA-256 hash
#: routinely contains ten consecutive decimal digits and would otherwise
#: false-trip the phone pattern.
#:
#: This is deliberately a denylist, not an allowlist of free-text fields. An
#: allowlist silently stops scanning any field added to the schema later, which
#: is the wrong failure direction for a privacy guard: a new ``landmark`` or
#: ``description`` field would carry reporter text and go unchecked. Exempting a
#: field is a decision someone has to make explicitly, here.
_UNSCANNED_KEYS = {
    "reportid",
    "devicehash",
    "sourcerevision",
    "sourcesha256",
    "artifactid",
    "schemaversion",
    "localityid",
    "gaugeid",
    "revisionid",
}


def assert_no_pii(payload: Any, *, banned_values: set[Any] | None = None) -> None:
    """Walk a payload and raise ``PrivacyError`` on any PII it finds.

    A value is rejected if:

    * any dict key (case-insensitive, after ``_``/``-`` normalisation) names
      a PII field &mdash; this catches accidental schema spillover even when
      the value is empty;
    * any free-text leaf matches a phone-number or email-shaped pattern;
    * any leaf numeric or string value is in ``banned_values`` &mdash; used
      to prove the original full-precision coordinate never survives into
      the stored record.

    Phone and email patterns are applied to every string leaf except the
    machine-generated identifiers in ``_UNSCANNED_KEYS``, so a field added to the
    schema later is scanned by default rather than exempt by default.
    """
    banned_values = banned_values or set()

    def walk(node: Any, key: str | None) -> None:
        if isinstance(node, dict):
            for child_key, value in node.items():
                normalised = re.sub(r"[-_]", "", str(child_key).casefold())
                if normalised in _PII_KEYS:
                    raise PrivacyError(f"PII field name in payload: {child_key!r}")
                walk(value, str(child_key))
        elif isinstance(node, list):
            for item in node:
                walk(item, key)
        elif isinstance(node, str):
            normalised = re.sub(r"[-_]", "", str(key).casefold()) if key else ""
            if normalised not in _UNSCANNED_KEYS:
                if _EMAIL.search(node):
                    raise PrivacyError(f"email-shaped string in {key!r}: {node!r}")
                if _PHONE.search(node):
                    raise PrivacyError(f"phone-number-shaped string in {key!r}: {node!r}")
            if node in banned_values:
                raise PrivacyError(f"banned value in {key!r}: {node!r}")
        elif isinstance(node, bool):
            # Guarded before the numeric branch: True == 1 in Python, so a bool
            # would otherwise match a banned coordinate of 1.
            return
        else:
            if node in banned_values:
                raise PrivacyError(f"banned value in {key!r}: {node!r}")

    walk(payload, None)


def serialise_for_audit(payload: Any) -> str:
    """Stable text used by tests to assert the raw GPS never survives.

    Sorting keys and disabling ``ensure_ascii`` produces a deterministic byte
    stream; the full-precision input coordinate, if it leaked, would appear
    inside that stream.
    """
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)