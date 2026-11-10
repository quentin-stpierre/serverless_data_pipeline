import os
import functions_framework
from fast_flights_scraper import (
    generate_flexible_date_pairs,
    fetch_flights_for_date_pairs,
    upload_raw_data_to_gcs,
)

@functions_framework.http
def fetch_flights(request):
    """HTTP Cloud Function entrypoint to scrape flight data based on request parameters."""
    request_json = request.get_json(silent=True) or {}

    # Extract query parameters with fallbacks
    search_name = request_json.get("search_name", "default") or "default"
    start_date = request_json.get("start_date", "2027-06-01")
    trip_length = int(request_json.get("trip_length", 24))
    flexibility_window = int(request_json.get("flexibility_window", 1))
    origin = request_json.get("origin", "BRU")
    destination = request_json.get("destination", "YUL")
    seat = request_json.get("seat", "economy")
    currency = request_json.get("currency", "EUR")
    adults = int(request_json.get("adults", 1))
    max_stops = int(request_json.get("max_stops", 0))

    # Generate flexible dates
    date_pairs = generate_flexible_date_pairs(
        start_date=start_date,
        trip_length=trip_length,
        flexibility_window=flexibility_window,
    )

    # Scrape raw data
    results = fetch_flights_for_date_pairs(
        date_pairs=date_pairs,
        origin=origin,
        destination=destination,
        seat=seat,
        currency=currency,
        adults=adults,
        max_stops=max_stops,
        search_name=search_name,
    )

    bucket_name = os.environ.get("RAW_DATA_BUCKET")
    if not bucket_name:
        return {"error": "RAW_DATA_BUCKET environment variable is not set"}, 500

    gcs_uri = upload_raw_data_to_gcs(bucket_name=bucket_name, data=results)

    return {
        "status": "success",
        "records_count": len(results),
        "gcs_uri": gcs_uri,
        "parameters": {
            "search_name": search_name,
            "origin": origin,
            "destination": destination,
            "start_date": start_date,
            "trip_length": trip_length,
            "flexibility_window": flexibility_window,
        },
    }, 200
