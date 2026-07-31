from pathlib import Path

import pdfplumber

from axom_flood.camps.discovery import load_district_registry
from axom_flood.camps.parser import _header_map, _number


def test_registry_has_all_35_districts() -> None:
    registry = load_district_registry(Path("config/assam-districts.json"))
    assert len(registry["districts"]) == 35
    assert len({item["name"] for item in registry["districts"]}) == 35


def test_header_mapping_and_assam_coordinate_bounds() -> None:
    mapping = _header_map(
        ["Sl. No", "Relief Camp", "Latitude", "Longitude", "Revenue Village", "Contact Number"]
    )
    assert mapping == {
        "name": 1,
        "latitude": 2,
        "longitude": 3,
        "village": 4,
        "contact_phone": 5,
    }
    assert _number("26.8188", 23, 29) == 26.8188
    assert _number("126.8188", 23, 29) is None


def test_pdf_dependency_is_available() -> None:
    assert pdfplumber.__version__
