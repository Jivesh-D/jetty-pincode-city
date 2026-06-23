"""Convert arbitrary-column NoonUAE sales CSV to normalized daily CSV."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

OUTPUT_COLUMNS = ("date", "platform_type", "item_id", "qty_sold", "revenue")


def read_csv_headers(content: bytes) -> list[str]:
    text = content.decode("utf-8-sig")
    if not text.strip():
        raise ValueError("CSV file is empty")

    reader = csv.reader(io.StringIO(text))
    row = next(reader, None)
    if not row:
        raise ValueError("CSV file has no header row")

    headers = [cell.strip() for cell in row]
    if not any(headers):
        raise ValueError("CSV header row is empty")

    return headers


def _parse_number(value: Any, *, field_name: str, row_num: int) -> float:
    if value is None:
        return 0.0

    text = str(value).strip()
    if not text:
        return 0.0

    text = text.replace(",", "")
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(
            f"Row {row_num}: invalid number in {field_name!r}: {value!r}"
        ) from exc


def _parse_iso_date(value: str, *, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: use YYYY-MM-DD") from exc


def convert_noon_uae_csv(
    content: bytes,
    *,
    platform_type_col: str,
    qty_sold_col: str,
    revenue_col: str,
    item_id_col: str,
    start_date: date,
    end_date: date,
) -> str:
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")

    text = content.decode("utf-8-sig")
    if not text.strip():
        raise ValueError("CSV file is empty")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("CSV file has no header row")

    header_map = {name.strip(): name for name in reader.fieldnames if name is not None}
    headers = list(header_map.keys())
    required_cols = {
        "platform_type": platform_type_col,
        "qty_sold": qty_sold_col,
        "revenue": revenue_col,
        "item_id": item_id_col,
    }
    missing = [name for name, col in required_cols.items() if col not in headers]
    if missing:
        raise ValueError(
            f"Mapped columns not found in CSV: {', '.join(missing)}"
        )

    aggregated: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"qty_sold": 0.0, "revenue": 0.0}
    )

    for row_num, row in enumerate(reader, start=2):
        item_id = (row.get(header_map[item_id_col]) or "").strip()
        platform_type = (row.get(header_map[platform_type_col]) or "").strip()
        if not item_id or not platform_type:
            continue

        qty = _parse_number(
            row.get(header_map[qty_sold_col]),
            field_name=qty_sold_col,
            row_num=row_num,
        )
        rev = _parse_number(
            row.get(header_map[revenue_col]),
            field_name=revenue_col,
            row_num=row_num,
        )
        key = (item_id, platform_type)
        aggregated[key]["qty_sold"] += qty
        aggregated[key]["revenue"] += rev

    days: list[date] = []
    current = start_date
    while current <= end_date:
        days.append(current)
        current += timedelta(days=1)
    num_days = len(days)

    output_rows: list[dict[str, Any]] = []
    for (item_id, platform_type), totals in sorted(aggregated.items()):
        daily_qty = totals["qty_sold"] / num_days
        daily_revenue = totals["revenue"] / num_days
        for day in days:
            output_rows.append(
                {
                    "date": day.isoformat(),
                    "platform_type": platform_type,
                    "item_id": item_id,
                    "qty_sold": daily_qty,
                    "revenue": daily_revenue,
                }
            )

    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(output_rows)
    return out.getvalue()


def parse_date_param(value: str, *, field_name: str) -> date:
    return _parse_iso_date(value.strip(), field_name=field_name)
