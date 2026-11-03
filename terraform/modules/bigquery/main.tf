resource "google_bigquery_dataset" "dataset" {
  project                    = var.project_id
  dataset_id                 = var.dataset_id
  description                = "Dataset containing raw flight pricing external tables"
  location                   = var.region
  delete_contents_on_destroy = true

  labels = {
    env     = "dev"
    project = "flights"
    layer   = "raw"
  }
}

resource "google_bigquery_dataset" "staging" {
  project                    = var.project_id
  dataset_id                 = "flight_staging"
  description                = "Silver layer: cleaned and normalized staging views for flight data"
  location                   = var.region
  delete_contents_on_destroy = true

  labels = {
    env     = "dev"
    project = "flights"
    layer   = "staging"
  }
}

resource "google_bigquery_dataset" "marts" {
  project                    = var.project_id
  dataset_id                 = "flight_marts"
  description                = "Gold layer: dimension and fact tables for flight analytics"
  location                   = var.region
  delete_contents_on_destroy = true

  labels = {
    env     = "dev"
    project = "flights"
    layer   = "marts"
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

# Seed dummy file required for BigQuery Hive partition validation on empty bucket
resource "google_storage_bucket_object" "hive_dummy_seed" {
  name   = "raw/source=google_flights/dt=2026-01-01/seed.jsonl"
  bucket = var.raw_bucket_name
  content = jsonencode({
    source                  = "init"
    round_trip_price        = 0.0
    from_airport            = "XXX"
    to_airport              = "YYY"
    outbound_airline        = "None"
    outbound_date           = "2026-01-01"
    outbound_departure_time = "00:00"
    outbound_duration       = 0
    return_date             = "2026-01-01"
    return_departure_time   = "00:00"
    return_duration         = 0
    _query_meta             = {}
  })
}

# External Table pointing to the Hive-partitioned GCS data
resource "google_bigquery_table" "table" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.dataset.dataset_id
  table_id            = var.table_id
  description         = "External table pointing to raw JSONL flight data in GCS."
  deletion_protection = false

  depends_on = [
    google_storage_bucket_iam_member.biglake_gcs_reader,
    google_storage_bucket_object.hive_dummy_seed
  ]

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
    "type": "FLOAT",
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
    "type": "INTEGER",
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
    "type": "INTEGER",
    "mode": "NULLABLE"
  },
  {
    "name": "_query_meta",
    "type": "JSON",
    "mode": "NULLABLE"
  },
  {
    "name": "dt",
    "type": "DATE",
    "mode": "NULLABLE"
  }
]
EOF

  lifecycle {
    ignore_changes = [
      external_data_configuration[0].connection_id
    ]
  }
}
