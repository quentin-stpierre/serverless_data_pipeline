"""Unit and integration tests for the fetch_flights Cloud Run function."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import io
import json
import logging
from pathlib import Path
import re
import sys
from typing import Any
from unittest.mock import MagicMock

import pytest

FUNCTIONS_DIR = Path(__file__).resolve().parents[1] / "functions" / "fetch_flights"
if str(FUNCTIONS_DIR) not in sys.path:
    sys.path.insert(0, str(FUNCTIONS_DIR))

from fast_flights import FlightsNotFound  # noqa: E402
import fast_flights_scraper  # noqa: E402
from fast_flights_scraper import (  # noqa: E402
    AllQueriesFailedError,
    ConsentAwareFetchIntegration,
    SOCS_CONSENT_COOKIE_ENV_VAR,
    ScrapeResultList,
    ScrapeStats,
    ScraperError,
    UpstreamScrapeError,
    fetch_flights_for_date_pairs,
    generate_flexible_date_pairs,
    upload_raw_data_to_gcs,
)
import logging_utils  # noqa: E402
from logging_utils import (  # noqa: E402
    configure_logging,
    parse_trace_headers,
    request_logging_context,
)
import main as fetch_flights_main  # noqa: E402
from main import ValidationError, fetch_flights, validate_request_params  # noqa: E402


VALID_FLIGHTS_HTML = (
    "<!doctype html><html><head></head><body>"
    '<script class="ds:1">AF_initDataCallback({key: \'ds:1\', data: [1, 2, 3]});</script>'
    "</body></html>"
)


@dataclass
class FakeHTTPResponse:
    """Lightweight mock HTTP response for primp.Client.get."""

    status_code: int = 200
    text: str = VALID_FLIGHTS_HTML
    url: str = "https://www.google.com/travel/flights/search"


@dataclass
class FakeFlightRecord:
    """Serializable fake flight object returned by mocked fast_flights.get_flights."""

    price: int
    airlines: list[str]
    departure_date: str


class FakeFlaskRequest:
    """Minimal Flask-compatible request stub for entrypoint & logging tests."""

    def __init__(
        self,
        *,
        json_body: Any = None,
        raw_data: bytes | str = b"",
        headers: dict[str, str] | None = None,
        method: str = "POST",
        url: str = "https://fetch-flights-xyz.a.run.app/",
        remote_addr: str = "169.254.1.1",
        protocol: str = "HTTP/1.1",
    ) -> None:
        self._json_body = json_body
        self.data = raw_data
        self.headers = headers or {}
        self.method = method
        self.url = url
        self.remote_addr = remote_addr
        self.environ = {"SERVER_PROTOCOL": protocol}

    def get_json(self, silent: bool = False) -> Any:
        if isinstance(self._json_body, Exception):
            if silent:
                return None
            raise self._json_body
        return self._json_body


# ---------------------------------------------------------------------------
# 1. GCP Structured Logging (logging_utils.py)
# ---------------------------------------------------------------------------


def test_parse_x_cloud_trace_context_exact_production_header() -> None:
    headers = {
        "X-Cloud-Trace-Context": "3e8882e6dbec1100590e6893ca5a8ec8/3737297187321845975;o=1"
    }
    trace_id, span_id, sampled = parse_trace_headers(headers)

    assert trace_id == "3e8882e6dbec1100590e6893ca5a8ec8"
    assert span_id == "33dd8bfda66298d7"
    assert sampled is True


def test_parse_trace_headers_w3c_traceparent_fallback_and_invalid() -> None:
    w3c_headers = {
        "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    }
    trace_id, span_id, sampled = parse_trace_headers(w3c_headers)
    assert trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert span_id == "00f067aa0ba902b7"
    assert sampled is True

    unsampled_headers = {
        "Traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-00"
    }
    _, _, unsampled = parse_trace_headers(unsampled_headers)
    assert unsampled is False

    assert parse_trace_headers({"X-Cloud-Trace-Context": "invalid"}) == (None, None, False)
    assert parse_trace_headers({}) == (None, None, False)


def test_structured_log_handler_emits_single_line_gcp_json_and_stack_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GCP_PROJECT", "serverless-data-pipeline-111")
    stream = io.StringIO()
    configure_logging(level="INFO", stream=stream)
    test_logger = logging.getLogger("tests.structured_logging")

    req = FakeFlaskRequest(
        headers={
            "X-Cloud-Trace-Context": "3e8882e6dbec1100590e6893ca5a8ec8/3737297187321845975;o=1",
            "User-Agent": "Google-Cloud-Workflows",
        },
        method="POST",
        url="https://fetch-flights.run.app/",
        remote_addr="10.0.0.5",
        protocol="HTTP/1.1",
    )

    try:
        with request_logging_context(req):
            test_logger.info(
                "Flight query batch started",
                extra={
                    "json_fields": {
                        "event": "batch_started",
                        "search_name": "summer_montreal",
                        "query_date": date(2027, 6, 1),
                    }
                },
            )
            try:
                raise AttributeError("'NoneType' object has no attribute 'text'")
            except AttributeError:
                test_logger.exception(
                    "Unhandled parser failure",
                    extra={"json_fields": {"event": "parser_crash"}},
                )

        # Outside request context: trace metadata must not leak into subsequent records.
        test_logger.warning("Post-request log line")

        raw_lines = stream.getvalue().splitlines()
        assert len(raw_lines) == 3

        info_payload = json.loads(raw_lines[0])
        assert info_payload["severity"] == "INFO"
        assert info_payload["message"] == "Flight query batch started"
        assert (
            info_payload["logging.googleapis.com/trace"]
            == "projects/serverless-data-pipeline-111/traces/3e8882e6dbec1100590e6893ca5a8ec8"
        )
        assert info_payload["logging.googleapis.com/spanId"] == "33dd8bfda66298d7"
        assert info_payload["logging.googleapis.com/trace_sampled"] is True
        assert "file" in info_payload["logging.googleapis.com/sourceLocation"]
        assert "line" in info_payload["logging.googleapis.com/sourceLocation"]
        assert "function" in info_payload["logging.googleapis.com/sourceLocation"]
        assert info_payload["httpRequest"] == {
            "requestMethod": "POST",
            "requestUrl": "https://fetch-flights.run.app/",
            "userAgent": "Google-Cloud-Workflows",
            "remoteIp": "10.0.0.5",
            "protocol": "HTTP/1.1",
        }
        assert info_payload["event"] == "batch_started"
        assert info_payload["search_name"] == "summer_montreal"
        assert info_payload["query_date"] == "2027-06-01"

        err_payload = json.loads(raw_lines[1])
        assert err_payload["severity"] == "ERROR"
        assert "Unhandled parser failure" in err_payload["message"]
        assert "Traceback (most recent call last):" in err_payload["message"]
        assert "AttributeError: 'NoneType' object has no attribute 'text'" in err_payload["message"]
        assert err_payload["event"] == "parser_crash"
        assert (
            err_payload["logging.googleapis.com/trace"]
            == "projects/serverless-data-pipeline-111/traces/3e8882e6dbec1100590e6893ca5a8ec8"
        )

        post_payload = json.loads(raw_lines[2])
        assert post_payload["severity"] == "WARNING"
        assert not post_payload.get("logging.googleapis.com/trace")
    finally:
        configure_logging()


# ---------------------------------------------------------------------------
# 2. Scraper Resilience & Deduplication (fast_flights_scraper.py)
# ---------------------------------------------------------------------------


def test_generate_flexible_date_pairs_window_2_counts() -> None:
    pairs = generate_flexible_date_pairs(
        start_date="2027-06-01",
        trip_length=24,
        flexibility_window=2,
    )
    assert len(pairs) == 25
    unique_return_dates = {ret_dt for _, ret_dt in pairs}
    assert len(unique_return_dates) == 9
    assert pairs[0] == ("2027-05-30", "2027-06-21")
    assert pairs[-1] == ("2027-06-03", "2027-06-29")


@pytest.fixture(autouse=True)
def _default_socs_cookie_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SOCS_CONSENT_COOKIE_ENV_VAR, "SOCS=test-consent-cookie")


def test_consent_aware_fetch_integration_requires_cookie_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(SOCS_CONSENT_COOKIE_ENV_VAR, raising=False)
    with pytest.raises(ScraperError, match="SOCS_CONSENT_COOKIE"):
        ConsentAwareFetchIntegration(client=MagicMock())


def test_consent_aware_fetch_integration_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(SOCS_CONSENT_COOKIE_ENV_VAR, "SOCS=secret-manager-cookie")
    mock_client = MagicMock()
    mock_client.get.return_value = FakeHTTPResponse(status_code=200, text=VALID_FLIGHTS_HTML)
    sleeps: list[float] = []

    integration = ConsentAwareFetchIntegration(
        client=mock_client,
        request_delay_range=(0.0, 0.0),
        max_retries=2,
        backoff_base_seconds=1.0,
        sleep_fn=sleeps.append,
    )

    html = integration.fetch_html("BRU-YUL")
    assert html == VALID_FLIGHTS_HTML
    assert integration.http_requests_attempted == 1
    assert sleeps == []
    mock_client.get.assert_called_once()
    _, kwargs = mock_client.get.call_args
    assert kwargs["headers"] == {"cookie": "SOCS=secret-manager-cookie"}


def test_consent_aware_fetch_integration_retries_503_and_missing_ds1() -> None:
    mock_client = MagicMock()
    mock_client.get.side_effect = [
        FakeHTTPResponse(status_code=503, text="Service Unavailable"),
        FakeHTTPResponse(status_code=200, text="<html><body>Consent shell without ds:1</body></html>"),
        FakeHTTPResponse(status_code=200, text=VALID_FLIGHTS_HTML),
    ]
    sleeps: list[float] = []

    integration = ConsentAwareFetchIntegration(
        client=mock_client,
        request_delay_range=(0.0, 0.0),
        max_retries=2,
        backoff_base_seconds=0.5,
        sleep_fn=sleeps.append,
    )

    html = integration.fetch_html("BRU-YUL")
    assert html == VALID_FLIGHTS_HTML
    assert integration.http_requests_attempted == 3
    assert len(sleeps) == 2


def test_consent_aware_fetch_integration_aborts_immediately_on_sorry_interstitial() -> None:
    mock_client = MagicMock()
    mock_client.get.return_value = FakeHTTPResponse(
        status_code=302,
        url="https://www.google.com/sorry/index?continue=https://www.google.com/travel/flights",
        text="<html><body>unusual traffic from your computer network</body></html>",
    )
    sleeps: list[float] = []

    integration = ConsentAwareFetchIntegration(
        client=mock_client,
        request_delay_range=(0.0, 0.0),
        max_retries=3,
        backoff_base_seconds=1.0,
        sleep_fn=sleeps.append,
    )

    with pytest.raises(UpstreamScrapeError) as exc_info:
        integration.fetch_html("BRU-YUL")

    assert exc_info.value.reason == "sorry_interstitial"
    assert integration.http_requests_attempted == 1
    assert mock_client.get.call_count == 1
    assert sleeps == []


def test_return_date_deduplication_executes_34_queries_for_window_2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pairs = generate_flexible_date_pairs("2027-06-01", trip_length=24, flexibility_window=2)
    assert len(pairs) == 25

    dummy_integration = ConsentAwareFetchIntegration(
        client=MagicMock(),
        request_delay_range=(0.0, 0.0),
        sleep_fn=lambda _: None,
    )

    call_count = 0

    def fake_get_flights(query: Any, *, integration: Any) -> list[FakeFlightRecord]:
        nonlocal call_count
        call_count += 1
        integration.http_requests_attempted += 1
        return [FakeFlightRecord(price=500 + call_count, airlines=["AC"], departure_date="2027-06-01")]

    monkeypatch.setattr(fast_flights_scraper, "get_flights", fake_get_flights)

    results = fetch_flights_for_date_pairs(
        date_pairs=pairs,
        origin="BRU",
        destination="YUL",
        search_name="dedup_test",
        integration=dummy_integration,
        request_delay_range=(0.0, 0.0),
    )

    # 25 round-trip + 9 unique one-way return dates = 34 actual get_flights executions
    assert call_count == 34
    assert results.stats.date_pairs_count == 25
    assert results.stats.total_logical_queries == 50
    assert results.stats.cached_return_queries == 16
    assert results.stats.succeeded_queries == 34
    assert results.stats.failed_queries == 0
    assert results.stats.http_requests_attempted == 34

    # 25 RT rows + 25 OW rows = 50 total emitted records across every (outbound_date, return_date)
    assert len(results) == 50
    rt_pairs = {
        (r["_query_meta"]["outbound_date"], r["_query_meta"]["return_date"])
        for r in results
        if r["_query_meta"]["trip"] == "round-trip"
    }
    ow_pairs = {
        (r["_query_meta"]["outbound_date"], r["_query_meta"]["return_date"])
        for r in results
        if r["_query_meta"]["trip"] == "one-way"
    }
    assert rt_pairs == set(pairs)
    assert ow_pairs == set(pairs)


def test_regression_query_9_none_type_attribute_error_continues_with_partial_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pairs = generate_flexible_date_pairs("2027-06-01", trip_length=24, flexibility_window=1)
    assert len(pairs) == 9

    dummy_integration = ConsentAwareFetchIntegration(
        client=MagicMock(),
        request_delay_range=(0.0, 0.0),
        sleep_fn=lambda _: None,
    )

    call_idx = 0

    def fake_get_flights(query: Any, *, integration: Any) -> list[FakeFlightRecord]:
        nonlocal call_idx
        call_idx += 1
        if call_idx == 9:
            raise AttributeError("'NoneType' object has no attribute 'text'")
        return [FakeFlightRecord(price=620, airlines=["LH"], departure_date="2027-06-01")]

    monkeypatch.setattr(fast_flights_scraper, "get_flights", fake_get_flights)

    results = fetch_flights_for_date_pairs(
        date_pairs=pairs,
        origin="BRU",
        destination="YUL",
        search_name="prod_regression",
        integration=dummy_integration,
        request_delay_range=(0.0, 0.0),
    )

    # 9 RT + 5 unique OW = 14 calls; query #9 crashed with AttributeError, other 13 succeeded
    assert call_idx == 14
    assert results.stats.failed_queries == 1
    assert results.stats.succeeded_queries == 13
    assert len(results) > 0


def test_all_queries_failed_raises_whereas_pure_flights_not_found_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pairs = [("2027-06-01", "2027-06-25")]
    dummy_integration = ConsentAwareFetchIntegration(
        client=MagicMock(),
        request_delay_range=(0.0, 0.0),
        sleep_fn=lambda _: None,
    )

    def fail_every_query(query: Any, *, integration: Any) -> list[Any]:
        raise UpstreamScrapeError("Blocked by upstream", status_code=503, reason="http_503")

    monkeypatch.setattr(fast_flights_scraper, "get_flights", fail_every_query)

    with pytest.raises(AllQueriesFailedError) as exc_info:
        fetch_flights_for_date_pairs(
            date_pairs=pairs,
            integration=dummy_integration,
            request_delay_range=(0.0, 0.0),
        )
    assert exc_info.value.stats is not None
    assert exc_info.value.stats.failed_queries == 2

    def no_flights_every_query(query: Any, *, integration: Any) -> list[Any]:
        raise FlightsNotFound()

    monkeypatch.setattr(fast_flights_scraper, "get_flights", no_flights_every_query)

    empty_results = fetch_flights_for_date_pairs(
        date_pairs=pairs,
        integration=dummy_integration,
        request_delay_range=(0.0, 0.0),
    )
    assert list(empty_results) == []
    assert empty_results.stats.failed_queries == 0
    assert empty_results.stats.no_flights_queries == 2


def test_upload_raw_data_to_gcs_uploads_utc_jsonl_and_skips_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_storage_client_cls = MagicMock()
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_storage_client_cls.return_value = mock_client
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob

    monkeypatch.setattr(fast_flights_scraper.storage, "Client", mock_storage_client_cls)

    assert upload_raw_data_to_gcs("raw-flights-bucket", []) is None
    mock_storage_client_cls.assert_not_called()

    records = [
        {"price": 510, "_query_meta": {"outbound_date": "2027-06-01"}},
        {"price": 540, "_query_meta": {"outbound_date": "2027-06-02"}},
    ]
    expected_dt = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    uri = upload_raw_data_to_gcs("raw-flights-bucket", records, source="google_flights")
    assert uri is not None
    assert re.fullmatch(
        rf"gs://raw-flights-bucket/raw/source=google_flights/dt={expected_dt}/default_[0-9a-f-]{{36}}\.jsonl",
        uri,
    )
    mock_client.bucket.assert_called_once_with("raw-flights-bucket")
    uploaded_payload, upload_kwargs = (
        mock_blob.upload_from_string.call_args[0][0],
        mock_blob.upload_from_string.call_args[1],
    )
    assert upload_kwargs == {"content_type": "application/x-ndjson"}
    parsed_lines = [json.loads(line) for line in uploaded_payload.splitlines()]
    assert parsed_lines == records


# ---------------------------------------------------------------------------
# 3. HTTP Entrypoint & Parameter Validation (main.py)
# ---------------------------------------------------------------------------


def test_validate_request_params_none_safe_defaults() -> None:
    normalized = validate_request_params(
        {
            "search_name": None,
            "start_date": None,
            "trip_length": None,
            "flexibility_window": None,
            "origin": "bru",
            "destination": "yul",
            "adults": None,
            "max_stops": None,
            "target_price": None,
        }
    )
    assert normalized == {
        "search_name": "default",
        "start_date": "2027-06-01",
        "trip_length": 24,
        "flexibility_window": 1,
        "origin": "BRU",
        "destination": "YUL",
        "seat": "economy",
        "currency": "EUR",
        "adults": 1,
        "max_stops": 0,
        "target_price": None,
    }


def test_validate_request_params_target_price_and_invalid_values() -> None:
    assert validate_request_params({"target_price": 600})["target_price"] == 600.0
    assert validate_request_params({"target_price": 599.95})["target_price"] == 599.95
    assert validate_request_params({"target_price": 0})["target_price"] == 0.0

    for bad_target in [-1, -0.01, True, False, "600", float("nan"), float("inf")]:
        with pytest.raises(fetch_flights_main.ValidationError):
            validate_request_params({"target_price": bad_target})


def test_upload_raw_data_to_gcs_prefixes_and_sanitizes_search_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_storage_client_cls = MagicMock()
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_storage_client_cls.return_value = mock_client
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob
    monkeypatch.setattr(fast_flights_scraper.storage, "Client", mock_storage_client_cls)

    expected_dt = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    records = [{"price": 450}]

    uri_canada = upload_raw_data_to_gcs("raw-flights-bucket", records, search_name="canada")
    assert uri_canada is not None
    assert re.fullmatch(
        rf"gs://raw-flights-bucket/raw/source=google_flights/dt={expected_dt}/canada_[0-9a-f-]{{36}}\.jsonl",
        uri_canada,
    )

    uri_sanitized = upload_raw_data_to_gcs(
        "raw-flights-bucket", records, search_name="europe/summer 2027!!"
    )
    assert uri_sanitized is not None
    assert re.fullmatch(
        rf"gs://raw-flights-bucket/raw/source=google_flights/dt={expected_dt}/europe_summer_2027_[0-9a-f-]{{36}}\.jsonl",
        uri_sanitized,
    )


@pytest.mark.parametrize(
    "bad_request",
    [
        FakeFlaskRequest(json_body={"start_date": "2027-02-30"}),
        FakeFlaskRequest(json_body={"start_date": "01-06-2027"}),
        FakeFlaskRequest(json_body={"origin": "BRU", "destination": "BRU"}),
        FakeFlaskRequest(json_body={"adults": 0}),
        FakeFlaskRequest(json_body={"adults": True}),
        FakeFlaskRequest(json_body={"flexibility_window": 8}),
        FakeFlaskRequest(json_body={"trip_length": 0}),
        FakeFlaskRequest(json_body=None, raw_data=b"{malformed json"),
    ],
)
def test_fetch_flights_invalid_inputs_return_400_json(
    bad_request: FakeFlaskRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAW_DATA_BUCKET", "test-raw-bucket")
    body, status_code = fetch_flights(bad_request)
    assert status_code == 400
    assert body["status"] == "error"
    assert body["error_type"] == "ValidationError"
    assert isinstance(body["error"], str) and body["error"]


def test_fetch_flights_missing_raw_data_bucket_returns_500_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RAW_DATA_BUCKET", raising=False)
    body, status_code = fetch_flights(FakeFlaskRequest(json_body={"origin": "BRU", "destination": "YUL"}))
    assert status_code == 500
    assert body == {
        "status": "error",
        "error": "RAW_DATA_BUCKET environment variable is not set",
        "error_type": "ConfigurationError",
    }


def test_fetch_flights_all_queries_failed_returns_503_with_stats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAW_DATA_BUCKET", "test-raw-bucket")
    stats = ScrapeStats(
        date_pairs_count=1,
        total_logical_queries=2,
        http_requests_attempted=2,
        failed_queries=2,
    )

    def raise_all_failed(**kwargs: Any) -> ScrapeResultList:
        raise AllQueriesFailedError("Upstream unavailable", stats=stats)

    monkeypatch.setattr(fetch_flights_main, "fetch_flights_for_date_pairs", raise_all_failed)

    body, status_code = fetch_flights(
        FakeFlaskRequest(
            json_body={"origin": "BRU", "destination": "YUL", "flexibility_window": 0}
        )
    )
    assert status_code == 503
    assert body["status"] == "error"
    assert body["error_type"] == "AllQueriesFailedError"
    assert body["scrape_stats"]["failed_queries"] == 2


def test_fetch_flights_unexpected_exception_returns_500_json_not_html(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAW_DATA_BUCKET", "test-raw-bucket")

    def raise_unexpected(**kwargs: Any) -> ScrapeResultList:
        raise RuntimeError("boom inside downstream helper")

    monkeypatch.setattr(fetch_flights_main, "fetch_flights_for_date_pairs", raise_unexpected)

    body, status_code = fetch_flights(FakeFlaskRequest(json_body={}))
    assert status_code == 500
    assert isinstance(body, dict)
    assert body["status"] == "error"
    assert body["error_type"] == "RuntimeError"
    assert body["detail"] == "boom inside downstream helper"


def test_fetch_flights_end_to_end_success_returns_200_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAW_DATA_BUCKET", "test-raw-bucket")
    fake_stats = ScrapeStats(
        date_pairs_count=1,
        total_logical_queries=2,
        http_requests_attempted=2,
        succeeded_queries=2,
    )
    fake_results = ScrapeResultList(
        [{"price": 495}, {"price": 310}],
        stats=fake_stats,
    )

    monkeypatch.setattr(
        fetch_flights_main,
        "fetch_flights_for_date_pairs",
        lambda **kwargs: fake_results,
    )
    monkeypatch.setattr(
        fetch_flights_main,
        "upload_raw_data_to_gcs",
        lambda bucket_name, data, search_name="default": (
            f"gs://{bucket_name}/raw/source=google_flights/dt=2027-06-01/{search_name}_run.jsonl"
        ),
    )

    req = FakeFlaskRequest(
        json_body={
            "search_name": "montreal_2027",
            "origin": "BRU",
            "destination": "YUL",
            "start_date": "2027-06-01",
            "trip_length": 24,
            "flexibility_window": 0,
            "adults": None,
            "target_price": None,
        },
        headers={
            "X-Cloud-Trace-Context": "3e8882e6dbec1100590e6893ca5a8ec8/3737297187321845975;o=1"
        },
    )

    body, status_code = fetch_flights(req)
    assert status_code == 200
    assert body["status"] == "success"
    assert body["records_count"] == 2
    assert body["gcs_uri"] == "gs://test-raw-bucket/raw/source=google_flights/dt=2027-06-01/montreal_2027_run.jsonl"
    assert body["parameters"] == {
        "search_name": "montreal_2027",
        "origin": "BRU",
        "destination": "YUL",
        "start_date": "2027-06-01",
        "trip_length": 24,
        "flexibility_window": 0,
        "target_price": None,
    }
    assert body["scrape_stats"] == fake_stats.to_dict()
