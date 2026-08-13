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


# --- Supply-area geometry ----------------------------------------------------
#
# Supply areas must partition the map: two areas may share a border but their
# interiors never intersect. Each place's area is therefore its Voronoi cell
# (every location nearer to this site than to any other site), clipped to a
# disk sized by how far the place's darkstores actually reach. Voronoi cells
# are pairwise disjoint by construction, and clipping only shrinks them.
#
# Geometry is done in a single equirectangular km-plane so every bisector is
# computed consistently; cells clipped to <=~200 km keep the projection error
# far below visual scale.

_KM_PER_DEG_LAT = 110.574
_KM_PER_DEG_LON = 111.320

_DISK_VERTICES = 48
_MIN_AREA_RADIUS_KM = 12.0

# Each cell is shrunk inward by this much, so adjacent areas end up separated
# by a real gap (2x this) instead of sharing a border. This is what makes the
# pairwise intersection exactly null rather than a shared line, and it
# absorbs the ~0.1 m vertex rounding introduced by the 6-decimal output.
_AREA_INSET_KM = 0.25


def _project(lat: float, lon: float, cos_ref: float) -> tuple[float, float]:
    return (lon * _KM_PER_DEG_LON * cos_ref, lat * _KM_PER_DEG_LAT)


def _unproject(x: float, y: float, cos_ref: float) -> tuple[float, float]:
    return (y / _KM_PER_DEG_LAT, x / (_KM_PER_DEG_LON * cos_ref))


def _clip_halfplane(
    polygon: list[tuple[float, float]],
    point: tuple[float, float],
    normal: tuple[float, float],
) -> list[tuple[float, float]]:
    """Sutherland-Hodgman clip keeping the side where (p - point) . normal >= 0."""

    def signed(p: tuple[float, float]) -> float:
        return (p[0] - point[0]) * normal[0] + (p[1] - point[1]) * normal[1]

    output: list[tuple[float, float]] = []
    count = len(polygon)
    for i in range(count):
        current, following = polygon[i], polygon[(i + 1) % count]
        d_current, d_following = signed(current), signed(following)
        if d_current >= 0:
            output.append(current)
            if d_following < 0:
                t = d_current / (d_current - d_following)
                output.append(
                    (
                        current[0] + t * (following[0] - current[0]),
                        current[1] + t * (following[1] - current[1]),
                    )
                )
        elif d_following >= 0:
            t = d_current / (d_current - d_following)
            output.append(
                (
                    current[0] + t * (following[0] - current[0]),
                    current[1] + t * (following[1] - current[1]),
                )
            )
    return output


def _inset_convex(
    polygon: list[tuple[float, float]], inset: float
) -> list[tuple[float, float]] | None:
    """Shrink a convex polygon inward by `inset`; None if it would vanish."""
    from math import hypot

    # Ensure counter-clockwise so the interior is to the left of each edge.
    signed_area = sum(
        polygon[i][0] * polygon[(i + 1) % len(polygon)][1]
        - polygon[(i + 1) % len(polygon)][0] * polygon[i][1]
        for i in range(len(polygon))
    )
    ring = polygon if signed_area > 0 else polygon[::-1]

    result = ring
    count = len(ring)
    for i in range(count):
        if len(result) < 3:
            return None
        (x1, y1), (x2, y2) = ring[i], ring[(i + 1) % count]
        length = hypot(x2 - x1, y2 - y1)
        if length == 0:
            continue
        # Inward (left) normal, moved in by `inset`.
        normal = (-(y2 - y1) / length, (x2 - x1) / length)
        anchor = (x1 + normal[0] * inset, y1 + normal[1] * inset)
        result = _clip_halfplane(result, anchor, normal)

    return result if len(result) >= 3 else None


def _voronoi_areas(
    site_points: list[tuple[float, float]], radii_km: list[float]
) -> list[list[list[float]] | None]:
    """One clipped Voronoi cell per site, as [[lat, lon], ...] rings."""
    from math import cos as _cos, pi, radians as _radians, sin as _sin

    if not site_points:
        return []

    lat_ref = sum(lat for lat, _ in site_points) / len(site_points)
    cos_ref = _cos(_radians(lat_ref))
    projected = [_project(lat, lon, cos_ref) for lat, lon in site_points]

    # Starting square generously containing every possible disk.
    xs = [x for x, _ in projected]
    ys = [y for _, y in projected]
    pad = max(radii_km) + 100.0
    box = [
        (min(xs) - pad, min(ys) - pad),
        (max(xs) + pad, min(ys) - pad),
        (max(xs) + pad, max(ys) + pad),
        (min(xs) - pad, max(ys) + pad),
    ]

    areas: list[list[list[float]] | None] = []
    for index, site in enumerate(projected):
        cell = box
        for other_index, other in enumerate(projected):
            if other_index == index or not cell:
                continue
            midpoint = ((site[0] + other[0]) / 2, (site[1] + other[1]) / 2)
            normal = (site[0] - other[0], site[1] - other[1])
            cell = _clip_halfplane(cell, midpoint, normal)

        # Clip to the reach disk (approximated by a convex polygon).
        radius = radii_km[index]
        for step in range(_DISK_VERTICES):
            angle = 2 * pi * step / _DISK_VERTICES
            edge_point = (site[0] + radius * _cos(angle), site[1] + radius * _sin(angle))
            inward = (-_cos(angle), -_sin(angle))
            if not cell:
                break
            cell = _clip_halfplane(cell, edge_point, inward)

        cell = _inset_convex(cell, _AREA_INSET_KM) or cell

        if len(cell) < 3:
            areas.append(None)
            continue
        areas.append(
            [
                [round(lat, 6), round(lon, 6)]
                for lat, lon in (_unproject(x, y, cos_ref) for x, y in cell)
            ]
        )
    return areas


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
        }
        places.append(place)

        for warehouse_index in site["warehouses"]:
            warehouses[warehouse_index]["pos"] = place["id"]
        for loc_index, km in member_localities:
            localities[loc_index]["pos"] = place["id"]
            localities[loc_index]["dist_km"] = round(km, 2)
    for locality, (_, _, basis) in zip(localities, assignments):
        locality["basis"] = basis

    # Disjoint supply areas: Voronoi cell per site, clipped to each place's
    # reach (how far its farthest darkstore is, lightly padded).
    site_points = [(p["lat"], p["lon"]) for p in places]
    radii = [max(_MIN_AREA_RADIUS_KM, p["max_km"] * 1.05 + 2.0) for p in places]
    for place, area in zip(places, _voronoi_areas(site_points, radii)):
        place["area"] = area

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
