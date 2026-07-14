resource "google_service_account" "workflow_sa" {
  account_id   = var.workflow_sa_name
  display_name = "Service Account for Weather Pipeline Workflow"
  project      = var.project_id
}

resource "google_project_iam_member" "workflow_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.workflow_sa.email}"
}

resource "google_project_iam_member" "workflow_gcf_invoker" {
  project = var.project_id
  role    = "roles/cloudfunctions.invoker"
  member  = "serviceAccount:${google_service_account.workflow_sa.email}"
}

resource "google_project_iam_member" "workflow_pubsub_publisher" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.workflow_sa.email}"
}

resource "google_project_iam_member" "workflow_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.workflow_sa.email}"
}

resource "google_workflows_workflow" "weather_workflow" {
  name            = var.weather_workflow_name
  region          = var.region
  project         = var.project_id
  description     = "Orchestrates weather data ingestion from Cloud Function to Pub/Sub"
  service_account = google_service_account.workflow_sa.email
  call_log_level  = "LOG_ALL_CALLS"

  source_contents = templatefile("${path.module}/workflow.yaml", {
    function_uri      = var.function_uri
    project_id        = var.project_id
    pubsub_topic_name = var.pubsub_topic_name
  })

  depends_on = [
    google_project_iam_member.workflow_invoker,
    google_project_iam_member.workflow_gcf_invoker,
    google_project_iam_member.workflow_pubsub_publisher,
    google_project_iam_member.workflow_logging
  ]
}
