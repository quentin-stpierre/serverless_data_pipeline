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
    "secretmanager.googleapis.com",
  ])
  project = google_project.project.project_id
  service = each.key

  disable_on_destroy = false
}


module "bigquery" {
  source = "./modules/bigquery"

  project_id = google_project.project.project_id
  dataset_id = var.dataset_id
  table_id   = var.table_id
  region     = var.region

  depends_on = [google_project_service.services]
}

resource "google_secret_manager_secret" "open_weather_map_api_key" {
  secret_id = "open-weather-map-api-key"
  project   = google_project.project.project_id

  replication {
    auto {}
  }

  depends_on = [google_project_service.services]
}
