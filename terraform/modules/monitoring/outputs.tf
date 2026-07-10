output "notification_channel_id" {
  description = "The ID of the monitoring notification channel"
  value       = google_monitoring_notification_channel.email_channel.id
}

output "alert_policy_id" {
  description = "The ID of the monitoring alert policy"
  value       = google_monitoring_alert_policy.workflow_failure_policy.id
}
