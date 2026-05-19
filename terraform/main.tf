terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 4.0"
    }
  }
}

provider "google" {
  project = "tokyo-analyst-496814-t9"
  region  = "europe-west1"
}

resource "google_bigquery_dataset" "dataset" {
  dataset_id                 = "processed_weather_data"
  friendly_name              = "processed_weather_data"
  description                = "Dataset created by Terraform for storing the OpenWeather Map Data after its transformations."
  location                   = "EU"
  delete_contents_on_destroy = true # Warning: Set to true to allow Terraform to delete the dataset even if it contains tables.

  labels = {
    env = "dev"
  }
}

resource "google_bigquery_table" "table" {
  dataset_id          = google_bigquery_dataset.dataset.dataset_id
  table_id            = "transformed_weather_data"
  deletion_protection = false # Set to true for production to prevent accidental deletion.

  time_partitioning {
    type = "DAY"
  }

  labels = {
    env = "dev"
  }

  schema = <<EOF
[
  {
    "name": "id",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Primary key for the record"
  },
  {
    "name": "timestamp",
    "type": "TIMESTAMP",
    "mode": "REQUIRED",
    "description": "Event timestamp"
  },
  {
    "name": "payload",
    "type": "JSON",
    "mode": "NULLABLE",
    "description": "Raw event data"
  }
]
EOF
}
