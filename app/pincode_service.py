import asyncio
import logging
import os
import re
from dataclasses import dataclass

import certifi
import httpx

logger = logging.getLogger(__name__)

UPSTREAM_BASE = "https://api.postalpincode.in/pincode"
# api.postalpincode.in currently serves an expired TLS certificate; set
# UPSTREAM_SSL_VERIFY=1 to enforce verification once their cert is renewed.
UPSTREAM_SSL_VERIFY = os.getenv("UPSTREAM_SSL_VERIFY", "0").lower() in (
    "1",
    "true",
    "yes",
)
MAX_BATCH_SIZE = 200
MAX_CONCURRENCY = 10
REQUEST_TIMEOUT = 10.0

PINCODE_RE = re.compile(r"^\d{6}$")


@dataclass
class LookupResult:
    pincode: str
    city: str | None
    state: str | None
    status: str
    message: str | None = None


def _normalize_pincode(raw: str) -> str:
    return raw.strip()


def _is_valid_pincode(pincode: str) -> bool:
    return bool(PINCODE_RE.match(pincode))


def _error_result(pincode: str, message: str) -> LookupResult:
    logger.warning("pincode=%s status=error message=%s", pincode, message)
    return LookupResult(
        pincode=pincode,
        city=None,
        state=None,
        status="error",
        message=message,
    )


async def _fetch_pincode(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    pincode: str,
) -> LookupResult:
    url = f"{UPSTREAM_BASE}/{pincode}"
    async with semaphore:
        logger.info("upstream GET %s", url)
        try:
            response = await client.get(url, timeout=REQUEST_TIMEOUT)
            logger.info(
                "upstream pincode=%s http_status=%s",
                pincode,
                response.status_code,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException:
            logger.error("upstream pincode=%s timed out after %ss", pincode, REQUEST_TIMEOUT)
            return _error_result(pincode, "Upstream request timed out")
        except httpx.HTTPStatusError as exc:
            body_preview = (exc.response.text or "")[:300]
            logger.error(
                "upstream pincode=%s http_status=%s body=%r",
                pincode,
                exc.response.status_code,
                body_preview,
            )
            return _error_result(
                pincode,
                f"Upstream HTTP {exc.response.status_code}",
            )
        except httpx.RequestError as exc:
            logger.exception("upstream pincode=%s request failed: %s", pincode, exc)
            return _error_result(
                pincode,
                str(exc) or "Upstream request failed",
            )
        except ValueError:
            logger.error(
                "upstream pincode=%s invalid JSON body=%r",
                pincode,
                (response.text or "")[:300],
            )
            return _error_result(pincode, "Invalid JSON from upstream")

    if not isinstance(data, list) or not data:
        logger.warning("upstream pincode=%s empty response", pincode)
        return LookupResult(
            pincode=pincode,
            city=None,
            state=None,
            status="not_found",
            message="Empty response from upstream",
        )

    entry = data[0]
    if not isinstance(entry, dict):
        logger.error(
            "upstream pincode=%s unexpected shape type=%s",
            pincode,
            type(entry).__name__,
        )
        return _error_result(pincode, "Unexpected upstream response shape")

    status = entry.get("Status", "")
    message = entry.get("Message")
    post_offices = entry.get("PostOffice") or []

    logger.info(
        "upstream pincode=%s api_status=%r message=%r post_offices=%d",
        pincode,
        status,
        message,
        len(post_offices) if isinstance(post_offices, list) else 0,
    )

    if status != "Success" or not post_offices:
        logger.warning(
            "upstream pincode=%s not_found api_status=%r message=%r",
            pincode,
            status,
            message,
        )
        return LookupResult(
            pincode=pincode,
            city=None,
            state=None,
            status="not_found",
            message=message or "No records found",
        )

    first = post_offices[0]
    if not isinstance(first, dict):
        logger.error("upstream pincode=%s invalid post office entry", pincode)
        return _error_result(pincode, "Unexpected post office data")

    city = first.get("District")
    state = first.get("State")
    logger.info(
        "upstream pincode=%s ok city=%r state=%r",
        pincode,
        city,
        state,
    )
    return LookupResult(
        pincode=pincode,
        city=city,
        state=state,
        status="ok",
    )


async def lookup_pincodes(pincodes: list[str]) -> list[LookupResult]:
    if len(pincodes) > MAX_BATCH_SIZE:
        raise ValueError(f"Maximum {MAX_BATCH_SIZE} pincodes per request")

    normalized = [_normalize_pincode(p) for p in pincodes]
    unique_valid = list(
        dict.fromkeys(p for p in normalized if _is_valid_pincode(p))
    )

    logger.info(
        "lookup batch total=%d unique_valid=%d",
        len(pincodes),
        len(unique_valid),
    )

    cache: dict[str, LookupResult] = {}
    if unique_valid:
        if UPSTREAM_SSL_VERIFY:
            ssl_verify: bool | str = certifi.where()
            logger.info("upstream ssl_verify=enabled (certifi)")
        else:
            ssl_verify = False
            logger.warning(
                "upstream ssl_verify=disabled — api.postalpincode.in has an "
                "expired certificate; set UPSTREAM_SSL_VERIFY=1 when renewed"
            )
        semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
        async with httpx.AsyncClient(verify=ssl_verify) as client:
            fetched = await asyncio.gather(
                *[
                    _fetch_pincode(client, semaphore, pincode)
                    for pincode in unique_valid
                ]
            )
        for item in fetched:
            cache[item.pincode] = item

    results: list[LookupResult] = []
    for raw, pincode in zip(pincodes, normalized, strict=True):
        if not _is_valid_pincode(pincode):
            logger.info("pincode=%r status=invalid", pincode or raw)
            results.append(
                LookupResult(
                    pincode=pincode or _normalize_pincode(raw),
                    city=None,
                    state=None,
                    status="invalid",
                    message="Pincode must be exactly 6 digits",
                )
            )
            continue

        cached = cache[pincode]
        results.append(
            LookupResult(
                pincode=pincode,
                city=cached.city,
                state=cached.state,
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
