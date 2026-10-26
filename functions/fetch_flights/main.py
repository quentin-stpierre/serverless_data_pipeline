import os
import uuid
import logging
from datetime import datetime
import functions_framework
import google.auth
from google.cloud import secretmanager
from google.api_core import exceptions as gcp_exceptions
import google.cloud.logging
from serpapi import GoogleSearch

# Initialize Google Cloud Logging only when running in production GCP environments (Cloud Run/Functions)
if os.environ.get("K_SERVICE"):
    try:
        logging_client = google.cloud.logging.Client()
        logging_client.setup_logging()
    except Exception as e:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
        logging.warning(f"Could not set up Cloud Logging, falling back to basic configuration: {e}")
else:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")

logger = logging.getLogger("fetch_flights")


def get_secret(secret_id: str) -> str:
    """Retrieves the secret value from GCP Secret Manager.
    Fails gracefully if not authenticated or not in a GCP environment.
    """
    try:
        client = secretmanager.SecretManagerServiceClient()
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT")
        if not project_id:
            _, project_id = google.auth.default()

        name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        logger.warning(f"Failed to retrieve secret '{secret_id}' from Secret Manager: {e}")
        return None


@functions_framework.http
def fetch_flights(request):
    """HTTP Cloud Function to fetch flight tracker information using SerpApi Google Flights."""

    # 1. Handle CORS Preflight request
    if request.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "3600",
        }
        return ("", 204, headers)

    # Set CORS headers for the main request
    headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}

    request_id = str(uuid.uuid4())
    log_fields = {"request_id": request_id, "function": "fetch_flights"}

    logger.info(
        "Starting flight tracker fetch",
        extra={"json_fields": {**log_fields, "stage": "start"}},
    )

    # 2. Parse request parameters (accept both GET query parameters and POST JSON body)
    params = {}
    if request.method == "POST":
        try:
            params = request.get_json(silent=True) or {}
        except Exception as e:
            logger.error(f"Failed to parse POST JSON body: {e}")
            return ({"error": "Invalid JSON body", "request_id": request_id}, 400, headers)
    elif request.method == "GET":
        params = request.args.to_dict()

    # Define defaults based on the user's snippet
    departure_id = params.get("departure_id", "QBR")
    arrival_id = params.get("arrival_id", "YMQ")
    outbound_date = params.get("outbound_date", "2027-06-15")
    return_date = params.get("return_date", "2027-06-29")
    currency = params.get("currency", "EUR")
    hl = params.get("hl", "en")

    # 3. Resolve SerpApi API Key
    # Priority:
    # A. Passed in request parameter/body
    # B. Environment Variable SERPAPI_API_KEY
    # C. GCP Secret Manager
    api_key = params.get("api_key") or os.environ.get("SERPAPI_API_KEY")
    api_key = ""
    if not api_key:
        api_key = get_secret("serpapi-api-key")

    if not api_key:
        logger.error(
            "SerpApi API key not found in request parameters, environment variables, or Secret Manager.",
            extra={"json_fields": {**log_fields, "stage": "api_key_check"}},
        )
        return (
            {
                "error": "Missing SerpApi API Key. Please provide it via 'api_key' query parameter/JSON property, "
                         "set the 'SERPAPI_API_KEY' environment variable, or configure 'serpapi-api-key' in GCP Secret Manager.",
                "request_id": request_id
            },
            401,
            headers
        )

    # 4. Construct search parameters
    search_params = {
        "engine": "google_flights",
        "departure_id": departure_id,
        "arrival_id": arrival_id,
        "outbound_date": outbound_date,
        "return_date": return_date,
        "currency": currency,
        "hl": hl,
        "api_key": api_key,
    }

    # Log search params (excluding full API key for security)
    safe_search_params = search_params.copy()
    safe_search_params["api_key"] = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***"
    logger.info(
        f"Calling SerpApi with params: {safe_search_params}",
        extra={"json_fields": {**log_fields, "stage": "serpapi_prepare", "params": safe_search_params}},
    )

    # 5. Execute SerpApi Google Search
    try:
        search = GoogleSearch(search_params)
        results = search.get_dict()
    except Exception as e:
        logger.error(
            f"SerpApi execution failed: {e}",
            extra={"json_fields": {**log_fields, "stage": "serpapi_execution_error"}},
        )
        return (
            {
                "error": "Failed to fetch data from flight tracking provider",
                "details": str(e),
                "request_id": request_id
            },
            502,
            headers
        )

    # 6. Extract flight results and construct final payload
    if "error" in results:
        # Handle API provider errors returned in the payload (e.g. invalid key, invalid parameters)
        provider_error = results["error"]
        logger.error(
            f"SerpApi returned error payload: {provider_error}",
            extra={"json_fields": {**log_fields, "stage": "serpapi_response_error", "error": provider_error}},
        )
        return (
            {
                "error": f"Flight search provider error: {provider_error}",
                "request_id": request_id
            },
            400,
            headers
        )

    best_flights = results.get("best_flights", [])
    other_flights = results.get("other_flights", [])
    price_insights = results.get("price_insights", {})

    transformed_payload = {
        "metadata": {
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "search_parameters": {
                "departure_id": departure_id,
                "arrival_id": arrival_id,
                "outbound_date": outbound_date,
                "return_date": return_date,
                "currency": currency,
                "hl": hl,
            }
        },
        "best_flights": best_flights,
        "other_flights": other_flights,
        "price_insights": price_insights
    }

    logger.info(
        "Successfully fetched flight tracker details",
        extra={"json_fields": {**log_fields, "stage": "success", "best_flights_count": len(best_flights)}},
    )

    return (transformed_payload, 200, headers)
