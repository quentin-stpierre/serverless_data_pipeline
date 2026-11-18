"""HTTP Cloud Run function entrypoint for Google Flights scraping."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
import logging
import os
import re
import time
from typing import Any

import functions_framework

from fast_flights_scraper import (
    AllQueriesFailedError,
    fetch_flights_for_date_pairs,
    generate_flexible_date_pairs,
    upload_raw_data_to_gcs,
)
from logging_utils import configure_logging, request_logging_context

configure_logging()
logger = logging.getLogger(__name__)

_VALID_SEATS = frozenset({"economy", "premium-economy", "business", "first"})
_IATA_CODE_RE = re.compile(r"^[A-Z]{3}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SEARCH_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class ValidationError(ValueError):
    """Raised when incoming HTTP request parameters fail validation."""


def _coalesce(payload: Mapping[str, Any], key: str, default: Any) -> Any:
    value = payload.get(key)
    return default if value is None else value


def _parse_bounded_int(
    name: str,
    raw_value: Any,
    *,
    min_value: int,
    max_value: int,
) -> int:
    if isinstance(raw_value, bool):
        raise ValidationError(f"Parameter '{name}' must be an integer, got boolean")
    if isinstance(raw_value, float):
        if not raw_value.is_integer():
            raise ValidationError(f"Parameter '{name}' must be an integer, got float {raw_value}")
        parsed = int(raw_value)
    elif isinstance(raw_value, int):
        parsed = raw_value
    elif isinstance(raw_value, str):
        stripped = raw_value.strip()
        if not stripped or not re.fullmatch(r"[+-]?\d+", stripped):
            raise ValidationError(f"Parameter '{name}' must be an integer, got {raw_value!r}")
        parsed = int(stripped)
    else:
        raise ValidationError(f"Parameter '{name}' must be an integer, got {type(raw_value).__name__}")

    if not (min_value <= parsed <= max_value):
        raise ValidationError(
            f"Parameter '{name}' must be between {min_value} and {max_value}, got {parsed}"
        )
    return parsed


def validate_request_params(request_json: Any) -> dict[str, Any]:
    """Validate and normalize incoming scraper request parameters (`None`-safe)."""
    if not isinstance(request_json, Mapping):
        raise ValidationError("Request JSON payload must be an object")

    raw_search_name = _coalesce(request_json, "search_name", "default")
    if not isinstance(raw_search_name, str):
        raise ValidationError("Parameter 'search_name' must be a string")
    search_name = raw_search_name.strip() or "default"
    if not _SEARCH_NAME_RE.fullmatch(search_name):
        raise ValidationError(
            "Parameter 'search_name' must match [A-Za-z0-9_-]{1,64}"
        )

    raw_start_date = _coalesce(request_json, "start_date", "2027-06-01")
    if not isinstance(raw_start_date, str) or not _ISO_DATE_RE.fullmatch(raw_start_date.strip()):
        raise ValidationError("Parameter 'start_date' must be formatted as YYYY-MM-DD")
    start_date = raw_start_date.strip()
    try:
        date.fromisoformat(start_date)
    except ValueError as exc:
        raise ValidationError(f"Parameter 'start_date' is not a valid calendar date: {start_date}") from exc

    trip_length = _parse_bounded_int(
        "trip_length",
        _coalesce(request_json, "trip_length", 24),
        min_value=1,
        max_value=365,
    )
    flexibility_window = _parse_bounded_int(
        "flexibility_window",
        _coalesce(request_json, "flexibility_window", 1),
        min_value=0,
        max_value=7,
    )
    adults = _parse_bounded_int(
        "adults",
        _coalesce(request_json, "adults", 1),
        min_value=1,
        max_value=9,
    )
    max_stops = _parse_bounded_int(
        "max_stops",
        _coalesce(request_json, "max_stops", 0),
        min_value=0,
        max_value=2,
    )

    raw_origin = _coalesce(request_json, "origin", "BRU")
    if not isinstance(raw_origin, str) or not _IATA_CODE_RE.fullmatch(raw_origin.strip().upper()):
        raise ValidationError("Parameter 'origin' must be a 3-letter IATA airport code")
    origin = raw_origin.strip().upper()

    raw_destination = _coalesce(request_json, "destination", "YUL")
    if not isinstance(raw_destination, str) or not _IATA_CODE_RE.fullmatch(raw_destination.strip().upper()):
        raise ValidationError("Parameter 'destination' must be a 3-letter IATA airport code")
    destination = raw_destination.strip().upper()

    if origin == destination:
        raise ValidationError("Parameters 'origin' and 'destination' must be different airports")

    raw_seat = _coalesce(request_json, "seat", "economy")
    if not isinstance(raw_seat, str) or raw_seat.strip().lower() not in _VALID_SEATS:
        raise ValidationError(
            f"Parameter 'seat' must be one of {sorted(_VALID_SEATS)}"
        )
    seat = raw_seat.strip().lower()

    raw_currency = _coalesce(request_json, "currency", "EUR")
    if not isinstance(raw_currency, str) or not _CURRENCY_RE.fullmatch(raw_currency.strip().upper()):
        raise ValidationError("Parameter 'currency' must be a 3-letter ISO currency code")
    currency = raw_currency.strip().upper()

    return {
        "search_name": search_name,
        "start_date": start_date,
        "trip_length": trip_length,
        "flexibility_window": flexibility_window,
        "origin": origin,
        "destination": destination,
        "seat": seat,
        "currency": currency,
        "adults": adults,
        "max_stops": max_stops,
    }


def _extract_json_body(request: Any) -> Any:
    parsed = request.get_json(silent=True) if hasattr(request, "get_json") else None
    if parsed is not None:
        return parsed

    raw_bytes = getattr(request, "data", None)
    if isinstance(raw_bytes, (bytes, str)) and raw_bytes.strip():
        raise ValidationError("Malformed JSON in request body")
    return {}


@functions_framework.http
def fetch_flights(request: Any):
    """HTTP Cloud Function entrypoint to scrape flight data based on request parameters."""
    started_at = time.monotonic()
    with request_logging_context(request):
        params: dict[str, Any] = {}
        try:
            raw_payload = _extract_json_body(request)
            params = validate_request_params(raw_payload)

            bucket_name = (os.environ.get("RAW_DATA_BUCKET") or "").strip()
            if not bucket_name:
                logger.error(
                    "RAW_DATA_BUCKET environment variable is not set",
                    extra={
                        "json_fields": {
                            "event": "configuration_error",
                            "search_name": params.get("search_name"),
                        }
                    },
                )
                return {
                    "status": "error",
                    "error": "RAW_DATA_BUCKET environment variable is not set",
                    "error_type": "ConfigurationError",
                }, 500

            date_pairs = generate_flexible_date_pairs(
                start_date=params["start_date"],
                trip_length=params["trip_length"],
                flexibility_window=params["flexibility_window"],
            )

            logger.info(
                "Starting flight scrape request",
                extra={
                    "json_fields": {
                        "event": "scrape_request_started",
                        "search_name": params["search_name"],
                        "origin": params["origin"],
                        "destination": params["destination"],
                        "start_date": params["start_date"],
                        "trip_length": params["trip_length"],
                        "flexibility_window": params["flexibility_window"],
                        "date_pairs_count": len(date_pairs),
                        "seat": params["seat"],
                        "currency": params["currency"],
                        "adults": params["adults"],
                        "max_stops": params["max_stops"],
                    }
                },
            )

            results = fetch_flights_for_date_pairs(
                date_pairs=date_pairs,
                origin=params["origin"],
                destination=params["destination"],
                seat=params["seat"],
                currency=params["currency"],
                adults=params["adults"],
                max_stops=params["max_stops"],
                search_name=params["search_name"],
            )

            gcs_uri = upload_raw_data_to_gcs(bucket_name=bucket_name, data=results)
            duration_ms = round((time.monotonic() - started_at) * 1000, 2)
            scrape_stats = results.stats.to_dict() if hasattr(results, "stats") else {}

            logger.info(
                "Completed flight scrape request",
                extra={
                    "json_fields": {
                        "event": "scrape_request_completed",
                        "search_name": params["search_name"],
                        "origin": params["origin"],
                        "destination": params["destination"],
                        "date_pairs_count": len(date_pairs),
                        "records_count": len(results),
                        "gcs_uri": gcs_uri,
                        "duration_ms": duration_ms,
                        **scrape_stats,
                    }
                },
            )

            return {
                "status": "success",
                "records_count": len(results),
                "gcs_uri": gcs_uri,
                "parameters": {
                    "search_name": params["search_name"],
                    "origin": params["origin"],
                    "destination": params["destination"],
                    "start_date": params["start_date"],
                    "trip_length": params["trip_length"],
                    "flexibility_window": params["flexibility_window"],
                },
                "scrape_stats": scrape_stats,
            }, 200

        except ValidationError as exc:
            duration_ms = round((time.monotonic() - started_at) * 1000, 2)
            logger.warning(
                f"Invalid flight scrape request parameters: {exc}",
                extra={
                    "json_fields": {
                        "event": "scrape_request_validation_failed",
                        "error_type": "ValidationError",
                        "error": str(exc),
                        "duration_ms": duration_ms,
                    }
                },
            )
            return {
                "status": "error",
                "error": str(exc),
                "error_type": "ValidationError",
            }, 400

        except AllQueriesFailedError as exc:
            duration_ms = round((time.monotonic() - started_at) * 1000, 2)
            scrape_stats = exc.stats.to_dict() if exc.stats else {}
            logger.error(
                f"All upstream flight queries failed: {exc}",
                exc_info=True,
                extra={
                    "json_fields": {
                        "event": "scrape_request_upstream_unavailable",
                        "search_name": params.get("search_name"),
                        "origin": params.get("origin"),
                        "destination": params.get("destination"),
                        "error_type": "AllQueriesFailedError",
                        "duration_ms": duration_ms,
                        **scrape_stats,
                    }
                },
            )
            return {
                "status": "error",
                "error": str(exc),
                "error_type": "AllQueriesFailedError",
                "scrape_stats": scrape_stats,
            }, 503

        except Exception as exc:
            duration_ms = round((time.monotonic() - started_at) * 1000, 2)
            logger.exception(
                "Unhandled exception during flight scrape execution",
                extra={
                    "json_fields": {
                        "event": "scrape_request_internal_error",
                        "search_name": params.get("search_name"),
                        "origin": params.get("origin"),
                        "destination": params.get("destination"),
                        "error_type": type(exc).__name__,
                        "duration_ms": duration_ms,
                    }
                },
            )
            return {
                "status": "error",
                "error": "Internal server error while scraping flights",
                "detail": str(exc),
                "error_type": type(exc).__name__,
            }, 500
