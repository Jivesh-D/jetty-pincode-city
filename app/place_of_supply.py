import csv
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent
WAREHOUSE_CSV = DATA_DIR / "warehouse.csv"
LOCALITIES_CSV = DATA_DIR / "localities.csv"

# Generous bounding box around India (incl. Andaman & Nicobar and Lakshadweep).
# Rows outside it are dropped rather than plotted somewhere absurd.
MIN_LAT, MAX_LAT = 5.0, 38.0
MIN_LON, MAX_LON = 66.0, 98.0


class PlaceOfSupplyDataError(RuntimeError):
    """Raised when a source CSV is missing or unreadable."""


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


@lru_cache(maxsize=1)
def load_points() -> dict[str, list[dict[str, object]]]:
    """Parse both source CSVs once per process and return map-ready points."""
    return {
        "warehouses": _load_warehouses(),
        "localities": _load_localities(),
    }
