from axom_flood.udise.matcher import normalize_name


def test_school_abbreviations_are_expanded() -> None:
    assert normalize_name("Nazira H.S.S.") == "nazira higher secondary school"
    assert normalize_name("No. 12 Bor LP School") == "no 12 bor lower primary school"
