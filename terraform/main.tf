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
    "cloudfunctions.googleapis.com",
    "cloudbuild.googleapis.com",
    "run.googleapis.com",
    "pubsub.googleapis.com",
    "workflows.googleapis.com",
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

module "cloud_function" {
  source = "./modules/cloud_function"

  project_id = google_project.project.project_id
  region     = var.region
  secret_id  = google_secret_manager_secret.open_weather_map_api_key.secret_id

  depends_on = [google_project_service.services]
}

module "pubsub" {
  source = "./modules/pubsub"

  project_id = google_project.project.project_id
  region     = var.region
  dataset_id = module.bigquery.dataset_id
  table_id   = module.bigquery.table_id

  depends_on = [google_project_service.services, module.bigquery]
}

module "workflows" {
  source = "./modules/workflows"

  project_id        = google_project.project.project_id
  region            = var.region
  function_uri      = module.cloud_function.function_uri
  pubsub_topic_name = module.pubsub.topic_name

  depends_on = [google_project_service.services, module.cloud_function, module.pubsub]
}
