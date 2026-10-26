import os
import sys
import time
import requests
import json

# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------
BRIGHTDATA_API_KEY = os.environ.get(
    "BRIGHTDATA_API_KEY", ""
)
DATASET_ID = os.environ.get("BRIGHTDATA_DATASET_ID", "gd_mhng7wen1rw0a3gvpf")
BASE_URL = "https://api.brightdata.com/datasets/v3"

headers = {
    "Authorization": f"Bearer {BRIGHTDATA_API_KEY}",
    "Content-Type": "application/json"
}

# Single flight search parameters: BRU -> YUL (June 1 to June 25, 2027)
params = {
    "origin": "BRU",
    "destination": "YUL",
    "departure": "2027-06-01T00:00:00.000Z",
    "return": "2027-06-25T00:00:00.000Z",
    "trip_type": "Round trip",  # 'Round trip' or 'One way'
    "adults": 1,
    "cabin": "Economy",
    "only_direct": True  # Set to True to filter strictly for non-stop flights
}


def download_snapshot(snapshot_id: str, only_direct: bool = True):
    """Downloads and displays the results of an existing snapshot without re-triggering."""
    progress_url = f"{BASE_URL}/progress/{snapshot_id}"
    snapshot_url = f"{BASE_URL}/snapshot/{snapshot_id}?format=json"

    print(f"Checking snapshot {snapshot_id} (only_direct={only_direct})...")
    res = requests.get(progress_url, headers=headers, timeout=15)
    if res.status_code != 200:
        print(f"Status check failed: {res.status_code} - {res.text}")
        return

    progress_data = res.json()
    status = progress_data.get("status")
    print(f"Status: {status} (Total duration: {progress_data.get('collection_duration', progress_data.get('running_time', 0)) // 1000}s)")

    if status in ("ready", "completed"):
        data_res = requests.get(snapshot_url, headers=headers, timeout=45)
        if data_res.status_code == 200:
            return display_results(data_res.json(), only_direct=only_direct)
        else:
            print(f"Failed to fetch data: {data_res.text}")
    else:
        print(f"Job is still {status}. Please wait or poll again later.")


def fetch_flights(only_direct: bool = None):
    """Triggers a single Google Flights scrape on Bright Data and polls until complete."""
    if only_direct is None:
        only_direct = params.get("only_direct", True)

    # API input payload (only accepts discovery filter schema)
    api_payload = {
        "origin": params["origin"],
        "destination": params["destination"],
        "departure": params["departure"],
        "return": params["return"],
        "trip_type": params["trip_type"],
        "adults": params["adults"],
        "cabin": params["cabin"],
    }

    print(f"Triggering Bright Data scrape for {params['origin']} -> {params['destination']} ({params['departure'][:10]} to {params['return'][:10]})...")
    print(f"Filter settings: only_direct = {only_direct}")

    trigger_url = (
        f"{BASE_URL}/trigger?dataset_id={DATASET_ID}"
        f"&format=json&type=discover_new&discover_by=input_filters"
    )

    try:
        response = requests.post(trigger_url, headers=headers, json=[api_payload], timeout=30)
    except requests.exceptions.RequestException as e:
        print(f"Failed to submit scrape job: {e}")
        return

    if response.status_code not in (200, 202):
        print(f"HTTP Error {response.status_code}: {response.text}")
        return

    snapshot_id = response.json().get("snapshot_id")
    if not snapshot_id:
        print(f"Unexpected response: {response.text}")
        return

    print(f"✅ Job submitted! Snapshot ID: {snapshot_id}")
    print("Bright Data uses full headless browsers with anti-bot solving.")
    print("Waiting for scrape results (polls every 15s)...")

    progress_url = f"{BASE_URL}/progress/{snapshot_id}"
    snapshot_url = f"{BASE_URL}/snapshot/{snapshot_id}?format=json"

    while True:
        time.sleep(15)
        try:
            status_res = requests.get(progress_url, headers=headers, timeout=15)
            if status_res.status_code != 200:
                continue

            status_data = status_res.json()
            status = status_data.get("status")
            running_secs = status_data.get("running_time", 0) // 1000
            print(f"  Status: {status} ({running_secs}s elapsed)")

            if status in ("ready", "completed"):
                print("🎉 Scraping complete! Downloading flight data...")
                data_res = requests.get(snapshot_url, headers=headers, timeout=45)
                if data_res.status_code == 200:
                    return display_results(data_res.json(), only_direct=only_direct)
                else:
                    print(f"Failed to download snapshot: {data_res.text}")
                break
            elif status == "failed":
                print("❌ Scrape job failed on Bright Data.")
                break
        except requests.exceptions.RequestException as e:
            print(f"Network warning: {e}")


def display_results(data, only_direct: bool = True):
    """Parses and prints the returned flight options, airlines, and prices."""
    if not data:
        print("No flight data returned.")
        return []

    items = data if isinstance(data, list) else data.get("data", [])

    filtered_records = []
    for item in items:
        legs = item.get("legs", [])
        outbound = legs[0] if len(legs) > 0 else {}
        inbound = legs[1] if len(legs) > 1 else {}

        out_stops = str(outbound.get("stops", "0"))
        in_stops = str(inbound.get("stops", "0")) if inbound else "0"

        # Check if both outbound and inbound legs are direct (0 stops)
        is_direct = (out_stops == "0") and (in_stops == "0")

        if only_direct and not is_direct:
            continue

        filtered_records.append((item, is_direct, out_stops, in_stops))

    filter_label = " [Direct Flights Only]" if only_direct else ""
    print(f"\n========================================================")
    print(f"  Found {len(filtered_records)} of {len(items)} Flight Option(s){filter_label}")
    print(f"========================================================")

    if not filtered_records and only_direct:
        print("No direct flights found for this route and date combination.")
        return []

    results = []
    for idx, (item, is_direct, out_stops, in_stops) in enumerate(filtered_records, start=1):
        pricing = item.get("pricing", {})
        providers = item.get("providers", [])
        legs = item.get("legs", [])

        # Price formatting (look for secondary EUR price or best total price)
        eur_price = None
        for p in providers:
            sec = p.get("secondary_price")
            if isinstance(sec, dict) and sec.get("currency") == "EUR":
                eur_price = f"{sec.get('value')} EUR"
                break

        total_price = eur_price or f"{pricing.get('best_total_price', 'N/A')} {pricing.get('currency', 'EUR')}"

        outbound = legs[0] if len(legs) > 0 else {}
        inbound = legs[1] if len(legs) > 1 else {}

        # Outbound flight details
        out_segments = outbound.get("segments", [])
        out_airline = out_segments[0].get("airline_name") if out_segments else "N/A"
        out_flight_no = out_segments[0].get("flight_number") if out_segments else ""
        stops_str = "Direct" if str(out_stops) == "0" else f"{out_stops} stop(s)"

        print(f"\nOption #{idx}: {out_airline} {out_flight_no} | Price: {total_price}")
        print(f"  Outbound ({outbound.get('date', '')[:10]}): {outbound.get('depart_local')} ({outbound.get('origin_airport')}) -> {outbound.get('arrive_local')} ({outbound.get('destination_airport')}) [{stops_str}]")

        if inbound:
            in_segments = inbound.get("segments", [])
            in_airline = in_segments[0].get("airline_name") if in_segments else "N/A"
            in_flight_no = in_segments[0].get("flight_number") if in_segments else ""
            in_stops_str = "Direct" if str(in_stops) == "0" else f"{in_stops} stop(s)"
            print(f"  Return   ({inbound.get('date', '')[:10]}): {inbound.get('depart_local')} ({inbound.get('origin_airport')}) -> {inbound.get('arrive_local')} ({inbound.get('destination_airport')}) [{in_stops_str}]")

        results.append({
            "airline": out_airline,
            "flight_number": out_flight_no,
            "price": total_price,
            "is_direct": is_direct,
            "details": item
        })

    return results


if __name__ == "__main__":
    # If a snapshot ID is passed as argument, download it directly:
    # python brightdata_scraper.py sd_mvp3e1wu14z5ijiebv
    if len(sys.argv) > 1 and sys.argv[1].startswith("sd_"):
        download_snapshot(sys.argv[1], only_direct=params["only_direct"])
    else:
        fetch_flights(only_direct=params["only_direct"])
