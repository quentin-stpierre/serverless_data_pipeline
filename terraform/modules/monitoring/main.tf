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

resource "google_monitoring_alert_policy" "flight_price_low_policy" {
  project      = var.project_id
  display_name = "Flight Low Price Alert - ${var.workflow_name}"
  combiner     = "OR"
  enabled      = true

  conditions {
    display_name = "Flight price reached a historical low or target threshold"

    condition_matched_log {
      filter = "resource.type = \"workflows.googleapis.com/Workflow\" AND resource.labels.workflow_id = \"${var.workflow_name}\" AND jsonPayload.event_type = \"FLIGHT_PRICE_LOW_ALERT\""

      label_extractors = {
        search_name        = "EXTRACT(jsonPayload.search_name)"
        alert_reason       = "EXTRACT(jsonPayload.alert_reason)"
        origin             = "EXTRACT(jsonPayload.origin)"
        destination        = "EXTRACT(jsonPayload.destination)"
        outbound_date      = "EXTRACT(jsonPayload.outbound_date)"
        return_date        = "EXTRACT(jsonPayload.return_date)"
        airlines           = "EXTRACT(jsonPayload.airlines)"
        departure_time     = "EXTRACT(jsonPayload.departure_time)"
        trip_type          = "EXTRACT(jsonPayload.trip_type)"
        current_price      = "EXTRACT(jsonPayload.current_price)"
        currency           = "EXTRACT(jsonPayload.currency)"
        previous_min_price = "EXTRACT(jsonPayload.previous_min_price)"
        target_price       = "EXTRACT(jsonPayload.target_price)"
      }
    }
  }

  alert_strategy {
    notification_rate_limit {
      period = "300s"
    }
    auto_close = "1800s"
  }

  documentation {
    mime_type = "text/markdown"
    content   = <<-EOT
      ## Flight Low Price Alert (`$${log.extracted_label.search_name}`)

      A flight price matching your low-price criteria was detected!

      * **Reason:** `$${log.extracted_label.alert_reason}`
      * **Route:** `$${log.extracted_label.origin}` -> `$${log.extracted_label.destination}` (`$${log.extracted_label.trip_type}`)
      * **Current Lowest Price:** **$${log.extracted_label.current_price} $${log.extracted_label.currency}**
      * **Previous Historical Low:** `$${log.extracted_label.previous_min_price} $${log.extracted_label.currency}`
      * **Target Price Threshold:** `$${log.extracted_label.target_price} $${log.extracted_label.currency}`
      * **Outbound Date:** `$${log.extracted_label.outbound_date}` (Departs `$${log.extracted_label.departure_time}`)
      * **Return Date:** `$${log.extracted_label.return_date}`
      * **Airlines:** `$${log.extracted_label.airlines}`
    EOT
  }

  notification_channels = [
    google_monitoring_notification_channel.email_channel.name
  ]
}
