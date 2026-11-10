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
    type     = "seed"
    price    = 0.0
    airlines = ["None"]
    flights = [
      {
        from_airport = {
          name = "None"
          code = "XXX"
        }
        to_airport = {
          name = "None"
          code = "YYY"
        }
        departure = {
          date = [2026, 1, 1]
          time = [0, 0]
        }
        arrival = {
          date = [2026, 1, 1]
          time = [0, 0]
        }
        duration   = 0
        plane_type = "None"
      }
    ]
    carbon = {
      typical_on_route = 0
      emission         = 0
    }
    _query_meta = {
      search_name   = "seed"
      outbound_date = "2026-01-01"
      return_date   = "2026-01-01"
      origin        = "XXX"
      destination   = "YYY"
      trip          = "round-trip"
      currency      = "EUR"
      seat          = "economy"
    }
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
    autodetect            = false
    source_format         = "NEWLINE_DELIMITED_JSON"
    connection_id         = google_bigquery_connection.biglake_connection.name
    ignore_unknown_values = true

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
    "name": "type",
    "type": "STRING",
    "mode": "NULLABLE"
  },
  {
    "name": "price",
    "type": "FLOAT",
    "mode": "NULLABLE"
  },
  {
    "name": "airlines",
    "type": "STRING",
    "mode": "REPEATED"
  },
  {
    "name": "flights",
    "type": "RECORD",
    "mode": "REPEATED",
    "fields": [
      {
        "name": "from_airport",
        "type": "RECORD",
        "mode": "NULLABLE",
        "fields": [
          { "name": "name", "type": "STRING", "mode": "NULLABLE" },
          { "name": "code", "type": "STRING", "mode": "NULLABLE" }
        ]
      },
      {
        "name": "to_airport",
        "type": "RECORD",
        "mode": "NULLABLE",
        "fields": [
          { "name": "name", "type": "STRING", "mode": "NULLABLE" },
          { "name": "code", "type": "STRING", "mode": "NULLABLE" }
        ]
      },
      {
        "name": "departure",
        "type": "RECORD",
        "mode": "NULLABLE",
        "fields": [
          { "name": "date", "type": "INTEGER", "mode": "REPEATED" },
          { "name": "time", "type": "INTEGER", "mode": "REPEATED" }
        ]
      },
      {
        "name": "arrival",
        "type": "RECORD",
        "mode": "NULLABLE",
        "fields": [
          { "name": "date", "type": "INTEGER", "mode": "REPEATED" },
          { "name": "time", "type": "INTEGER", "mode": "REPEATED" }
        ]
      },
      {
        "name": "duration",
        "type": "INTEGER",
        "mode": "NULLABLE"
      },
      {
        "name": "plane_type",
        "type": "STRING",
        "mode": "NULLABLE"
      }
    ]
  },
  {
    "name": "carbon",
    "type": "RECORD",
    "mode": "NULLABLE",
    "fields": [
      { "name": "typical_on_route", "type": "INTEGER", "mode": "NULLABLE" },
      { "name": "emission", "type": "INTEGER", "mode": "NULLABLE" }
    ]
  },
  {
    "name": "_query_meta",
    "type": "RECORD",
    "mode": "NULLABLE",
    "fields": [
      { "name": "search_name", "type": "STRING", "mode": "NULLABLE" },
      { "name": "outbound_date", "type": "STRING", "mode": "NULLABLE" },
      { "name": "return_date", "type": "STRING", "mode": "NULLABLE" },
      { "name": "origin", "type": "STRING", "mode": "NULLABLE" },
      { "name": "destination", "type": "STRING", "mode": "NULLABLE" },
      { "name": "trip", "type": "STRING", "mode": "NULLABLE" },
      { "name": "currency", "type": "STRING", "mode": "NULLABLE" },
      { "name": "seat", "type": "STRING", "mode": "NULLABLE" }
    ]
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
