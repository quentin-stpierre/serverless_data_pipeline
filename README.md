# Serverless Weather Data Pipeline

A modern, modular, and serverless data pipeline on Google Cloud Platform (GCP) that automatically fetches weather data from the OpenWeatherMap API, performs data transformations, and prepares it for analytical ingestion in BigQuery.

The infrastructure is entirely provisioned using infrastructure-as-code with **Terraform**, and the pipeline's extraction/transformation logic runs on **Google Cloud Functions (Gen 2 / Cloud Run)** in Python.

---

## Architecture Overview

1. **Orchestration:** **Cloud Workflows** coordinates the pipeline execution by triggering the Cloud Function and forwarding the result to Pub/Sub.
2. **Extraction & Transformation:** An HTTP-triggered Python Cloud Function is called to fetch weather data, perform transformations, and return structured JSON.
3. **Secret Management:** The Cloud Function securely retrieves the OpenWeatherMap API key from GCP **Secret Manager** on the fly, eliminating hardcoded credentials.
4. **Data Ingestion:** The workflow formats the transformed payload and publishes it to a **Pub/Sub** topic.
5. **Storage:** A native **BigQuery Subscription** on the Pub/Sub topic automatically streams the JSON messages directly into a **BigQuery** analytical table (`processed_weather_data.transformed_weather_data`), matching fields automatically.

---

## Project Structure

```
serverless_data_pipeline/
├── functions/
│   └── fetch_weather/               # Cloud Function source code
│       ├── main.py                  # Python extraction & transformation logic
│       └── requirements.txt         # Python dependencies
├── terraform/                       # Infrastructure-as-Code (Terraform)
│   ├── modules/
│   │   ├── bigquery/                # BigQuery dataset & table module
│   │   ├── cloud_function/          # Package, upload, and deploy Cloud Function Gen 2
│   │   ├── pubsub/                  # Pub/Sub topic & BigQuery native subscription module
│   │   └── workflows/               # Cloud Workflows orchestration module
│   ├── main.tf                      # Global entrypoint (project, services, secret container)
│   ├── providers.tf                 # Terraform provider configuration (Google, Archive)
│   ├── terraform.tfvars             # Environment variables / values
│   └── variables.tf                 # Global input variables
└── README.md                        # Project documentation (this file)
```

---

## Setup & Deployment Guide

### Prerequisites
- [Google Cloud SDK (gcloud CLI)](https://cloud.google.com/sdk/docs/install) installed and authenticated.
- [Terraform (>= 1.0)](https://developer.hashicorp.com/terraform/downloads) installed.
- A valid [OpenWeatherMap API Key](https://openweathermap.org/api).

---

### Step 1: Configure Secret Manager & Populate API Key
To keep secrets secure, we provision the Secret Manager "container" via Terraform, and then add your API key manually as an active version.

1. Initialize and run Terraform to create the secret container:
   ```bash
   cd terraform
   terraform init
   terraform apply
   ```
2. Manually add your actual OpenWeatherMap API key as version `1` of the secret:
   ```bash
   echo -n "YOUR_OPENWEATHERMAP_API_KEY" | gcloud secrets versions add open-weather-map-api-key --data-file=- --project=serverless-data-pipeline-111
   ```

---

### Step 2: Deploy the Entire Infrastructure
After adding the secret key version, run `terraform apply` again to deploy the remaining services, including the GCS source buckets and the Cloud Function itself:
```bash
cd terraform
terraform apply
```
Once complete, Terraform will output the Cloud Function's HTTP Trigger URL.

---

## Local Development & Testing

You can run the Cloud Function locally on your machine using the **Google Functions Framework**. Since the function relies on GCP Secret Manager, you will need to authenticate your terminal so local Python code can read secrets.

### 1. Set Up Local Python Virtual Environment
Navigate to the root directory and create/activate a virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r functions/fetch_weather/requirements.txt
```

### 2. Authenticate to GCP Locally
Authorize your terminal via Google Application Default Credentials (ADC) and set your target GCP project:
```bash
gcloud auth application-default login
gcloud config set project serverless-data-pipeline-111
```

### 3. Start the Local Server
Run the local `functions-framework` server. We pass the `GCP_PROJECT` environment variable so the function knows which GCP project's Secret Manager to query:
```bash
GCP_PROJECT=serverless-data-pipeline-111 functions-framework \
  --source=functions/fetch_weather/main.py \
  --target=fetch_weather \
  --port=8080
```

### 4. Test the Endpoint
In another terminal, trigger the local function with `curl`:
```bash
curl http://localhost:8080
```

You should receive a successful JSON response containing the flat, structured weather fields:
- `location`, `country`
- `temperature_c`, `temperature_f`, `feels_like_c`, `feels_like_f`
- `humidity`, `pressure`, `wind_speed_mps`
- `weather_condition`, `weather_description`
- `timestamp` (UTC)

---

## Triggering the Pipeline

Once deployed, you can trigger the pipeline using Cloud Workflows. This will run the Cloud Function, extract/transform the weather data, send it to Pub/Sub, and automatically load it into BigQuery via the native subscription.

To execute the workflow via `gcloud`:
```bash
gcloud workflows run weather-data-pipeline --project=serverless-data-pipeline-111 --location=europe-west1
```

### Automatic Loading to BigQuery
The Pub/Sub subscription `weather-data-bq` is configured to natively write messages into the BigQuery table `processed_weather_data.transformed_weather_data`.
The pipeline uses a flat schema where every field returned by the Cloud Function (e.g., `location`, `country`, `temperature_c`, `humidity`, `timestamp`, etc.) maps directly to its corresponding column in BigQuery.

Because `use_table_schema` is enabled and `write_metadata` is false, Pub/Sub automatically maps the flat JSON keys in the message directly to the corresponding columns of the BigQuery table.

## Automated Schedule
The pipeline is automated using **Cloud Scheduler** which is configured to trigger the Cloud Workflow every day at **9:00 AM Europe/Brussels** timezone.
The Cloud Scheduler job runs with a dedicated service account having `roles/workflows.invoker` permission to securely invoke the Workflows Execution API.

---

## Future Enhancements
- **Monitoring & Alerts:** Implement Cloud Monitoring alerts to notify the team if any workflow execution fails or if the scheduler job experiences issues.
