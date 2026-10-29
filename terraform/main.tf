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
    "cloudfunctions.googleapis.com",
    "cloudbuild.googleapis.com",
    "run.googleapis.com",
    "workflows.googleapis.com",
    "cloudscheduler.googleapis.com",
    "monitoring.googleapis.com",
  ])
  project = google_project.project.project_id
  service = each.key

  disable_on_destroy = false
}

module "scheduler" {
  source = "./modules/scheduler"

  project_id      = google_project.project.project_id
  region          = var.region
  workflow_name   = module.workflows.workflow_name
  flight_searches = var.flight_searches

  scheduler_sa_name = var.scheduler_sa_name

  depends_on = [google_project_service.services, module.workflows]
}

module "workflows" {
  source = "./modules/workflows"

  project_id    = google_project.project.project_id
  region        = var.region
  function_uri  = module.cloud_function.function_uri
  function_name = module.cloud_function.function_name

  workflow_sa_name = var.workflow_sa_name
  workflow_name    = var.flight_workflow_name

  depends_on = [google_project_service.services, module.cloud_function]
}

module "cloud_function" {
  source = "./modules/cloud_function"

  project_id           = google_project.project.project_id
  region               = var.region
  raw_data_bucket_name = var.raw_data_bucket_name

  cloud_function_sa_name = var.cloud_function_sa_name
  cloud_function_name    = var.cloud_function_name

  depends_on = [google_project_service.services]
}

module "bigquery" {
  source = "./modules/bigquery"

  project_id      = google_project.project.project_id
  dataset_id      = var.dataset_id
  table_id        = var.table_id
  region          = var.region
  raw_bucket_name = module.storage.bucket_name

  depends_on = [google_project_service.services, module.storage]
}

module "storage" {
  source = "./modules/storage"

  project_id              = google_project.project.project_id
  region                  = var.region
  bucket_name             = var.raw_data_bucket_name
  cloud_function_sa_email = module.cloud_function.function_sa_email

  depends_on = [google_project_service.services, module.cloud_function]
}

module "monitoring" {
  source = "./modules/monitoring"

  project_id          = google_project.project.project_id
  alert_email_address = var.alert_email_address
  workflow_name       = module.workflows.workflow_name

  depends_on = [google_project_service.services, module.workflows]
}

module "cicd" {
  source = "./modules/cicd"

  project_id   = google_project.project.project_id
  github_owner = var.github_owner
  github_repo  = var.github_repo

  terraform_cicd_sa         = var.terraform_cicd_sa
  cloud_build_trigger_name  = var.cloud_build_trigger_name
  terraform_apply_approvers = var.terraform_apply_approvers
  depends_on                = [google_project_service.services]
  region                    = var.region
}
