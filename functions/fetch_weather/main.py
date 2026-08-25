import os
import uuid
from datetime import datetime
import logging
import functions_framework
import google.auth
from google.cloud import secretmanager
from google.api_core import exceptions as gcp_exceptions
import google.cloud.logging
import requests

# Initialize Google Cloud Logging and integrate with standard Python logging
try:
    logging_client = google.cloud.logging.Client()
    logging_client.setup_logging()
except Exception as e:
    logging.basicConfig(level=logging.INFO)
    logging.warning(f"Could not set up Cloud Logging, falling back to basic configuration: {e}")

logger = logging.getLogger("fetch_weather")


def get_secret(secret_id: str) -> str:
    """Retrieves the secret value from GCP Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()

    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT")
    if not project_id:
        _, project_id = google.auth.default()

    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")


@functions_framework.http
def fetch_weather(request):
    """HTTP Cloud Function to fetch, transform, and log/return OpenWeatherMap data."""
    request_id = str(uuid.uuid4())
    log_fields = {"request_id": request_id, "function": "fetch_weather"}

    logger.debug(
        "Starting weather fetch",
        extra={"json_fields": {**log_fields, "stage": "start"}},
    )

    # --- 1. Get the API key ---
    try:
        api_key = get_secret("open-weather-map-api-key")
    except gcp_exceptions.NotFound as e:
        logger.critical(
            f"Secret not found — check secret name/permissions: {e}",
            extra={"json_fields": {**log_fields, "stage": "secret_fetch"}},
        )
        return {"error": "Server misconfiguration", "request_id": request_id}, 500
    except Exception as e:
        logger.critical(
            f"Unexpected error retrieving secret: {e}",
            extra={"json_fields": {**log_fields, "stage": "secret_fetch"}},
        )
        return {"error": "Server misconfiguration", "request_id": request_id}, 500

    # --- 2. Call the weather API ---
    lat, lon = 50.8503, 4.3517
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&units=metric&appid={api_key}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        weather_data = response.json()
    except requests.exceptions.Timeout as e:
        logger.error(
            f"OpenWeatherMap request timed out: {e}",
            extra={"json_fields": {**log_fields, "stage": "api_call"}},
        )
        return {"error": "Upstream weather service timed out", "request_id": request_id}, 504
    except requests.exceptions.HTTPError as e:
        status = response.status_code if response is not None else None
        severity = "WARNING" if status and 400 <= status < 500 else "ERROR"
        logger.log(
            logging.WARNING if severity == "WARNING" else logging.ERROR,
            f"OpenWeatherMap returned HTTP error {status}: {e}",
            extra={"json_fields": {**log_fields, "stage": "api_call", "upstream_status": status}},
        )
        return {"error": "Upstream weather service error", "request_id": request_id}, 502
    except requests.exceptions.RequestException as e:
        logger.error(
            f"Network error calling OpenWeatherMap: {e}",
            extra={"json_fields": {**log_fields, "stage": "api_call"}},
        )
        return {"error": "Could not reach weather service", "request_id": request_id}, 502
    except ValueError as e:  # includes JSONDecodeError
        logger.error(
            f"Failed to parse OpenWeatherMap response as JSON: {e}",
            extra={"json_fields": {**log_fields, "stage": "api_call"}},
        )
        return {"error": "Invalid response from weather service", "request_id": request_id}, 502

    # --- 3. Transform ---
    try:
        main = weather_data.get("main", {})

        transformed_payload = {
            "location": "Brussels" if "Brussel" in weather_data.get("name", "") else weather_data.get("name", "Brussels"),
            "country": weather_data.get("sys", {}).get("country", "BE"),
            "temperature_c": main.get("temp"),
            "temperature_f": (main.get("temp") * 9 / 5 + 32) if main.get("temp") is not None else None,
            "feels_like_c": main.get("feels_like"),
            "feels_like_f": (main.get("feels_like") * 9 / 5 + 32) if main.get("feels_like") is not None else None,
            "humidity": main.get("humidity"),
            "pressure": main.get("pressure"),
            "wind_speed_mps": weather_data.get("wind", {}).get("speed"),
            "weather_condition": weather_data.get("weather", [{}])[0].get("main"),
            "weather_description": weather_data.get("weather", [{}])[0].get("description"),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    except Exception as e:
        logger.error(
            f"Failed to transform weather data: {e}",
            extra={"json_fields": {**log_fields, "stage": "transform"}},
        )
        return {"error": "Failed to process weather data", "request_id": request_id}, 500

    logger.info(
        "Successfully processed weather data",
        extra={"json_fields": {**log_fields, "stage": "success", "payload": transformed_payload}},
    )

    return transformed_payload, 200
