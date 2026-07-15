import asyncio
import logging
import re
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

UPSTREAM_BASE = "https://api.bigdatacloud.net/data/reverse-geocode-client"
MAX_BATCH_SIZE = 5000
MAX_CONCURRENCY = 10
REQUEST_TIMEOUT = 10.0

COORDINATE_SPLIT_RE = re.compile(r"[,\t]+")


@dataclass
class LookupResult:
    raw: str
    latitude: float | None
    longitude: float | None
    city: str | None
    locality: str | None
    postcode: str | None
    plus_code: str | None
    principal_subdivision: str | None
    status: str
    message: str | None = None


def _parse_coordinate(raw: str) -> tuple[float, float] | None:
    text = raw.strip()
    if not text:
        return None

    parts = [p.strip() for p in COORDINATE_SPLIT_RE.split(text) if p.strip()]
    if len(parts) != 2:
        parts = text.split()
    if len(parts) != 2:
        return None

    try:
        lat = float(parts[0])
        lon = float(parts[1])
    except ValueError:
        return None

    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return None

    return lat, lon


def _error_result(raw: str, lat: float | None, lon: float | None, message: str) -> LookupResult:
    logger.warning("coordinate=%s status=error message=%s", raw, message)
    return LookupResult(
        raw=raw,
        latitude=lat,
        longitude=lon,
        city=None,
        locality=None,
        postcode=None,
        plus_code=None,
        principal_subdivision=None,
        status="error",
        message=message,
    )


async def _fetch_coordinate(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    raw: str,
    lat: float,
    lon: float,
) -> LookupResult:
    params = {"latitude": lat, "longitude": lon, "localityLanguage": "en"}
    async with semaphore:
        logger.info("upstream GET %s params=%s", UPSTREAM_BASE, params)
        try:
            response = await client.get(UPSTREAM_BASE, params=params, timeout=REQUEST_TIMEOUT)
            logger.info(
                "upstream coordinate=%s http_status=%s",
                raw,
                response.status_code,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException:
            logger.error("upstream coordinate=%s timed out after %ss", raw, REQUEST_TIMEOUT)
            return _error_result(raw, lat, lon, "Upstream request timed out")
        except httpx.HTTPStatusError as exc:
            body_preview = (exc.response.text or "")[:300]
            logger.error(
                "upstream coordinate=%s http_status=%s body=%r",
                raw,
                exc.response.status_code,
                body_preview,
            )
            return _error_result(
                raw,
                lat,
                lon,
                f"Upstream HTTP {exc.response.status_code}",
            )
        except httpx.RequestError as exc:
            logger.exception("upstream coordinate=%s request failed: %s", raw, exc)
            return _error_result(raw, lat, lon, str(exc) or "Upstream request failed")
        except ValueError:
            logger.error(
                "upstream coordinate=%s invalid JSON body=%r",
                raw,
                (response.text or "")[:300],
            )
            return _error_result(raw, lat, lon, "Invalid JSON from upstream")

    if not isinstance(data, dict):
        logger.error("upstream coordinate=%s unexpected shape type=%s", raw, type(data).__name__)
        return _error_result(raw, lat, lon, "Unexpected upstream response shape")

    city = data.get("city") or None
    locality = data.get("locality") or None
    postcode = data.get("postcode") or None
    plus_code = data.get("plusCode") or None
    principal_subdivision = data.get("principalSubdivision") or None

    if not city and not locality and not data.get("countryName"):
        logger.warning("upstream coordinate=%s not_found", raw)
        return LookupResult(
            raw=raw,
            latitude=lat,
            longitude=lon,
            city=None,
            locality=None,
            postcode=None,
            plus_code=None,
            principal_subdivision=None,
            status="not_found",
            message="No location found for these coordinates",
        )

    logger.info(
        "upstream coordinate=%s ok city=%r locality=%r",
        raw,
        city,
        locality,
    )
    return LookupResult(
        raw=raw,
        latitude=lat,
        longitude=lon,
        city=city,
        locality=locality,
        postcode=postcode,
        plus_code=plus_code,
        principal_subdivision=principal_subdivision,
        status="ok",
    )


async def lookup_coordinates(raw_lines: list[str]) -> list[LookupResult]:
    if len(raw_lines) > MAX_BATCH_SIZE:
        raise ValueError(f"Maximum {MAX_BATCH_SIZE} coordinate pairs per request")

    parsed: list[tuple[float, float] | None] = [_parse_coordinate(r) for r in raw_lines]

    unique_valid: dict[tuple[float, float], None] = {}
    for p in parsed:
        if p is not None:
            key = (round(p[0], 6), round(p[1], 6))
            unique_valid.setdefault(key, None)
    unique_points = list(unique_valid.keys())

    logger.info(
        "lookup batch total=%d unique_valid=%d",
        len(raw_lines),
        len(unique_points),
    )

    cache: dict[tuple[float, float], LookupResult] = {}
    if unique_points:
        semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
        async with httpx.AsyncClient() as client:
            fetched = await asyncio.gather(
                *[
                    _fetch_coordinate(client, semaphore, f"{lat},{lon}", lat, lon)
                    for lat, lon in unique_points
                ]
            )
        for item in fetched:
            cache[(round(item.latitude, 6), round(item.longitude, 6))] = item

    results: list[LookupResult] = []
    for raw, p in zip(raw_lines, parsed, strict=True):
        if p is None:
            logger.info("coordinate=%r status=invalid", raw)
            results.append(
                LookupResult(
                    raw=raw,
                    latitude=None,
                    longitude=None,
                    city=None,
                    locality=None,
                    postcode=None,
                    plus_code=None,
                    principal_subdivision=None,
                    status="invalid",
                    message="Expected 'latitude,longitude' with valid ranges",
                )
            )
            continue

        key = (round(p[0], 6), round(p[1], 6))
        cached = cache[key]
        results.append(
            LookupResult(
                raw=raw,
                latitude=cached.latitude,
                longitude=cached.longitude,
                city=cached.city,
                locality=cached.locality,
                postcode=cached.postcode,
                plus_code=cached.plus_code,
                principal_subdivision=cached.principal_subdivision,
                status=cached.status,
                message=cached.message,
            )
        )

    ok = sum(1 for r in results if r.status == "ok")
    errors = sum(1 for r in results if r.status == "error")
    not_found = sum(1 for r in results if r.status == "not_found")
    invalid = sum(1 for r in results if r.status == "invalid")
    logger.info(
        "lookup done ok=%d not_found=%d invalid=%d error=%d",
        ok,
        not_found,
        invalid,
        errors,
    )

    return results
