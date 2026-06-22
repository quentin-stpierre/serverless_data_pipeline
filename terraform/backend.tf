resource "google_storage_bucket" "tf_state" {
  project                     = var.project_id
  name                        = "${var.project_id}-tfstate"
  location                    = var.region
  force_destroy               = false
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  depends_on = [google_project_service.services]
}
