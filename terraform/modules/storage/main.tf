resource "google_storage_bucket" "raw_bucket" {
  name                        = var.bucket_name
  project                     = var.project_id
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false

  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 90
    }
  }
}

resource "google_storage_bucket_iam_member" "cloud_function_writer" {
  count  = var.cloud_function_sa_email != "" ? 1 : 0
  bucket = google_storage_bucket.raw_bucket.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${var.cloud_function_sa_email}"
}
