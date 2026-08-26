resource "google_monitoring_notification_channel" "email_channel" {
  project      = var.project_id
  display_name = "Workflow Alert Notification"
  type         = "email"
  labels = {
    email_address = var.alert_email_address
  }
}

resource "google_monitoring_alert_policy" "workflow_failure_policy" {
  project      = var.project_id
  display_name = "Workflow Failure Alert Policy - ${var.workflow_name}"
  combiner     = "OR"
  enabled      = true

  conditions {
    display_name = "Workflow execution failed for ${var.workflow_name}"

    condition_threshold {
      filter          = "resource.type = \"workflows.googleapis.com/Workflow\" AND resource.labels.workflow_id = \"${var.workflow_name}\" AND metric.type = \"workflows.googleapis.com/finished_execution_count\" AND metric.labels.status != \"SUCCEEDED\""
      duration        = "0s" # Alert immediately on failure
      comparison      = "COMPARISON_GT"
      threshold_value = 0

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_COUNT"
      }
    }
  }

  notification_channels = [
    google_monitoring_notification_channel.email_channel.name
  ]
}
