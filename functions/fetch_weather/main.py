import os
import uuid
from datetime import datetime
import functions_framework
import google.auth
from google.cloud import secretmanager
import requests

def get_secret(secret_id: str) -> str:
    """Retrieves the secret value from GCP Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()

    # Check env vars first (standard in Cloud Functions, easy to override locally)
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT")
    if not project_id:
        _, project_id = google.auth.default()

    # Build the resource name of the secret
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"

    # Access the secret version
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

@functions_framework.http
def fetch_weather(request):
    """HTTP Cloud Function to fetch, transform, and log/return OpenWeatherMap data."""
    try:
        # 1. Pull the API Key from Secret Manager
        api_key = get_secret("open-weather-map-api-key")

        # 2. Pull the Weather Data, coordinates of Brussels
        lat = 50.8503
        lon = 4.3517
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&units=metric&appid={api_key}"

        response = requests.get(url)
        response.raise_for_status()
        weather_data = response.json()

        # 3. Apply Transformations
        # Extract and format fields to match our desired structure
        transformed_payload = {
            "location": "Brussels" if "Brussel" in weather_data.get("name", "") else weather_data.get("name", "Brussels"),
            "country": weather_data.get("sys", {}).get("country", "BE"),
            "temperature_c": weather_data.get("main", {}).get("temp"),
            "temperature_f": weather_data.get("main", {}).get("temp") * 9/5 + 32,
            "feels_like_c": weather_data.get("main", {}).get("feels_like"),
            "feels_like_f": weather_data.get("main", {}).get("feels_like")* 9/5 + 32,
            "humidity": weather_data.get("main", {}).get("humidity"),
            "pressure": weather_data.get("main", {}).get("pressure"),
            "wind_speed_mps": weather_data.get("wind", {}).get("speed"),
            "weather_condition": weather_data.get("weather", [{}])[0].get("main"),
            "weather_description": weather_data.get("weather", [{}])[0].get("description"),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

        print(f"Successfully processed weather data: {transformed_payload}")

        return transformed_payload, 200

    except Exception as e:
        error_msg = f"Error in fetch_weather function: {str(e)}"
        print(error_msg)
        return {"error": error_msg}, 500
