resource "google_service_account" "scheduler_sa" {
  account_id   = var.scheduler_sa_name
  display_name = "Service Account for Flight Scraper Cloud Scheduler"
  project      = var.project_id
}

resource "google_project_iam_member" "scheduler_workflow_invoker" {
  project = var.project_id
  role    = "roles/workflows.invoker"
  member  = "serviceAccount:${google_service_account.scheduler_sa.email}"
}

resource "google_cloud_scheduler_job" "flight_pipeline_triggers" {
  for_each = var.flight_searches

  name             = "flight-trigger-${replace(each.key, "_", "-")}"
  description      = "Trigger flight scraping workflow for ${each.key} (${each.value.origin} -> ${each.value.destination})"
  schedule         = each.value.schedule
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
    body = base64encode(jsonencode({
      argument = jsonencode({
        origin             = each.value.origin
        destination        = each.value.destination
        start_date         = each.value.start_date
        trip_length        = each.value.trip_length
        flexibility_window = each.value.flexibility_window
        trip_type          = each.value.trip_type
        currency           = each.value.currency
        seat               = each.value.seat
        adults             = each.value.adults
        max_stops          = each.value.max_stops
      })
    }))

    oauth_token {
      service_account_email = google_service_account.scheduler_sa.email
    }
  }

  depends_on = [
    google_project_iam_member.scheduler_workflow_invoker
  ]
}
