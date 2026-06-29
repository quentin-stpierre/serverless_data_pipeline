resource "google_service_account" "scheduler_sa" {
  account_id   = "weather-scheduler-sa"
  display_name = "Service Account for Weather Pipeline Cloud Scheduler"
  project      = var.project_id
}

resource "google_project_iam_member" "scheduler_workflow_invoker" {
  project = var.project_id
  role    = "roles/workflows.invoker"
  member  = "serviceAccount:${google_service_account.scheduler_sa.email}"
}

resource "google_cloud_scheduler_job" "workflow_trigger" {
  name             = "weather-workflow-trigger"
  description      = "Trigger weather workflow daily at 9am Europe/Brussels"
  schedule         = "0 9 * * *"
  time_zone        = "Europe/Brussels"
  project          = var.project_id
  region           = var.region
  attempt_deadline = "320s"

  retry_config {
    retry_count = 1
  }

  http_target {
    uri         = "https://workflowexecutions.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/workflows/${var.workflow_name}/executions"
    http_method = "POST"
    body        = base64encode("{}")

    oauth_token {
      service_account_email = google_service_account.scheduler_sa.email
    }
  }

  depends_on = [
    google_project_iam_member.scheduler_workflow_invoker
  ]
}
