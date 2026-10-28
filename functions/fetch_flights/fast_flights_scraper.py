import json
import os
import uuid
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta
from typing import Any

from fast_flights import FlightQuery, FlightsNotFound, Passengers, create_query, get_flights
from fast_flights.integrations.base import FetchIntegration
from google.cloud import storage
from primp import Client


class ConsentAwareFetchIntegration(FetchIntegration):
    def fetch_html(self, q) -> str:
        return Client(impersonate="chrome_145").get(
            "https://www.google.com/travel/flights/search",
            params=q.params(),
            headers={"cookie": "SOCS=CAESEwgDEgk2ODEwNTc2NjIaAmVuIAEaBgiA_LyaBg"},
        ).text


def generate_flexible_date_pairs(
    start_date: str, trip_length: int, flexibility_window: int = 0
) -> list[tuple[str, str]]:
    """Generates (outbound_date, return_date) pairs symmetrically around start_date and trip_length."""
    base_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    pairs: list[tuple[str, str]] = []

    for out_offset in range(-flexibility_window, flexibility_window + 1):
        outbound_dt = base_date + timedelta(days=out_offset)
        for len_offset in range(-flexibility_window, flexibility_window + 1):
            current_length = trip_length + len_offset
            if current_length < 1:
                continue
            return_dt = outbound_dt + timedelta(days=current_length)
            pairs.append((outbound_dt.strftime("%Y-%m-%d"), return_dt.strftime("%Y-%m-%d")))

    return pairs


def _to_serializable(obj: Any) -> Any:
    """Recursively converts an object to a JSON-serializable format, supporting dataclasses."""
    if is_dataclass(obj):
        return asdict(obj)
    if hasattr(obj, "__dict__"):
        return {k: _to_serializable(v) for k, v in obj.__dict__.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_serializable(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj


def fetch_flights_for_date_pairs(
    date_pairs: list[tuple[str, str]],
    origin: str = "BRU",
    destination: str = "YUL",
    seat: str = "economy",
    currency: str = "EUR",
    adults: int = 1,
    max_stops: int = 0,
) -> list[dict]:
    """Queries Google Flights for each date pair and returns all raw flight records."""
    integration = ConsentAwareFetchIntegration()
    raw_results: list[dict] = []

    for outbound_date, return_date in date_pairs:
        # 1. Fetch round-trip options (raw)
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
            for flight in get_flights(rt_query, integration=integration):
                data = _to_serializable(flight)
                data["_query_meta"] = {
                    "outbound_date": outbound_date,
                    "return_date": return_date,
                    "origin": origin,
                    "destination": destination,
                    "trip": "round-trip",
                    "currency": currency,
                    "seat": seat,
                }
                raw_results.append(data)
        except FlightsNotFound:
            pass

        # 2. Fetch return leg options (raw)
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
            for flight in get_flights(ret_query, integration=integration):
                data = _to_serializable(flight)
                data["_query_meta"] = {
                    "outbound_date": outbound_date,
                    "return_date": return_date,
                    "origin": destination,
                    "destination": origin,
                    "trip": "one-way",
                    "currency": currency,
                    "seat": seat,
                }
                raw_results.append(data)
        except FlightsNotFound:
            pass

    return raw_results


def upload_raw_data_to_gcs(
    bucket_name: str,
    data: list[dict],
    source: str = "google_flights",
) -> str | None:
    """Dumps raw flight records as a JSONL file to the specified Google Cloud Storage bucket."""
    if not data:
        print("No flight data to upload.")
        return None

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    scrape_id = str(uuid.uuid4())
    dt_str = datetime.utcnow().strftime("%Y-%m-%d")
    blob_name = f"raw/source={source}/dt={dt_str}/{scrape_id}.jsonl"

    blob = bucket.blob(blob_name)
    jsonl_content = "\n".join(json.dumps(record, default=str) for record in data)
    blob.upload_from_string(jsonl_content, content_type="application/x-ndjson")

    gcs_uri = f"gs://{bucket_name}/{blob_name}"
    print(f"Successfully uploaded {len(data)} raw records to {gcs_uri}")
    return gcs_uri


if __name__ == "__main__":
    date_pairs = generate_flexible_date_pairs(
        start_date="2027-06-01",
        trip_length=24,
        flexibility_window=1,
    )
    results = fetch_flights_for_date_pairs(
        date_pairs=date_pairs,
        origin="BRU",
        destination="YUL",
    )
    bucket_name = os.environ.get("RAW_DATA_BUCKET")
    if bucket_name:
        upload_raw_data_to_gcs(bucket_name=bucket_name, data=results)
    else:
        print(f"Scraped {len(results)} records. RAW_DATA_BUCKET environment variable not set; skipping upload.")
