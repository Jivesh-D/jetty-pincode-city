import csv
import logging
import statistics
from functools import lru_cache
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent
WAREHOUSE_CSV = DATA_DIR / "warehouse.csv"
LOCALITIES_CSV = DATA_DIR / "localities.csv"

# Generous bounding box around India (incl. Andaman & Nicobar and Lakshadweep).
# Rows outside it are dropped rather than plotted somewhere absurd.
MIN_LAT, MAX_LAT = 5.0, 38.0
MIN_LON, MAX_LON = 66.0, 98.0

# A darkstore is assigned to the warehouse site of its own labeled
# dc_blinkit_internal_city when one exists -- that label is Blinkit's own
# operational grouping -- unless a different site is closer by more than this
# many km, which indicates the label is wrong (e.g. a "mumbai"-labeled store
# physically sitting in Nashik). Darkstores in cities with no warehouse
# attach to the nearest site by distance.
LABEL_OVERRIDE_KM = 25.0

# Assignments beyond this distance are flagged as remote in the place stats.
REMOTE_KM = 50.0

EARTH_RADIUS_KM = 6371.0088


class PlaceOfSupplyDataError(RuntimeError):
    """Raised when a source CSV is missing or unreadable."""


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rlat1, rlon1, rlat2, rlon2 = map(radians, (lat1, lon1, lat2, lon2))
    h = sin((rlat2 - rlat1) / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin((rlon2 - rlon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(h))


def _parse_coordinate(lat_raw: str | None, lon_raw: str | None) -> tuple[float, float] | None:
    try:
        lat = float((lat_raw or "").strip())
        lon = float((lon_raw or "").strip())
    except ValueError:
        return None

    if not (MIN_LAT <= lat <= MAX_LAT and MIN_LON <= lon <= MAX_LON):
        return None

    return lat, lon


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise PlaceOfSupplyDataError(f"Missing data file: {path.name}")

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError as exc:
        raise PlaceOfSupplyDataError(f"Could not read {path.name}: {exc}") from exc


def _load_warehouses() -> list[dict[str, object]]:
    points: list[dict[str, object]] = []
    skipped = 0

    for row in _read_rows(WAREHOUSE_CSV):
        coordinate = _parse_coordinate(row.get("latitude"), row.get("longitude"))
        if coordinate is None:
            skipped += 1
            continue

        lat, lon = coordinate
        points.append(
            {
                "id": (row.get("dc_blinkit_warehouse_id") or "").strip(),
                "name": (row.get("warehouse") or "").strip(),
                "city": (row.get("dc_blinkit_internal_city") or "").strip(),
                "lat": lat,
                "lon": lon,
            }
        )

    if skipped:
        logger.warning("place-of-supply: skipped %d warehouse row(s) with bad coordinates", skipped)

    return points


def _load_localities() -> list[dict[str, object]]:
    points: list[dict[str, object]] = []
    skipped = 0

    for row in _read_rows(LOCALITIES_CSV):
        coordinate = _parse_coordinate(row.get("latitude"), row.get("longitude"))
        if coordinate is None:
            skipped += 1
            continue

        lat, lon = coordinate
        points.append(
            {
                "store_id": (row.get("store_id") or "").strip(),
                "store_name": (row.get("store_name") or "").strip(),
                "city": (row.get("dc_blinkit_internal_city") or "").strip(),
                "lat": lat,
                "lon": lon,
            }
        )

    if skipped:
        logger.warning("place-of-supply: skipped %d locality row(s) with bad coordinates", skipped)

    return points


def _convex_hull(points: list[tuple[float, float]]) -> list[list[float]] | None:
    """Monotone-chain convex hull; None for degenerate (<3 distinct / collinear)."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return None

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)

    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    hull = lower[:-1] + upper[:-1]
    if len(hull) < 3:
        return None
    return [[round(lat, 6), round(lon, 6)] for lat, lon in hull]


def _slug(text: str) -> str:
    return "-".join(text.lower().split())


def _compute_places(
    warehouses: list[dict[str, object]], localities: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Group warehouses into supply sites and assign every darkstore to one.

    Every warehouse in a city shares a single placeholder coordinate in the
    source data (101 unique coordinates for 101 cities), so one site per
    unique coordinate is the finest granularity the data supports.
    """
    # One site per unique warehouse coordinate.
    site_by_coord: dict[tuple[float, float], dict[str, object]] = {}
    for index, warehouse in enumerate(warehouses):
        key = (warehouse["lat"], warehouse["lon"])
        site = site_by_coord.setdefault(
            key, {"lat": key[0], "lon": key[1], "cities": set(), "warehouses": []}
        )
        site["cities"].add(warehouse["city"])
        site["warehouses"].append(index)

    sites = list(site_by_coord.values())
    site_by_city: dict[str, int] = {}
    for site_index, site in enumerate(sites):
        for city in site["cities"]:
            site_by_city[city] = site_index

    # Assign each darkstore: own-city site unless another is far closer.
    assignments: list[tuple[int, float, str]] = []  # (site_index, km, basis)
    for locality in localities:
        distances = [
            _haversine_km(locality["lat"], locality["lon"], site["lat"], site["lon"])
            for site in sites
        ]
        nearest = min(range(len(sites)), key=distances.__getitem__)

        own = site_by_city.get(locality["city"])
        if own is None:
            assignments.append((nearest, distances[nearest], "nearest"))
        elif distances[own] - distances[nearest] > LABEL_OVERRIDE_KM:
            assignments.append((nearest, distances[nearest], "label-overridden"))
        else:
            basis = "label" if own != nearest else "label+nearest"
            assignments.append((own, distances[own], basis))

    # Build the place records.
    places: list[dict[str, object]] = []
    for site_index, site in enumerate(sites):
        cities = sorted(site["cities"])
        name = " / ".join(cities)
        member_localities = [
            (loc_index, km)
            for loc_index, (assigned, km, _) in enumerate(assignments)
            if assigned == site_index
        ]
        distances_km = [km for _, km in member_localities]

        hull_points = [(site["lat"], site["lon"])] + [
            (localities[i]["lat"], localities[i]["lon"]) for i, _ in member_localities
        ]

        place = {
            "id": _slug(cities[0]),
            "name": name,
            "lat": round(site["lat"], 6),
            "lon": round(site["lon"], 6),
            "warehouse_count": len(site["warehouses"]),
            "locality_count": len(member_localities),
            "median_km": round(statistics.median(distances_km), 1) if distances_km else 0.0,
            "max_km": round(max(distances_km), 1) if distances_km else 0.0,
            "remote_count": sum(1 for km in distances_km if km > REMOTE_KM),
            "hull": _convex_hull(hull_points),
        }
        places.append(place)

        for warehouse_index in site["warehouses"]:
            warehouses[warehouse_index]["pos"] = place["id"]
        for loc_index, km in member_localities:
            localities[loc_index]["pos"] = place["id"]
            localities[loc_index]["dist_km"] = round(km, 2)
    for locality, (_, _, basis) in zip(localities, assignments):
        locality["basis"] = basis

    places.sort(key=lambda p: (-p["locality_count"], p["id"]))
    return places


@lru_cache(maxsize=1)
def load_points() -> dict[str, list[dict[str, object]]]:
    """Parse both source CSVs once per process and return map-ready points
    with their place-of-supply assignment."""
    warehouses = _load_warehouses()
    localities = _load_localities()
    places = _compute_places(warehouses, localities)
    logger.info(
        "place-of-supply: %d warehouses, %d localities, %d places",
        len(warehouses),
        len(localities),
        len(places),
    )
    return {"warehouses": warehouses, "localities": localities, "places": places}


def build_mapping_csv() -> str:
    """Flat CSV of every warehouse and darkstore with its place-of-supply."""
    import io

    data = load_points()
    place_by_id = {p["id"]: p for p in data["places"]}

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "kind",
            "id",
            "name",
            "dc_blinkit_internal_city",
            "latitude",
            "longitude",
            "place_of_supply",
            "assignment_basis",
            "distance_km",
            "pos_warehouse_count",
            "pos_locality_count",
        ]
    )
    for w in data["warehouses"]:
        place = place_by_id[w["pos"]]
        writer.writerow(
            [
                "warehouse", w["id"], w["name"], w["city"], w["lat"], w["lon"],
                w["pos"], "site", "", place["warehouse_count"], place["locality_count"],
            ]
        )
    for l in data["localities"]:
        place = place_by_id[l["pos"]]
        writer.writerow(
            [
                "darkstore", l["store_id"], l["store_name"], l["city"], l["lat"], l["lon"],
                l["pos"], l["basis"], l["dist_km"], place["warehouse_count"], place["locality_count"],
            ]
        )
    return buffer.getvalue()
