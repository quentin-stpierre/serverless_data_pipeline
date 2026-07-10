variable "project_id" {
  description = "The ID of the GCP project"
  type        = string
}

variable "alert_email_address" {
  description = "The email address to send alert notifications to"
  type        = string
}

variable "workflow_name" {
  description = "The name of the Cloud Workflow to monitor"
  type        = string
}
