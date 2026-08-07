"""Build Phase 1 revenue-circle and village-search artifacts.

Run with:
  uv run --with xlrd python scripts/build_localities.py \
    --census-xls /path/to/Rdir_2001_MDDS_18.xls

Administrative names and memberships come from the official Census 2011 MDDS
directory. Centre points are medians of exact village-name matches in the
recorded UDISE coordinate snapshot, never inputs to gauge selection.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

# Reused, not reimplemented: the same registry lookup the gauge pipeline uses to
# resolve a source's district spelling to this project's canonical name and slug,
# and the recorded station reference that says where each gauge physically is.
from axom_flood.cwc.pipeline import (
    haversine_km,
    load_district_lookup,
    load_station_reference,
)

# The reviewed answers to "does this gauge sit on water that reaches this
# circle". Shared with scripts/audit_gauge_mappings.py so a full rebuild and the
# nightly audit apply one decision the same way.
from axom_flood.gauges import decisions as gauge_decisions

# Same rule scripts/audit_locality_centroids.py enforces, imported rather than
# copied so a rebuild and the audit can never disagree about a circle's centre.
from axom_flood.geometry import corrected_centre, load_circle_outlines

# One village name can be recorded for schools 100 km apart, and the district
# column is too coarse to tell them apart. Shared with the boundary scorer so a
# centre and the boundary it is scored against are built from the same points.
from axom_flood.udise.villages import coherent_village_points

DISTRICT_LOOKUP = load_district_lookup()

ROOT = Path(__file__).resolve().parent.parent
DECISIONS = ROOT / "config" / "gauge-topology-decisions.json"

# How far a circle may sit from the gauge it reads from before the mapping has to
# be defended rather than assumed.
#
# These are not hydrology. A gauge 15 km away on the wrong river is worse than one
# 80 km downstream on yours, and no distance rule can tell those apart. What a
# distance rule *can* do is catch the failure this project actually made: a
# district-wide default quietly applied to a circle in another basin, carrying the
# same confident sentence as a reviewed match. Silonijan read from Kampur, 101 km
# away across the Karbi hills, while a warning-level gauge sat 51 km off on its own
# river — and nothing in the build objected.
#
# So the rule is deliberately weak and deliberately loud: past FAR_KM, or when a
# much nearer gauge exists, the record cannot claim to be reviewed and goes to the
# queue with its numbers attached. A hydrologist still decides.
FAR_KM = 60.0
MUCH_NEARER_KM = 25.0

CENSUS_SOURCE = (
    "https://censusindia.gov.in/nada/index.php/catalog/7057/download/10169/"
    "Rdir_2001_MDDS_18.xls"
)

GAUGES = {
    "baksa": ("001-LBDJPG", "Beki at Mathanguri", "medium"),
    "barpeta": ("002-LBDJPG", "Beki at Beki Road Bridge", "medium"),
    "bongaigaon": ("004-LBDJPG", "Manas at NH Crossing", "medium"),
    "cachar": ("01-11-01-007", "Barak at Annapurna Ghat", "high"),
    "chirang": ("004-LBDJPG", "Manas at NH Crossing downstream", "unverified"),
    "darrang": ("006-MBDGHY", "Puthimari at NH Road Crossing downstream", "unverified"),
    "dhemaji": ("021-UBDDIB", "Subansiri at Chouldhowaghat downstream", "medium"),
    "dhubri": ("005-LBDJPG", "Brahmaputra at Dhubri", "high"),
    "dibrugarh": ("010-UBDDIB", "Brahmaputra at Dibrugarh", "medium"),
    "dimahasao": ("033-UBDDIB", "Kopili at Kampur downstream", "unverified"),
    "goalpara": ("002-MBDGHY", "Brahmaputra at Goalpara", "high"),
    "golaghat": ("026-UBDDIB", "Dhansiri South at Golaghat", "medium"),
    "hailakandi": ("01-11-01-002", "Katakhal at Matijuri", "high"),
    "jorhat": ("019-UBDDIB", "Brahmaputra at Neamatighat", "medium"),
    "kamrup": ("001-MBDGHY", "Brahmaputra at Guwahati downstream", "medium"),
    "karbianglong": ("033-UBDDIB", "Kopili at Kampur downstream", "unverified"),
    "kokrajhar": ("039LBDJPG", "Gaurang at Kokrajhar", "medium"),
    "lakhimpur": ("36-UBDDIB", "Ranganadi at NT Road Crossing", "medium"),
    "morigaon": ("034-UBDDIB", "Kopili at Dharamtul", "high"),
    "nagaon": ("033-UBDDIB", "Kopili at Kampur", "medium"),
    "nalbari": ("004-MBDGHY", "Pagladiya at NT Road Crossing", "medium"),
    "sivasagar": ("018-ubddib", "Dikhow at Sivasagar", "medium"),
    "sonitpur": ("031-UBDDIB", "Brahmaputra at Tezpur", "medium"),
    "sribhumi": ("021-MBDGHY", "Kushiyara at Karimganj", "medium"),
    "tinsukia": ("007-UBDDIB", "Lohit at Dholabazar downstream", "medium"),
    "udalguri": ("030-UBDDIB", "Jiabharali at NT Road Crossing downstream", "unverified"),
}

DISTRICT_ALIASES = {
    "karimganj": "sribhumi",
    "kamrupmetropolitan": "kamrup",
}

# The Census rural directory is the reproducible base, but it omits Guwahati
# Revenue Circle even though the current district administration and its
# disaster-management plan both name it as one of Kamrup Metropolitan's five
# revenue circles. Keep current-administration supplements explicit and
# evidence-backed rather than silently pretending they came from the workbook.
CURRENT_ADMIN_LOCALITIES = [
    {
        "locality_id": "kamrup-metropolitan-guwahati",
        "name": "Guwahati",
        "district": "Kamrup Metropolitan",
        "district_slug": "kamrupmetro",
        "source_url": "https://kamrupmetro.assam.gov.in/about-us/about-district",
        "centroid": [91.753943, 26.180598],
        "centroid_method": "OpenStreetMap city point; search and map display only",
        "primary_gauge": "001-MBDGHY",
        "gauge_basis": "Brahmaputra at Guwahati D.C. Court within Guwahati Revenue Circle",
        "gauge_confidence": "medium",
        "source_aliases": ["Gauhati"],
    },
]

# Eight of Assam's 35 districts were created after the 2011 Census, so the Census
# workbook files their revenue circles under the parent district they were carved
# from. Someone in Biswanath would otherwise have to know to look under Sonitpur.
#
# Which 2011 circle belongs to which new district is a gazette fact, not something
# to infer from a name or a coordinate, and a wrong district routes a flood alert
# to the wrong place. Every entry below is keyed on (census district, circle) —
# not on circle name alone, because the Census splits several circles across two
# districts with a "(Pt)" suffix and only the part under the documented parent
# moves. Each carries the page that evidences it.
#
# Verified against district administrations on 2026-07-27. Anything not evidenced
# is deliberately absent and goes to the review queue instead.
DISTRICT_REASSIGNMENTS: dict[tuple[str, str], tuple[str, str, str]] = {
    # "New Flood Contingency plan 2026 for Bajali Revenue Circle" and
    # "... for Sarupeta Revenue Circle". Carved from Barpeta by notification
    # GAG(B) 491/2019/107 of 12 January 2021. Barnagar is NOT evidenced as
    # Bajali's and therefore stays in Barpeta.
    ("Barpeta", "Bajali (Pt)"): (
        "Bajali", "https://bajali.assam.gov.in/about-district", "high",
    ),
    ("Barpeta", "Sarupeta (Pt)"): (
        "Bajali", "https://bajali.assam.gov.in/", "high",
    ),
    # Recruitment notices name "Biswanath Revenue Circle", "Helem Revenue
    # Circle" and "Na-Duar Revenue Circle"; Gohpur is listed as a co-district.
    ("Sonitpur", "Biswanath"): (
        "Biswanath", "https://biswanath.assam.gov.in/", "high",
    ),
    ("Sonitpur", "Helem"): (
        "Biswanath", "https://biswanath.assam.gov.in/", "high",
    ),
    ("Sonitpur", "Na-Duar"): (
        "Biswanath", "https://biswanath.assam.gov.in/", "high",
    ),
    ("Sonitpur", "Gohpur"): (
        "Biswanath", "https://biswanath.assam.gov.in/", "high",
    ),
    # "Administrative Setup: Revenue Circles 1. Sonari 2. Sapekhati 3. Mahmora".
    # Created from Sivasagar by notification GAG(B) 27/01/2016. Nazira is named
    # only as a neighbouring Sivasagar sub-division and stays there.
    ("Sivasagar", "Sonari"): (
        "Charaideo", "https://charaideo.assam.gov.in/about-district", "high",
    ),
    ("Sivasagar", "Mahmora"): (
        "Charaideo", "https://charaideo.assam.gov.in/about-district", "high",
    ),
    # "Revenue Circles: 3", and flood-beneficiary lists published per circle for
    # Doboka, Hojai and Lanka — which is exactly those three.
    ("Nagaon", "Doboka"): ("Hojai", "https://hojai.assam.gov.in/", "high"),
    ("Nagaon", "Hojai"): ("Hojai", "https://hojai.assam.gov.in/", "high"),
    ("Nagaon", "Lanka"): ("Hojai", "https://hojai.assam.gov.in/", "high"),
    # Headquarter "Garamur, Majuli", 2 revenue circles. Only one of the two
    # appears in the 2011 workbook.
    ("Jorhat", "Majuli"): ("Majuli", "https://majuli.assam.gov.in/", "high"),
    # "created by bifurcating Old Dhubri district in 2016".
    ("Dhubri", "Mankachar"): (
        "South Salmara-Mankachar",
        "https://southsalmaramankachar.assam.gov.in/about-district",
        "high",
    ),
    ("Dhubri", "South Salmara"): (
        "South Salmara-Mankachar",
        "https://southsalmaramankachar.assam.gov.in/about-district",
        "high",
    ),
    # "Revenue Circles: 02 - (i) Tamulpur (ii) Goreswar".
    ("Baksa", "Tamulpur"): ("Tamulpur", "https://tamulpur.assam.gov.in/", "high"),
    ("Baksa", "Goreswar (Pt)"): (
        "Tamulpur", "https://tamulpur.assam.gov.in/", "high",
    ),
    # West Karbi Anglong is absent on purpose: its administration publishes no
    # revenue-circle list, so none of Karbi Anglong's circles can be reassigned
    # on evidence. See the review queue.
}

#: Districts known to exist but for which no circle could be evidenced. Recorded
#: so the gap is visible rather than looking like an oversight.
UNEVIDENCED_DISTRICTS = {
    "West Karbi Anglong": (
        "https://westkarbianglong.assam.gov.in/",
        "The district site publishes no revenue-circle list, and none of Karbi "
        "Anglong's 2011 circles (Diphu, Donka, Phuloni, Silonijan) is named on "
        "it. Reassignment needs a gazette notification or an LGD export.",
    ),
}

UDISE_DISTRICT_ALIASES = {
    "kamrup": "kamruprural",
    "kamrupmetropolitan": "kamrupmetro",
    "sivasagar": "sibsagar",
}

CIRCLE_OVERRIDES = {
    ("dhubri", "agamoni"): ("008-LBDJPG", "Sankosh at Golokganj downstream", "medium"),
    ("dhubri", "golokganjpt"): ("008-LBDJPG", "Sankosh at Golokganj", "high"),
    ("dibrugarh", "naharkatiya"): ("012-ubddib", "Buridehing at Naharkatia", "high"),
    ("dibrugarh", "moran"): ("013-UBDDIB", "Buridehing at Chenimari Khowang", "medium"),
    ("dibrugarh", "tingkhong"): ("013-UBDDIB", "Buridehing at Chenimari Khowang", "medium"),
    ("dibrugarh", "tengakhat"): ("013-UBDDIB", "Buridehing at Chenimari Khowang", "medium"),
    ("golaghat", "bokakhat"): ("024-UBDDIB", "Dhansiri South at Numaligarh upstream", "medium"),
    ("golaghat", "morangi"): ("024-UBDDIB", "Dhansiri South at Numaligarh", "medium"),
    ("kamrup", "rangia"): ("006-MBDGHY", "Puthimari at NH Road Crossing", "medium"),
    ("kamrup", "kamalpur"): ("006-MBDGHY", "Puthimari at NH Road Crossing", "medium"),
    ("lakhimpur", "dhakuakhanapt"): (
        "022-UBDDIB",
        "Subansiri at Badatighat downstream",
        "medium",
    ),
    ("lakhimpur", "subansiript"): ("022-UBDDIB", "Subansiri at Badatighat", "medium"),
    ("nagaon", "kampur"): ("033-UBDDIB", "Kopili at Kampur", "high"),
    ("sivasagar", "dimow"): ("016-UBDDIB", "Desang at Nanglamoraghat", "medium"),
    ("sivasagar", "sibsagar"): ("018-ubddib", "Dikhow at Sivasagar", "high"),
    ("sivasagar", "nazira"): ("018-ubddib", "Dikhow at Sivasagar downstream", "medium"),
    ("sonitpur", "chariduar"): ("030-UBDDIB", "Jiabharali at NT Road Crossing", "high"),
}

CIRCLE_ALIASES = {
    "Bagibari": "Bagribari (Pt)",
    "Baksa": "Baska",
    "Biswanath Chariali": "Biswanath",
    "Boikakhat": "Bokakhat",
    "Chaygaon": "Chhaygaon",
    "Chengar": "Chenga",
    "Demow": "Dimow",
    "Halem": "Helem",
    "Marigaon": "Morigaon",
    "Naharkatia": "Naharkatiya",
    "Palashbari": "Palasbari",
    "Sivasagar": "Sibsagar",
    "Sivsagar": "Sibsagar",
    "Sonari RC part": "Sonari",
    "Tingkhang": "Tingkhong",
}


def fold(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


CIRCLE_ALIAS_LOOKUP = {fold(key): value for key, value in CIRCLE_ALIASES.items()}


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def census_rows(path: Path) -> tuple[list[dict[str, str]], str]:
    import xlrd

    payload = path.read_bytes()
    sheet = xlrd.open_workbook(file_contents=payload).sheet_by_index(0)
    rows: list[dict[str, str]] = []
    district = ""
    circle = ""
    for index in range(2, sheet.nrows):
        row = [str(value).strip() for value in sheet.row_values(index)]
        district_code, circle_code, village_code, name = row[6:10]
        if district_code != "000" and circle_code == "00000":
            district = name
            continue
        if circle_code != "00000" and village_code == "000000":
            circle = name
            continue
        if village_code != "000000":
            rows.append(
                {
                    "district": district,
                    "circle": circle,
                    "village": name,
                    "census_district_code": district_code,
                    "census_subdistrict_code": circle_code,
                    "census_village_code": village_code,
                }
            )
    return rows, hashlib.sha256(payload).hexdigest()


def udise_centres(path: Path) -> dict[tuple[str, str], list[tuple[float, float]]]:
    """School coordinates per district-and-village-name key.

    A key whose schools are scattered is thrown away rather than averaged. The
    district is too coarse to separate repeated village names inside it, so a
    name can collect schools 100 km apart, and the median of those lands in
    empty ground between them. See `axom_flood.udise.villages`.
    """
    points: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                point = (float(row["longitude"]), float(row["latitude"]))
            except (TypeError, ValueError):
                continue
            points[(fold(row["district"]), fold(row["village"]))].append(point)
    coherent = {
        key: kept
        for key, group in points.items()
        if (kept := coherent_village_points(group))
    }
    return defaultdict(list, coherent)


def udise_district_key(value: str) -> str:
    key = fold(value)
    return UDISE_DISTRICT_ALIASES.get(key, key)


def midpoint(points: list[tuple[float, float]]) -> list[float]:
    return [round(median(p[0] for p in points), 6), round(median(p[1] for p in points), 6)]


def mapping_for(district: str, circle: str) -> tuple[str, str, str]:
    district_key = DISTRICT_ALIASES.get(fold(district), fold(district))
    default = GAUGES.get(district_key, ("", "", ""))
    return CIRCLE_OVERRIDES.get((district_key, fold(circle)), default)


def gauge_geometry(
    centroid: list[float],
    code: str,
    stations: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """How far the assigned gauge is, and whether something closer exists.

    Reported for every circle, not only the suspect ones. A reader who is told
    which instrument their reading comes from is owed how far away it is, and the
    number is the same number the audit uses — one source, not two.
    """
    here = [station for station in stations.values() if station.get("coordinates")]
    assigned = stations.get(code) if code else None
    distance = (
        round(haversine_km(centroid, assigned["coordinates"]), 1)
        if assigned and assigned.get("coordinates")
        else None
    )
    nearest_km = None
    nearest_code = None
    nearest_name = None
    for station in here:
        candidate = haversine_km(centroid, station["coordinates"])
        if nearest_km is None or candidate < nearest_km:
            nearest_km = candidate
            nearest_code = station["cwc_station_code"]
            nearest_name = station.get("site_name")
    # "Much nearer" means a different gauge, closer by a margin wide enough that
    # it cannot be explained by the centroid being a median of school points.
    much_nearer = (
        distance is not None
        and nearest_km is not None
        and nearest_code != code
        and distance - nearest_km > MUCH_NEARER_KM
    )
    return {
        "distance_km": distance,
        "nearest_gauge": nearest_code,
        "nearest_gauge_name": nearest_name,
        "nearest_gauge_km": round(nearest_km, 1) if nearest_km is not None else None,
        "far": distance is not None and distance > FAR_KM,
        "much_nearer_gauge_exists": much_nearer,
    }


def review_reason(geometry: dict[str, Any], claimed: str) -> str:
    """Why this record is in the queue, in the words a reviewer needs.

    A queue of 139 identical strings tells a hydrologist nothing about where to
    start. The distance is the sorting key, so it goes in the reason.
    """
    parts = []
    if geometry["much_nearer_gauge_exists"]:
        parts.append(
            f"assigned gauge is {geometry['distance_km']} km away while "
            f"{geometry['nearest_gauge_name']} sits {geometry['nearest_gauge_km']} km "
            "off — confirm which river drains this circle"
        )
    elif geometry["far"]:
        parts.append(
            f"assigned gauge is {geometry['distance_km']} km away, beyond the "
            f"{FAR_KM:.0f} km review threshold"
        )
    if geometry["far"] or geometry["much_nearer_gauge_exists"]:
        if claimed == "high":
            parts.append("claimed high confidence was demoted by the distance audit")
        return "; ".join(parts)
    return "river/topology mapping requires hydrology review"


def build(args: argparse.Namespace) -> None:
    villages, census_sha = census_rows(args.census_xls)
    reviewed = gauge_decisions.load(args.decisions)
    stations = load_station_reference(args.data_dir)
    if not stations:
        raise RuntimeError(
            f"no CWC station reference under {args.data_dir}/reference/cwc — the "
            "gauge-distance audit cannot run, and a build that skips it would "
            "publish the same unchecked mappings this audit exists to catch"
        )
    circle_outlines = load_circle_outlines()
    school_points = udise_centres(args.udise_csv)
    circle_points: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    district_points: dict[str, list[tuple[float, float]]] = defaultdict(list)
    exact: dict[str, list[float]] = {}
    for row in villages:
        key = (udise_district_key(row["district"]), fold(row["village"]))
        if points := school_points.get(key):
            centre = midpoint(points)
            exact[row["census_village_code"]] = centre
            circle_points[(row["district"], row["circle"])].append(tuple(centre))
            district_points[row["district"]].append(tuple(centre))

    circle_centres = {key: midpoint(points) for key, points in circle_points.items()}
    district_centres = {key: midpoint(points) for key, points in district_points.items()}
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in villages:
        grouped[(row["district"], row["circle"])].append(row)

    localities: list[dict[str, Any]] = []
    search: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    for (district, source_circle), circle_villages in sorted(grouped.items()):
        canonical = CIRCLE_ALIAS_LOOKUP.get(fold(source_circle), source_circle)
        centre = circle_centres.get((district, source_circle), district_centres.get(district))
        if centre is None:
            raise RuntimeError(f"no coordinate anchor for {district}/{source_circle}")
        # Computed before the geometry rather than with the rest of the record:
        # the centroid correction below is keyed by it, and `gauge_geometry`
        # measures from the corrected point.
        locality_id = f"{slug(district)}-{slug(canonical)}"
        # The median of matched village points lands outside the circle whenever
        # the name match picked up villages elsewhere in the state — Gohpur's sat
        # 100 km west, in Tezpur.
        centre, centre_method = corrected_centre(locality_id, centre, circle_outlines)
        code, basis, claimed_confidence = mapping_for(district, source_circle)
        decision = reviewed.get(locality_id)
        if decision is not None:
            code = gauge_decisions.gauge_for(decision, code)
        geometry = gauge_geometry(centre, code, stations)
        # Geometry cannot promote a mapping — only a reviewer can. It can
        # demote one, and that is the whole point: a claim of "high" that reads
        # from another basin is exactly the claim nobody was checking.
        mapping_confidence = (
            "unverified"
            if geometry["far"] or geometry["much_nearer_gauge_exists"]
            else (claimed_confidence or "unverified")
        )
        source_aliases = sorted(
            {
                value
                for value in [source_circle, *CIRCLE_ALIASES]
                if CIRCLE_ALIAS_LOOKUP.get(fold(value)) == canonical and value != canonical
            }
        )
        # The Census workbook spells districts as of 2011, so Sribhumi appears as
        # its former name Karimganj. Resolving through the canonical registry
        # keeps one spelling across the gauge feed and the locality registry,
        # instead of showing a user two names for their own district.
        #
        # locality_id deliberately keeps the Census-derived slug: the PWA and the
        # published bundles key on it, so it must stay stable even when the
        # district is renamed.
        canonical_district = DISTRICT_LOOKUP.get(fold(district))
        current_name = canonical_district[0] if canonical_district else district
        current_slug = canonical_district[1] if canonical_district else None
        assignment = {
            "method": "census_2011_parent",
            "source_url": None,
            "confidence": "high",
            "reviewed": False,
        }
        reassignment = DISTRICT_REASSIGNMENTS.get((district, canonical))
        if reassignment:
            # `district_confidence` is how sure we are which *district* this circle
            # belongs to. It used to be unpacked into `confidence`, the variable
            # holding how sure we are about the *gauge* — so every circle in the
            # seven post-2011 districts inherited "high" from a gazette lookup that
            # had nothing to say about rivers, was stamped reviewed, and dropped
            # out of the hydrology queue. Goreswar (Pt) read from a gauge 78 km
            # away under a reviewed label. Two different questions, two names.
            new_district, source_url, district_confidence = reassignment
            resolved = DISTRICT_LOOKUP.get(fold(new_district))
            if resolved is None:
                raise RuntimeError(
                    f"reassignment target {new_district!r} is not in the canonical "
                    "district registry"
                )
            current_name, current_slug = resolved
            assignment = {
                "method": "post_2011_district_reassignment",
                "source_url": source_url,
                "confidence": district_confidence,
                "reviewed": False,
            }
        locality = {
            "schema_version": 1,
            "locality_id": locality_id,
            "name_en": canonical,
            "name_as": None,
            "assamese_review": {"reviewed": False, "reviewed_by": None, "reviewed_at": None},
            "district": current_name,
            "district_slug": current_slug,
            "census_2011_district": district,
            "district_assignment": assignment,
            "revenue_circle": canonical,
            "source_aliases": source_aliases,
            "centroid": centre,
            "centroid_method": centre_method,
            "boundary_geojson_ref": None,
            "primary_gauge": code or None,
            "primary_gauge_mapping": {
                "confidence": mapping_confidence,
                "basis": basis or "No defensible river/topology mapping recorded",
                "method": "manual_river_topology",
                "reviewed": mapping_confidence == "high",
                **geometry,
            },
            "population_estimate": None,
            "flood_threshold_m": None,
            "flood_threshold_confidence": None,
            "flood_threshold_n_events": None,
        }
        # A reviewed decision is the only thing in this build that can call a
        # mapping checked, and it also takes the circle out of the queue: the
        # question has been answered, including the distance objection the
        # reviewer saw in their packet before deciding.
        if decision is not None:
            locality = gauge_decisions.apply(locality, decision, geometry)
            mapping_confidence = locality["primary_gauge_mapping"]["confidence"]
        localities.append(locality)
        if mapping_confidence not in {"high", gauge_decisions.NO_GAUGE_CONFIDENCE}:
            review.append(
                {
                    "locality_id": locality_id,
                    "district": district,
                    "revenue_circle": canonical,
                    "proposed_primary_gauge": code or None,
                    "confidence": mapping_confidence,
                    **geometry,
                    "basis": basis or None,
                    "review_reason": review_reason(geometry, claimed_confidence),
                }
            )
        for village in circle_villages:
            village_centre = exact.get(village["census_village_code"], centre)
            search.append(
                {
                    "village_name": village["village"],
                    "normalized_name": fold(village["village"]),
                    "locality_id": locality_id,
                    "revenue_circle": canonical,
                    "district": district,
                    "centre": village_centre,
                    "centre_confidence": (
                        "exact_village_school_median"
                        if village["census_village_code"] in exact
                        else "revenue_circle_fallback"
                    ),
                    "census_village_code": village["census_village_code"],
                }
            )

    for supplement in CURRENT_ADMIN_LOCALITIES:
        locality_id = supplement["locality_id"]
        if any(item["locality_id"] == locality_id for item in localities):
            raise RuntimeError(f"current-administration locality duplicates {locality_id}")
        # The hand-written supplements go through the same audit as the generated
        # ones. A mapping typed by a person is not a mapping checked by a person.
        decision = reviewed.get(locality_id)
        code = supplement["primary_gauge"]
        if decision is not None:
            code = gauge_decisions.gauge_for(decision, code)
        geometry = gauge_geometry(supplement["centroid"], code, stations)
        mapping_confidence = (
            "unverified"
            if geometry["far"] or geometry["much_nearer_gauge_exists"]
            else supplement["gauge_confidence"]
        )
        locality = {
            "schema_version": 1,
            "locality_id": locality_id,
            "name_en": supplement["name"],
            "name_as": None,
            "assamese_review": {"reviewed": False, "reviewed_by": None, "reviewed_at": None},
            "district": supplement["district"],
            "district_slug": supplement["district_slug"],
            "census_2011_district": None,
            "district_assignment": {
                "method": "current_district_administration",
                "source_url": supplement["source_url"],
                "confidence": "high",
                "reviewed": True,
            },
            "revenue_circle": supplement["name"],
            "source_aliases": supplement["source_aliases"],
            "centroid": supplement["centroid"],
            "centroid_method": supplement["centroid_method"],
            "boundary_geojson_ref": None,
            "primary_gauge": code,
            "primary_gauge_mapping": {
                "confidence": mapping_confidence,
                "basis": supplement["gauge_basis"],
                "method": "manual_river_topology",
                "reviewed": False,
                **geometry,
            },
            "population_estimate": None,
            "flood_threshold_m": None,
            "flood_threshold_confidence": None,
            "flood_threshold_n_events": None,
        }
        if decision is not None:
            locality = gauge_decisions.apply(locality, decision, geometry)
            mapping_confidence = locality["primary_gauge_mapping"]["confidence"]
        district_positions = [
            index
            for index, item in enumerate(localities)
            if item["district"] == supplement["district"]
        ]
        insert_at = district_positions[-1] + 1 if district_positions else len(localities)
        localities.insert(insert_at, locality)
        if mapping_confidence not in {"high", gauge_decisions.NO_GAUGE_CONFIDENCE}:
            review.append(
                {
                    "locality_id": locality_id,
                    "district": supplement["district"],
                    "revenue_circle": supplement["name"],
                    "proposed_primary_gauge": supplement["primary_gauge"],
                    "confidence": mapping_confidence,
                    **geometry,
                    "basis": supplement["gauge_basis"],
                    "review_reason": review_reason(
                        geometry, supplement["gauge_confidence"]
                    ),
                }
            )
    provenance = {
        "administrative_source": "Census of India 2011 MDDS Assam rural directory",
        "administrative_source_url": CENSUS_SOURCE,
        "administrative_source_sha256": census_sha,
        "centre_source": "Recorded UDISE school-coordinate snapshot",
        "centre_source_path": str(args.udise_csv),
        "administrative_vintage": "2011",
        "post_2011_district_reassignment": (
            "Districts created after the 2011 Census are resolved from their "
            "administrations' own published revenue-circle lists. Districts with "
            "no evidenced circle are listed in districts_without_evidenced_circles "
            "rather than assigned by inference."
        ),
        "districts_without_evidenced_circles": {
            name: {"source_checked": url, "reason": reason}
            for name, (url, reason) in sorted(UNEVIDENCED_DISTRICTS.items())
        },
        "gauge_distance_audit": (
            f"Every circle's distance to its assigned gauge is measured against the "
            f"recorded CWC station reference. A mapping more than {FAR_KM:.0f} km away, "
            f"or more than {MUCH_NEARER_KM:.0f} km further than the nearest station, is "
            "forced to unverified and queued for hydrology review regardless of what "
            "the mapping table claimed. Distance is a smoke alarm, not a river model: "
            "it never promotes a mapping and never picks a replacement gauge."
        ),
        "gauge_topology_review": (
            "A circle whose mapping was decided by a person reads "
            "method reviewed_river_topology and carries the reviewer, their stated "
            "qualification, and their reasoning. Those circles skip the distance "
            "demotion, because the reviewer saw the distance before deciding. "
            "Decisions are the only path that can mark a mapping reviewed. Source: "
            f"{DECISIONS.relative_to(ROOT)}, {len(reviewed)} decided."
        ),
    }
    locality_provenance = {
        **provenance,
        "current_administration_supplements": [
            {
                "locality_id": item["locality_id"],
                "source_url": item["source_url"],
                "reason": (
                    "Current revenue circle omitted from the Census rural directory "
                    "used as the base registry"
                ),
            }
            for item in CURRENT_ADMIN_LOCALITIES
        ],
    }
    locality_doc = {
        "schema_version": 1,
        "provenance": locality_provenance,
        "localities": localities,
    }
    village_doc = {"schema_version": 1, "provenance": provenance, "villages": search}
    review_doc = {
        "schema_version": 1,
        "queue": "primary_gauge_mapping",
        "records": review,
    }
    for path, value in [
        (args.localities_out, locality_doc),
        (args.villages_out, village_doc),
        (args.review_out, review_doc),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--census-xls", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--decisions", type=Path, default=DECISIONS)
    parser.add_argument(
        "--udise-csv",
        type=Path,
        default=Path(
            "data/reference/udise/"
            "assam-schools-6570f268f67197d42ce3584f6e54ca703c4dca348ec0d8a960f10e479bfb888d.csv"
        ),
    )
    parser.add_argument(
        "--localities-out", type=Path, default=Path("config/assam-localities.json")
    )
    parser.add_argument(
        "--villages-out",
        type=Path,
        default=Path("config/assam-village-search-index.json"),
    )
    parser.add_argument(
        "--review-out",
        type=Path,
        default=Path("data/review/locality-gauge-mappings/current.json"),
    )
    build(parser.parse_args())


if __name__ == "__main__":
    main()
