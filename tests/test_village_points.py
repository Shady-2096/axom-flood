"""One village name can name two places. These are the cases that decides."""

from __future__ import annotations

from axom_flood.udise.villages import VILLAGE_RADIUS_KM, coherent_village_points

# Roughly a kilometre in Assam, in degrees, for both axes.
KM = 0.009


def test_a_single_school_is_kept_because_it_cannot_disagree_with_itself():
    assert coherent_village_points([(92.8, 26.0)]) == [(92.8, 26.0)]


def test_schools_in_one_village_are_all_kept():
    points = [(92.8, 26.0), (92.8 + KM, 26.0), (92.8, 26.0 + KM)]
    assert coherent_village_points(points) == points


def test_a_school_far_from_the_rest_is_dropped():
    """The signature of the name match: four together and one 60 km away."""
    near = [(92.8, 26.0), (92.81, 26.0), (92.8, 26.01), (92.81, 26.01)]
    assert coherent_village_points([*near, (93.4, 26.5)]) == near


def test_two_schools_far_apart_leave_nothing():
    """Neither has a claim over the other, so the village gets no position at all
    rather than the empty ground between them."""
    assert coherent_village_points([(92.8, 26.0), (93.4, 26.5)]) == []


def test_an_even_split_between_two_places_is_refused():
    """Three schools each in two places. Whichever side the median lands on would
    be a coin toss, and a wrong centre is worse here than no centre."""
    here = [(92.8, 26.0), (92.805, 26.0), (92.8, 26.005)]
    there = [(93.4, 26.5), (93.405, 26.5), (93.4, 26.505)]
    assert coherent_village_points([*here, *there]) == []


def test_a_clear_majority_keeps_the_village_and_drops_the_stragglers():
    here = [(92.8, 26.0), (92.805, 26.0), (92.8, 26.005), (92.805, 26.005)]
    there = [(93.4, 26.5), (93.405, 26.5), (93.4, 26.505)]
    assert coherent_village_points([*here, *there]) == here


def test_the_radius_is_measured_from_the_median_not_between_the_points():
    """A village spread evenly over twice the radius is not two villages, so the
    test is distance from the middle rather than the widest pair."""
    span = VILLAGE_RADIUS_KM * 0.9 * KM
    points = [(92.8 - span, 26.0), (92.8, 26.0), (92.8 + span, 26.0)]
    assert coherent_village_points(points) == points
