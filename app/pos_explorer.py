import csv
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent
SUMMARY_CSV = DATA_DIR / "place_of_supply.csv"
INVENTORY_DEEPDIVE_CSV = DATA_DIR / "place_of_supply_inventory_deepdive.csv"
PO_DEEPDIVE_CSV = DATA_DIR / "place_of_supply_po_deepdive.csv"


class PosExplorerDataError(RuntimeError):
    """Raised when a source CSV is missing or unreadable."""


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise PosExplorerDataError(f"Missing data file: {path.name}")

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError as exc:
        raise PosExplorerDataError(f"Could not read {path.name}: {exc}") from exc


@lru_cache(maxsize=1)
def load_summary_rows() -> list[dict[str, str]]:
    rows = _read_rows(SUMMARY_CSV)
    logger.info("pos-explorer: loaded %d summary rows", len(rows))
    return rows


def _build_index(path: Path, label: str) -> dict[str, list[dict[str, str]]]:
    index: dict[str, list[dict[str, str]]] = {}
    rows = _read_rows(path)
    for row in rows:
        index.setdefault(row.get("filter_key", ""), []).append(row)
    logger.info(
        "pos-explorer: loaded %d %s deepdive rows across %d filter keys",
        len(rows),
        label,
        len(index),
    )
    return index


@lru_cache(maxsize=1)
def _inventory_index() -> dict[str, list[dict[str, str]]]:
    return _build_index(INVENTORY_DEEPDIVE_CSV, "inventory")


@lru_cache(maxsize=1)
def _po_index() -> dict[str, list[dict[str, str]]]:
    return _build_index(PO_DEEPDIVE_CSV, "po")


def load_deepdive_rows(filter_key: str) -> dict[str, list[dict[str, str]]]:
    return {
        "inventory": _inventory_index().get(filter_key, []),
        "po": _po_index().get(filter_key, []),
    }
