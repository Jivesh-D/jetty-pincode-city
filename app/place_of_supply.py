import csv
import logging
import statistics
from functools import lru_cache
from math import asin, ceil, cos, floor, pi, radians, sin, sqrt
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent
WAREHOUSE_CSV = DATA_DIR / "warehouse.csv"
LOCALITIES_CSV = DATA_DIR / "localities.csv"

# Generous bounding box around India (incl. Andaman & Nicobar and Lakshadweep).
# Rows outside it are dropped rather than plotted somewhere absurd.
MIN_LAT, MAX_LAT = 5.0, 38.0
MIN_LON, MAX_LON = 66.0, 98.0

# Only warehouses flagged is_active=1 in warehouse.csv actually ship stock to
# darkstores, so only those define places of supply. Dormant warehouses are
# still carried through the mapping -- they get assigned to whichever place
# now covers them -- but they never create a place, never move a boundary and
# never size an area.
ACTIVE_VALUES = {"1", "true", "yes", "y", "t"}

# A darkstore is assigned to the place of its own dc_blinkit_internal_city
# when that city has an active warehouse -- that label is Blinkit's own
# operational grouping -- unless a different place is closer by more than this
# many km, which indicates the label is wrong (e.g. a "mumbai"-labeled store
# physically sitting in Nashik). Points in cities with no active warehouse
# attach to the nearest place by distance.
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
                "is_active": (row.get("is_active") or "").strip().lower() in ACTIVE_VALUES,
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
# A place's area starts as the smallest region enclosing everything it
# supplies: the convex hull of its active warehouse sites and every darkstore
# assigned to it, expanded by a small margin so points sit inside the shape
# rather than on its edge. One place is one shape in one colour.
#
# Hulls are convex, so two of them can overlap where Blinkit's city label sends
# a darkstore across a border -- most visibly in Delhi NCR. Overlapping fills
# would layer on top of each other and misreport who supplies the contested
# ground, so the hulls are resolved into a partition: the map is rasterised,
# and any cell claimed by more than one hull is awarded to the place whose own
# served points lie nearest. Because a darkstore is at zero distance from
# itself, that rule cannot pull ground out from under the store that put it
# there -- every point stays inside its own place's area, and no two areas
# share any ground at all.
#
# Geometry is done in a single equirectangular km-plane.

_KM_PER_DEG_LAT = 110.574
_KM_PER_DEG_LON = 111.320

# Margin added around the hull, so a warehouse or darkstore on the boundary
# sits inside the shaded area instead of on the line. Kept small: the point of
# the hull is to be the *minimum* enclosing shape.
_HULL_PAD_KM = 3.0

# Points used to round each hull corner when the margin is applied.
_HULL_ARC_STEPS = 10

# Raster pitch used to resolve overlapping hulls into a partition, and so the
# resolution of any boundary between two neighbouring places.
_GRID_KM = 1.5

# Boundary simplification. Above the cell size, so the long straight run of a
# hull edge collapses back to a straight line instead of a staircase.
_SIMPLIFY_KM = 2.0

# Rings smaller than this are dropped as raster slivers.
_MIN_RING_KM2 = 60.0

# Places whose areas touch, or come within this distance, are given
# different colours.
_COLOR_GAP_KM = 25.0

# A place is called out as an exception when its ground-per-warehouse is this
# many times off the national median -- the sparse single-warehouse regions
# (one site covering a whole state) and the dense metros where several
# warehouses share one city.
_AREA_BALANCE_TOLERANCE = 2.0


def _project(lat: float, lon: float, cos_ref: float) -> tuple[float, float]:
    return (lon * _KM_PER_DEG_LON * cos_ref, lat * _KM_PER_DEG_LAT)


def _unproject(x: float, y: float, cos_ref: float) -> tuple[float, float]:
    return (y / _KM_PER_DEG_LAT, x / (_KM_PER_DEG_LON * cos_ref))


def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Andrew's monotone chain; returns the hull counter-clockwise."""
    unique = sorted(set(points))
    if len(unique) <= 2:
        return unique

    def half(sequence: list[tuple[float, float]]) -> list[tuple[float, float]]:
        chain: list[tuple[float, float]] = []
        for point in sequence:
            while len(chain) >= 2:
                (x1, y1), (x2, y2) = chain[-2], chain[-1]
                cross = (x2 - x1) * (point[1] - y1) - (y2 - y1) * (point[0] - x1)
                if cross > 0:
                    break
                chain.pop()
            chain.append(point)
        return chain

    lower = half(unique)
    upper = half(unique[::-1])
    return lower[:-1] + upper[:-1]


def _expand_hull(hull: list[tuple[float, float]], pad: float) -> list[tuple[float, float]]:
    """Grow a hull outward by `pad` in every direction.

    The Minkowski sum of a convex set with a disk is exactly the convex hull of
    the vertices ringed by that disk, so stamping a small circle on each vertex
    and re-hulling gives a correctly rounded margin -- and handles the
    degenerate one- and two-point hulls (a lone site becomes a disk) for free.
    """
    if not hull:
        return []
    stamped = [
        (x + pad * cos(2 * pi * k / _HULL_ARC_STEPS), y + pad * sin(2 * pi * k / _HULL_ARC_STEPS))
        for x, y in hull
        for k in range(_HULL_ARC_STEPS)
    ]
    return _convex_hull(stamped)


def _polygon_area_km2(ring: list[tuple[float, float]]) -> float:
    total = 0.0
    for i in range(len(ring)):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % len(ring)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2


def _hull_cells(hull: list[tuple[float, float]]):
    """Grid cells whose centre lies inside a convex ring.

    Scanned row by row: a horizontal line meets a convex polygon in exactly one
    span, so each row costs one pass over the edges instead of a containment
    test per cell.
    """
    if len(hull) < 3:
        return

    ys = [y for _, y in hull]
    first = int((min(ys) - _GRID_KM) // _GRID_KM)
    last = int((max(ys) + _GRID_KM) // _GRID_KM)

    count = len(hull)
    for row in range(first, last + 1):
        y = (row + 0.5) * _GRID_KM
        lo, hi = float("inf"), -float("inf")
        for i in range(count):
            (x1, y1), (x2, y2) = hull[i], hull[(i + 1) % count]
            if (y1 > y) == (y2 > y):
                continue
            x = x1 + (y - y1) / (y2 - y1) * (x2 - x1)
            if x < lo:
                lo = x
            if x > hi:
                hi = x
        if lo > hi:
            continue
        # Columns whose centre falls in [lo, hi], without testing each one.
        start = ceil(lo / _GRID_KM - 0.5)
        stop = floor(hi / _GRID_KM - 0.5)
        for column in range(start, stop + 1):
            yield (column, row)


def _trace_labelled_rings(
    cells: set[tuple[int, int]], owner: dict[tuple[int, int], int], mine: int
) -> list[list[tuple[tuple[int, int], object]]]:
    """Outline one place's cells, tagging every boundary step with the place on
    the far side (None where it faces open ground).

    Each cell edge with a different owner behind it becomes a directed segment,
    wound so this place is on the left; chaining them start-to-end yields one
    ring per connected boundary.
    """
    edges: dict[tuple[int, int], list[tuple[tuple[int, int], object]]] = {}
    for gx, gy in cells:
        for neighbour, start, end in (
            ((gx, gy - 1), (gx, gy), (gx + 1, gy)),
            ((gx + 1, gy), (gx + 1, gy), (gx + 1, gy + 1)),
            ((gx, gy + 1), (gx + 1, gy + 1), (gx, gy + 1)),
            ((gx - 1, gy), (gx, gy + 1), (gx, gy)),
        ):
            if owner.get(neighbour) != mine:
                edges.setdefault(start, []).append((end, owner.get(neighbour)))

    rings: list[list[tuple[tuple[int, int], object]]] = []
    for origin in list(edges):
        while edges.get(origin):
            node, label = edges[origin].pop()
            ring = [(origin, label)]
            while node != origin:
                outgoing = edges.get(node)
                if not outgoing:
                    ring = []
                    break
                if len(outgoing) == 1:
                    following, label = outgoing.pop()
                else:
                    # Two cells meeting corner to corner give this vertex two
                    # exits; take the sharpest right turn so the walk hugs this
                    # ring instead of hopping onto the other.
                    ax, ay = node[0] - ring[-1][0][0], node[1] - ring[-1][0][1]
                    pick = min(
                        range(len(outgoing)),
                        key=lambda k: (
                            -(ax * (outgoing[k][0][1] - node[1]) - ay * (outgoing[k][0][0] - node[0])),
                            -(ax * (outgoing[k][0][0] - node[0]) + ay * (outgoing[k][0][1] - node[1])),
                        ),
                    )
                    following, label = outgoing.pop(pick)
                ring.append((node, label))
                node = following
            if len(ring) >= 4:
                rings.append(ring)
    return rings


def _simplify_shared(
    ring: list[tuple[tuple[int, int], object]],
    mine: int,
    cache: dict[object, list[tuple[int, int]]],
    strict: set[int],
) -> list[tuple[float, float]]:
    """Simplify a ring one border at a time, reusing the line each border got
    the first time it was seen.

    A border between two places is walked once by each of them, in opposite
    directions. Simplifying the two walks independently lets them disagree by
    up to the tolerance and lay one area over the other; caching the result
    under a direction-free key makes both sides reuse the identical line, so
    the areas stay exactly disjoint however hard they are simplified.
    """
    # Split the ring into maximal runs that face the same neighbour.
    labels = [label for _, label in ring]
    start = next((i for i in range(len(labels)) if labels[i] != labels[i - 1]), None)
    if start is None:
        runs = [list(range(len(ring)))]
    else:
        order = list(range(start, len(ring))) + list(range(start))
        runs, current = [], [order[0]]
        for index in order[1:]:
            if labels[index] == labels[current[-1]]:
                current.append(index)
            else:
                runs.append(current)
                current = [index]
        runs.append(current)

    out: list[tuple[float, float]] = []
    for run in runs:
        vertices = [ring[i][0] for i in run]
        vertices.append(ring[(run[-1] + 1) % len(ring)][0])
        other = ring[run[0]][1]
        # A border touching a place that stranded one of its own points is kept
        # exactly as traced; both sides agree because strictness is decided
        # from the pair, not from who is drawing.
        tolerance = (
            0.0
            if mine in strict or other in strict
            else _SIMPLIFY_KM / _GRID_KM
        )
        if other is None:
            # Faces open ground -- nobody else draws this line.
            simple = _simplify_open(vertices, tolerance)
        else:
            forward = tuple(vertices)
            backward = tuple(reversed(vertices))
            flipped = backward < forward
            key = (min(mine, other), max(mine, other), backward if flipped else forward)
            if key not in cache:
                cache[key] = _simplify_open(list(backward if flipped else forward), tolerance)
            simple = list(reversed(cache[key])) if flipped else list(cache[key])
        out.extend((x * _GRID_KM, y * _GRID_KM) for x, y in simple[:-1])
    return out


def _simplify_open(
    line: list[tuple[float, float]], tolerance: float
) -> list[tuple[float, float]]:
    """Douglas-Peucker on an open polyline, endpoints pinned."""
    if len(line) < 3:
        return line
    keep = [False] * len(line)
    keep[0] = keep[-1] = True
    stack = [(0, len(line) - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi <= lo + 1:
            continue
        (x1, y1), (x2, y2) = line[lo], line[hi]
        dx, dy = x2 - x1, y2 - y1
        norm = (dx * dx + dy * dy) ** 0.5
        worst, worst_i = -1.0, lo
        for i in range(lo + 1, hi):
            x, y = line[i]
            d = (
                abs(dy * x - dx * y + x2 * y1 - y2 * x1) / norm
                if norm
                else ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
            )
            if d > worst:
                worst, worst_i = d, i
        if worst > tolerance:
            keep[worst_i] = True
            stack.extend(((lo, worst_i), (worst_i, hi)))
    return [pt for pt, k in zip(line, keep) if k]


def _signed_area_km2(ring: list[tuple[float, float]]) -> float:
    total = 0.0
    for i in range(len(ring)):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % len(ring)]
        total += x1 * y2 - x2 * y1
    return total / 2


def _point_in_ring(point: tuple[float, float], ring: list[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    for i in range(len(ring)):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % len(ring)]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) / (y2 - y1) * (x2 - x1):
            inside = not inside
    return inside


def _hull_gap_km(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> float:
    """Separating-axis distance between two convex rings; <=0 when they overlap."""
    best = -float("inf")
    for subject, other in ((a, b), (b, a)):
        count = len(subject)
        for i in range(count):
            (x1, y1), (x2, y2) = subject[i], subject[(i + 1) % count]
            ex, ey = x2 - x1, y2 - y1
            length = (ex * ex + ey * ey) ** 0.5
            if length == 0:
                continue
            nx, ny = ey / length, -ex / length
            hi = max(nx * (x - x1) + ny * (y - y1) for x, y in subject)
            lo = min(nx * (x - x1) + ny * (y - y1) for x, y in other)
            best = max(best, lo - hi)
    return best


def _assign_colors(hulls: list[list[tuple[float, float]]]) -> list[int]:
    """Greedy graph colouring so no two touching or near places share a tint."""
    count = len(hulls)
    neighbours: list[set[int]] = [set() for _ in range(count)]
    for i in range(count):
        for j in range(i + 1, count):
            if hulls[i] and hulls[j] and _hull_gap_km(hulls[i], hulls[j]) < _COLOR_GAP_KM:
                neighbours[i].add(j)
                neighbours[j].add(i)

    colors = [-1] * count
    for index in sorted(range(count), key=lambda i: -len(neighbours[i])):
        taken = {colors[n] for n in neighbours[index] if colors[n] >= 0}
        colors[index] = next(c for c in range(count) if c not in taken)
    return colors


def _place_areas(
    served: list[list[tuple[float, float]]], cos_ref: float
) -> tuple[list[list[list[list[float]]]], list[float], list[int], int]:
    """Rings, area and colour index per place, plus the contested km2 resolved.

    Areas are a strict partition: every grid cell belongs to exactly one place,
    and every shared border is simplified once and reused by both sides, so no
    two areas overlap anywhere.
    """
    hulls = [_expand_hull(_convex_hull(points), _HULL_PAD_KM) for points in served]

    # Claim staking. A cell inside a single hull is settled; a cell inside
    # several goes to whichever place has a served point nearest to it.
    owner: dict[tuple[int, int], int] = {}
    claims: dict[tuple[int, int], list[int]] = {}
    for index, hull in enumerate(hulls):
        for cell in _hull_cells(hull):
            previous = owner.setdefault(cell, index)
            if previous != index:
                claims.setdefault(cell, [previous]).append(index)

    for cell, claimants in claims.items():
        px, py = (cell[0] + 0.5) * _GRID_KM, (cell[1] + 0.5) * _GRID_KM
        winner, best = claimants[0], float("inf")
        for index in claimants:
            for x, y in served[index]:
                distance = (x - px) ** 2 + (y - py) ** 2
                if distance < best:
                    winner, best = index, distance
        owner[cell] = winner
    contested = len(claims)

    # A cell is awarded on its centre, which can hand the ground under a
    # darkstore to a neighbour whose own points sit closer to that centre. The
    # cell a point occupies is therefore pinned to that point's place, so every
    # warehouse and darkstore is guaranteed to lie inside its own area. Where
    # two places both have a point in one cell the nearer to the centre keeps
    # it -- unavoidable at any finite resolution, and reported by the caller.
    pinned: dict[tuple[int, int], tuple[float, int]] = {}
    for index, points in enumerate(served):
        for x, y in points:
            cell = (int(x // _GRID_KM), int(y // _GRID_KM))
            px, py = (cell[0] + 0.5) * _GRID_KM, (cell[1] + 0.5) * _GRID_KM
            distance = (x - px) ** 2 + (y - py) ** 2
            if cell not in pinned or distance < pinned[cell][0]:
                pinned[cell] = (distance, index)
    for cell, (_, index) in pinned.items():
        owner[cell] = index

    by_place: list[set[tuple[int, int]]] = [set() for _ in hulls]
    for cell, index in owner.items():
        by_place[index].add(cell)

    def build(strict: set[int]) -> list[list[list[tuple[float, float]]]]:
        cache: dict[object, list[tuple[int, int]]] = {}
        built: list[list[list[tuple[float, float]]]] = []
        for index, cells in enumerate(by_place):
            outers: list[list[tuple[float, float]]] = []
            holes: list[list[tuple[float, float]]] = []
            for ring in _trace_labelled_rings(cells, owner, index):
                simple = _simplify_shared(ring, index, cache, strict)
                if len(simple) < 3:
                    continue
                area = _signed_area_km2(simple)
                if abs(area) < _MIN_RING_KM2:
                    continue
                (outers if area > 0 else holes).append(simple)

            # Losing a contested lens can leave a place wrapped around a
            # neighbour; nest such a void into its enclosing ring so it renders
            # as a hole instead of as fill over that neighbour.
            outers.sort(key=lambda r: abs(_signed_area_km2(r)))
            polygons: list[list[list[tuple[float, float]]]] = [[ring] for ring in outers]
            for hole in holes:
                for position, ring in enumerate(outers):
                    if _point_in_ring(hole[0], ring):
                        polygons[position].append(hole)
                        break
            built.append(polygons)
        return built

    def stranded(built: list[list[list[tuple[float, float]]]]) -> set[int]:
        missing: set[int] = set()
        for index, points in enumerate(served):
            for point in points:
                if not any(
                    _point_in_ring(point, polygon[0])
                    and not any(_point_in_ring(point, h) for h in polygon[1:])
                    for polygon in built[index]
                ):
                    missing.add(index)
                    break
        return missing

    # Simplifying a border can shave the corner a point sits in. Any place that
    # loses one of its own points has its borders re-traced exactly; the pass
    # is idempotent because an unsimplified border follows the cells, and the
    # cells already contain every point.
    polygons_by_place = build(set())
    strict = stranded(polygons_by_place)
    if strict:
        polygons_by_place = build(strict)

    def to_latlon(ring: list[tuple[float, float]]) -> list[list[float]]:
        return [
            [round(lat, 6), round(lon, 6)]
            for lat, lon in (_unproject(x, y, cos_ref) for x, y in ring)
        ]

    rings_out = [
        [[to_latlon(r) for r in polygon] for polygon in polygons]
        for polygons in polygons_by_place
    ]
    areas_out = [len(cells) * (_GRID_KM * _GRID_KM) for cells in by_place]
    return rings_out, areas_out, _assign_colors(hulls), round(contested * (_GRID_KM * _GRID_KM))


def _slug(text: str) -> str:
    return "-".join(text.lower().split())


def _assign(
    lat: float,
    lon: float,
    city: str,
    sites: list[dict[str, object]],
    site_indices_by_place: list[list[int]],
    place_by_city: dict[str, int],
) -> tuple[int, int, float, str]:
    """Attach one point to a place. Returns (place, nearest site, km, basis)."""
    site_km = [_haversine_km(lat, lon, site["lat"], site["lon"]) for site in sites]
    place_km = [min(site_km[i] for i in indices) for indices in site_indices_by_place]

    nearest = min(range(len(place_km)), key=place_km.__getitem__)
    own = place_by_city.get(city)

    if own is None:
        place, basis = nearest, "nearest"
    elif place_km[own] - place_km[nearest] > LABEL_OVERRIDE_KM:
        place, basis = nearest, "label-overridden"
    else:
        place = own
        basis = "label+nearest" if own == nearest else "label"

    host = min(site_indices_by_place[place], key=lambda i: site_km[i])
    return place, host, place_km[place], basis


def _compute_places(
    warehouses: list[dict[str, object]], localities: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Define places of supply from the active warehouses, then attach every
    darkstore and every dormant warehouse to one.

    A *site* is one unique active-warehouse coordinate; a *place* is every site
    sharing a dc_blinkit_internal_city. Cities with no active warehouse do not
    become places -- nothing ships from them -- their points fall to whichever
    active place is nearest.
    """
    active = [w for w in warehouses if w["is_active"]]
    if not active:
        raise PlaceOfSupplyDataError(
            "No warehouse rows have is_active set; cannot define any place of supply"
        )

    # One site per unique active coordinate, grouped into places by city.
    sites: list[dict[str, object]] = []
    site_by_coord: dict[tuple[float, float], int] = {}
    place_by_city: dict[str, int] = {}
    site_indices_by_place: list[list[int]] = []
    place_cities: list[str] = []

    for index, warehouse in enumerate(active):
        city = warehouse["city"]
        if city not in place_by_city:
            place_by_city[city] = len(site_indices_by_place)
            site_indices_by_place.append([])
            place_cities.append(city)
        place = place_by_city[city]

        coord = (warehouse["lat"], warehouse["lon"])
        site_index = site_by_coord.get(coord)
        if site_index is None:
            site_index = len(sites)
            site_by_coord[coord] = site_index
            sites.append({"lat": coord[0], "lon": coord[1], "place": place, "warehouses": []})
            site_indices_by_place[place].append(site_index)
        sites[site_index]["warehouses"].append(index)

    place_of_site = [site["place"] for site in sites]
    place_count = len(site_indices_by_place)

    # Active warehouses define their own place; everything else is attached.
    for warehouse in active:
        warehouse["pos_index"] = place_by_city[warehouse["city"]]
        warehouse["basis"] = "site"
        warehouse["dist_km"] = 0.0
        warehouse["src_lat"] = warehouse["lat"]
        warehouse["src_lon"] = warehouse["lon"]

    inactive_counts = [0] * place_count
    for warehouse in warehouses:
        if warehouse["is_active"]:
            continue
        place, host, km, basis = _assign(
            warehouse["lat"], warehouse["lon"], warehouse["city"],
            sites, site_indices_by_place, place_by_city,
        )
        warehouse["pos_index"] = place
        warehouse["basis"] = basis
        warehouse["dist_km"] = round(km, 2)
        warehouse["src_lat"] = sites[host]["lat"]
        warehouse["src_lon"] = sites[host]["lon"]
        inactive_counts[place] += 1

    # Darkstores. `host` is the nearest site within the assigned place; it is
    # where the store's supply link starts.
    locality_km: list[list[float]] = [[] for _ in range(place_count)]
    served: list[list[tuple[float, float]]] = [[] for _ in range(place_count)]
    for locality in localities:
        place, host, km, basis = _assign(
            locality["lat"], locality["lon"], locality["city"],
            sites, site_indices_by_place, place_by_city,
        )
        locality["pos_index"] = place
        locality["basis"] = basis
        locality["dist_km"] = round(km, 2)
        # The site actually covering this store -- a place can hold several,
        # and a supply link drawn from the place's mean coordinate would start
        # in open country between them.
        locality["src_lat"] = sites[host]["lat"]
        locality["src_lon"] = sites[host]["lon"]
        locality_km[place].append(km)
        served[place].append((locality["lat"], locality["lon"]))

    # Geometry. The hull encloses the active sites and the darkstores they
    # serve. Dormant warehouses are deliberately left out: they are assigned to
    # a place but do not supply from it, and one shuttered site 300 km away
    # would stretch the whole area to reach it.
    site_points = [(site["lat"], site["lon"]) for site in sites]
    for site in sites:
        served[site["place"]].append((site["lat"], site["lon"]))

    cos_ref = cos(radians(sum(lat for lat, _ in site_points) / len(site_points)))
    served_xy = [[_project(lat, lon, cos_ref) for lat, lon in group] for group in served]
    place_rings, place_area_km2, place_color, contested_km2 = _place_areas(
        served_xy, cos_ref
    )
    if contested_km2:
        logger.info(
            "place-of-supply: %d km2 claimed by more than one hull, resolved to "
            "the nearest served point",
            contested_km2,
        )

    places: list[dict[str, object]] = []
    for place_index in range(place_count):
        members = site_indices_by_place[place_index]
        distances_km = locality_km[place_index]
        active_count = sum(len(sites[i]["warehouses"]) for i in members)
        area_km2 = place_area_km2[place_index]

        places.append(
            {
                "id": _slug(place_cities[place_index]),
                "name": place_cities[place_index],
                "lat": round(sum(sites[i]["lat"] for i in members) / len(members), 6),
                "lon": round(sum(sites[i]["lon"] for i in members) / len(members), 6),
                "site_count": len(members),
                "active_warehouse_count": active_count,
                "inactive_warehouse_count": inactive_counts[place_index],
                "warehouse_count": active_count + inactive_counts[place_index],
                "locality_count": len(distances_km),
                "median_km": round(statistics.median(distances_km), 1) if distances_km else 0.0,
                "max_km": round(max(distances_km), 1) if distances_km else 0.0,
                "remote_count": sum(1 for km in distances_km if km > REMOTE_KM),
                "area_km2": round(area_km2),
                "color_index": place_color[place_index],
                "km2_per_warehouse": round(area_km2 / active_count),
                "areas": place_rings[place_index],
            }
        )

    # Ground-per-warehouse is expected to be roughly flat: a place covering
    # twice the area should be running twice the warehouses. Places that are
    # far off the median are the exceptions -- sparse regions where one site
    # serves a whole state, and metros where several sites share one city.
    typical = statistics.median(p["km2_per_warehouse"] for p in places)
    for place in places:
        ratio = place["km2_per_warehouse"] / typical if typical else 1.0
        place["area_per_warehouse_ratio"] = round(ratio, 2)
        if ratio > _AREA_BALANCE_TOLERANCE:
            place["area_balance"] = "stretched"
        elif ratio < 1 / _AREA_BALANCE_TOLERANCE:
            place["area_balance"] = "concentrated"
        else:
            place["area_balance"] = "proportional"

    for point in (*warehouses, *localities):
        point["pos"] = places[point["pos_index"]]["id"]
        del point["pos_index"]

    places.sort(key=lambda p: (-p["locality_count"], p["id"]))
    return places


@lru_cache(maxsize=1)
def load_points() -> dict[str, list[dict[str, object]]]:
    """Parse both source CSVs once per process and return map-ready points
    with their place-of-supply assignment."""
    warehouses = _load_warehouses()
    localities = _load_localities()
    places = _compute_places(warehouses, localities)
    active = sum(1 for w in warehouses if w["is_active"])
    logger.info(
        "place-of-supply: %d warehouses (%d active), %d localities, %d places",
        len(warehouses),
        active,
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
            "is_active",
            "place_of_supply",
            "assignment_basis",
            "distance_km",
            "supply_site_latitude",
            "supply_site_longitude",
            "pos_active_warehouse_count",
            "pos_inactive_warehouse_count",
            "pos_locality_count",
            "pos_area_km2",
            "pos_km2_per_active_warehouse",
            "pos_area_balance",
        ]
    )

    def stats(place: dict[str, object]) -> list[object]:
        return [
            place["active_warehouse_count"],
            place["inactive_warehouse_count"],
            place["locality_count"],
            place["area_km2"],
            place["km2_per_warehouse"],
            place["area_balance"],
        ]

    for w in data["warehouses"]:
        place = place_by_id[w["pos"]]
        writer.writerow(
            [
                "warehouse", w["id"], w["name"], w["city"], w["lat"], w["lon"],
                1 if w["is_active"] else 0, w["pos"], w["basis"],
                "" if w["is_active"] else w["dist_km"],
                w["src_lat"], w["src_lon"], *stats(place),
            ]
        )
    for l in data["localities"]:
        place = place_by_id[l["pos"]]
        writer.writerow(
            [
                "darkstore", l["store_id"], l["store_name"], l["city"], l["lat"], l["lon"],
                "", l["pos"], l["basis"], l["dist_km"],
                l["src_lat"], l["src_lon"], *stats(place),
            ]
        )
    return buffer.getvalue()
