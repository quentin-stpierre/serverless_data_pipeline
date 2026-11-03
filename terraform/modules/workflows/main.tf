resource "google_service_account" "workflow_sa" {
  account_id   = var.workflow_sa_name
  display_name = "Service Account for Flights Pipeline Workflow"
  project      = var.project_id
}

resource "google_cloud_run_service_iam_member" "workflow_run_invoker" {
  project  = var.project_id
  location = var.region
  service  = var.function_name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.workflow_sa.email}"
}

resource "google_cloudfunctions2_function_iam_member" "workflow_gcf_invoker" {
  project        = var.project_id
  location       = var.region
  cloud_function = var.function_name
  role           = "roles/cloudfunctions.invoker"
  member         = "serviceAccount:${google_service_account.workflow_sa.email}"
}

resource "google_project_iam_member" "workflow_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.workflow_sa.email}"
}

resource "google_project_iam_member" "workflow_dataform_editor" {
  project = var.project_id
  role    = "roles/dataform.editor"
  member  = "serviceAccount:${google_service_account.workflow_sa.email}"
}

resource "google_workflows_workflow" "pipeline_workflow" {
  name                = var.workflow_name
  region              = var.region
  project             = var.project_id
  description         = "Orchestrates flight data scraping and ingestion into GCS"
  service_account     = google_service_account.workflow_sa.email
  call_log_level      = "LOG_ALL_CALLS"
  deletion_protection = false

  source_contents = templatefile("${path.module}/workflow.yaml", {
    function_uri             = var.function_uri
    project_id               = var.project_id
    region                   = var.region
    dataform_repo_name       = var.dataform_repo_name
    dataform_runner_sa_email = var.dataform_runner_sa_email
  })

  depends_on = [
    google_cloud_run_service_iam_member.workflow_run_invoker,
    google_cloudfunctions2_function_iam_member.workflow_gcf_invoker,
    google_project_iam_member.workflow_logging
  ]
}
