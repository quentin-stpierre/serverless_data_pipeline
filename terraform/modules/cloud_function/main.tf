resource "google_storage_bucket" "function_bucket" {
  name                        = "${var.project_id}-function-source"
  location                    = var.region
  project                     = var.project_id
  uniform_bucket_level_access = true
  force_destroy               = true
}

data "archive_file" "function_zip" {
  type             = "zip"
  source_dir       = "${path.module}/../../../functions/fetch_flights"
  output_path      = "${path.module}/fetch_flights.zip"
  output_file_mode = "0666"
  excludes = [
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "tests",
  ]
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

resource "google_project_iam_member" "function_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.function_sa.email}"
}

resource "google_secret_manager_secret" "socs_consent_cookie" {
  project   = var.project_id
  secret_id = var.socs_cookie_secret_id

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_iam_member" "function_socs_cookie_accessor" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.socs_consent_cookie.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.function_sa.email}"
}

resource "google_cloudfunctions2_function" "fetch_flights" {
  name        = var.cloud_function_name
  location    = var.region
  project     = var.project_id
  description = "HTTP-triggered function to scrape flight data and store raw results in GCS"

  build_config {
    runtime     = "python314"
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
      GCP_PROJECT     = var.project_id
      RAW_DATA_BUCKET = var.raw_data_bucket_name
    }

    secret_environment_variables {
      key        = "SOCS_CONSENT_COOKIE"
      project_id = var.project_id
      secret     = google_secret_manager_secret.socs_consent_cookie.secret_id
      version    = "latest"
    }
  }

  depends_on = [
    google_project_iam_member.function_logging,
    google_secret_manager_secret_iam_member.function_socs_cookie_accessor,
  ]
}
