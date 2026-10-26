import json
from serpapi import GoogleSearch
from datetime import datetime, timedelta, date

# ---------------------------------------------------------
# Configuration & Hardcoded API Key
# ---------------------------------------------------------
SERPAPI_KEY = ""

params = {
    "engine": "google_flights",
    "departure_id": "BRU,CRL",          # Brussels Metropolitan Area (BRU & CRL)
    "arrival_id": "YUL",            # Montreal Metropolitan Area (YUL)
    "outbound_date": "2027-06-01",  # YYYY-MM-DD
    "return_date": "2027-06-25",    # YYYY-MM-DD
    "currency": "EUR",
    "type": "1",
    "hl": "en",                     # Language
    "api_key": SERPAPI_KEY
}

def fetch_flights():
    print("Sending request to SerpApi...")

    # Execute the API call
    search = GoogleSearch(params)
    results = search.get_dict()

    # Check for API errors
    if "error" in results:
        print(f"API Error: {results['error']}")
        return

    print(results)

    # # Process Best Flights
    # best_flights = results.get("best_flights", [])
    # print(f"\n--- Found {len(best_flights)} Best Flight Option(s) ---")

    # for idx, flight in enumerate(best_flights, start=1):
    #     price = flight.get("price")
    #     total_duration = flight.get("total_duration")
    #     flights_leg = flight.get("flights", [])

    #     print(f"\nOption #{idx}:")
    #     print(f"  Price: {price} EUR")
    #     print(f"  Duration: {total_duration} minutes")

    #     for leg in flights_leg:
    #         airline = leg.get("airline")
    #         flight_num = leg.get("flight_number")
    #         dep_airport = leg.get("departure_airport", {}).get("name")
    #         arr_airport = leg.get("arrival_airport", {}).get("name")
    #         print(f"  - Leg: {airline} ({flight_num}) | {dep_airport} -> {arr_airport}")



def generate_flexible_date_pairs(
    start_date="2027-06-01", trip_length=25, flexibility_window=2
):
    """
    Generates outbound and return date pairs based on a start date, target trip length,
    and a flexibility window.

    Generates the base date pair (start_date and start_date + trip_length) along with
    all combinations obtained by varying the departure and return dates by +/- flexibility_window days.
    """
    if isinstance(start_date, str):
        base_start = datetime.strptime(start_date, "%Y-%m-%d").date()
    elif isinstance(start_date, datetime):
        base_start = start_date.date()
    elif isinstance(start_date, date):
        base_start = start_date
    else:
        raise ValueError(
            "start_date must be a string (YYYY-MM-DD), date, or datetime object"
        )

    base_end = base_start + timedelta(days=trip_length)
    date_pairs = []

    for dep_offset in range(-flexibility_window, flexibility_window + 1):
        outbound = base_start + timedelta(days=dep_offset)
        for ret_offset in range(-flexibility_window, flexibility_window + 1):
            inbound = base_end + timedelta(days=ret_offset)
            date_pairs.append({
                "outbound": outbound.strftime("%Y-%m-%d"),
                "return": inbound.strftime("%Y-%m-%d"),
                "duration_days": (inbound - outbound).days,
            })

    return date_pairs



# Example output:
# date_matrix = generate_flexible_date_pairs(
#     start_date="2027-06-01", trip_length=14, flexibility_window=2
# )
# print(f"Generated {len(date_matrix)} flight combinations to query.")
# print(date_matrix)

if __name__ == "__main__":
    # fetch_flights()
    date_matrix = generate_flexible_date_pairs(
        start_date="2027-06-01", trip_length=26, flexibility_window=2
    )
    print(date_matrix)
    print(len(date_matrix))
