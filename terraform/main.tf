resource "google_project" "project" {
  name            = var.project_name
  project_id      = var.project_id
  billing_account = var.billing_account
  folder_id       = var.folder_id != "" ? var.folder_id : null
  org_id          = (var.org_id != "" && var.folder_id == "") ? var.org_id : null
}

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

resource "google_storage_bucket" "tf_state" {
  project                     = google_project.project.project_id
  name                        = "${google_project.project.project_id}-tfstate"
  location                    = var.region
  force_destroy               = false
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  depends_on = [google_project_service.services]
}

resource "google_bigquery_dataset" "dataset" {
  project                    = google_project.project.project_id
  dataset_id                 = var.dataset_id
  description                = "Dataset for storing OpenWeather Map Data after transformations."
  location                   = var.region
  delete_contents_on_destroy = true

  labels = {
    env = "dev"
  }

  depends_on = [google_project_service.services]
}

resource "google_bigquery_table" "table" {
  project             = google_project.project.project_id
  dataset_id          = google_bigquery_dataset.dataset.dataset_id
  table_id            = var.table_id
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
