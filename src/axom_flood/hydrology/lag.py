"""Robust monsoon travel-lag evidence from paired CWC level histories.

Levels at two gauges use different datums, so correlating their absolute values
is not meaningful. This module instead cross-correlates exact six-hour level
changes during May-October. Pearson correlation is calculated after deterministic
one-percent winsorisation, which limits transcription spikes without deleting
flood rises. Unclipped Pearson is retained as a diagnostic.

Every completed monsoon is fitted independently. A relationship clears the
quality gates only when multiple years agree on both correlation and lag. Even a
passing result remains review-only and can never promote a gauge mapping.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import datetime, timedelta
from statistics import median
from typing import Any

from axom_flood.cwc.history import HistorySeries, Observation

MONSOON_START_MONTH = 5
MONSOON_END_MONTH = 10
CHANGE_WINDOW_HOURS = 6
MAX_LAG_HOURS = 72
QUIET_CHANGE_M = 0.005
WINSOR_FRACTION = 0.01

MIN_MONSOON_COVERAGE = 0.75
MIN_ACTIVE_PAIRS = 800
MIN_RISE_EVENTS = 5
RISE_EVENT_SEPARATION_HOURS = 24
MIN_COMPLETED_YEARS = 3
MIN_ROBUST_CORRELATION = 0.35
MIN_CORRELATED_YEAR_FRACTION = 0.70
MAX_STABLE_DEVIATION_HOURS = 12
MIN_STABLE_YEAR_FRACTION = 0.70
MAX_LAG_IQR_HOURS = 12
MIN_ZERO_LAG_IMPROVEMENT = 0.02


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _quartiles(values: list[float]) -> tuple[float, float]:
    return _percentile(values, 0.25), _percentile(values, 0.75)


def _pearson(first: list[float], second: list[float]) -> float | None:
    if len(first) != len(second) or len(first) < 3:
        return None
    first_mean = sum(first) / len(first)
    second_mean = sum(second) / len(second)
    first_delta = [value - first_mean for value in first]
    second_delta = [value - second_mean for value in second]
    denominator = math.sqrt(
        sum(value * value for value in first_delta)
        * sum(value * value for value in second_delta)
    )
    if denominator == 0:
        return None
    return sum(
        first_value * second_value
        for first_value, second_value in zip(first_delta, second_delta, strict=True)
    ) / denominator


def _winsor_bounds(values: Iterable[float]) -> tuple[float, float]:
    materialized = list(values)
    return (
        _percentile(materialized, WINSOR_FRACTION),
        _percentile(materialized, 1 - WINSOR_FRACTION),
    )


def _clip(value: float, bounds: tuple[float, float]) -> float:
    return max(bounds[0], min(bounds[1], value))


def _monsoon_hours(year: int) -> int:
    start = datetime(year, MONSOON_START_MONTH, 1)
    end = datetime(year + 1, 1, 1) if MONSOON_END_MONTH == 12 else datetime(
        year, MONSOON_END_MONTH + 1, 1
    )
    return int((end - start).total_seconds() / 3600)


def _by_time(observations: Iterable[Observation]) -> dict[datetime, float]:
    return {item.observed_at: item.level_m for item in observations}


def _coverage(
    observations: Iterable[Observation],
    year: int,
) -> float:
    timestamps = {
        item.observed_at
        for item in observations
        if item.observed_at.year == year
        and MONSOON_START_MONTH <= item.observed_at.month <= MONSOON_END_MONTH
    }
    return len(timestamps) / _monsoon_hours(year)


def _changes(
    observations: Iterable[Observation],
    year: int,
) -> dict[datetime, float]:
    values = _by_time(observations)
    window = timedelta(hours=CHANGE_WINDOW_HOURS)
    return {
        observed_at: level - values[observed_at - window]
        for observed_at, level in values.items()
        if observed_at.year == year
        and MONSOON_START_MONTH <= observed_at.month <= MONSOON_END_MONTH
        and observed_at - window in values
    }


def _rise_event_count(changes: dict[datetime, float]) -> tuple[int, float | None]:
    positive = [value for value in changes.values() if value > 0]
    if not positive:
        return 0, None
    threshold = max(0.02, _percentile(positive, 0.90))
    candidates = sorted(
        observed_at for observed_at, value in changes.items() if value >= threshold
    )
    event_count = 0
    last_event: datetime | None = None
    separation = timedelta(hours=RISE_EVENT_SEPARATION_HOURS)
    for observed_at in candidates:
        if last_event is None or observed_at - last_event >= separation:
            event_count += 1
            last_event = observed_at
    return event_count, round(threshold, 4)


def _lag_score(
    upstream: dict[datetime, float],
    downstream: dict[datetime, float],
    lag_hours: int,
    *,
    upstream_bounds: tuple[float, float],
    downstream_bounds: tuple[float, float],
) -> dict[str, Any]:
    lag = timedelta(hours=lag_hours)
    first: list[float] = []
    second: list[float] = []
    for observed_at, upstream_change in upstream.items():
        downstream_change = downstream.get(observed_at + lag)
        if downstream_change is None:
            continue
        if (
            abs(upstream_change) < QUIET_CHANGE_M
            and abs(downstream_change) < QUIET_CHANGE_M
        ):
            continue
        first.append(upstream_change)
        second.append(downstream_change)
    robust_first = [_clip(value, upstream_bounds) for value in first]
    robust_second = [_clip(value, downstream_bounds) for value in second]
    robust = _pearson(robust_first, robust_second)
    ordinary = _pearson(first, second)
    return {
        "lag_hours": lag_hours,
        "paired_changes": len(first),
        "robust_correlation": robust,
        "ordinary_correlation": ordinary,
    }


def _analyse_year(
    upstream: HistorySeries,
    downstream: HistorySeries,
    year: int,
    *,
    complete: bool,
) -> dict[str, Any]:
    upstream_changes = _changes(upstream.observations, year)
    downstream_changes = _changes(downstream.observations, year)
    upstream_coverage = _coverage(upstream.observations, year)
    downstream_coverage = _coverage(downstream.observations, year)
    rise_events, rise_threshold = _rise_event_count(upstream_changes)
    reasons: list[str] = []
    if not complete:
        reasons.append("monsoon_year_in_progress")
    if upstream_coverage < MIN_MONSOON_COVERAGE:
        reasons.append("upstream_monsoon_coverage_below_gate")
    if downstream_coverage < MIN_MONSOON_COVERAGE:
        reasons.append("downstream_monsoon_coverage_below_gate")
    if not upstream_changes or not downstream_changes:
        reasons.append("no_paired_change_series")
        return {
            "year": year,
            "complete_year": complete,
            "eligible_for_stability": False,
            "ineligible_reasons": reasons,
            "upstream_monsoon_coverage": round(upstream_coverage, 4),
            "downstream_monsoon_coverage": round(downstream_coverage, 4),
            "upstream_rise_events": rise_events,
            "rise_event_threshold_m_per_6h": rise_threshold,
            "best_lag_hours": None,
            "best_robust_correlation": None,
            "zero_lag_robust_correlation": None,
            "best_minus_zero_lag": None,
            "near_best_lag_range_hours": None,
            "paired_changes_at_best_lag": 0,
        }

    upstream_bounds = _winsor_bounds(upstream_changes.values())
    downstream_bounds = _winsor_bounds(downstream_changes.values())
    scores = [
        _lag_score(
            upstream_changes,
            downstream_changes,
            lag,
            upstream_bounds=upstream_bounds,
            downstream_bounds=downstream_bounds,
        )
        for lag in range(MAX_LAG_HOURS + 1)
    ]
    scored = [item for item in scores if item["robust_correlation"] is not None]
    if not scored:
        reasons.append("change_series_has_zero_variance")
        return {
            "year": year,
            "complete_year": complete,
            "eligible_for_stability": False,
            "ineligible_reasons": reasons,
            "upstream_monsoon_coverage": round(upstream_coverage, 4),
            "downstream_monsoon_coverage": round(downstream_coverage, 4),
            "upstream_rise_events": rise_events,
            "rise_event_threshold_m_per_6h": rise_threshold,
            "best_lag_hours": None,
            "best_robust_correlation": None,
            "best_ordinary_correlation": None,
            "zero_lag_robust_correlation": None,
            "best_minus_zero_lag": None,
            "near_best_lag_range_hours": None,
            "paired_changes_at_best_lag": 0,
        }
    best = max(
        scored,
        key=lambda item: (item["robust_correlation"], -item["lag_hours"]),
    )
    zero = scores[0]
    near = [
        item["lag_hours"]
        for item in scored
        if item["robust_correlation"] >= best["robust_correlation"] - 0.02
    ]
    if best["paired_changes"] < MIN_ACTIVE_PAIRS:
        reasons.append("paired_changes_below_gate")
    if rise_events < MIN_RISE_EVENTS:
        reasons.append("independent_rise_events_below_gate")
    eligible = not reasons
    zero_correlation = zero["robust_correlation"]
    improvement = (
        best["robust_correlation"] - zero_correlation
        if zero_correlation is not None
        else None
    )
    return {
        "year": year,
        "complete_year": complete,
        "eligible_for_stability": eligible,
        "ineligible_reasons": reasons,
        "upstream_monsoon_coverage": round(upstream_coverage, 4),
        "downstream_monsoon_coverage": round(downstream_coverage, 4),
        "upstream_rise_events": rise_events,
        "rise_event_threshold_m_per_6h": rise_threshold,
        "best_lag_hours": best["lag_hours"],
        "best_robust_correlation": round(best["robust_correlation"], 4),
        "best_ordinary_correlation": (
            round(best["ordinary_correlation"], 4)
            if best["ordinary_correlation"] is not None
            else None
        ),
        "zero_lag_robust_correlation": (
            round(zero_correlation, 4) if zero_correlation is not None else None
        ),
        "best_minus_zero_lag": round(improvement, 4) if improvement is not None else None,
        "near_best_lag_range_hours": [min(near), max(near)],
        "paired_changes_at_best_lag": best["paired_changes"],
    }


def _quality_summary(years: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [item for item in years if item["eligible_for_stability"]]
    lags = [float(item["best_lag_hours"]) for item in eligible]
    correlations = [float(item["best_robust_correlation"]) for item in eligible]
    improvements = [
        float(item["best_minus_zero_lag"])
        for item in eligible
        if item["best_minus_zero_lag"] is not None
    ]
    gates: dict[str, bool] = {
        "enough_completed_years": len(eligible) >= MIN_COMPLETED_YEARS,
        "median_correlation": False,
        "correlated_year_fraction": False,
        "lag_iqr": False,
        "stable_year_fraction": False,
        "positive_lead_time": False,
        "improves_on_zero_lag": False,
    }
    if not eligible:
        return {
            "passes_quality_gates": False,
            "gates": gates,
            "eligible_completed_years": 0,
            "recommended_lag_hours": None,
            "observed_yearly_lag_range_hours": None,
            "lag_interquartile_range_hours": None,
            "median_robust_correlation": None,
            "correlated_year_fraction": 0.0,
            "stable_year_fraction": 0.0,
            "median_best_minus_zero_lag": None,
        }

    recommended = float(median(lags))
    first_quartile, third_quartile = _quartiles(lags)
    correlated_fraction = (
        sum(value >= MIN_ROBUST_CORRELATION for value in correlations) / len(correlations)
    )
    stable_fraction = (
        sum(abs(value - recommended) <= MAX_STABLE_DEVIATION_HOURS for value in lags)
        / len(lags)
    )
    median_correlation = float(median(correlations))
    median_improvement = float(median(improvements)) if improvements else None
    gates.update(
        {
            "median_correlation": median_correlation >= MIN_ROBUST_CORRELATION,
            "correlated_year_fraction": (
                correlated_fraction >= MIN_CORRELATED_YEAR_FRACTION
            ),
            "lag_iqr": third_quartile - first_quartile <= MAX_LAG_IQR_HOURS,
            "stable_year_fraction": stable_fraction >= MIN_STABLE_YEAR_FRACTION,
            "positive_lead_time": recommended >= 1,
            "improves_on_zero_lag": (
                median_improvement is not None
                and median_improvement >= MIN_ZERO_LAG_IMPROVEMENT
            ),
        }
    )
    passes = all(gates.values())
    return {
        "passes_quality_gates": passes,
        "gates": gates,
        "eligible_completed_years": len(eligible),
        "recommended_lag_hours": round(recommended, 1),
        "observed_yearly_lag_range_hours": [int(min(lags)), int(max(lags))],
        "lag_interquartile_range_hours": round(third_quartile - first_quartile, 1),
        "median_robust_correlation": round(median_correlation, 4),
        "correlated_year_fraction": round(correlated_fraction, 4),
        "stable_year_fraction": round(stable_fraction, 4),
        "median_best_minus_zero_lag": (
            round(median_improvement, 4) if median_improvement is not None else None
        ),
    }


def analyze_relationship(
    upstream: HistorySeries,
    downstream: HistorySeries,
    *,
    now: datetime,
) -> dict[str, Any]:
    """Fit each monsoon independently and return review-only evidence."""

    all_years = sorted(
        {
            item.observed_at.year
            for series in (upstream, downstream)
            for item in series.observations
        }
    )
    year_results = [
        _analyse_year(
            upstream,
            downstream,
            year,
            complete=year < now.year
            or (year == now.year and now.month > MONSOON_END_MONTH),
        )
        for year in all_years
    ]
    quality = _quality_summary(year_results)
    return {
        "method": "may_october_six_hour_change_cross_correlation_v1",
        "change_window_hours": CHANGE_WINDOW_HOURS,
        "lag_search_hours": [0, MAX_LAG_HOURS],
        "quality_gate_thresholds": {
            "minimum_monsoon_coverage": MIN_MONSOON_COVERAGE,
            "minimum_active_pairs_per_year": MIN_ACTIVE_PAIRS,
            "minimum_upstream_rise_events_per_year": MIN_RISE_EVENTS,
            "minimum_completed_years": MIN_COMPLETED_YEARS,
            "minimum_robust_correlation": MIN_ROBUST_CORRELATION,
            "minimum_correlated_year_fraction": MIN_CORRELATED_YEAR_FRACTION,
            "maximum_lag_interquartile_range_hours": MAX_LAG_IQR_HOURS,
            "maximum_stable_deviation_hours": MAX_STABLE_DEVIATION_HOURS,
            "minimum_stable_year_fraction": MIN_STABLE_YEAR_FRACTION,
            "minimum_zero_lag_improvement": MIN_ZERO_LAG_IMPROVEMENT,
        },
        "robustness": (
            "Per-year six-hour changes; both-quiet pairs removed; each change "
            "series winsorised at 1% before Pearson correlation; completed "
            "monsoons fitted independently."
        ),
        "quality": quality,
        "year_results": year_results,
    }


__all__ = ["analyze_relationship"]
