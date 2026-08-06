"""Rainfall totals over the windows a person actually asks about.

Workstream C of the local-accuracy master plan, third piece. `zonal.py` turns one
grid into one circle number over whatever window the caller happened to hand it.
This turns a running series of half-hour grids into the fixed set the plan names:
the last 1, 3, 6, 24 and 72 hours over one circle.

Windows fail one at a time
--------------------------

The all-or-nothing coverage rule in `zonal.py` is right, but applied to a whole
series it is too blunt. A 72-hour window reaching back three days will meet a
missing granule long before a 1-hour window does, and letting that erase the
recent hours would throw away the most useful and most complete number on the
page. So each window is computed and refused independently, and every refusal
carries a machine-readable reason as well as a sentence.

Nothing is stretched to fit
---------------------------

A window is either covered exactly — every cell, every half hour from
``as_of - hours`` to ``as_of``, no gap and no overlap — or it is unavailable.
Three habits are refused by construction:

- **Ending the window early.** A "last 24 hours" that actually ends four hours
  ago is a different claim from the one its label makes.
- **Averaging the granules that did arrive.** A hole in the middle of a window
  reads as less rain, not as missing rain.
- **Mixing Early and Late runs.** They are separate products with separate
  error characteristics. Late for the older hours and Early for the newest is a
  tempting way to fill a 72-hour window and it is not one number. Build one
  series per run and call this twice.

None of these produce a number that looks wrong. They produce a number that
looks fine and is low, which is why they are closed here rather than checked
downstream.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from .imerg import ImergGridCellObservation, ImergRun, accumulate_imerg_cell
from .provenance import require_aware
from .zonal import ZONAL_FORBIDS, ZONAL_PERMITS, CoverageError, ZonalWeights

#: The windows the plan asks for. Short ones speak to waterlogging and small
#: streams, long ones to a river that has been fed for days.
RAINFALL_WINDOW_HOURS = (1, 3, 6, 24, 72)

#: IMERG granules are half-hourly, so every window boundary must land on a whole
#: half hour or a granule would have to be cut in two.
_GRANULE_MINUTES = 30

#: Why a window has no number. Machine-readable so the site can choose its own
#: wording, and so an operator can count the failures by kind.
REASON_MISSING_CELLS = "missing_cells"
REASON_SERIES_BROKEN = "series_broken"
REASON_WINDOW_NOT_COVERED = "window_not_covered"


@dataclass(frozen=True, slots=True)
class WindowTotal:
    """One window's rainfall over one circle, or the reason there is none."""

    hours: int
    interval_start: datetime
    interval_end: datetime
    total_mm: Decimal | None
    unavailable_reason: str | None
    unavailable_detail: str | None
    cell_count: int
    granule_count: int
    source_revision_sha256s: tuple[str, ...]

    @property
    def available(self) -> bool:
        return self.total_mm is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "hours": self.hours,
            "interval_start": self.interval_start.isoformat(),
            "interval_end": self.interval_end.isoformat(),
            "available": self.available,
            "total_precipitation_mm": (
                None if self.total_mm is None else float(self.total_mm)
            ),
            "unavailable_reason": self.unavailable_reason,
            "unavailable_detail": self.unavailable_detail,
            "cell_count": self.cell_count,
            "granule_count": self.granule_count,
            "source_revision_sha256s": list(self.source_revision_sha256s),
        }


@dataclass(frozen=True, slots=True)
class CircleRainfall:
    """Every requested window for one circle, available or not."""

    locality_id: str
    run: ImergRun
    as_of: datetime
    boundary_sha256: str
    cell_count: int
    windows: tuple[WindowTotal, ...]

    def window(self, hours: int) -> WindowTotal:
        for entry in self.windows:
            if entry.hours == hours:
                return entry
        raise KeyError(f"{self.locality_id} has no {hours}-hour window")

    @property
    def longest_available_hours(self) -> int | None:
        available = [entry.hours for entry in self.windows if entry.available]
        return max(available) if available else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "record": "circle_rainfall_windows",
            "locality_id": self.locality_id,
            "run": self.run.value,
            "as_of": self.as_of.isoformat(),
            "aggregation": "area_weighted_mean_over_circle",
            "boundary_sha256": self.boundary_sha256,
            "cell_count": self.cell_count,
            "windows": [entry.as_dict() for entry in self.windows],
            "permits": ZONAL_PERMITS,
            "forbids": ZONAL_FORBIDS,
        }


def _require_granule_aligned(moment: datetime, field: str) -> None:
    require_aware(moment, field)
    if moment.second or moment.microsecond or moment.minute % _GRANULE_MINUTES:
        raise ValueError(
            f"{field} must land on a half hour; IMERG granules cannot be cut in two"
        )


def _single_run(observations: list[ImergGridCellObservation]) -> ImergRun:
    runs = {observation.run for observation in observations}
    if len(runs) != 1:
        raise CoverageError(
            "Early and Late are different products and cannot share one series; "
            "accumulate each run separately"
        )
    return runs.pop()


def _window_total(
    weights: ZonalWeights,
    by_cell: dict[str, list[ImergGridCellObservation]],
    *,
    hours: int,
    window_start: datetime,
    as_of: datetime,
) -> WindowTotal:
    """One window over one circle: exact coverage, or a named refusal."""

    empty = WindowTotal(
        hours=hours,
        interval_start=window_start,
        interval_end=as_of,
        total_mm=None,
        unavailable_reason=None,
        unavailable_detail=None,
        cell_count=len(weights.weights),
        granule_count=0,
        source_revision_sha256s=(),
    )

    def refuse(reason: str, detail: str) -> WindowTotal:
        return replace(empty, unavailable_reason=reason, unavailable_detail=detail)

    in_window: dict[str, list[ImergGridCellObservation]] = {}
    for cell_id, observations in by_cell.items():
        kept = [
            observation
            for observation in observations
            if observation.interval_start >= window_start
            and observation.interval_end <= as_of
        ]
        if kept:
            in_window[cell_id] = kept

    missing = sorted(set(weights.cell_ids) - in_window.keys())
    if missing:
        return refuse(
            REASON_MISSING_CELLS,
            f"{len(missing)} of {len(weights.cell_ids)} cells have no reading in "
            f"this window ({', '.join(missing[:5])}"
            f"{', …' if len(missing) > 5 else ''})",
        )

    total = Decimal(0)
    revisions: list[str] = []
    granules = 0
    for weight in weights.weights:
        try:
            cell = accumulate_imerg_cell(in_window[weight.grid_cell_id])
        except ValueError as exc:
            return refuse(
                REASON_SERIES_BROKEN,
                f"cell {weight.grid_cell_id} cannot be accumulated: {exc}",
            )
        if cell.interval_start != window_start or cell.interval_end != as_of:
            return refuse(
                REASON_WINDOW_NOT_COVERED,
                f"cell {weight.grid_cell_id} covers "
                f"{cell.interval_start.isoformat()} to {cell.interval_end.isoformat()}, "
                f"not the whole window",
            )
        total += cell.total_mm * Decimal(str(weight.share))
        revisions.extend(cell.source_revision_sha256s)
        granules += cell.interval_count

    return replace(
        empty,
        total_mm=total,
        granule_count=granules,
        source_revision_sha256s=tuple(dict.fromkeys(revisions)),
    )


def accumulate_windows(
    weights: ZonalWeights,
    observations: list[ImergGridCellObservation],
    *,
    as_of: datetime,
    window_hours: tuple[int, ...] = RAINFALL_WINDOW_HOURS,
) -> CircleRainfall:
    """Area-weighted rainfall over one circle for each requested window.

    `as_of` is the end of every window, not the newest thing in `observations`.
    Passing the clock rather than the data is deliberate: a series that stopped
    two hours ago should make the windows unavailable, not quietly relabel a
    total that ends earlier than it claims.
    """

    _require_granule_aligned(as_of, "as_of")
    if not window_hours:
        raise ValueError("at least one window is required")
    if any(hours <= 0 for hours in window_hours):
        raise ValueError("window hours must be positive")
    if not observations:
        raise CoverageError("no observations were supplied for any window")

    run = _single_run(observations)

    by_cell: dict[str, list[ImergGridCellObservation]] = {}
    for observation in observations:
        by_cell.setdefault(observation.grid_cell_id, []).append(observation)

    wanted = set(weights.cell_ids)
    extra = sorted(by_cell.keys() - wanted)
    if extra:
        raise CoverageError(
            f"{weights.locality_id} was given cells outside its own boundary: "
            f"{', '.join(extra[:5])}"
        )

    windows = tuple(
        _window_total(
            weights,
            by_cell,
            hours=hours,
            window_start=as_of - timedelta(hours=hours),
            as_of=as_of,
        )
        for hours in sorted(window_hours)
    )
    return CircleRainfall(
        locality_id=weights.locality_id,
        run=run,
        as_of=as_of,
        boundary_sha256=weights.boundary_sha256,
        cell_count=len(weights.weights),
        windows=windows,
    )
