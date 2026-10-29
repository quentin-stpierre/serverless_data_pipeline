# Serverless Flight Tracking Pipeline (ELT Architecture)

This document provides a comprehensive technical overview of the serverless Extract-Load-Transform (ELT) flight price tracking pipeline, detailing its end-to-end architecture, step-by-step lifecycle, code specifications, and operational guide.

---

## 1. High-Level Architecture

The pipeline follows a modern **ELT (Extract, Load, Transform)** pattern on Google Cloud Platform:
1. **Extract & Load:** Scrape raw, untransformed flight data from Google Flights and immediately land it as JSON Lines (`.jsonl`) into Google Cloud Storage (GCS).
2. **Transform:** Ingest raw files into BigQuery, where Dataform handles SQL transformations (deduplication, schema harmonization, and price trend analysis).
3. **Evaluate & Alert:** Detect price drops across runs and trigger notifications.

```
[Cloud Scheduler]
 (Cron triggers per search target)
       │
       ▼ (HTTP POST with search parameters)
[Cloud Workflows]
 (Orchestrator: manages execution & credentials)
       │
       ▼ (HTTP POST with OIDC Auth)
[Cloud Function (fetch_flights)]
 (Python 3.10 / Fast-Flights scraper)
       │
       ▼ (Raw JSONL upload)
[Google Cloud Storage (GCS)]
 gs://<raw-bucket>/raw/source=google_flights/dt=YYYY-MM-DD/{scrape_id}.jsonl
       │
       ▼ (BigQuery External Table / Raw Landing)
[BigQuery Raw Layer]
       │
       ▼ (Triggered via Cloud Workflows / Dataform API)
[Dataform Execution API]
 ├── 1. raw_layer: Deduplication & strict type-casting
 ├── 2. staging:   Harmonize schemas across multiple sources
 └── 3. marts:     Min price aggregation & price drop detection
       │
       ▼
[Price Drop Alerting]
 └── Notifications (Cloud Function / Pub/Sub / SendGrid)
```

---

## 2. Step-by-Step Pipeline Flow

### Step 1: Trigger & Parameterization (Cloud Scheduler)
- **Module:** `terraform/modules/scheduler`
- **Mechanism:** Cloud Scheduler runs on user-defined cron schedules (e.g., every 2–3 days).
- **Key Feature:** Cloud Scheduler acts as the **parameter source**. Instead of static workflows, each job carries its own search configuration directly inside the HTTP POST body sent to the Workflows Execution API.
- **Payload sent to Workflows:**
  ```json
  {
    "argument": "{\"origin\": \"BRU\", \"destination\": \"YUL\", \"start_date\": \"2027-07-01\", \"trip_length\": 24, \"flexibility_window\": 2, \"currency\": \"EUR\", \"seat\": \"economy\"}"
  }
  ```

### Step 2: Dynamic Orchestration (Cloud Workflows)
- **Module:** `terraform/modules/workflows`
- **Definition:** `terraform/modules/workflows/workflow.yaml`
- **Mechanism:**
  - Declares `params: [args]`, dynamically receiving the parameters passed by Cloud Scheduler (or manual CLI runs).
  - Uses GCP-managed **OIDC authentication** to securely invoke the scraper Cloud Function.
  - Passes the `$${args}` JSON directly into the Cloud Function HTTP body.

### Step 3: Raw Extraction (Cloud Function: `fetch_flights`)
- **Source Directory:** `functions/fetch_flights/`
- **Entrypoint:** `fetch_flights(request)` in `main.py`
- **Scraper Engine:** `fast_flights_scraper.py`
- **Process:**
  1. Parses incoming query parameters (`origin`, `destination`, `start_date`, `trip_length`, `flexibility_window`, etc.).
  2. Generates a Cartesian product of outbound/return dates based on `flexibility_window`.
  3. Executes Google Flights queries using `fast_flights` and `primp` to bypass consent banners and bot detection.
  4. Preserves **100% of the raw data** returned by the API (no filtering for the cheapest flight or flattening).
  5. Attaches query context metadata (`_query_meta`) for downstream tracking.

### Step 4: Storage Landing Zone (Google Cloud Storage)
- **Module:** `terraform/modules/storage`
- **Storage Pattern:** Hive-partitioned directory layout:
  ```text
  gs://<RAW_DATA_BUCKET>/raw/source=google_flights/dt=YYYY-MM-DD/<scrape_id>.jsonl
  ```
- **Format:** Newline-delimited JSON (`application/x-ndjson`).
- **Features:**
  - `uniform_bucket_level_access = true` for simplified IAM.
  - Object versioning enabled to prevent accidental overwrites.
  - 90-day automatic deletion lifecycle rule to optimize storage costs.

### Step 5: Transformations & Business Logic (BigQuery & Dataform) *(Target State)*
- **BigQuery:** Creates an external table over `gs://<RAW_DATA_BUCKET>/raw/source=google_flights/*` using Hive partitioning (`dt` column).
- **Dataform Layers:**
  1. `raw_layer`: Flattens nested JSON, casts datatypes, and deduplicates flights based on flight number, departure time, and scrape timestamp.
  2. `staging`: Normalizes schemas so multiple scrapers (e.g. Google Flights, Skyscanner, Bright Data) share identical schema columns.
  3. `marts`: Evaluates time-series price movements, computes minimum and average prices per route/date combination, and flags sudden price drops.

---

## 3. Code & Technical Specifications

### `functions/fetch_flights/fast_flights_scraper.py`

#### 1. Anti-Bot & Consent Handling
```python
class ConsentAwareFetchIntegration(FetchIntegration):
    def fetch_html(self, q) -> str:
        return Client(impersonate="chrome_145").get(
            "https://www.google.com/travel/flights/search",
            params=q.params(),
            headers={"cookie": "SOCS=CAESEwgDEgk2ODEwNTc2NjIaAmVuIAEaBgiA_LyaBg"},
        ).text
```
- **`primp` Client:** Mimics real browser TLS/JA3 fingerprints using `impersonate="chrome_145"`.
- **`SOCS` Cookie:** Bypasses Google's regional GDPR/EU cookie consent modal that would otherwise block automated HTML extraction.

#### 2. Symmetric Date Pair Generation
```python
def generate_flexible_date_pairs(
    start_date: str, trip_length: int, flexibility_window: int = 0
) -> list[tuple[str, str]]:
```
- For a `start_date` of `2027-07-01`, `trip_length = 24`, and `flexibility_window = 1`:
  - Outbound offsets: `[-1, 0, +1]` (e.g., June 30, July 01, July 02).
  - Trip length offsets: `[23, 24, 25]` days.
  - Generates 9 outbound-return combinations, ensuring exhaustive price discovery.

#### 3. Data Serialization & Metadata
```python
def _to_serializable(obj: Any) -> Any:
```
- Recursively converts Python `@dataclass` structures, objects with `__dict__`, and `datetime` types into pure dictionaries.
- Appends `_query_meta` to each record with the exact parameters requested.

#### 4. GCS Uploading
```python
def upload_raw_data_to_gcs(bucket_name: str, data: list[dict], source: str = "google_flights") -> str | None:
```
- Generates a UUID `scrape_id` and UTC date stamp `dt=YYYY-MM-DD`.
- Writes newline-separated JSON (`.jsonl`) via `blob.upload_from_string(content, content_type="application/x-ndjson")`.

---

### `functions/fetch_flights/main.py`
- Implements the Functions Framework HTTP entrypoint (`@functions_framework.http`).
- Safely reads JSON from `request.get_json(silent=True)`.
- Falls back to sensible defaults if any parameter is omitted.
- Reads target bucket from environment variable `RAW_DATA_BUCKET`.

---

## 4. Configuration Guide

### Adding or Modifying Search Targets
To track a new destination or change dates, edit `terraform/terraform.tfvars`:

```hcl
flight_searches = {
  canada_july = {
    schedule           = "0 9 * * 1,4"  # Every Monday and Thursday at 09:00 UTC
    origin             = "BRU"
    destination        = "YUL"
    start_date         = "2027-07-01"
    trip_length        = 24
    flexibility_window = 2
    currency           = "EUR"
    seat               = "economy"
  },
  guatemala_april = {
    schedule           = "0 10 * * 2,5" # Every Tuesday and Friday at 10:00 UTC
    origin             = "BRU"
    destination        = "GUA"
    start_date         = "2027-04-10"
    trip_length        = 18
    flexibility_window = 1
    currency           = "EUR"
    seat               = "economy"
  }
}
```
Running `terraform apply` will automatically provision a new Cloud Scheduler job for each entry.

---

## 5. Manual Execution & Testing

### Triggering via Google Cloud CLI
You can test or run an ad-hoc scrape at any time without waiting for Cloud Scheduler:

```bash
gcloud workflows execute flights-data-pipeline \
  --location=europe-west1 \
  --data='{
    "origin": "BRU",
    "destination": "YUL",
    "start_date": "2027-07-01",
    "trip_length": 24,
    "flexibility_window": 1,
    "currency": "EUR"
  }'
```

### Local Testing of the Scraper
You can execute the scraper directly on your machine:

```bash
export RAW_DATA_BUCKET="serverless-data-pipeline-111-raw-data"
python3 functions/fetch_flights/fast_flights_scraper.py
```

---

## 6. IAM & Security Model

| Identity / Service Account | Granted Role | Resource | Purpose |
| :--- | :--- | :--- | :--- |
| `flights-scheduler-sa` | `roles/workflows.invoker` | Project | Allows Cloud Scheduler to trigger workflow executions. |
| `flights-pipeline-sa` | `roles/run.invoker`<br>`roles/cloudfunctions.invoker` | Cloud Function | Allows Cloud Workflows to call the HTTP Cloud Function via OIDC. |
| `flights-pipeline-sa` | `roles/logging.logWriter` | Project | Allows Cloud Workflows to record logs in Cloud Logging. |
| `fetch-flights-sa` | `roles/storage.objectUser` | GCS Raw Bucket | Allows Cloud Function to create and write `.jsonl` objects in the raw landing bucket. |
