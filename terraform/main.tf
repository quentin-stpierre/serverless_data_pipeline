terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 4.0"
    }
  }

  # NOTE: To use GCS as a backend, the bucket must already exist.
  # 1. Run 'terraform apply' with this block commented out to create the bucket.
  # 2. Uncomment this block and run 'terraform init' to migrate state.
  backend "gcs" {
    bucket = "serverless-data-pipeline-111-tfstate"
    prefix = "terraform/state"
  }
}

provider "google" {
  region = var.region
}

variable "project_id" {
  description = "The ID of the GCP project"
  type        = string
  default     = ""
}

variable "region" {
  description = "The region to deploy resources in"
  type        = string
  default     = ""
}

variable "billing_account" {
  description = "The billing account ID to associate with the project"
  type        = string
  default     = ""
}

variable "org_id" {
  description = "The organization ID where the project will be created"
  type        = string
  default     = ""
}

variable "folder_id" {
  description = "The folder ID where the project will be created"
  type        = string
  default     = ""
}

# 1. Create the GCP Project
resource "google_project" "project" {
  name            = "Serverless Data Pipeline"
  project_id      = var.project_id
  billing_account = var.billing_account
  folder_id       = var.folder_id != "" ? var.folder_id : null
  org_id          = (var.org_id != "" && var.folder_id == "") ? var.org_id : null
}

# 2. Enable necessary APIs
resource "google_project_service" "services" {
  for_each = toset([
    "bigquery.googleapis.com",
    "storage.googleapis.com",
    "cloudresourcemanager.googleapis.com",
  ])
  project = google_project.project.project_id
  service = each.key

  disable_on_destroy = false
}

# 3. Cloud Storage bucket for Terraform State
resource "google_storage_bucket" "tf_state" {
  project                     = google_project.project.project_id
  name                        = "${google_project.project.project_id}-tfstate"
  location                    = "EU"
  force_destroy               = false
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  depends_on = [google_project_service.services]
}

# 4. BigQuery Dataset
resource "google_bigquery_dataset" "dataset" {
  project                    = google_project.project.project_id
  dataset_id                 = "processed_weather_data"
  friendly_name              = "Processed Weather Data"
  description                = "Dataset for storing OpenWeather Map Data after transformations."
  location                   = "EU"
  delete_contents_on_destroy = true

  labels = {
    env = "dev"
  }

  depends_on = [google_project_service.services]
}

# 5. BigQuery Table
resource "google_bigquery_table" "table" {
  project             = google_project.project.project_id
  dataset_id          = google_bigquery_dataset.dataset.dataset_id
  table_id            = "transformed_weather_data"
  deletion_protection = false

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
