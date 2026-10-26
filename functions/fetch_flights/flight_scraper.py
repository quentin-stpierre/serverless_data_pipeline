import os
import requests
import json

# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------
RAPIDAPI_KEY = os.environ.get(
    "RAPIDAPI_KEY", ""
)

# API Host for "Flights Scraper Sky" on RapidAPI
API_HOST = "flights-sky.p.rapidapi.com"
URL = f"https://{API_HOST}/google/price-calendar/for-roundtrip"

headers = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": API_HOST
}

# Parameters: Querying BRU to YUL for June 2027
params = {
    "departureId": "BRU",          # Brussels
    "arrivalId": "YUL",            # Montreal
    "departureDate": "2027-06-01",
    "arrivalDate": "2027-06-31",
    "currency": "EUR",
    "daysBetween": "24"
}

def fetch_monthly_calendar():
    print("Fetching monthly calendar price matrix...")

    response = requests.get(URL, headers=headers, params=params)

    if response.status_code != 200:
        print(f"Error {response.status_code}: {response.text}")
        return

    try:
        data = response.json()
    except Exception as e:
        print(f"Failed to parse JSON response: {e}")
        return

    # Check for API-level errors
    if isinstance(data, dict) and data.get("status") is False and "errors" in data:
        print(f"API Error: {data.get('message', 'Errors returned')}")
        print(json.dumps(data["errors"], indent=2))
        return

    # Extract the calendar price matrix from response
    print("\n--- Daily Price Estimates for June 2027 ---")

    # The API returns a list of flight date prices under 'data'
    raw_data = data.get("data")

    print(raw_data)


if __name__ == "__main__":
    fetch_monthly_calendar()
