"""Resilient Google Flights scraper and GCS raw JSONL uploader."""

from __future__ import annotations

from collections.abc import Callable
import copy
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime, timedelta, timezone
import json
import logging
import os
import random
import re
import time
from typing import Any
import uuid

from fast_flights import FlightQuery, FlightsNotFound, Passengers, create_query, get_flights
from fast_flights.integrations.base import FetchIntegration
from fast_flights.querying import Query
from google.cloud import storage
from primp import Client
from selectolax.lexbor import LexborHTMLParser

logger = logging.getLogger(__name__)

GOOGLE_FLIGHTS_SEARCH_URL = "https://www.google.com/travel/flights/search"
SOCS_CONSENT_COOKIE_ENV_VAR = "SOCS_CONSENT_COOKIE"
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class ScraperError(Exception):
    """Base exception for flight scraper errors."""


class UpstreamScrapeError(ScraperError):
    """Raised when Google Flights blocks, redirects to /sorry/, or returns an unparseable response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        url: str | None = None,
        reason: str = "upstream_fetch_failed",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.url = url
        self.reason = reason


@dataclass
class ScrapeStats:
    """Execution telemetry for a batch flight scrape run."""

    date_pairs_count: int = 0
    total_logical_queries: int = 0
    http_requests_attempted: int = 0
    cached_return_queries: int = 0
    succeeded_queries: int = 0
    no_flights_queries: int = 0
    failed_queries: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


class AllQueriesFailedError(ScraperError):
    """Raised when zero flight records were collected and at least one upstream query failed."""

    def __init__(self, message: str, *, stats: ScrapeStats | None = None) -> None:
        super().__init__(message)
        self.stats = stats


class ScrapeResultList(list[dict[str, Any]]):
    """List of raw flight dicts with `.stats` telemetry attached."""

    stats: ScrapeStats

    def __init__(
        self,
        iterable: list[dict[str, Any]] | None = None,
        *,
        stats: ScrapeStats | None = None,
    ) -> None:
        super().__init__(iterable or ())
        self.stats = stats or ScrapeStats()


def _has_flights_script(html: str) -> bool:
    """Return True if the Google Flights SSR payload script tag (`script.ds:1`) is present."""
    if not html:
        return False
    return LexborHTMLParser(html).css_first(r"script.ds\:1") is not None


def _is_sorry_challenge(url: str, html: str) -> bool:
    """Detect Google's `/sorry/` interstitial without attempting to solve or bypass it."""
    lowered_url = url.lower()
    if "/sorry/" in lowered_url or "google.com/sorry" in lowered_url:
        return True
    snippet = html[:2048].lower()
    return "google.com/sorry" in snippet or "/sorry/index" in snippet


class ConsentAwareFetchIntegration(FetchIntegration):
    """Session-reusing, rate-paced Google Flights fetcher with bounded retry and SSR validation."""

    def __init__(
        self,
        *,
        client: Client | None = None,
        consent_cookie: str | None = None,
        request_delay_range: tuple[float, float] = (0.35, 0.75),
        max_retries: int = 2,
        backoff_base_seconds: float = 1.0,
        timeout: int = 15,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        raw_cookie = (
            consent_cookie
            if consent_cookie is not None
            else os.environ.get(SOCS_CONSENT_COOKIE_ENV_VAR, "")
        )
        resolved_cookie = raw_cookie.strip()
        if not resolved_cookie:
            raise ScraperError(
                f"{SOCS_CONSENT_COOKIE_ENV_VAR} environment variable is not set"
            )
        self._consent_cookie = resolved_cookie
        self._client = client or Client(
            impersonate="chrome_145",
            impersonate_os="macos",
            cookie_store=True,
            referer=True,
            follow_redirects=True,
            timeout=timeout,
        )
        self._request_delay_range = request_delay_range
        self._max_retries = max(0, max_retries)
        self._backoff_base_seconds = max(0.0, backoff_base_seconds)
        self._sleep_fn = sleep_fn
        self.http_requests_attempted = 0

    def _pace_before_request(self) -> None:
        low, high = self._request_delay_range
        if self.http_requests_attempted > 0 and high > 0:
            delay = random.uniform(max(0.0, low), max(low, high))
            if delay > 0:
                self._sleep_fn(delay)

    def _sleep_backoff(self, attempt: int) -> None:
        if self._backoff_base_seconds <= 0:
            return
        jitter = random.uniform(0.0, 0.25 * self._backoff_base_seconds)
        delay = (self._backoff_base_seconds * (2**attempt)) + jitter
        self._sleep_fn(delay)

    def fetch_html(self, q: Query | str, /) -> str:
        params = q.params() if isinstance(q, Query) else {"q": q}
        self._pace_before_request()

        for attempt in range(self._max_retries + 1):
            self.http_requests_attempted += 1
            try:
                resp = self._client.get(
                    GOOGLE_FLIGHTS_SEARCH_URL,
                    params=params,
                    headers={"cookie": self._consent_cookie},
                )
            except Exception as exc:
                is_last = attempt >= self._max_retries
                logger.warning(
                    "HTTP transport error while fetching Google Flights",
                    extra={
                        "json_fields": {
                            "event": "upstream_transport_error",
                            "attempt": attempt + 1,
                            "max_attempts": self._max_retries + 1,
                            "will_retry": not is_last,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }
                    },
                )
                if is_last:
                    raise UpstreamScrapeError(
                        f"Transport error after {attempt + 1} attempt(s): {exc}",
                        reason="transport_error",
                    ) from exc
                self._sleep_backoff(attempt)
                continue

            status_code = getattr(resp, "status_code", None)
            resp_url = str(getattr(resp, "url", "") or GOOGLE_FLIGHTS_SEARCH_URL)
            html = getattr(resp, "text", "") or ""

            if _is_sorry_challenge(resp_url, html):
                logger.warning(
                    "Google Flights redirected to /sorry/ anti-bot interstitial; aborting query without retry",
                    extra={
                        "json_fields": {
                            "event": "upstream_sorry_interstitial",
                            "status_code": status_code,
                            "url": resp_url,
                            "attempt": attempt + 1,
                        }
                    },
                )
                raise UpstreamScrapeError(
                    f"Blocked by Google /sorry/ interstitial (HTTP {status_code})",
                    status_code=status_code,
                    url=resp_url,
                    reason="sorry_interstitial",
                )

            if status_code != 200:
                retryable = status_code in _RETRYABLE_STATUS_CODES
                is_last = (not retryable) or (attempt >= self._max_retries)
                logger.warning(
                    "Unexpected HTTP status from Google Flights",
                    extra={
                        "json_fields": {
                            "event": "upstream_non_200_status",
                            "status_code": status_code,
                            "url": resp_url,
                            "attempt": attempt + 1,
                            "max_attempts": self._max_retries + 1,
                            "will_retry": not is_last,
                        }
                    },
                )
                if is_last:
                    raise UpstreamScrapeError(
                        f"Google Flights returned HTTP {status_code}",
                        status_code=status_code,
                        url=resp_url,
                        reason=f"http_{status_code}",
                    )
                self._sleep_backoff(attempt)
                continue

            if not _has_flights_script(html):
                is_last = attempt >= self._max_retries
                logger.warning(
                    "Google Flights 200 response missing script.ds:1 payload",
                    extra={
                        "json_fields": {
                            "event": "upstream_missing_ds1_script",
                            "status_code": status_code,
                            "url": resp_url,
                            "body_length": len(html),
                            "attempt": attempt + 1,
                            "max_attempts": self._max_retries + 1,
                            "will_retry": not is_last,
                        }
                    },
                )
                if is_last:
                    raise UpstreamScrapeError(
                        "Google Flights response missing script.ds:1 payload",
                        status_code=status_code,
                        url=resp_url,
                        reason="missing_ds1_script",
                    )
                self._sleep_backoff(attempt)
                continue

            return html

        raise UpstreamScrapeError("Exhausted retries fetching Google Flights", reason="exhausted_retries")


def generate_flexible_date_pairs(
    start_date: str,
    trip_length: int | None = 24,
    flexibility_window: int = 0,
    trip_type: str = "round-trip",
) -> list[tuple[str, str | None]]:
    """Generates (outbound_date, return_date) pairs, or (outbound_date, None) for one-way trips."""
    base_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    pairs: list[tuple[str, str | None]] = []

    if trip_type == "one-way":
        for out_offset in range(-flexibility_window, flexibility_window + 1):
            outbound_dt = base_date + timedelta(days=out_offset)
            pairs.append((outbound_dt.strftime("%Y-%m-%d"), None))
        return pairs

    effective_length = 24 if trip_length is None else trip_length
    for out_offset in range(-flexibility_window, flexibility_window + 1):
        outbound_dt = base_date + timedelta(days=out_offset)
        for len_offset in range(-flexibility_window, flexibility_window + 1):
            current_length = effective_length + len_offset
            if current_length < 1:
                continue
            return_dt = outbound_dt + timedelta(days=current_length)
            pairs.append((outbound_dt.strftime("%Y-%m-%d"), return_dt.strftime("%Y-%m-%d")))

    return pairs


def _to_serializable(obj: Any) -> Any:
    """Recursively converts an object to a JSON-serializable format, supporting dataclasses."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return _to_serializable(asdict(obj))
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_serializable(item) for item in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if hasattr(obj, "__dict__") and not isinstance(obj, type):
        return {k: _to_serializable(v) for k, v in obj.__dict__.items()}
    return obj


def fetch_flights_for_date_pairs(
    date_pairs: list[tuple[str, str | None]],
    origin: str = "BRU",
    destination: str = "YUL",
    seat: str = "economy",
    currency: str = "EUR",
    adults: int = 1,
    max_stops: int | None = None,
    search_name: str = "default",
    target_price: float | None = None,
    trip_type: str = "round-trip",
    *,
    integration: FetchIntegration | None = None,
    request_delay_range: tuple[float, float] = (0.35, 0.75),
    max_retries: int = 2,
) -> ScrapeResultList:
    """Queries Google Flights for each date pair and returns all raw flight records with `.stats`."""
    active_integration = integration or ConsentAwareFetchIntegration(
        request_delay_range=request_delay_range,
        max_retries=max_retries,
    )
    stats = ScrapeStats(date_pairs_count=len(date_pairs))
    raw_results = ScrapeResultList(stats=stats)

    return_cache: dict[str, tuple[str, list[dict[str, Any]]]] = {}

    for outbound_date, return_date in date_pairs:
        if trip_type == "one-way" or return_date is None:
            stats.total_logical_queries += 1
            ow_query = create_query(
                flights=[
                    FlightQuery(date=outbound_date, from_airport=origin, to_airport=destination, max_stops=max_stops),
                ],
                trip="one-way",
                seat=seat,
                currency=currency,
                max_stops=max_stops,
                passengers=Passengers(adults=adults),
            )
            try:
                ow_flights = get_flights(ow_query, integration=active_integration)
                if not ow_flights:
                    stats.no_flights_queries += 1
                else:
                    stats.succeeded_queries += 1
                    for flight in ow_flights:
                        data = _to_serializable(flight)
                        data["_query_meta"] = {
                            "search_name": search_name,
                            "outbound_date": outbound_date,
                            "return_date": None,
                            "origin": origin,
                            "destination": destination,
                            "trip": "one-way",
                            "currency": currency,
                            "seat": seat,
                            "target_price": target_price,
                        }
                        raw_results.append(data)
            except FlightsNotFound:
                stats.no_flights_queries += 1
            except (UpstreamScrapeError, AttributeError, TypeError, IndexError, ValueError, KeyError) as exc:
                stats.failed_queries += 1
                logger.warning(
                    "One-way outbound flight query failed; continuing remaining dates",
                    extra={
                        "json_fields": {
                            "event": "flight_query_failed",
                            "search_name": search_name,
                            "origin": origin,
                            "destination": destination,
                            "outbound_date": outbound_date,
                            "return_date": None,
                            "trip": "one-way",
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }
                    },
                )
            continue

        # 1. Fetch round-trip options (raw)
        stats.total_logical_queries += 1
        rt_query = create_query(
            flights=[
                FlightQuery(date=outbound_date, from_airport=origin, to_airport=destination, max_stops=max_stops),
                FlightQuery(date=return_date, from_airport=destination, to_airport=origin, max_stops=max_stops),
            ],
            trip="round-trip",
            seat=seat,
            currency=currency,
            max_stops=max_stops,
            passengers=Passengers(adults=adults),
        )
        try:
            rt_flights = get_flights(rt_query, integration=active_integration)
            if not rt_flights:
                stats.no_flights_queries += 1
            else:
                stats.succeeded_queries += 1
                for flight in rt_flights:
                    data = _to_serializable(flight)
                    data["_query_meta"] = {
                        "search_name": search_name,
                        "outbound_date": outbound_date,
                        "return_date": return_date,
                        "origin": origin,
                        "destination": destination,
                        "trip": "round-trip",
                        "currency": currency,
                        "seat": seat,
                        "target_price": target_price,
                    }
                    raw_results.append(data)
        except FlightsNotFound:
            stats.no_flights_queries += 1
        except (UpstreamScrapeError, AttributeError, TypeError, IndexError, ValueError, KeyError) as exc:
            stats.failed_queries += 1
            logger.warning(
                "Round-trip flight query failed; continuing remaining date pairs",
                extra={
                    "json_fields": {
                        "event": "flight_query_failed",
                        "search_name": search_name,
                        "origin": origin,
                        "destination": destination,
                        "outbound_date": outbound_date,
                        "return_date": return_date,
                        "trip": "round-trip",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                },
            )

        # 2. Fetch return leg options (raw), deduplicated per unique return_date
        stats.total_logical_queries += 1
        if return_date in return_cache:
            stats.cached_return_queries += 1
            cached_state, cached_records = return_cache[return_date]
        else:
            ret_query = create_query(
                flights=[
                    FlightQuery(date=return_date, from_airport=destination, to_airport=origin, max_stops=max_stops),
                ],
                trip="one-way",
                seat=seat,
                currency=currency,
                max_stops=max_stops,
                passengers=Passengers(adults=adults),
            )
            try:
                ret_flights = get_flights(ret_query, integration=active_integration)
                serialized_ret = [_to_serializable(flight) for flight in ret_flights]
                if not serialized_ret:
                    stats.no_flights_queries += 1
                    cached_state, cached_records = "not_found", []
                else:
                    stats.succeeded_queries += 1
                    cached_state, cached_records = "ok", serialized_ret
            except FlightsNotFound:
                stats.no_flights_queries += 1
                cached_state, cached_records = "not_found", []
            except (UpstreamScrapeError, AttributeError, TypeError, IndexError, ValueError, KeyError) as exc:
                stats.failed_queries += 1
                cached_state, cached_records = "failed", []
                logger.warning(
                    "One-way return flight query failed; continuing remaining date pairs",
                    extra={
                        "json_fields": {
                            "event": "flight_query_failed",
                            "search_name": search_name,
                            "origin": destination,
                            "destination": origin,
                            "outbound_date": outbound_date,
                            "return_date": return_date,
                            "trip": "one-way",
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }
                    },
                )
            return_cache[return_date] = (cached_state, cached_records)

        if cached_state == "ok":
            for base_record in cached_records:
                record = copy.deepcopy(base_record)
                record["_query_meta"] = {
                    "search_name": search_name,
                    "outbound_date": outbound_date,
                    "return_date": return_date,
                    "origin": destination,
                    "destination": origin,
                    "trip": "one-way",
                    "currency": currency,
                    "seat": seat,
                    "target_price": target_price,
                }
                raw_results.append(record)

    stats.http_requests_attempted = getattr(active_integration, "http_requests_attempted", 0)

    if len(raw_results) == 0 and stats.failed_queries > 0:
        raise AllQueriesFailedError(
            f"All flight queries failed or yielded 0 records ({stats.failed_queries} failed, "
            f"{stats.no_flights_queries} had no flights) for search '{search_name}' ({origin}->{destination}).",
            stats=stats,
        )

    return raw_results


def upload_raw_data_to_gcs(
    bucket_name: str,
    data: list[dict[str, Any]],
    source: str = "google_flights",
    search_name: str = "default",
) -> str | None:
    """Dumps raw flight records as a JSONL file to the specified Google Cloud Storage bucket."""
    safe_search_name = re.sub(r"[^A-Za-z0-9_-]+", "_", search_name or "").strip("_") or "default"
    if not data:
        logger.info(
            "No flight data to upload to GCS",
            extra={
                "json_fields": {
                    "event": "gcs_upload_skipped",
                    "bucket": bucket_name,
                    "source": source,
                    "search_name": safe_search_name,
                    "records_count": 0,
                }
            },
        )
        return None

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    scrape_id = str(uuid.uuid4())
    dt_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    blob_name = f"raw/source={source}/dt={dt_str}/{safe_search_name}_{scrape_id}.jsonl"

    blob = bucket.blob(blob_name)
    jsonl_content = "\n".join(json.dumps(record, default=str) for record in data)
    blob.upload_from_string(jsonl_content, content_type="application/x-ndjson")

    gcs_uri = f"gs://{bucket_name}/{blob_name}"
    logger.info(
        "Uploaded raw flight records to GCS",
        extra={
            "json_fields": {
                "event": "gcs_upload_completed",
                "bucket": bucket_name,
                "gcs_uri": gcs_uri,
                "source": source,
                "search_name": safe_search_name,
                "records_count": len(data),
            }
        },
    )
    return gcs_uri


if __name__ == "__main__":
    from logging_utils import configure_logging

    configure_logging()
    cli_pairs = generate_flexible_date_pairs(
        start_date="2027-06-01",
        trip_length=24,
        flexibility_window=1,
    )
    cli_results = fetch_flights_for_date_pairs(
        date_pairs=cli_pairs,
        origin="BRU",
        destination="YUL",
    )
    cli_bucket = os.environ.get("RAW_DATA_BUCKET")
    if cli_bucket:
        upload_raw_data_to_gcs(bucket_name=cli_bucket, data=cli_results)
    else:
        logger.info(
            "RAW_DATA_BUCKET not set; skipping GCS upload",
            extra={"json_fields": {"records_count": len(cli_results), **cli_results.stats.to_dict()}},
        )
