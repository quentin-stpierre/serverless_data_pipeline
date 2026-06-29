# Serverless Weather Data Pipeline

A modern, modular, and serverless data pipeline on Google Cloud Platform (GCP) that automatically fetches weather data from the OpenWeatherMap API, performs data transformations, and prepares it for analytical ingestion in BigQuery.

The infrastructure is entirely provisioned using infrastructure-as-code with **Terraform**, and the pipeline's extraction/transformation logic runs on **Google Cloud Functions (Gen 2 / Cloud Run)** in Python.

---

## Architecture Overview

1. **Extraction & Transformation:** An HTTP-triggered Python Cloud Function is called to run the pipeline.
2. **Secret Management:** The Cloud Function securely retrieves the OpenWeatherMap API key from GCP **Secret Manager** on the fly, eliminating hardcoded credentials.
3. **Data Ingestion (Future Scope):** The transformed data is structured and ready to be streamed into a **BigQuery** analytical table (`processed_weather_data.transformed_weather_data`).

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
│   │   └── cloud_function/          # Package, upload, and deploy Cloud Function Gen 2
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

## Future Enhancements
- **Scheduled Triggering:** Incorporate Cloud Scheduler and Cloud Workflows to automate function execution every hour.
- **Pub/Sub Ingestion:** Pipe the function's transformed payloads to a Pub/Sub topic to decouple ingestion from storage, writing directly into BigQuery.
