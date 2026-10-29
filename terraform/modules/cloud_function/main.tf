resource "google_storage_bucket" "function_bucket" {
  name                        = "${var.project_id}-function-source"
  location                    = var.region
  project                     = var.project_id
  uniform_bucket_level_access = true
  force_destroy               = true
}

data "archive_file" "function_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../../functions/fetch_flights"
  output_path = "${path.module}/fetch_flights.zip"
}

resource "google_storage_bucket_object" "function_zip_object" {
  name   = "fetch_flights.${data.archive_file.function_zip.output_md5}.zip"
  bucket = google_storage_bucket.function_bucket.name
  source = data.archive_file.function_zip.output_path
}

resource "google_service_account" "function_sa" {
  account_id   = var.cloud_function_sa_name
  display_name = "Fetch Flights Cloud Function Service Account"
  project      = var.project_id
}

resource "google_cloudfunctions2_function" "fetch_flights" {
  name        = var.cloud_function_name
  location    = var.region
  project     = var.project_id
  description = "HTTP-triggered function to scrape flight data and store raw results in GCS"

  build_config {
    runtime     = "python310"
    entry_point = "fetch_flights"
    source {
      storage_source {
        bucket = google_storage_bucket.function_bucket.name
        object = google_storage_bucket_object.function_zip_object.name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    available_memory      = "512M"
    timeout_seconds       = 300
    service_account_email = google_service_account.function_sa.email

    environment_variables = {
      RAW_DATA_BUCKET = var.raw_data_bucket_name
    }
  }
}
