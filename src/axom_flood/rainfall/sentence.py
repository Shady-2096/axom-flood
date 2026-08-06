"""Reviewed English for a rainfall estimate. No generative model in the live path.

Workstream C, the last credential-free piece: the step between a number and a
person. It mirrors `alerts/sentence.py`, which does the same job for a river
gauge, and it exists now rather than later because every string here has to be
translated into Assamese by the one person who can review it. Writing the copy
while the pipeline is still being built is the difference between a two-week
wait at the end and no wait at all.

What this sentence is careful not to say
----------------------------------------

- **Not a measurement.** IMERG is a satellite estimate. Nobody stood in this
  circle with a rain gauge. The word "estimate" is in every sentence and is not
  optional.
- **Not a flood.** Rain is not flooding, and the copy never lets the reader
  carry the certainty of a number over to a claim about water at their house.
- **Not severity.** There is no "heavy", "very heavy" or "extremely heavy" here.
  IMD publishes those bands for daily gauge totals, and pinning them onto a
  rolling satellite estimate would borrow official language this number has not
  earned. The millimetres go out plain.
- **Not the circle's shape.** The number is an average over the whole circle.
  Rain over one corner is not rain at an address, and the phrasing says "over
  this area", never "where you are".

Missing data gets a sentence too. A circle with no usable estimate says so in
words, because a blank space reads as "no rain" to somebody scrolling on a phone.
"""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

from .imerg import IMERG_POLICIES
from .windows import (
    REASON_MISSING_CELLS,
    REASON_SERIES_BROKEN,
    REASON_WINDOW_NOT_COVERED,
    CircleRainfall,
)

IST = ZoneInfo("Asia/Kolkata")

#: The window a person is actually asking about. Longer ones are context; the
#: last day is the one that gets forwarded.
PREFERRED_WINDOW_HOURS = 24

#: How far past the run's own documented latency an estimate may fall behind
#: before the copy stops presenting it as the current picture. Generous on
#: purpose: the point is to catch a stalled pipeline, not to hide a normal wait.
STALE_MARGIN_HOURS = 6

#: How recently a window must have ended for "the last 24 hours" to be a true
#: description of it.
#:
#: This is a different question from staleness and was originally conflated with
#: it. Staleness asks whether the pipeline is stuck. This asks whether the
#: sentence is accurate. Measured against the live archive on 2026-08-07, the
#: Late run publishes about 15 hours behind its own observation window and the
#: Early run about 5 — both perfectly healthy. Deciding the wording on staleness
#: alone therefore printed "in the last 24 hours" on every card in the country
#: for a window that had ended most of a day earlier, which is the exact failure
#: the plan names: a window that ends early, labelled as though it did not.
#:
#: One hour is a granule and a half, so it holds only for a source that really is
#: nearly live. Every other case names the hour the window ended, and lets the
#: reader see it for themselves.
PRESENT_TENSE_WITHIN_HOURS = 1

ATTRIBUTION = "NASA GPM IMERG"

#: Plain-language versions of the refusal codes in `windows.py`. Kept here rather
#: than in the sentence body so each one can be translated on its own.
UNAVAILABLE_TEXT = {
    REASON_MISSING_CELLS: (
        "Part of this area has no reading, so no total can be given for the whole "
        "area."
    ),
    REASON_SERIES_BROKEN: (
        "Some half-hourly readings in the middle of this period are missing."
    ),
    REASON_WINDOW_NOT_COVERED: "The most recent readings have not arrived yet.",
}

HEDGE = (
    "Heavy rain can cause local flooding, but this does not confirm flooding at "
    "your location."
)

ESTIMATE_NOTE = "This is a satellite estimate, not a rain gauge reading."


def _window_phrase(hours: int) -> str:
    if hours == 1:
        return "the last hour"
    if hours == 24:
        return "the last 24 hours"
    if hours == 72:
        return "the last 3 days"
    return f"the last {hours} hours"


def _dated_window_phrase(hours: int) -> str:
    """The same window, described by its length rather than by "the last …"."""

    if hours == 1:
        return "the hour"
    if hours == 72:
        return "the 3 days"
    return f"the {hours} hours"


def _amount_phrase(total_mm: Decimal) -> str:
    """Whole millimetres, and an honest floor instead of a misleading '0 mm'.

    Rounding a 0.4 mm estimate to "0 mm" would be read as "it did not rain",
    which is a stronger claim than the number supports.
    """

    if total_mm < 1:
        return "less than 1 mm"
    whole = total_mm.quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return f"about {whole} mm"


def _age_hours(as_of: datetime, now: datetime) -> float:
    return round((now - as_of).total_seconds() / 3600, 2)


def describe_circle_rainfall(
    rainfall: CircleRainfall,
    *,
    now: datetime,
    place_name: str,
    preferred_hours: int = PREFERRED_WINDOW_HOURS,
) -> dict[str, Any]:
    """Reviewed English for one circle's rainfall, available or not.

    Falls back to the longest window that is actually covered when the preferred
    one is not. A 6-hour total that exists beats a 24-hour total that does not,
    and the label always names the window it really used.
    """

    policy = IMERG_POLICIES[rainfall.run]
    age_hours = _age_hours(rainfall.as_of, now)
    stale_after = policy.typical_latency_hours + STALE_MARGIN_HOURS
    is_stale = age_hours > stale_after
    period_end = rainfall.as_of.astimezone(IST)

    base = {
        "language": "en",
        "locality_id": rainfall.locality_id,
        "source": ATTRIBUTION,
        "run": rainfall.run.value,
        "as_of": rainfall.as_of.isoformat(),
        "age_hours": age_hours,
        "attribution": f"{ATTRIBUTION} ({rainfall.run.value} run)",
        "window_hours": None,
        "total_precipitation_mm": None,
        "estimate_note": ESTIMATE_NOTE,
        "hedge": HEDGE,
    }

    chosen = rainfall.window(preferred_hours) if any(
        entry.hours == preferred_hours for entry in rainfall.windows
    ) else None
    if chosen is None or not chosen.available:
        available = [entry for entry in rainfall.windows if entry.available]
        chosen = max(available, key=lambda entry: entry.hours) if available else chosen

    if chosen is None or not chosen.available:
        reason = chosen.unavailable_reason if chosen is not None else None
        detail = UNAVAILABLE_TEXT.get(
            reason or "", "No usable readings arrived for this period."
        )
        headline = (
            f"No satellite rainfall estimate is available for {place_name}. {detail}"
        )
        return {
            **base,
            "status": "unavailable",
            "unavailable_reason": reason,
            "headline": headline,
            "text": f"{headline} {HEDGE}",
        }

    amount = _amount_phrase(chosen.total_mm)
    fresh_headline = (
        f"Satellite estimates show {amount} of rain over {place_name} in "
        f"{_window_phrase(chosen.hours)}."
    )
    # Naming the hour the window ended is the normal case, not the failure case.
    # A satellite product that runs hours behind by design is not broken, and
    # saying so plainly costs one clause.
    dated_headline = (
        f"Satellite estimates show {amount} of rain over {place_name} in "
        f"{_dated_window_phrase(chosen.hours)} up to {period_end:%-I:%M %p} on "
        f"{period_end:%-d %b}."
    )
    # Only this one adds the note that the pipeline has fallen behind. It is also
    # published alongside whichever headline is chosen, because the reader's
    # clock is not the build's: a phone opening a cached artifact a day later
    # needs the sentence that stays true as the file ages.
    stale_headline = f"{dated_headline} Nothing newer has arrived."

    # Two separate questions, deliberately not one: `is_stale` asks whether the
    # pipeline is stuck, and how long ago the window ended asks whether the
    # present tense is a true sentence.
    if is_stale:
        headline = stale_headline
    elif age_hours <= PRESENT_TENSE_WITHIN_HOURS:
        headline = fresh_headline
    else:
        headline = dated_headline
    return {
        **base,
        "status": "stale_estimate" if is_stale else "estimate",
        "unavailable_reason": None,
        "window_hours": chosen.hours,
        "total_precipitation_mm": float(chosen.total_mm),
        "headline": headline,
        "stale_headline": stale_headline,
        "stale_after_hours": stale_after,
        "text": f"{headline} {ESTIMATE_NOTE} {HEDGE}",
    }
