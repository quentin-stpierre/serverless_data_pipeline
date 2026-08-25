resource "google_storage_bucket" "function_bucket" {
  name                        = "${var.project_id}-function-source"
  location                    = var.region
  project                     = var.project_id
  uniform_bucket_level_access = true
  force_destroy               = true
}

data "archive_file" "function_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../../functions/fetch_weather"
  output_path = "${path.module}/fetch_weather.zip"
}

resource "google_storage_bucket_object" "function_zip_object" {
  name   = "fetch_weather.${data.archive_file.function_zip.output_md5}.zip"
  bucket = google_storage_bucket.function_bucket.name
  source = data.archive_file.function_zip.output_path
}

resource "google_service_account" "function_sa" {
  account_id   = var.cloud_function_sa_name
  display_name = "Fetch Weather Cloud Function Service Account"
  project      = var.project_id
}

resource "google_secret_manager_secret_iam_member" "secret_accessor" {
  project   = var.project_id
  secret_id = var.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.function_sa.email}"
}

resource "google_cloudfunctions2_function" "fetch_weather" {
  name        = var.cloud_function_name
  location    = var.region
  project     = var.project_id
  description = "HTTP-triggered function to fetch and transform OpenWeatherMap data"

  build_config {
    runtime     = "python310"
    entry_point = "fetch_weather"
    source {
      storage_source {
        bucket = google_storage_bucket.function_bucket.name
        object = google_storage_bucket_object.function_zip_object.name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    available_memory      = "256M"
    timeout_seconds       = 60
    service_account_email = google_service_account.function_sa.email
  }
}
