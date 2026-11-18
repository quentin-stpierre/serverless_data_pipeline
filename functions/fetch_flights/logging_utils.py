"""Google Cloud structured logging utilities for Cloud Run functions."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import date, datetime
import json
import logging
import os
import re
import sys
from typing import Any

import google.cloud.logging_v2
from google.cloud.logging_v2.handlers import StructuredLogHandler

_EXCLUDED_LOGGERS = (
    "werkzeug",
    "google.cloud",
    "google.auth",
    "google_auth_httplib2",
    "google.api_core.bidi",
)

_TRACEPARENT_RE = re.compile(
    r"^\s*(?!ff)([0-9a-f]{2})-(?!0{32})([0-9a-f]{32})-(?!0{16})([0-9a-f]{16})-([0-9a-f]{2})(?:-.*)?\s*$"
)
_XCLOUD_TRACE_RE = re.compile(
    r"^\s*([0-9a-fA-F]{32})(?:/([0-9a-fA-F]+))?(?:;o=(\d+))?\s*$"
)


@dataclass(frozen=True)
class RequestTraceContext:
    """Per-request trace and HTTP metadata bound via contextvars."""

    trace_id: str | None = None
    span_id: str | None = None
    trace_sampled: bool = False
    http_request: dict[str, Any] | None = None


_request_context_var: ContextVar[RequestTraceContext | None] = ContextVar(
    "request_trace_context",
    default=None,
)


class _SafeJSONEncoder(json.JSONEncoder):
    """JSON encoder that safely serializes dates, sets, and arbitrary objects."""

    def default(self, o: Any) -> Any:
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, (set, frozenset, tuple)):
            return list(o)
        if isinstance(o, BaseException):
            return str(o)
        return str(o)


def _get_header(headers: Mapping[str, Any] | Any, name: str) -> str | None:
    """Case-insensitively retrieve a string header from a Flask/dict headers mapping."""
    if headers is None:
        return None
    if hasattr(headers, "get"):
        direct = headers.get(name)
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        lower = headers.get(name.lower())
        if isinstance(lower, str) and lower.strip():
            return lower.strip()
    if isinstance(headers, Mapping):
        target = name.lower()
        for key, value in headers.items():
            if isinstance(key, str) and key.lower() == target and isinstance(value, str):
                stripped = value.strip()
                if stripped:
                    return stripped
    return None


def _parse_x_cloud_trace_context(header: str | None) -> tuple[str | None, str | None, bool]:
    """Parse X-Cloud-Trace-Context: TRACE_ID[/SPAN_ID][;o=TRACE_SAMPLED]."""
    if not header:
        return None, None, False

    match = _XCLOUD_TRACE_RE.match(header)
    if not match:
        return None, None, False

    trace_id = match.group(1).lower()
    if trace_id == "0" * 32:
        return None, None, False

    raw_span = match.group(2)
    span_id: str | None = None
    if raw_span:
        if raw_span.isdigit():
            span_int = int(raw_span)
            if 0 < span_int < 2**64:
                span_id = f"{span_int:016x}"
        elif len(raw_span) == 16 and all(c in "0123456789abcdefABCDEF" for c in raw_span):
            lowered = raw_span.lower()
            if lowered != "0" * 16:
                span_id = lowered

    trace_sampled = match.group(3) == "1"
    return trace_id, span_id, trace_sampled


def _parse_traceparent(header: str | None) -> tuple[str | None, str | None, bool]:
    """Parse W3C Traceparent: 00-TRACE_ID-SPAN_ID-FLAGS."""
    if not header:
        return None, None, False

    match = _TRACEPARENT_RE.match(header.lower())
    if not match:
        return None, None, False

    trace_id = match.group(2)
    span_id = match.group(3)
    flags = int(match.group(4), 16)
    trace_sampled = bool(flags & 1)
    return trace_id, span_id, trace_sampled


def parse_trace_headers(headers: Mapping[str, Any] | Any) -> tuple[str | None, str | None, bool]:
    """Extract (trace_id, span_id, trace_sampled) from X-Cloud-Trace-Context or Traceparent."""
    xcloud_header = _get_header(headers, "X-Cloud-Trace-Context")
    traceparent_header = _get_header(headers, "Traceparent")

    trace_id, span_id, trace_sampled = _parse_x_cloud_trace_context(xcloud_header)
    tp_trace_id, tp_span_id, tp_sampled = _parse_traceparent(traceparent_header)

    if trace_id is None:
        return tp_trace_id, tp_span_id, tp_sampled

    if tp_trace_id == trace_id:
        if span_id is None:
            span_id = tp_span_id
        if not trace_sampled and tp_sampled:
            trace_sampled = True

    return trace_id, span_id, trace_sampled


def _extract_http_request_metadata(request: Any) -> dict[str, Any] | None:
    """Build a Cloud Logging httpRequest payload from a Flask-compatible request object."""
    if request is None:
        return None

    method = getattr(request, "method", None)
    url = getattr(request, "url", None)
    if not isinstance(method, str) or not isinstance(url, str):
        return None

    http_req: dict[str, Any] = {
        "requestMethod": method,
        "requestUrl": url,
    }

    headers = getattr(request, "headers", None)
    user_agent = _get_header(headers, "User-Agent")
    if user_agent:
        http_req["userAgent"] = user_agent

    remote_addr = getattr(request, "remote_addr", None)
    if isinstance(remote_addr, str) and remote_addr:
        http_req["remoteIp"] = remote_addr

    environ = getattr(request, "environ", None)
    if isinstance(environ, Mapping):
        protocol = environ.get("SERVER_PROTOCOL")
        if isinstance(protocol, str) and protocol:
            http_req["protocol"] = protocol

    return http_req


class RequestContextFilter(logging.Filter):
    """Injects per-request Cloud Trace and HTTP metadata into LogRecords before formatting."""

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = _request_context_var.get()
        if ctx is None:
            return True

        project_id = (
            os.environ.get("GCP_PROJECT")
            or os.environ.get("GOOGLE_CLOUD_PROJECT")
            or ""
        ).strip()

        if ctx.trace_id and not getattr(record, "trace", None):
            if project_id:
                record.trace = f"projects/{project_id}/traces/{ctx.trace_id}"
            else:
                record.trace = ctx.trace_id

        if ctx.span_id and not getattr(record, "span_id", None):
            record.span_id = ctx.span_id

        if not hasattr(record, "trace_sampled"):
            record.trace_sampled = ctx.trace_sampled

        if ctx.http_request and not getattr(record, "http_request", None):
            record.http_request = ctx.http_request

        return True


def bind_request_context(request: Any) -> Token[RequestTraceContext | None]:
    """Bind trace and HTTP metadata from an incoming Flask request to contextvars."""
    headers = getattr(request, "headers", None) if request is not None else None
    trace_id, span_id, trace_sampled = parse_trace_headers(headers)
    http_request = _extract_http_request_metadata(request)
    ctx = RequestTraceContext(
        trace_id=trace_id,
        span_id=span_id,
        trace_sampled=trace_sampled,
        http_request=http_request,
    )
    return _request_context_var.set(ctx)


def clear_request_context(token: Token[RequestTraceContext | None] | None = None) -> None:
    """Restore or clear the active request trace context."""
    if token is not None:
        _request_context_var.reset(token)
    else:
        _request_context_var.set(None)


@contextmanager
def request_logging_context(request: Any) -> Iterator[RequestTraceContext | None]:
    """Context manager that binds and deterministically resets per-request trace context."""
    token = bind_request_context(request)
    try:
        yield _request_context_var.get()
    finally:
        clear_request_context(token)


def configure_logging(
    *,
    level: int | str | None = None,
    stream: Any = None,
) -> StructuredLogHandler:
    """Configure root Python logger with GCP StructuredLogHandler on stdout."""
    resolved_stream = stream if stream is not None else sys.stdout
    raw_level = level if level is not None else os.environ.get("LOG_LEVEL", "INFO")
    if isinstance(raw_level, str):
        resolved_level = getattr(logging, raw_level.upper(), logging.INFO)
    else:
        resolved_level = raw_level

    project_id = (
        os.environ.get("GCP_PROJECT")
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or None
    )

    google.cloud.logging_v2._instrumentation_emitted = True

    handler = StructuredLogHandler(
        stream=resolved_stream,
        project_id=project_id,
        json_encoder_cls=_SafeJSONEncoder,
    )
    handler.filters.insert(0, RequestContextFilter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(resolved_level)
    root_logger.addHandler(handler)

    for logger_name in _EXCLUDED_LOGGERS:
        logging.getLogger(logger_name).propagate = False

    return handler
