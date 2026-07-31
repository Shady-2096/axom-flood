"""The centroid a circle publishes must lie inside that circle.

It is what the map draws the gauge line from and what the gauge-distance audit
measures. Gohpur's sat 100 km west of Gohpur, so the app told people their gauge
was 26 km away when it was 92 km away.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from audit_locality_centroids import find_corrections  # noqa: E402

from axom_flood.geometry import (  # noqa: E402
    CORRECTED_METHOD,
    SOURCE_METHOD,
    corrected_centre,
    load_circle_outlines,
    point_in_rings,
    representative_point,
)

SQUARE = [[[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]]]
# A C shape. Its area-weighted centroid falls in the notch, outside the polygon.
C_SHAPE = [
    [
        [0.0, 0.0], [3.0, 0.0], [3.0, 1.0], [1.0, 1.0],
        [1.0, 2.0], [3.0, 2.0], [3.0, 3.0], [0.0, 3.0],
    ]
]


def test_a_point_inside_a_simple_circle_is_inside() -> None:
    assert point_in_rings([1.0, 1.0], SQUARE) is True
    assert point_in_rings([3.0, 1.0], SQUARE) is False


def test_representative_point_of_a_concave_circle_is_inside_it() -> None:
    """River-following boundaries are concave, so this is the normal case."""
    point = representative_point(C_SHAPE)
    assert point is not None
    assert point_in_rings(point, C_SHAPE) is True


def test_representative_point_of_a_square_is_its_centre() -> None:
    assert representative_point(SQUARE) == [1.0, 1.0]


def test_a_centroid_already_inside_its_circle_is_left_alone() -> None:
    """A circle is an area; its centre is allowed not to be its namesake town."""
    outlines = {"x": SQUARE}
    centre, method = corrected_centre("x", [1.5, 0.5], outlines)
    assert centre == [1.5, 0.5]
    assert method == SOURCE_METHOD


def test_a_centroid_outside_its_circle_is_replaced() -> None:
    outlines = {"x": SQUARE}
    centre, method = corrected_centre("x", [9.0, 9.0], outlines)
    assert point_in_rings(centre, SQUARE) is True
    assert method == CORRECTED_METHOD


def test_a_circle_with_no_outline_keeps_what_it_had() -> None:
    centre, method = corrected_centre("missing", [9.0, 9.0], {})
    assert centre == [9.0, 9.0]
    assert method == SOURCE_METHOD


def test_the_committed_registry_holds_no_centroid_outside_its_circle() -> None:
    """The regression guard. This is what CI is for."""
    root = Path(__file__).resolve().parents[1]
    localities = json.loads((root / "config" / "assam-localities.json").read_text())
    shapes = load_circle_outlines(root / "config" / "assam-circle-shapes.json")
    corrections, unfixable = find_corrections(localities["localities"], shapes)
    assert corrections == [], f"{len(corrections)} centroids sit outside their circle"
    assert unfixable == []
