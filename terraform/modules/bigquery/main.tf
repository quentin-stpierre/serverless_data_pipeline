resource "google_bigquery_dataset" "dataset" {
  project                    = var.project_id
  dataset_id                 = var.dataset_id
  description                = "Dataset containing raw and staged flight pricing data"
  location                   = var.region
  delete_contents_on_destroy = true

  labels = {
    env     = "dev"
    project = "flights"
  }
}

# Create a BigLake connection so BigQuery can read from GCS
resource "google_bigquery_connection" "biglake_connection" {
  project       = var.project_id
  location      = var.region
  connection_id = "biglake-gcs-connection"
  friendly_name = "BigLake GCS Connection"
  description   = "Connection to read raw JSONL flight data from GCS"

  cloud_resource {}
}

# Grant the BigLake connection service account access to the raw GCS bucket
resource "google_storage_bucket_iam_member" "biglake_gcs_reader" {
  bucket = var.raw_bucket_name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_bigquery_connection.biglake_connection.cloud_resource[0].service_account_id}"
}

# External Table pointing to the Hive-partitioned GCS data
resource "google_bigquery_table" "table" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.dataset.dataset_id
  table_id            = var.table_id
  description         = "External table pointing to raw JSONL flight data in GCS."
  deletion_protection = false

  external_data_configuration {
    autodetect    = false
    source_format = "NEWLINE_DELIMITED_JSON"
    connection_id = google_bigquery_connection.biglake_connection.name

    # Point to the source=google_flights subfolder so hive partitioning works accurately
    source_uris = [
      "gs://${var.raw_bucket_name}/raw/source=google_flights/*"
    ]

    # Hive partitioning configuration
    hive_partitioning_options {
      mode                     = "AUTO"
      source_uri_prefix        = "gs://${var.raw_bucket_name}/raw/source=google_flights/"
      require_partition_filter = false
    }
  }

  schema = <<EOF
[
  {
    "name": "source",
    "type": "STRING",
    "mode": "NULLABLE"
  },
  {
    "name": "round_trip_price",
    "type": "FLOAT64",
    "mode": "NULLABLE"
  },
  {
    "name": "from_airport",
    "type": "STRING",
    "mode": "NULLABLE"
  },
  {
    "name": "to_airport",
    "type": "STRING",
    "mode": "NULLABLE"
  },
  {
    "name": "outbound_airline",
    "type": "STRING",
    "mode": "NULLABLE"
  },
  {
    "name": "outbound_date",
    "type": "STRING",
    "mode": "NULLABLE"
  },
  {
    "name": "outbound_departure_time",
    "type": "STRING",
    "mode": "NULLABLE"
  },
  {
    "name": "outbound_duration",
    "type": "INT64",
    "mode": "NULLABLE"
  },
  {
    "name": "return_date",
    "type": "STRING",
    "mode": "NULLABLE"
  },
  {
    "name": "return_departure_time",
    "type": "STRING",
    "mode": "NULLABLE"
  },
  {
    "name": "return_duration",
    "type": "INT64",
    "mode": "NULLABLE"
  },
  {
    "name": "_query_meta",
    "type": "JSON",
    "mode": "NULLABLE"
  }
]
EOF
}
